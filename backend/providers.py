"""Provider and model registry — the single source of truth for routing.

Policy (2026-10-27):
  * Locally-run Ollama models are NOT exposed. Their default 4K context is
    mostly consumed by Relay's system prompt, which makes multi-step tool
    use unreliable. Only Ollama's cloud proxies (``*-cloud``) stay.
  * Ollama cloud proxies serve the ``fast`` tier: short and medium tasks.
  * DeepSeek and APInex serve the ``deep`` tier: multi-step agentic work.

Provider identity is never inferred from a model-name prefix at call time.
Callers ask this module: ``get_model_spec()``, ``provider_of()``, ``tier_of()``.

APInex's free catalog rotates, so it is verified against the provider's public
model list when a key is present. Models that stopped being free are dropped
instead of failing at request time.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import http_client

logger = logging.getLogger("kodama")

# Credentials are persisted here (gitignored).
ENV_PATH = Path(__file__).resolve().parent / ".env"

# ── Tiers ─────────────────────────────────────────────────────────

FAST = "fast"
DEEP = "deep"

TIER_LABELS = {
    FAST: "Rápidos",
    DEEP: "Avanzados",
}


class UnknownModelError(LookupError):
    """Raised when a model is not in the catalog (e.g. a removed local model)."""

    def __init__(self, name):
        self.name = name
        super().__init__(
            f"Model '{name}' is not available. Locally-run Ollama models are not "
            f"supported; use an Ollama cloud model (ending in '-cloud'), DeepSeek, "
            f"or APInex."
        )


# ── Providers ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderSpec:
    """A backend Relay can talk to.

    ``backend`` selects the transport: ``ollama`` (native ``/api/chat``) or
    ``openai`` (``/v1/chat/completions``). ``env_key`` is empty for providers
    that need no credentials (Ollama runs on localhost).
    """

    name: str
    label: str
    backend: str
    default_base_url: str
    base_url_env: str = ""
    env_key: str = ""
    docs_url: str = ""

    @property
    def base_url(self) -> str:
        override = os.environ.get(self.base_url_env, "").strip() if self.base_url_env else ""
        return (override or self.default_base_url).rstrip("/")

    @property
    def api_key(self) -> str:
        return os.environ.get(self.env_key, "").strip() if self.env_key else ""

    @property
    def requires_key(self) -> bool:
        return bool(self.env_key)

    @property
    def configured(self) -> bool:
        """True when the provider can serve requests right now."""
        return bool(self.api_key) if self.env_key else True


PROVIDERS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        name="ollama",
        label="Ollama Cloud",
        backend="ollama",
        default_base_url="http://127.0.0.1:11434",
        base_url_env="OLLAMA_HOST",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        label="DeepSeek",
        backend="openai",
        default_base_url="https://api.deepseek.com",
        env_key="DEEPSEEK_API_KEY",
        docs_url="https://platform.deepseek.com/api_keys",
    ),
    "apinex": ProviderSpec(
        name="apinex",
        label="APInex",
        backend="openai",
        default_base_url="https://api.apinex.bond",
        env_key="APINEX_API_KEY",
        docs_url="https://apinex.bond/models",
    ),
}

# Ollama cloud proxies are the only Ollama models Relay runs. The suffix is
# Ollama's own convention for cloud-hosted models, not a routing heuristic.
OLLAMA_CLOUD_SUFFIX = "-cloud"
OLLAMA_CONTEXT_LIMIT = 131_072


# ── Model catalog ─────────────────────────────────────────────────

@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    tier: str
    context_limit: int
    label: str = ""

    @property
    def spec(self) -> ProviderSpec:
        return PROVIDERS[self.provider]


DEEPSEEK_CONTEXT = 131_072

DEEPSEEK_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("deepseek-v4-pro", "deepseek", DEEP, DEEPSEEK_CONTEXT, "DeepSeek V4 Pro"),
    ModelSpec("deepseek-v4-flash", "deepseek", DEEP, DEEPSEEK_CONTEXT, "DeepSeek V4 Flash"),
)


def _parse_context(raw) -> int | None:
    """Parse APInex's context string ("1M", "131K") into tokens."""
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().upper()
    multiplier = 1
    if text.endswith("M"):
        multiplier, text = 1_048_576, text[:-1]
    elif text.endswith("K"):
        multiplier, text = 1_024, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


# Curated preference order. Verified against the live free catalog on
# 2026-10-27: every entry is allowFree, tool-capable and billed at $0.
# Free-tier models consume the daily allowance multiplied by a weight (2-4),
# so lower weight means more usable turns per day.
DEFAULT_APINEX_IDS: tuple[str, ...] = (
    "free/deepseek-v4-pro-0813",      # tools, weight 3 — strongest for code
    "free/gemini-3.8-flash",          # tools + vision, weight 3
    "free/gpt-6-luna",                # tools + vision, weight 3
    "free/kimi-k3",                   # tools + vision, weight 3
    "free/mimo-v2.6-pro",             # tools + vision, weight 2 — cheapest
    "free/minimax-m3.1-flash",        # tools + vision, weight 2 — cheapest
)

APINEX_DEFAULT_CONTEXT = 1_048_576
# Ceiling on how many APInex models the UI lists, so the picker stays usable.
APINEX_MAX_MODELS = 8
# APInex's public catalog endpoint (no auth required).
APINEX_CATALOG_URL = "https://apinex.bond/api/public/models"


def _parse_model_list(raw: str, default_limit: int) -> tuple[ModelSpec, ...]:
    """Parse ``name`` or ``name@context_limit`` entries separated by commas."""
    out = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, _, limit = entry.partition("@")
        out.append(ModelSpec(
            name=name.strip(),
            provider="apinex",
            tier=DEEP,
            context_limit=int(limit) if limit.strip().isdigit() else default_limit,
        ))
    return tuple(out)


def _env_apinex_ids() -> tuple[str, ...] | None:
    """``KODAMA_APINEX_MODELS`` overrides the curated list when set."""
    raw = os.environ.get("KODAMA_APINEX_MODELS", "").strip()
    return tuple(p.name for p in _parse_model_list(raw, APINEX_DEFAULT_CONTEXT)) if raw else None


_apinex_models: tuple[ModelSpec, ...] = _parse_model_list(
    ",".join(_env_apinex_ids() or DEFAULT_APINEX_IDS),
    APINEX_DEFAULT_CONTEXT,
)


def apinex_models() -> tuple[ModelSpec, ...]:
    """Currently selectable APInex models (curated order, tier ``deep``)."""
    return _apinex_models


def catalog() -> tuple[ModelSpec, ...]:
    """Every statically-known model, across providers."""
    return DEEPSEEK_MODELS + _apinex_models


def _index() -> dict[str, ModelSpec]:
    return {m.name.lower(): m for m in catalog()}


# ── Live catalog verification ─────────────────────────────────────

def _fetch_apinex_catalog(timeout: float = 10.0) -> list[dict]:
    req = urllib.request.Request(
        APINEX_CATALOG_URL,
        headers={"Accept": "application/json"},
    )
    with http_client.open_request(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise ValueError("unexpected APInex catalog shape")
    return models


def _live_free_apinex(entries: list[dict]) -> dict[str, dict]:
    """Free + tool-capable + billed-at-zero models, keyed by id."""
    live = {}
    for entry in entries:
        model_id = entry.get("id") or ""
        if not entry.get("allowFree") or not model_id.startswith("free/"):
            continue
        if not entry.get("supportsTools"):
            continue  # an agent cannot use a model without tool calling
        if entry.get("health") not in ("live", "no_data"):
            continue
        if entry.get("dollarsPer1M"):
            continue
        live[model_id] = entry
    return live


def refresh_apinex_models(timeout: float = 10.0) -> bool:
    """Rebuild the APInex list from the provider's live catalog.

    Keeps the curated order, drops models that are no longer free, and appends
    other live free tool-capable models (cheapest weight first) up to
    ``APINEX_MAX_MODELS``.

    Returns True when the list was refreshed; False keeps the current one.
    """
    global _apinex_models

    try:
        live = _live_free_apinex(_fetch_apinex_catalog(timeout=timeout))
    except (urllib.error.URLError, ValueError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not verify the APInex free catalog (%s). Keeping the current list.", exc)
        return False

    if not live:
        logger.warning("APInex reported no free tool-capable models. Keeping the current list.")
        return False

    overridden = _env_apinex_ids()
    preferred = overridden or DEFAULT_APINEX_IDS

    ordered: list[str] = [mid for mid in preferred if mid in live]
    dropped = [mid for mid in preferred if mid not in live]
    if dropped:
        logger.warning("APInex models no longer free/available: %s", ", ".join(dropped))

    remaining = sorted(
        (mid for mid in live if mid not in ordered),
        key=lambda mid: (live[mid].get("weight") or 99, mid),
    )
    for model_id in remaining:
        if len(ordered) >= APINEX_MAX_MODELS:
            break
        ordered.append(model_id)

    _apinex_models = tuple(
        ModelSpec(
            name=model_id,
            provider="apinex",
            tier=DEEP,
            context_limit=_parse_context(live[model_id].get("contextWindow")) or APINEX_DEFAULT_CONTEXT,
            label=live[model_id].get("name") or "",
        )
        for model_id in ordered
    )
    logger.info("APInex catalog verified: %d free tool-capable models", len(_apinex_models))
    return True


# ── Credentials ───────────────────────────────────────────────────

def save_api_key(provider_name: str, key: str) -> None:
    """Persist a provider credential to backend/.env and the live environment."""
    spec = PROVIDERS[provider_name]
    if not spec.env_key:
        raise ValueError(f"{spec.label} does not use an API key")

    from dotenv import set_key

    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), spec.env_key, key)
    os.environ[spec.env_key] = key
    logger.info("Saved %s credential to .env", spec.label)


def clear_api_key(provider_name: str) -> None:
    """Remove a provider credential from backend/.env and the environment."""
    spec = PROVIDERS[provider_name]
    if not spec.env_key:
        raise ValueError(f"{spec.label} does not use an API key")

    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        kept = [
            line for line in lines
            if not line.startswith(f"{spec.env_key}=") and not line.startswith(f"export {spec.env_key}=")
        ]
        ENV_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.environ.pop(spec.env_key, None)
    logger.info("Removed %s credential", spec.label)


# ── Lookups ───────────────────────────────────────────────────────

def _ollama_spec(name: str) -> ModelSpec:
    return ModelSpec(
        name=name,
        provider="ollama",
        tier=FAST,
        context_limit=OLLAMA_CONTEXT_LIMIT,
    )


def is_ollama_cloud(name: str) -> bool:
    return name.lower().endswith(OLLAMA_CLOUD_SUFFIX)


def get_model_spec(name: str) -> ModelSpec:
    """Return the catalog entry for *name*.

    Raises ``UnknownModelError`` for anything not routable — including
    locally-run Ollama models, which Relay no longer exposes.
    """
    if not name or not name.strip():
        raise UnknownModelError(name)
    known = _index().get(name.strip().lower())
    if known is not None:
        return known
    if is_ollama_cloud(name):
        return _ollama_spec(name.strip())
    raise UnknownModelError(name)


def provider_of(name: str) -> str:
    return get_model_spec(name).provider


def tier_of(name: str) -> str:
    return get_model_spec(name).tier


def context_limit_of(name: str, default: int = 65_536) -> int:
    """Declared context window for *name*, or *default* for unknown models."""
    try:
        return get_model_spec(name).context_limit
    except UnknownModelError:
        return default


def is_configured(name: str) -> bool:
    """True when *name*'s provider has what it needs to serve requests."""
    try:
        return get_model_spec(name).spec.configured
    except UnknownModelError:
        return False


def default_model() -> str:
    """First model of the highest-priority configured provider.

    Order: DeepSeek → APInex. Ollama cloud models need discovery (a network
    call), so callers fall back to the first discovered model for those.
    """
    for provider_name in ("deepseek", "apinex"):
        if not PROVIDERS[provider_name].configured:
            continue
        for model in catalog():
            if model.provider == provider_name:
                return model.name
    return ""
