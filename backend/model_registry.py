"""Model registry — client construction and model discovery.

Routing is delegated to ``providers``: this module only builds clients for a
``ProviderSpec`` and enumerates what the configured providers can serve.
"""
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request

import http_client
import providers
from agent_core import OllamaModelClient
from model_clients import OpenAICompatibleClient
from providers import FAST, DEEP, PROVIDERS, UnknownModelError

logger = logging.getLogger("kodama")

import agent_core as _core
_core.MAX_HISTORY = 40000

def _ollama_type(raw_type: str) -> dict:
    """Map Relay's flat schema types ('str', 'int=20', 'list[str]') to JSON schema."""
    t = raw_type.strip().lower()
    if t.startswith("list["):
        inner = t[5:-1].strip()
        items = {"type": "string"}
        if inner in ("int", "integer", "float", "number"):
            items = {"type": "number"}
        return {"type": "array", "items": items}
    if t in ("str", "string"):
        return {"type": "string"}
    if t in ("int", "integer"):
        return {"type": "integer"}
    if t in ("float", "number"):
        return {"type": "number"}
    if t in ("bool", "boolean"):
        return {"type": "boolean"}
    return {"type": "string"}


def build_ollama_tools(tools: dict) -> list:
    """Convert Relay's tool dict (name -> {schema, description, ...}) to Ollama's
    native tool-calling format (``{type: function, function: {...}}``).

    Schema entries are flat strings: 'str', 'int=20' (native tools; '=default'
    marks optional) or 'string?' (MCP tools; '?' marks optional).
    """
    result = []
    for name, tool in tools.items():
        if not isinstance(tool, dict):
            continue
        schema = tool.get("schema") or tool.get("parameters") or {}
        if not isinstance(schema, dict):
            continue
        properties = {}
        required = []
        for key, raw in schema.items():
            if key == "type":
                continue
            s = str(raw)
            optional = s.endswith("?")
            if optional:
                s = s[:-1]
            if "=" in s:
                s = s.split("=", 1)[0].strip()
                optional = True
            properties[key] = _ollama_type(s)
            if not optional:
                required.append(key)
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return result


def _format_tool_call(tool_call: dict) -> str:
    """Convert one Ollama tool_call to Relay's <tool> text protocol."""
    fn = (tool_call or {}).get("function", {}) or {}
    name = fn.get("name", "")
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return f'<tool>{json.dumps({"name": name, "args": args}, ensure_ascii=False)}</tool>'


class ChatModelClient(OllamaModelClient):
    """Uses /api/chat instead of /api/generate.

    Cloud proxy models (gpt-oss:20b-cloud, etc.) don't work with the
    raw /api/generate endpoint. /api/chat works for both local and cloud.

    Retries up to 2 times on HTTP 500 (cloud proxy models are flaky).
    """

    def _call(self, payload, retries=2):
        last_exc = None
        for attempt in range(retries + 1):
            if attempt > 0:
                time.sleep(1.5 * attempt)
            request = urllib.request.Request(
                self.host + "/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with http_client.open_request(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_exc = exc
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 500 and attempt < retries:
                    continue
                raise RuntimeError(f"Ollama request failed with HTTP {exc.code}: {body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    "Could not reach Ollama.\n"
                    "Make sure `ollama serve` is running and the model is available.\n"
                    f"Host: {self.host}\n"
                    f"Model: {self.model}"
                ) from exc
        # Should not reach here
        raise RuntimeError(f"Ollama request failed after {retries} retries")

    def complete(self, prompt, max_new_tokens, images=None, tools=None, **kwargs):
        message = {"role": "user", "content": prompt}
        if images:
            message["images"] = images
        payload = {
            "model": self.model,
            "messages": [message],
            "stream": False,
            "options": {
                "num_predict": max_new_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }
        if tools:
            payload["tools"] = tools
        data = self._call(payload)

        if data.get("error"):
            raise RuntimeError(f"Ollama error: {data['error']}")
        try:
            msg = data["message"]
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                wrapped = "\n".join(_format_tool_call(tc) for tc in tool_calls)
                return f"{content}\n{wrapped}".strip() if content else wrapped
            return content
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Ollama chat response format: {data}") from exc

    def complete_stream(self, prompt, max_new_tokens, images=None, system_prefix=None, tools=None, **kwargs):
        """Streaming version of complete() using Ollama /api/chat with stream=True.

        Yields content chunks as they arrive via NDJSON.
        The ask_stream() loop already detects complete_stream via hasattr
        and uses it for incremental SSE feedback.

        When *tools* is provided, Ollama returns native tool_calls (the final
        streamed chunk carries them); they are translated back to Relay's
        <tool> text protocol and yielded after the content.
        """
        message = {"role": "user", "content": prompt}
        if images:
            message["images"] = images
        payload = {
            "model": self.model,
            "messages": [message],
            "stream": True,
            "options": {
                "num_predict": max_new_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }
        if tools:
            payload["tools"] = tools
        request = urllib.request.Request(
            self.host + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        tool_calls = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for line in http_client.iter_stream_lines(response):
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise RuntimeError(f"Ollama error: {data['error']}")
                    msg = data.get("message", {}) or {}
                    content = msg.get("content", "")
                    if content:
                        yield content
                    calls = msg.get("tool_calls") or []
                    if calls:
                        tool_calls.extend(calls)
                    if data.get("done"):
                        break
            if tool_calls:
                yield "\n".join(_format_tool_call(tc) for tc in tool_calls)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama streaming failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Could not reach Ollama.\n"
                "Make sure `ollama serve` is running and the model is available.\n"
                f"Host: {self.host}\n"
                f"Model: {self.model}"
            ) from exc


# ── Provider resolution ────────────────────────────────────────


def resolve_client(model: str, temperature=0.2, top_p=0.9, timeout=300):
    """Return the client for *model*, chosen by its ``ProviderSpec``.

    Raises ``providers.UnknownModelError`` when the model is not routable —
    locally-run Ollama models, for instance, are not in the catalog.
    """
    spec = providers.get_model_spec(model)
    if spec.provider == "ollama":
        return ChatModelClient(
            model=spec.name,
            host=PROVIDERS["ollama"].base_url,
            temperature=temperature,
            top_p=top_p,
            timeout=timeout,
        )
    return OpenAICompatibleClient(
        model=spec.name,
        provider=spec.spec,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )


def detect_model_tier(model_name: str) -> str:
    """Return ``fast`` (short/medium tasks) or ``deep`` (multi-step agentic).

    The tier is declared in the catalog, never inferred from the model name.
    """
    return providers.get_model_spec(model_name).tier

# ── Ollama discovery ───────────────────────────────────────────


def _ollama_endpoint(path: str) -> str:
    return f"{PROVIDERS['ollama'].base_url}{path}"


def list_ollama_models():
    """List Ollama's cloud models.

    Locally-run models are filtered out: Relay only exposes Ollama cloud
    proxies. Returns dicts ``{"name", "size", "modified"}``.

    Strategy:
      1. Ollama REST API (``/api/tags``) — works regardless of whether
         ``ollama`` is on PATH (e.g. when launched from run.bat).
      2. Fall back to ``ollama list`` if the REST call fails.
    """
    try:
        req = urllib.request.Request(
            _ollama_endpoint("/api/tags"),
            headers={"Content-Type": "application/json"},
        )
        with http_client.open_request(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if not providers.is_ollama_cloud(name):
                continue
            modified = m.get("modified_at", "-")[:10] if m.get("modified_at") else "-"
            models.append({"name": name, "size": "-", "modified": modified})
        return models
    except Exception as exc:
        logger.warning("Ollama REST API unavailable (%s). Falling back to subprocess.", exc)

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        models = []
        for line in result.stdout.strip().splitlines()[1:]:
            name = line.split()[0] if line.split() else ""
            if name and providers.is_ollama_cloud(name):
                models.append({"name": name, "size": "-", "modified": "-"})
        return models
    except subprocess.TimeoutExpired as exc:
        logger.warning("Ollama subprocess timed out: %s", exc)
        return []
    except FileNotFoundError:
        logger.warning("Ollama CLI not found on PATH. Is Ollama installed?")
        return []


# ── Model listing ──────────────────────────────────────────────


def list_available_models():
    """Every model the user can select right now.

    Shape: ``{"name", "label", "provider", "provider_label", "tier",
    "context_limit", "size", "modified"}``.

    Ollama cloud models need no credentials and are always listed; DeepSeek
    and APInex appear only when their API key is set.
    """
    models = []

    for m in list_ollama_models():
        spec = providers.get_model_spec(m["name"])
        models.append({
            "name": spec.name,
            "label": spec.name,
            "provider": spec.provider,
            "provider_label": spec.spec.label,
            "tier": spec.tier,
            "context_limit": spec.context_limit,
            "size": m["size"],
            "modified": m["modified"],
        })

    for spec in providers.catalog():
        provider = spec.spec
        if not provider.configured:
            continue
        models.append({
            "name": spec.name,
            "label": spec.label or spec.name,
            "provider": spec.provider,
            "provider_label": provider.label,
            "tier": spec.tier,
            "context_limit": spec.context_limit,
            "size": "-",
            "modified": "-",
        })

    return models


def default_model() -> str:
    """Model to use when none is specified: the best one available."""
    preferred = providers.default_model()
    if preferred:
        return preferred
    available = list_available_models()
    return available[0]["name"] if available else ""


def switch_model(agent, model_name, temperature=0.2, top_p=0.9, timeout=300):
    """Hot-swap the model client on an existing agent.

    Raises ``providers.UnknownModelError`` if the model is not routable.
    """
    agent.model_client = resolve_client(
        model=model_name,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )
    return agent
