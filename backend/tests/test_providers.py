"""Tests for providers.py — the model catalog and routing policy."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import providers
from providers import (
    DEEP, FAST, PROVIDERS, UnknownModelError,
    context_limit_of, default_model, get_model_spec, is_configured,
    is_ollama_cloud, provider_of, tier_of, _parse_model_list,
    _live_free_apinex, _parse_context,
)


@pytest.fixture
def clean_keys(monkeypatch):
    """No provider credentials, so tests control availability explicitly."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("APINEX_API_KEY", raising=False)


# ── Tier assignments ────────────────────────────────────────────

class TestTiers:
    """Ollama cloud serves fast tasks; DeepSeek and APInex serve deep work."""

    def test_ollama_cloud_is_fast(self):
        spec = get_model_spec("gpt-oss:120b-cloud")
        assert spec.provider == "ollama"
        assert spec.tier == FAST

    def test_deepseek_is_deep(self):
        assert tier_of("deepseek-v4-pro") == DEEP

    def test_apinex_is_deep(self):
        assert tier_of("free/kimi-k3") == DEEP

    def test_declared_tier_matches_provider_policy(self):
        for model in providers.catalog():
            expected = FAST if model.provider == "ollama" else DEEP
            assert model.tier == expected


# ── Local models are excluded ───────────────────────────────────

class TestLocalModelsRejected:
    """Locally-run Ollama models are no longer routable."""

    @pytest.mark.parametrize("name", [
        "qwen3.5:4b", "gemma3:4b", "llama3.2:3b", "qwen2.5-coder:7b",
    ])
    def test_local_names_rejected(self, name):
        with pytest.raises(UnknownModelError):
            get_model_spec(name)

    def test_empty_name_rejected(self):
        with pytest.raises(UnknownModelError):
            get_model_spec("")

    def test_error_message_explains_the_policy(self):
        with pytest.raises(UnknownModelError) as exc:
            get_model_spec("qwen3.5:4b")
        assert "Locally-run Ollama models are not supported" in str(exc.value)

    def test_unknown_model_rejected(self):
        with pytest.raises(UnknownModelError):
            provider_of("not-a-model")


# ── Context limits ──────────────────────────────────────────────

class TestContextLimits:
    def test_apinex_has_large_window(self):
        assert context_limit_of("free/kimi-k3") >= 1_000_000

    def test_deepseek_window(self):
        assert context_limit_of("deepseek-v4-pro") == providers.DEEPSEEK_CONTEXT

    def test_unknown_model_uses_default(self):
        assert context_limit_of("nope", default=1234) == 1234


# ── Provider availability ───────────────────────────────────────

class TestAvailability:
    def test_ollama_needs_no_key(self, clean_keys):
        assert is_configured("gpt-oss:120b-cloud") is True

    def test_deepseek_needs_key(self, clean_keys):
        assert is_configured("deepseek-v4-pro") is False

    def test_deepseek_available_with_key(self, clean_keys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
        assert is_configured("deepseek-v4-pro") is True

    def test_apinex_needs_its_own_key(self, clean_keys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
        assert is_configured("free/kimi-k3") is False


# ── Default model selection ─────────────────────────────────────

class TestDefaultModel:
    def test_prefers_deepseek(self, clean_keys, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
        monkeypatch.setenv("APINEX_API_KEY", "apx-x")
        assert default_model().startswith("deepseek-")

    def test_falls_back_to_apinex(self, clean_keys, monkeypatch):
        monkeypatch.setenv("APINEX_API_KEY", "apx-x")
        assert default_model().startswith("free/")

    def test_empty_when_nothing_configured(self, clean_keys):
        assert default_model() == ""


# ── APInex catalog parsing ──────────────────────────────────────

class TestApinexCatalog:
    def test_plain_names_get_default_limit(self):
        specs = _parse_model_list("free/a,free/b", 5000)
        assert [s.name for s in specs] == ["free/a", "free/b"]
        assert all(s.context_limit == 5000 for s in specs)
        assert all(s.provider == "apinex" and s.tier == DEEP for s in specs)

    def test_explicit_limits_override(self):
        specs = _parse_model_list("free/a@65536, free/b@1048576", 5000)
        assert [s.context_limit for s in specs] == [65536, 1048576]

    def test_blank_entries_ignored(self):
        assert len(_parse_model_list("free/a,,  ,free/b", 1)) == 2


# ── Live catalog verification ───────────────────────────────────

def _entry(model_id, *, free=True, tools=True, health="live", weight=3,
           context="1M", price=0.0):
    return {
        "id": model_id,
        "name": model_id.split("/")[-1],
        "allowFree": free,
        "supportsTools": tools,
        "health": health,
        "weight": weight,
        "contextWindow": context,
        "dollarsPer1M": price,
    }


class TestContextParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("1M", 1_048_576),
        ("131K", 134_144),
        ("64K", 65_536),
        (200_000, 200_000),
        ("", None),
        ("garbage", None),
    ])
    def test_parse_context(self, raw, expected):
        assert _parse_context(raw) == expected


class TestLiveFreeFilter:
    """Only models that are free, tool-capable and billed at zero survive."""

    def test_keeps_free_tool_models(self):
        live = _live_free_apinex([_entry("free/a")])
        assert set(live) == {"free/a"}

    def test_drops_paid_models_with_free_prefix(self):
        """The prefix lies: some ``free/`` ids are subscription-only."""
        live = _live_free_apinex([_entry("free/paid", free=False)])
        assert live == {}

    def test_drops_models_without_tools(self):
        """An agent cannot drive a model that cannot call tools."""
        live = _live_free_apinex([_entry("free/no-tools", tools=False)])
        assert live == {}

    def test_drops_non_free_pricing(self):
        live = _live_free_apinex([_entry("free/priced", price=0.5)])
        assert live == {}

    def test_drops_dead_models(self):
        live = _live_free_apinex([_entry("free/dead", health="down")])
        assert live == {}


class TestRefreshApinexModels:
    def _run(self, monkeypatch, entries, preferred):
        monkeypatch.setattr(providers, "_fetch_apinex_catalog", lambda timeout=10.0: entries)
        monkeypatch.setattr(providers, "DEFAULT_APINEX_IDS", preferred)
        monkeypatch.delenv("KODAMA_APINEX_MODELS", raising=False)
        ok = providers.refresh_apinex_models()
        return ok, [m.name for m in providers.apinex_models()]

    def test_keeps_curated_order(self, monkeypatch):
        entries = [_entry("free/b"), _entry("free/a")]
        ok, names = self._run(monkeypatch, entries, ("free/a", "free/b"))
        assert ok and names == ["free/a", "free/b"]

    def test_drops_curated_model_that_stopped_being_free(self, monkeypatch):
        entries = [_entry("free/still-free"), _entry("free/dead", free=False)]
        ok, names = self._run(monkeypatch, entries, ("free/dead", "free/still-free"))
        assert ok
        assert names == ["free/still-free"]

    def test_appends_extra_live_models_cheapest_first(self, monkeypatch):
        entries = [
            _entry("free/curated", weight=3),
            _entry("free/expensive", weight=4),
            _entry("free/cheap", weight=2),
        ]
        ok, names = self._run(monkeypatch, entries, ("free/curated",))
        assert ok
        assert names == ["free/curated", "free/cheap", "free/expensive"]

    def test_network_failure_keeps_current_list(self, monkeypatch):
        def boom(timeout=10.0):
            raise OSError("offline")
        monkeypatch.setattr(providers, "_fetch_apinex_catalog", boom)
        before = [m.name for m in providers.apinex_models()]
        assert providers.refresh_apinex_models() is False
        assert [m.name for m in providers.apinex_models()] == before

    def test_empty_result_keeps_current_list(self, monkeypatch):
        monkeypatch.setattr(providers, "_fetch_apinex_catalog", lambda timeout=10.0: [])
        assert providers.refresh_apinex_models() is False


# ── Provider specs ──────────────────────────────────────────────

class TestProviderSpecs:
    def test_openai_providers_require_keys(self):
        for name in ("deepseek", "apinex"):
            assert PROVIDERS[name].backend == "openai"
            assert PROVIDERS[name].env_key

    def test_ollama_uses_native_backend(self):
        assert PROVIDERS["ollama"].backend == "ollama"
        assert PROVIDERS["ollama"].env_key == ""

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://example.test:11434/")
        assert PROVIDERS["ollama"].base_url == "http://example.test:11434"


# ── Credential persistence ──────────────────────────────────────

class TestCredentials:
    def test_save_then_clear_round_trip(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=1\n", encoding="utf-8")
        monkeypatch.setattr(providers, "ENV_PATH", env_file)
        monkeypatch.delenv("APINEX_API_KEY", raising=False)

        providers.save_api_key("apinex", "apx-secret")
        assert "APINEX_API_KEY='apx-secret'" in env_file.read_text(encoding="utf-8")
        assert providers.PROVIDERS["apinex"].configured is True

        providers.clear_api_key("apinex")
        assert "APINEX_API_KEY" not in env_file.read_text(encoding="utf-8")
        assert providers.PROVIDERS["apinex"].configured is False

    def test_clear_preserves_other_keys(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("DEEPSEEK_API_KEY=sk-keep\nAPINEX_API_KEY=apx\n", encoding="utf-8")
        monkeypatch.setattr(providers, "ENV_PATH", env_file)
        monkeypatch.setenv("APINEX_API_KEY", "apx")

        providers.clear_api_key("apinex")
        text = env_file.read_text(encoding="utf-8")
        assert "DEEPSEEK_API_KEY=sk-keep" in text
        assert "apx" not in text

    def test_keyless_provider_rejects_credentials(self):
        with pytest.raises(ValueError, match="does not use an API key"):
            providers.save_api_key("ollama", "x")
