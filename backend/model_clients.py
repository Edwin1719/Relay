"""OpenAI-compatible model client.

Every cloud provider Relay supports (DeepSeek, APInex, and any future
OpenAI-compatible endpoint) speaks ``POST /v1/chat/completions``, so they all
share this one client. The provider's identity, base URL and credential live
in ``providers.ProviderSpec`` — nothing here inspects the model name.

The client retries transient failures (429 and 5xx) with exponential backoff,
honouring ``Retry-After``. Free tiers are request-rate limited, so a 429 here
is normal traffic, not an error the user should see.
"""

import json
import time
import urllib.error
import urllib.request

import http_client

# Statuses worth retrying: rate limits and transient upstream failures.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
MAX_RETRY_AFTER = 30.0
BACKOFF_CAP = 15.0


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before attempt number *attempt* (1-based)."""
    if retry_after:
        try:
            return min(float(retry_after), MAX_RETRY_AFTER)
        except ValueError:
            pass
    return min(2.0 ** (attempt - 1), BACKOFF_CAP)


def _content_for(prompt: str, images: list[str] | None):
    """Build the ``content`` field, adding vision parts when images are given."""
    if not images:
        return prompt
    return [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        for b64 in images
    ]

class BillingError(RuntimeError):
    """Terminal free-tier account error (e.g. APInex daily check-in)."""


class OpenAICompatibleClient:
    """Talks to any ``/v1/chat/completions`` endpoint.

    ``complete()`` returns the full text; ``complete_stream()`` yields deltas.
    """

    def __init__(self, model: str, provider, temperature=0.2, top_p=0.9,
                 timeout=300, max_attempts=MAX_ATTEMPTS):
        self.model = model
        self.provider = provider
        self.host = provider.base_url
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.api_key = provider.api_key

    # ── Internals ──────────────────────────────────────────────

    def _missing_key_error(self) -> RuntimeError:
        return RuntimeError(
            f"{self.provider.env_key} is not set. "
            f"Add it to backend/.env or set it as an environment variable."
        )

    def _billing_message(self, body: str) -> str:
        """Turn a free-tier billing error (HTTP 402) into an actionable message."""
        label = self.provider.label
        url = ""
        try:
            message = (json.loads(body).get("error") or {}).get("message", "")
            if isinstance(message, str):
                start = message.find("http")
                if start != -1:
                    url = message[start:].split()[0].rstrip('.,;)"')
        except (json.JSONDecodeError, AttributeError):
            pass
        base = f"{label} requiere un check-in diario para usar los modelos gratuitos."
        if url:
            base += f" Visita {url}, haz check-in y vuelve a intentarlo."
        else:
            base += " Revisa tu plan o credito en el panel del proveedor."
        return base

    def _payload(self, prompt, max_new_tokens, system_prefix, images, stream):
        messages = []
        if system_prefix:
            # Kept byte-identical across turns so prefix caching applies.
            messages.append({"role": "system", "content": system_prefix})
        messages.append({"role": "user", "content": _content_for(prompt, images)})
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": stream,
        }

    def _request(self, payload):
        return urllib.request.Request(
            f"{self.host}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

    def _open(self, request):
        """Open the request, retrying transient failures.

        Returns the response object. Raises ``RuntimeError`` for terminal
        errors (auth, bad request) or when retries are exhausted.
        """
        label = self.provider.label
        for attempt in range(1, self.max_attempts + 1):
            try:
                return http_client.open_request(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 402:
                    raise BillingError(self._billing_message(body)) from exc
                if exc.code in RETRY_STATUSES and attempt < self.max_attempts:
                    delay = _retry_delay(attempt, exc.headers.get("Retry-After"))
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"{label} API error (HTTP {exc.code}): {body}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Could not reach {label} API at {self.host}. "
                    f"Check your network connection and {self.provider.env_key or 'endpoint'}."
                ) from exc
        raise RuntimeError(f"{label} API unavailable after {self.max_attempts} attempts")

    # ── Public API ─────────────────────────────────────────────

    def complete(self, prompt, max_new_tokens, images=None, system_prefix=None):
        if self.provider.env_key and not self.api_key:
            raise self._missing_key_error()
        payload = self._payload(prompt, max_new_tokens, system_prefix, images, stream=False)
        label = self.provider.label
        with self._open(self._request(payload)) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("error"):
            raise RuntimeError(f"{label} API error: {data['error']}")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected {label} response format: {data}") from exc

    def complete_stream(self, prompt, max_new_tokens, images=None, system_prefix=None):
        """Yield text deltas as they arrive via SSE.

        Connection setup and rate-limit retries happen in ``_open()``, before
        the first byte is consumed. A failure *after* streaming has started is
        terminal: replaying the request would duplicate text in the transcript.
        """
        if self.provider.env_key and not self.api_key:
            raise self._missing_key_error()
        payload = self._payload(prompt, max_new_tokens, system_prefix, images, stream=True)
        label = self.provider.label

        with self._open(self._request(payload)) as response:
            for line in http_client.iter_stream_lines(response):
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    return
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    raise RuntimeError(f"{label} API error: {data['error']}")
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
