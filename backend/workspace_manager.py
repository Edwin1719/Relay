"""Workspace manager for Relay — allows changing the agent's working directory."""

import os
from pathlib import Path


# ── Persistent workspace root ────────────────────────────────────
# Stored in a simple file so it survives restarts
_CONFIG_DIR = Path(__file__).parent / ".kodama"
_CONFIG_FILE = _CONFIG_DIR / "workspace.txt"


def _ensure_config_dir():
    _CONFIG_DIR.mkdir(exist_ok=True)


def get_workspace_root() -> str:
    """Get the current workspace root directory."""
    # 1. Check env var
    env_val = os.environ.get("AGENT_CWD")
    if env_val:
        return env_val

    # 2. Check persistent config file
    _ensure_config_dir()
    if _CONFIG_FILE.exists():
        saved = _CONFIG_FILE.read_text(encoding="utf-8").strip()
        if saved and Path(saved).exists():
            return saved

    # 3. Default to the parent of the kodama folder
    return str(Path(__file__).resolve().parent.parent)


def set_workspace_root(path: str) -> str:
    """Set and persist a new workspace root. Returns the resolved path."""
    resolved = str(Path(path).resolve())
    if not Path(resolved).exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not Path(resolved).is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    _ensure_config_dir()
    _CONFIG_FILE.write_text(resolved, encoding="utf-8")
    os.environ["AGENT_CWD"] = resolved
    return resolved
