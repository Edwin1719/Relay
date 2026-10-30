"""Integrations / Marketplace manager for Relay.

Manages the catalog of known MCP integrations, user configuration
(enable/disable, API keys → .env, non-sensitive args → SQLite),
and lifecycle of individual MCP servers.

Design:
  - Non-sensitive config (enabled, args) → SQLite ``integrations`` table
  - Sensitive config (API keys, tokens) → ``backend/.env`` (gitignored)
  - MCP server lifecycle → delegates to ``_MCPServerConn`` from mcp_manager
"""

import json
import os
import sys
import shutil
import asyncio
import logging
import threading
from pathlib import Path
from dotenv import set_key, load_dotenv

logger = logging.getLogger("kodama.integrations")

# ── Preflight check results (module-level, set during startup) ───
_preflight_results: dict[str, dict] = {}


def preflight_checks() -> dict[str, dict]:
    """Check availability of external dependencies for all integrations.

    Returns a dict mapping server_name -> {command, available, path}.
    Results are cached in the module-level _preflight_results.
    Also checks for Chrome/Chromium availability (needed by Playwright/Puppeteer).
    """
    global _preflight_results

    if _preflight_results:
        return _preflight_results

    results = {}

    for item in CATALOG:
        server_name = item["server_name"]
        command = item.get("command", "")

        # Check the main command (npx, uvx, python)
        cmd_path = shutil.which(command)
        available = cmd_path is not None

        result = {
            "command": command,
            "available": available,
            "path": cmd_path or "",
        }

        # Extra check: Playwright/Puppeteer need Chrome/Chromium
        if server_name in ("playwright", "puppeteer"):
            chrome_path = shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")
            # On Windows, check common paths
            if not chrome_path and os.name == "nt":
                chrome_candidates = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                ]
                for candidate in chrome_candidates:
                    if os.path.exists(candidate):
                        chrome_path = candidate
                        break
            result["chrome_available"] = chrome_path is not None
            result["chrome_path"] = chrome_path or ""

        results[server_name] = result

    _preflight_results = results
    logger.info("Preflight checks complete: %s",
                ", ".join(f"{k}={v['available']}" for k, v in results.items()))
    return results


def get_preflight_results() -> dict[str, dict]:
    """Return cached preflight check results (empty if not yet run)."""
    return dict(_preflight_results)

# ── Paths ─────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"


# ── Integration Catalog ───────────────────────────────────────
# Known integrations. Each entry describes an MCP server and its
# configurable fields.  To add a new integration to the marketplace,
# append an entry here (no code changes needed unless the server
# requires special startup logic).

CATALOG = [
    {
        "server_name": "Context7",
        "display_name": "Context7 Docs",
        "description": "Documentación actualizada de librerías y frameworks. "
                       "Resuelve IDs de librerías y consulta docs oficiales.",
        "tools_description": "resolve-library-id, query-docs",
        "command": "npx",
        "default_args": ["-y", "@upstash/context7-mcp@latest"],
        "config_fields": [],
    },
    {
        "server_name": "playwright",
        "display_name": "Playwright Browser",
        "description": "Automatización de navegador headless. "
                       "Permite navegar, hacer clic, llenar formularios "
                       "y capturar screenshots.",
        "tools_description": "navigate, click, snapshot, fill, extract, +20 más",
        "command": "npx",
        "default_args": ["@playwright/mcp@latest"],
        "config_fields": [],
    },
    {
        "server_name": "github",
        "display_name": "GitHub",
        "description": "Gestión de repositorios, pull requests, issues, "
                       "revisiones de código y más desde el chat.",
        "tools_description": "create_pr, list_issues, review_code, merge_pr, list_repos",
        "command": "npx",
        "default_args": ["-y", "@modelcontextprotocol/server-github"],
        "config_fields": [
            {
                "name": "GITHUB_PERSONAL_ACCESS_TOKEN",
                "label": "GitHub Token",
                "type": "api_key",
                "env_var": "GITHUB_PERSONAL_ACCESS_TOKEN",
                "required": True,
                "placeholder": "ghp_...",
            }
        ],
    },
    {
        "server_name": "google-maps",
        "display_name": "Google Maps",
        "description": "Búsqueda de lugares, direcciones, distancias "
                       "y coordenadas geográficas.",
        "tools_description": "search_places, get_directions, get_location",
        "command": "npx",
        "default_args": ["-y", "@modelcontextprotocol/server-google-maps"],
        "config_fields": [
            {
                "name": "GOOGLE_MAPS_API_KEY",
                "label": "Google Maps API Key",
                "type": "api_key",
                "env_var": "GOOGLE_MAPS_API_KEY",
                "required": True,
                "placeholder": "AIza...",
            }
        ],
    },
    {
        "server_name": "puppeteer",
        "display_name": "Puppeteer Browser",
        "description": "Automatización de navegador headless. "
                       "Alternativa ligera a Playwright para "
                       "navegar, capturar screenshots y extraer contenido.",
        "tools_description": "navigate, screenshot, click, fill, extract_text",
        "command": "npx",
        "default_args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "config_fields": [],
    },
    {
        "server_name": "filesystem",
        "display_name": "Filesystem",
        "description": "Operaciones avanzadas del sistema de archivos: "
                       "leer, escribir, buscar, mover, copiar archivos "
                       "y directorios.",
        "tools_description": "read_file, write_file, search, list_dir, move, copy",
        "command": "npx",
        "default_args": ["-y", "@modelcontextprotocol/server-filesystem",
                         str(Path.home() / "Desktop")],
        "config_fields": [
            {
                "name": "directory",
                "label": "Directorio de trabajo",
                "type": "string",
                "env_var": "",
                "arg_index": 2,
                "required": False,
                "placeholder": "C:/ruta/del/directorio",
            }
        ],
    },
    {
        "server_name": "gmail",
        "display_name": "Gmail",
        "description": "Envía y lee correos electrónicos directamente desde el chat. "
                       "Gestiona tu bandeja de entrada sin salir de Relay.",
        "tools_description": "enviar_correo, revisar_recibidos, revisar_no_leidos, buscar_por_remitente",
        "command": "python",
        "default_args": ["-u", "mcp_scripts/gmail_server.py"],
        "config_fields": [
            {
                "name": "GMAIL_USER",
                "label": "Correo Gmail",
                "type": "api_key",
                "env_var": "GMAIL_USER",
                "required": True,
                "placeholder": "tucorreo@gmail.com",
            },
            {
                "name": "GMAIL_APP_PASSWORD",
                "label": "Contraseña de aplicación",
                "type": "api_key",
                "env_var": "GMAIL_APP_PASSWORD",
                "required": True,
                "placeholder": "xxxx xxxx xxxx xxxx",
            },
        ],
    },
    {
        "server_name": "whatsapp",
        "display_name": "WhatsApp",
        "description": "Envía mensajes de WhatsApp desde el chat. "
                       "Requiere Chrome y WhatsApp Web escaneado.",
        "tools_description": "enviar_whatsapp",
        "command": "python",
        "default_args": ["-u", "mcp_scripts/whatsapp_server.py"],
        "config_fields": [],
    },
    {
        "server_name": "wigolo",
        "display_name": "Wigolo Web Intelligence",
        "description": "Capa de inteligencia web local-first sin API keys ni "
                       "dependencias cloud. Búsqueda multi-motor (18 adaptadores), "
                       "fetch con navegador headless, crawl, extracción "
                       "estructurada, research autónomo y diff de páginas.",
        "tools_description": "search, fetch, crawl, extract, cache, "
                             "find_similar, research, agent, diff, watch",
        "command": "npx",
        "default_args": ["-y", "wigolo@0.2.1"],
        "config_fields": [],
    },
    {
        "server_name": "codebase-memory-mcp",
        "display_name": "Codebase Memory",
        "description": "Indexa repositorios en un grafo de conocimiento: "
                       "158 lenguajes, consultas sub-ms. Busca símbolos, "
                       "traza llamadas y analiza arquitectura del código.",
        "tools_description": "index_repository, search_graph, trace_path, "
                             "get_code_snippet, query_graph, get_architecture",
        "command": os.environ.get(
            "CODEBASE_MEMORY_BIN", "codebase-memory-mcp"
        ),
        "default_args": [],
        "config_fields": [],
    },
]


def get_catalog():
    """Return the full integration catalog."""
    return list(CATALOG)


def get_catalog_item(server_name: str) -> dict | None:
    """Look up a single integration from the catalog by server name."""
    for item in CATALOG:
        if item["server_name"] == server_name:
            return item
    return None


# ── .env management ───────────────────────────────────────────

def _ensure_env_exists():
    """Create backend/.env if it doesn't exist."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
        logger.info("Created %s", ENV_PATH)


def set_env_key(key: str, value: str) -> str:
    """Write or update a key in backend/.env.

    Uses python-dotenv's set_key to preserve existing entries.
    Returns the value written (or masked for display).
    """
    _ensure_env_exists()
    load_dotenv(ENV_PATH)  # refresh so set_key sees current state
    set_key(str(ENV_PATH), key, value)
    logger.info("Updated .env: %s=***", key)
    return value


def get_env_key(key: str) -> str:
    """Read a key from the environment (already loaded via dotenv)."""
    return os.environ.get(key, "")


def remove_env_key(key: str) -> None:
    """Remove a key from backend/.env."""
    _ensure_env_exists()
    load_dotenv(ENV_PATH)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    filtered = [ln for ln in lines if not ln.startswith(f"{key}=") and not ln.startswith(f"export {key}=")]
    ENV_PATH.write_text("\n".join(filtered) + "\n", encoding="utf-8")
    # Also remove from current process env
    os.environ.pop(key, None)
    logger.info("Removed from .env: %s", key)


# ── Integration config (SQLite) ───────────────────────────────

def init_integrations_table(conn):
    """Create the integrations table in the existing SQLite DB.

    Call from session_db.init_db().
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS integrations (
            server_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            config TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
    """)
    # Seed catalog entries so they appear even before first enable
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    for item in CATALOG:
        conn.execute(
            """INSERT OR IGNORE INTO integrations (server_name, enabled, config, updated_at)
               VALUES (?, 0, '{}', ?)""",
            (item["server_name"], now),
        )
    conn.commit()


def set_integration_enabled(conn, server_name: str, enabled: bool, config: dict | None = None) -> dict:
    """Enable or disable an integration, optionally updating config.

    Returns the full integration record.
    """
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    existing = conn.execute(
        "SELECT config FROM integrations WHERE server_name = ?", (server_name,)
    ).fetchone()

    merged_config = existing["config"] if existing and not config else "{}"
    if config is not None:
        merged_config = json.dumps(config)
    elif existing and enabled:
        # Re-enabling: keep whatever config was saved
        merged_config = existing["config"]
    elif not enabled:
        # Disabling: keep last config for when it's re-enabled
        merged_config = json.loads(merged_config) if isinstance(merged_config, str) else merged_config
        merged_config = json.dumps(merged_config)

    conn.execute(
        """UPDATE integrations SET enabled = ?, config = ?, updated_at = ?
           WHERE server_name = ?""",
        (1 if enabled else 0, merged_config, now, server_name),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM integrations WHERE server_name = ?", (server_name,)
    ).fetchone()
    return dict(row)


def get_integrations(conn) -> list[dict]:
    """Return all integration records."""
    rows = conn.execute(
        "SELECT * FROM integrations ORDER BY server_name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_integration(conn, server_name: str) -> dict | None:
    """Return a single integration record or None."""
    row = conn.execute(
        "SELECT * FROM integrations WHERE server_name = ?", (server_name,)
    ).fetchone()
    return dict(row) if row else None


# ── MCP lifecycle bridge ──────────────────────────────────────

def _build_server_params(catalog_item: dict, config: dict, env_overrides: dict | None = None) -> dict:
    """Build the MCP server parameters dict from catalog + user config.

    Args:
        catalog_item: Entry from CATALOG.
        config: User config dict from SQLite (non-sensitive).
        env_overrides: Additional env vars (e.g., from .env keys).

    Returns:
        dict with 'command', 'args', 'env' ready for _MCPServerConn.
    """
    merged_env = {}
    if env_overrides:
        merged_env.update(env_overrides)

    # If user config has env var overrides, merge those too
    user_config = config or {}
    user_env = user_config.get("_env", {})
    merged_env.update(user_env)

    # Start with default args, then apply any arg_index overrides from config
    args = list(catalog_item["default_args"])
    for field in catalog_item.get("config_fields", []):
        arg_index = field.get("arg_index")
        if arg_index is not None and field["name"] in user_config:
            override_value = user_config[field["name"]]
            if override_value and arg_index < len(args):
                args[arg_index] = override_value

    # Force unbuffered stdout for Python-based servers (MCP stdio hangs otherwise)
    # Also use sys.executable (full path) so the subprocess finds Python even
    # when launched from run.bat where 'python' may not be in PATH.
    command = catalog_item.get("command", "")
    if command == "python":
        merged_env["PYTHONUNBUFFERED"] = "1"
        command = sys.executable

    return {
        "command": command,
        "args": args,
        "env": merged_env,
    }

# ── IntegrationsManager ───────────────────────────────────────

class IntegrationsManager:
    """High-level manager that bridges catalog, config, .env, and MCP lifecycle.

    Delegates actual MCP connection/disconnection to mcp_manager's
    _MCPServerConn instances.
    """

    def __init__(self, mcp_manager):
        self._mcp = mcp_manager
        self._connections: dict[str, object] = {}  # server_name -> _MCPServerConn

    def start_configured(self, conn):
        """On startup: load all enabled integrations from DB and start them.

        Call this during the FastAPI lifespan startup, after the MCP
        manager is initialized.
        """
        # Run preflight checks first so the UI shows dependency status
        preflight_checks()

        if not self._mcp.is_available:
            logger.warning("MCP SDK not available — skipping integrations startup")
            return []

        results = []
        integrations = get_integrations(conn)
        for rec in integrations:
            if not rec["enabled"]:
                continue
            server_name = rec["server_name"]
            
            # Skip if already connected via mcp_config.json (avoids overriding working connections)
            if self._mcp.has_server(server_name):
                logger.info("Integration %s already connected via MCP config — skipping", server_name)
                # Still report tools from the existing connection
                existing_conn = self._mcp._connections.get(server_name)
                if existing_conn:
                    tools_info = [
                        {"name": t.name, "description": t.description or ""}
                        for t in existing_conn.tools
                    ]
                    results.append({
                        "server": server_name,
                        "status": "connected",
                        "tools": tools_info,
                    })
                continue
            
            catalog_item = get_catalog_item(server_name)
            if not catalog_item:
                logger.warning("Unknown integration in DB: %s", server_name)
                continue

            # Gather env vars from .env
            env_vars = self._gather_env_for(catalog_item)
            params = _build_server_params(catalog_item, json.loads(rec["config"]), env_vars)

            try:
                result = self._start_one(server_name, params)
                results.append(result)
            except Exception as exc:
                logger.error("Failed to start integration %s: %s", server_name, exc)
                results.append({
                    "server": server_name,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    def _gather_env_for(self, catalog_item: dict) -> dict:
        """Read the API keys/tokens from env for a catalog item."""
        env = {}
        for field in catalog_item.get("config_fields", []):
            if field["type"] == "api_key":
                val = get_env_key(field["env_var"])
                if val:
                    env[field["env_var"]] = val
        return env

    def _start_one(self, server_name: str, params: dict) -> dict:
        """Start a single MCP server by name.

        Delegates to mcp_manager's internal _MCPServerConn.
        Returns status dict.
        """
        if not self._mcp.is_available:
            return {"server": server_name, "status": "error",
                    "error": "MCP SDK not installed"}

        # If already connected (e.g. via mcp_config.json), return existing tools
        if self._mcp.has_server(server_name):
            existing = self._mcp._connections.get(server_name)
            if existing:
                tools_info = [
                    {"name": t.name, "description": t.description or ""}
                    for t in existing.tools
                ]
                logger.info("Integration %s already connected — reusing existing (%d tools)",
                            server_name, len(tools_info))
                return {
                    "server": server_name,
                    "status": "connected",
                    "tools": tools_info,
                }

        # Use the MCP manager's internal method
        conn = self._mcp._start_server(server_name, params)
        self._connections[server_name] = conn
        tools_info = [
            {"name": t.name, "description": t.description or ""}
            for t in conn.tools
        ]
        return {
            "server": server_name,
            "status": "connected",
            "tools": tools_info,
        }

    def enable(self, conn, server_name: str, api_keys: dict | None = None,
               config: dict | None = None) -> dict:
        """Enable an integration: save config, store API keys, start server.

        Args:
            conn: SQLite connection.
            server_name: Which integration to enable.
            api_keys: Dict of env_var -> value to write to .env.
            config: Non-sensitive config to store in SQLite.

        Returns:
            Status dict with server status + tools.
        """
        catalog_item = get_catalog_item(server_name)
        if not catalog_item:
            raise ValueError(f"Unknown integration: {server_name}")

        # 1. Write API keys to .env (sensitive storage)
        if api_keys:
            for env_var, value in api_keys.items():
                if value:
                    set_env_key(env_var, value)

        # 2. Save non-sensitive config to SQLite
        rec = set_integration_enabled(conn, server_name, True, config)
        merged_config = json.loads(rec["config"])

        # 3. Gather env vars from .env
        env_vars = self._gather_env_for(catalog_item)
        if api_keys:
            env_vars.update(api_keys)

        # 4. Build server params and start
        params = _build_server_params(catalog_item, merged_config, env_vars)
        try:
            result = self._start_one(server_name, params)
            result["config"] = merged_config
            return result
        except Exception as exc:
            logger.exception("Failed to start integration %s", server_name)
            return {
                "server": server_name,
                "status": "error",
                "error": str(exc),
                "config": merged_config,
            }

    def disable(self, conn, server_name: str) -> dict:
        """Disable an integration: stop server, update DB.

        Does NOT remove API keys from .env — they stay for when the
        user re-enables the integration.
        """
        # 1. Stop the MCP server
        self._mcp._stop_server(server_name)
        self._connections.pop(server_name, None)

        # 2. Update DB
        rec = set_integration_enabled(conn, server_name, False)
        return {"server": server_name, "status": "disabled"}

    def configure(self, conn, server_name: str, api_keys: dict | None = None,
                  config: dict | None = None) -> dict:
        """Update config for an integration. Restarts if currently enabled.

        Args:
            conn: SQLite connection.
            server_name: Which integration to configure.
            api_keys: Dict of env_var -> value to write to .env.
            config: Non-sensitive config to store in SQLite.
        """
        catalog_item = get_catalog_item(server_name)
        if not catalog_item:
            raise ValueError(f"Unknown integration: {server_name}")

        # 1. Write new API keys to .env
        if api_keys:
            for env_var, value in api_keys.items():
                if value:
                    set_env_key(env_var, value)

        # 2. Update config in SQLite
        rec = set_integration_enabled(conn, server_name, True, config)
        merged_config = json.loads(rec["config"])

        # 3. Restart if currently running
        was_running = server_name in self._connections
        if was_running:
            self._mcp._stop_server(server_name)
            self._connections.pop(server_name, None)

            env_vars = self._gather_env_for(catalog_item)
            if api_keys:
                env_vars.update(api_keys)

            params = _build_server_params(catalog_item, merged_config, env_vars)
            try:
                result = self._start_one(server_name, params)
                result["config"] = merged_config
                return result
            except Exception as exc:
                logger.exception("Failed to restart integration %s after config", server_name)
                return {
                    "server": server_name,
                    "status": "error",
                    "error": str(exc),
                    "config": merged_config,
                }

        return {
            "server": server_name,
            "status": "configured",
            "config": merged_config,
        }

    def get_connection_status(self) -> list[dict]:
        """Return status of all integration connections."""
        results = []
        for server_name, conn in self._connections.items():
            tools_info = [
                {"name": t.name, "description": t.description or ""}
                for t in conn.tools
            ]
            results.append({
                "server": server_name,
                "status": "connected",
                "tools": tools_info,
            })
        return results

    def stop_all(self):
        """Stop all integration-managed servers."""
        for server_name in list(self._connections.keys()):
            self._mcp._stop_server(server_name)
        self._connections.clear()
        logger.info("All integrations stopped")
