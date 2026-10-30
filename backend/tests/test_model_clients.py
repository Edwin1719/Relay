"""Tests for model_clients.OpenAICompatibleClient.

The client serves every OpenAI-compatible provider (DeepSeek, APInex, ...).
All network calls are mocked via http_client.open_request — no real API keys
or HTTP requests are made.
"""

import sys
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model_clients import OpenAICompatibleClient
from providers import PROVIDERS


def deepseek_client(model, host=None, **kwargs):
    """OpenAICompatibleClient wired to the DeepSeek provider.

    *host* overrides the base URL, for the URL-construction tests.
    """
    provider = PROVIDERS["deepseek"]
    if host is not None:
        provider = replace(provider, default_base_url=host)
    return OpenAICompatibleClient(model, provider, **kwargs)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_urlopen(monkeypatch):
    """Replace http_client.open_request and urllib.request.urlopen with a controllable mock.

    Returns the mock so tests can configure .return_value.
    """
    mock = MagicMock()
    monkeypatch.setattr("urllib.request.urlopen", mock)
    monkeypatch.setattr("http_client.open_request", mock)
    return mock


@pytest.fixture
def set_api_key(monkeypatch):
    """Set DEEPSEEK_API_KEY in the environment for the test duration."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-123")
    return "sk-test-key-123"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Never actually sleep while exercising the retry policy."""
    monkeypatch.setattr("model_clients.time.sleep", lambda _s: None)


# ── DeepSeekClient initialization ───────────────────────────────

class TestDeepSeekClientInit:
    """Constructor and default values."""

    def test_default_values(self):
        client = deepseek_client("deepseek-v4-flash")
        assert client.model == "deepseek-v4-flash"
        assert client.host == "https://api.deepseek.com"
        assert client.temperature == 0.2
        assert client.top_p == 0.9
        assert client.timeout == 300

    def test_default_timeout_is_high(self):
        """Default timeout is 300s to handle reasoning models (V4 Pro)."""
        client = deepseek_client("deepseek-v4-pro")
        assert client.timeout == 300

    def test_custom_host(self):
        client = deepseek_client("deepseek-v4-flash", host="https://custom.api.com")
        assert client.host == "https://custom.api.com"

    def test_custom_host_strips_trailing_slash(self):
        client = deepseek_client("deepseek-v4-flash", host="https://custom.api.com/")
        assert client.host == "https://custom.api.com"

    def test_custom_temperature_and_top_p(self):
        client = deepseek_client("deepseek-v4-flash", temperature=0.5, top_p=0.8)
        assert client.temperature == 0.5
        assert client.top_p == 0.8

    def test_custom_timeout(self):
        client = deepseek_client("deepseek-v4-flash", timeout=120)
        assert client.timeout == 120

    def test_api_key_from_env(self, set_api_key):
        client = deepseek_client("deepseek-v4-flash")
        assert client.api_key == "sk-test-key-123"

    def test_api_key_empty_when_not_set(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        client = deepseek_client("deepseek-v4-flash")
        assert client.api_key == ""


# ── DeepSeekClient.complete() ───────────────────────────────────

class TestDeepSeekClientComplete:
    """Tests for the synchronous complete() method."""

    def test_success(self, set_api_key, mock_urlopen):
        """complete() builds the correct payload and returns content."""
        # Mock HTTP response
        response_data = {
            "choices": [{"message": {"content": "Hello from DeepSeek"}}]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        result = client.complete("What is 2+2?", 100)

        assert result == "Hello from DeepSeek"

        # Verify the request payload
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))

        assert payload["model"] == "deepseek-v4-flash"
        assert payload["messages"][0]["content"] == "What is 2+2?"
        assert payload["max_tokens"] == 100
        assert payload["temperature"] == 0.2
        assert payload["top_p"] == 0.9
        assert payload["stream"] is False

        # Verify auth header
        headers = request.headers
        assert headers["Authorization"] == "Bearer sk-test-key-123"
        assert headers["Content-type"] == "application/json"

    def test_missing_api_key(self):
        """complete() raises RuntimeError when API key is not set."""
        client = deepseek_client("deepseek-v4-flash")
        client.api_key = ""
        with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is not set"):
            client.complete("test", 100)

    def test_http_error(self, set_api_key, mock_urlopen):
        """complete() raises RuntimeError on HTTP 4xx/5xx."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.deepseek.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=BytesIO(b'{"error":{"message":"Rate limit exceeded"}}'),
        )

        client = deepseek_client("deepseek-v4-flash")
        with pytest.raises(RuntimeError, match="DeepSeek API error.*429"):
            client.complete("test", 100)

    def test_url_error(self, set_api_key, mock_urlopen):
        """complete() raises RuntimeError on connection errors."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        client = deepseek_client("deepseek-v4-flash")
        with pytest.raises(RuntimeError, match="Could not reach DeepSeek API"):
            client.complete("test", 100)

    def test_api_error_in_response_body(self, set_api_key, mock_urlopen):
        """complete() raises RuntimeError when response has error field."""
        response_data = {"error": {"message": "Invalid API key"}}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        with pytest.raises(RuntimeError, match="DeepSeek API error"):
            client.complete("test", 100)

    def test_malformed_response_missing_choices(self, set_api_key, mock_urlopen):
        """complete() raises RuntimeError when response has no choices."""
        response_data = {"unexpected": "format"}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        with pytest.raises(RuntimeError, match="Unexpected DeepSeek response"):
            client.complete("test", 100)

    def test_malformed_response_empty_choices(self, set_api_key, mock_urlopen):
        """complete() raises RuntimeError when choices list is empty."""
        response_data = {"choices": []}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        with pytest.raises(RuntimeError, match="Unexpected DeepSeek response"):
            client.complete("test", 100)

    def test_custom_host_used_in_url(self, set_api_key, mock_urlopen):
        """URL is built from the host attribute."""
        response_data = {"choices": [{"message": {"content": "ok"}}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash", host="https://custom.deepseek.com")
        client.complete("test", 100)

        request = mock_urlopen.call_args[0][0]
        assert request.full_url == "https://custom.deepseek.com/v1/chat/completions"


# ── DeepSeekClient.complete_stream() ────────────────────────────

class TestDeepSeekClientCompleteStream:
    """Tests for the streaming complete_stream() method."""

    def test_success_yields_chunks(self, set_api_key, mock_urlopen):
        """complete_stream() yields text chunks from SSE data."""

        # Simulate SSE stream with multiple data events
        sse_data = (
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":" World"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = [sse_data, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["Hello", " World"]

    def test_success_with_partial_chunks(self, set_api_key, mock_urlopen):
        """Handles SSE data split across multiple read() calls."""
        mock_response = MagicMock()
        mock_response.read.side_effect = [
            b'data: {"choices":[{"delta":{"content":"Part"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"ial"}}]}\n\n',
            b'data: [DONE]\n\n',
            b"",
        ]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["Part", "ial"]

    def test_missing_api_key(self):
        """complete_stream() raises RuntimeError when API key is not set."""
        client = deepseek_client("deepseek-v4-flash")
        client.api_key = ""
        with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY is not set"):
            list(client.complete_stream("test", 100))

    def test_stream_flag_is_true(self, set_api_key, mock_urlopen):
        """Payload has stream=True for streaming requests."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"data: [DONE]\n\n"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        list(client.complete_stream("test", 100))

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["stream"] is True

    def test_ignores_non_data_lines(self, set_api_key, mock_urlopen):
        """Lines not starting with 'data: ' are skipped."""
        sse_data = (
            b'event: message\n'
            b'data: {"choices":[{"delta":{"content":"Valid"}}]}\n\n'
            b':comment\n'
            b'data: [DONE]\n\n'
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = [sse_data, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["Valid"]

    def test_ignores_invalid_json(self, set_api_key, mock_urlopen):
        """Malformed JSON in data line is silently skipped."""
        sse_data = (
            b'data: {invalid json}\n\n'
            b'data: {"choices":[{"delta":{"content":"Good"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = [sse_data, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["Good"]

    def test_empty_delta(self, set_api_key, mock_urlopen):
        """Delta with empty content is not yielded."""
        sse_data = (
            b'data: {"choices":[{"delta":{}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"Real"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = [sse_data, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["Real"]

    def test_no_choices_in_delta(self, set_api_key, mock_urlopen):
        """Line with data but no choices key is handled gracefully."""
        sse_data = (
            b'data: {"id":"123","object":"chat.completion.chunk"}\n\n'
            b'data: {"choices":[{"delta":{"content":"After"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = [sse_data, b""]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        chunks = list(client.complete_stream("test", 100))

        assert chunks == ["After"]



# ── ChatModelClient (Ollama) payload ───────────────────────────

class TestChatModelClientPayload:
    """ChatModelClient must send sampling options (num_predict/temperature/top_p)
    so Ollama (including cloud proxies like gpt-oss:120b-cloud) produces
    deterministic, length-bounded output — same contract as DeepSeekClient.
    """

    def test_complete_sends_options(self, mock_urlopen):
        from model_registry import ChatModelClient

        response_data = {"message": {"content": "hola"}}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = ChatModelClient(
            "gpt-oss:120b-cloud", host="http://127.0.0.1:11434",
            temperature=0.2, top_p=0.9, timeout=300,
        )
        result = client.complete("test", 512)
        assert result == "hola"

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "gpt-oss:120b-cloud"
        assert payload["stream"] is False
        assert payload["options"]["num_predict"] == 512
        assert payload["options"]["temperature"] == 0.2
        assert payload["options"]["top_p"] == 0.9

    def test_complete_stream_sends_options(self, mock_urlopen):
        from model_registry import ChatModelClient

        stream = (
            json.dumps({"message": {"content": "hola"}}).encode("utf-8") + b"\n",
            b"",
        )
        mock_response = MagicMock()
        mock_response.read.side_effect = stream
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = ChatModelClient(
            "gpt-oss:120b-cloud", host="http://127.0.0.1:11434",
            temperature=0.2, top_p=0.9, timeout=300,
        )
        chunks = list(client.complete_stream("test", 512))
        assert chunks == ["hola"]

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["stream"] is True
        assert payload["options"]["num_predict"] == 512
        assert payload["options"]["temperature"] == 0.2
        assert payload["options"]["top_p"] == 0.9



# ── Ollama native tool-calling bridge ─────────────────────────

class TestOllamaNativeTools:
    """build_ollama_tools + tool_calls → <tool> text translation."""

    def test_build_ollama_tools_converts_schemas(self):
        from model_registry import build_ollama_tools

        tools = {
            "read_file": {"schema": {"path": "str", "start": "int=1"}, "description": "Lee archivo", "risky": False},
            "mcp_x_y": {"schema": {"q": "string?", "n": "string"}, "description": "MCP tool"},
            "weird": {"schema": {"paths": "list[str]"}, "description": ""},
        }
        out = build_ollama_tools(tools)
        by_name = {t["function"]["name"]: t["function"] for t in out}
        assert set(by_name) == {"read_file", "mcp_x_y", "weird"}

        read = by_name["read_file"]
        assert read["parameters"]["properties"]["path"] == {"type": "string"}
        assert read["parameters"]["properties"]["start"] == {"type": "integer"}
        assert read["parameters"]["required"] == ["path"]  # '=1' default → optional

        mcp = by_name["mcp_x_y"]
        assert mcp["parameters"]["required"] == ["n"]  # '?' marks optional
        assert "q" not in mcp["parameters"]["required"]

        assert by_name["weird"]["parameters"]["properties"]["paths"] == {
            "type": "array", "items": {"type": "string"},
        }

    def test_complete_returns_tool_wrapper_when_native_call(self, mock_urlopen):
        from model_registry import ChatModelClient

        response_data = {"message": {"content": "", "tool_calls": [
            {"function": {"name": "mcp_playwright_browser_navigate",
                          "arguments": {"url": "https://databiq.com/contact"}}}
        ]}}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = ChatModelClient("gpt-oss:120b-cloud", host="http://127.0.0.1:11434",
                                 temperature=0.2, top_p=0.9, timeout=300)
        tools = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
        result = client.complete("test", 512, tools=tools)

        assert result == ('<tool>{"name": "mcp_playwright_browser_navigate", '
                          '"args": {"url": "https://databiq.com/contact"}}</tool>')
        # tools must be forwarded in the payload
        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["tools"] == tools

    def test_complete_stream_yields_tool_wrapper_from_final_chunk(self, mock_urlopen):
        from model_registry import ChatModelClient

        chunks = [
            json.dumps({"message": {"content": "Voy a navegar"}}).encode("utf-8") + b"\n",
            json.dumps({"message": {"tool_calls": [
                {"function": {"name": "mcp_x", "arguments": {"a": 1}}}
            ]}, "done": True}).encode("utf-8") + b"\n",
        ]
        mock_response = MagicMock()
        mock_response.read.side_effect = chunks
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = ChatModelClient("gpt-oss:120b-cloud", host="http://127.0.0.1:11434",
                                 temperature=0.2, top_p=0.9, timeout=300)
        out = list(client.complete_stream("test", 512, tools=[{"type": "function"}]))

        assert out == ["Voy a navegar", '<tool>{"name": "mcp_x", "args": {"a": 1}}</tool>']


# ── Retry policy ────────────────────────────────────────────────

class TestRetryPolicy:
    """Transient failures are retried; terminal ones surface immediately."""

    @staticmethod
    def _http_error(code, retry_after=None):
        import urllib.error
        headers = {"Retry-After": retry_after} if retry_after else {}
        return urllib.error.HTTPError(
            url="https://api.test.com/",
            code=code,
            msg="err",
            hdrs=headers,
            fp=BytesIO(b'{"error":"boom"}'),
        )

    def test_retries_429_then_succeeds(self, set_api_key, mock_urlopen):
        """A 429 is retried while attempts remain, then the call succeeds."""
        response_data = {"choices": [{"message": {"content": "ok"}}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.side_effect = [self._http_error(429), mock_response]

        client = deepseek_client("deepseek-v4-flash", max_attempts=3)
        assert client.complete("test", 100) == "ok"
        assert mock_urlopen.call_count == 2

    def test_429_exhausts_attempts(self, set_api_key, mock_urlopen):
        """When every attempt is rate limited, the last error is raised."""
        mock_urlopen.side_effect = self._http_error(429)

        client = deepseek_client("deepseek-v4-flash", max_attempts=2)
        with pytest.raises(RuntimeError, match=r"DeepSeek API error \(HTTP 429\)"):
            client.complete("test", 100)
        assert mock_urlopen.call_count == 2

    def test_auth_error_is_not_retried(self, set_api_key, mock_urlopen):
        """401 is terminal: retrying would just burn quota."""
        mock_urlopen.side_effect = self._http_error(401)

        client = deepseek_client("deepseek-v4-flash", max_attempts=3)
        with pytest.raises(RuntimeError, match=r"HTTP 401"):
            client.complete("test", 100)
        assert mock_urlopen.call_count == 1

    def test_retry_after_header_is_honoured(self, set_api_key, mock_urlopen, monkeypatch):
        """The Retry-After header drives the wait instead of the backoff curve."""
        waits = []
        monkeypatch.setattr("model_clients.time.sleep", waits.append)
        mock_urlopen.side_effect = self._http_error(429, retry_after="7")

        client = deepseek_client("deepseek-v4-flash", max_attempts=2)
        with pytest.raises(RuntimeError):
            client.complete("test", 100)
        assert waits == [7.0]

    def test_retry_after_is_capped(self, set_api_key, mock_urlopen, monkeypatch):
        """An absurd Retry-After cannot stall the agent for minutes."""
        waits = []
        monkeypatch.setattr("model_clients.time.sleep", waits.append)
        mock_urlopen.side_effect = self._http_error(429, retry_after="9999")

        client = deepseek_client("deepseek-v4-flash", max_attempts=2)
        with pytest.raises(RuntimeError):
            client.complete("test", 100)
        assert waits == [30.0]


# ── Provider-specific payloads ──────────────────────────────────

class TestProviderPayload:
    """The same client serves several providers; the spec drives the request."""

    def test_apinex_uses_its_own_base_url_and_key(self, monkeypatch, mock_urlopen):
        monkeypatch.setenv("APINEX_API_KEY", "apx-key")
        response_data = {"choices": [{"message": {"content": "ok"}}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = OpenAICompatibleClient("free/claude-sonnet-4.6", PROVIDERS["apinex"])
        assert client.complete("hola", 50) == "ok"

        request = mock_urlopen.call_args[0][0]
        assert request.full_url == "https://api.apinex.bond/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer apx-key"

    def test_error_message_names_the_provider(self, monkeypatch, mock_urlopen):
        """Users must see which provider failed, not a generic 'API error'."""
        monkeypatch.setenv("APINEX_API_KEY", "apx-key")
        mock_urlopen.side_effect = TestRetryPolicy._http_error(400)

        client = OpenAICompatibleClient("free/x", PROVIDERS["apinex"])
        with pytest.raises(RuntimeError, match="APInex API error"):
            client.complete("hola", 50)

    def test_missing_apinex_key_names_the_env_var(self, monkeypatch):
        monkeypatch.delenv("APINEX_API_KEY", raising=False)
        client = OpenAICompatibleClient("free/x", PROVIDERS["apinex"])
        with pytest.raises(RuntimeError, match="APINEX_API_KEY is not set"):
            client.complete("hola", 50)

    def test_images_become_vision_parts(self, set_api_key, mock_urlopen):
        """Attached images are sent as image_url parts, not silently dropped."""
        response_data = {"choices": [{"message": {"content": "ok"}}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        client.complete("describe", 50, images=["QUJD"])

        request = mock_urlopen.call_args[0][0]
        content = json.loads(request.data.decode("utf-8"))["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "describe"}
        assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"

    def test_system_prefix_is_first_message(self, set_api_key, mock_urlopen):
        """The system prefix stays byte-identical for prompt caching."""
        response_data = {"choices": [{"message": {"content": "ok"}}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = deepseek_client("deepseek-v4-flash")
        client.complete("hola", 50, system_prefix="[RULES]")

        request = mock_urlopen.call_args[0][0]
        messages = json.loads(request.data.decode("utf-8"))["messages"]
        assert messages[0] == {"role": "system", "content": "[RULES]"}
        assert messages[1]["role"] == "user"
