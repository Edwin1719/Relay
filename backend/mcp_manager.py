"""MCP Server Manager for Relay.

Manages multiple MCP server processes, discovers their tools,
and bridges them to the MiniAgent's tool system.
"""

import asyncio
import json
import logging
import os
import threading
from pathlib import Path

from http_client import resolve_env_var
from session_db import (
    mcp_is_broken, mcp_record_success, mcp_record_failure, mcp_reset_server,
)

logger = logging.getLogger("kodama.mcp")


# ── Attempt to import the MCP SDK ────────────────────────────────
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp package not installed. Run: pip install mcp")


# ── MCP Server Connection ────────────────────────────────────────

class _MCPServerConn:
    """Manages the lifecycle of a single MCP server process."""

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.session: ClientSession | None = None
        self.tools: list = []
        self._stdio_ctx = None
        self._session_ctx = None
        self._read = None
        self._write = None

    async def connect(self):
        """Spawn the server process and connect via stdio."""
        resolved_env = {k: resolve_env_var(v) for k, v in self.cfg.get("env", {}).items()}
        params = StdioServerParameters(
            command=self.cfg["command"],
            args=self.cfg.get("args", []),
            env={**os.environ, **resolved_env},
        )
        self._stdio_ctx = stdio_client(params)
        self._read, self._write = await self._stdio_ctx.__aenter__()

        self._session_ctx = ClientSession(self._read, self._write)
        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()

        # Discover tools
        result = await self.session.list_tools()
        self.tools = result.tools
        logger.info(
            "MCP connected: %s (%d tools)", self.name, len(self.tools)
        )

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on this server and return the result as text."""
        if not self.session:
            raise RuntimeError(f"MCP server '{self.name}' is not connected")
        try:
            result = await self.session.call_tool(tool_name, arguments)
            parts = []
            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
            return "\n".join(parts) if parts else str(result)
        except Exception as exc:
            return f"Error calling MCP tool {self.name}.{tool_name}: {exc}"

    async def disconnect(self):
        """Cleanly shut down the server connection."""
        try:
            if self._session_ctx:
                await self._session_ctx.__aexit__(None, None, None)
            if self._stdio_ctx:
                await self._stdio_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        self.session = None
        self.tools = []
        self._session_ctx = None
        self._stdio_ctx = None
        logger.info("MCP disconnected: %s", self.name)


# ── MCP Manager ──────────────────────────────────────────────────

class MCPManager:
    """Manages all MCP server connections in a background asyncio thread."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connections: dict[str, _MCPServerConn] = {}
        self._ready = threading.Event()

    @property
    def is_available(self) -> bool:
        return MCP_AVAILABLE

    def start(self, config_path: str | Path | None = None, enabled_servers: set[str] | None = None) -> list[dict]:
        """Start the MCP manager and connect all configured servers.

        Args:
            config_path: Path to JSON config file. If None, looks for
                         mcp_config.json in the same directory as this file.
            enabled_servers: If provided, only servers whose names appear
                             in this set will be connected. Others are skipped.
                             If None (default), all servers in the config file
                             are connected (backward-compatible behavior).

        Returns:
            List of connection results with status for each server.
        """
        if not MCP_AVAILABLE:
            return [{"server": "system", "status": "error",
                     "error": "mcp package not installed"}]

        # Load config
        if config_path is None:
            config_path = Path(__file__).parent / "mcp_config.json"
        config_path = Path(config_path)

        if not config_path.exists():
            return [{"server": "system", "status": "error",
                     "error": f"Config not found: {config_path}"}]

        with open(config_path) as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        if not servers:
            return [{"server": "system", "status": "error",
                     "error": "No MCP servers configured"}]

        # Start asyncio loop in background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="mcp-loop"
        )
        self._thread.start()

        # Connect all servers (skip broken ones)
        results = []
        futures = []
        for name, cfg in servers.items():
            if mcp_is_broken(name):
                logger.warning("MCP server '%s' is broken — skipping (use /api/mcp/reset to retry)", name)
                results.append({
                    "server": name,
                    "status": "broken",
                    "error": "Circuit breaker open — too many consecutive failures",
                })
                continue

            # Lazy-load: skip servers not in the enabled set (if provided)
            if enabled_servers is not None and name not in enabled_servers:
                logger.info("MCP server '%s' not enabled — skipping", name)
                results.append({
                    "server": name,
                    "status": "disabled",
                    "error": "Not enabled by user",
                })
                continue

            conn = _MCPServerConn(name, cfg)
            self._connections[name] = conn
            future = asyncio.run_coroutine_threadsafe(
                conn.connect(), self._loop
            )
            futures.append((name, future))

        for name, future in futures:
            try:
                future.result(timeout=60)
                conn = self._connections[name]
                tools_info = [
                    {"name": t.name, "description": t.description or ""}
                    for t in conn.tools
                ]
                mcp_record_success(name)
                results.append({
                    "server": name,
                    "status": "connected",
                    "tools": tools_info,
                })
            except Exception as exc:
                error_msg = str(exc)
                mcp_record_failure(name, error_msg)
                results.append({
                    "server": name,
                    "status": "error",
                    "error": error_msg,
                })

        self._ready.set()
        return results

    def _run_loop(self):
        """Run the asyncio event loop."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop(self):
        """Disconnect all servers and stop the event loop."""
        if not self._loop:
            return

        for name, conn in list(self._connections.items()):
            asyncio.run_coroutine_threadsafe(
                conn.disconnect(), self._loop
            ).result(timeout=10)

        self._connections.clear()
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None

    def get_all_mcp_tools(self) -> dict:
        """Return all MCP tools formatted for the MiniAgent tool system.

        Returns:
            dict of tool_name -> {schema, risky, description, run}
        """
        if not MCP_AVAILABLE:
            return {}

        tools = {}
        for server_name, conn in self._connections.items():
            for tool in conn.tools:
                # Namespace: mcp_<server>_<tool>
                full_name = f"mcp_{server_name}_{tool.name}"

                # Build a schema from the tool's inputSchema
                schema = {}
                if hasattr(tool, "inputSchema") and tool.inputSchema:
                    props = tool.inputSchema.get("properties", {})
                    required = set(tool.inputSchema.get("required", []))
                    for prop_name, prop_def in props.items():
                        schema[prop_name] = prop_def.get(
                            "type", "str"
                        )
                        if prop_name not in required:
                            schema[prop_name] = f"{schema[prop_name]}?"

                description = tool.description or f"MCP tool from {server_name}"
                # Keep descriptions short — they bloat the agent prompt
                if len(description) > 100:
                    description = description[:97] + "..."
                description = f"[MCP:{server_name}] {description}"

                tools[full_name] = {
                    "schema": schema,
                    "risky": True,
                    "description": description,
                    "run": self._make_tool_runner(server_name, tool.name),
                }
        return tools

    def _make_tool_runner(self, server_name: str, tool_name: str):
        """Create a synchronous callable for a specific MCP tool."""
        def run(args):
            if not self._loop:
                return "error: MCP manager is not running"
            if not isinstance(args, dict):
                args = {}
            future = asyncio.run_coroutine_threadsafe(
                self._connections[server_name].call_tool(tool_name, args),
                self._loop,
            )
            return future.result(timeout=120)
        return run

    def get_status(self) -> list[dict]:
        """Get the status of all MCP server connections."""
        results = []
        for name, conn in self._connections.items():
            tools_info = [
                {"name": t.name, "description": t.description or ""}
                for t in conn.tools
            ]
            results.append({
                "server": name,
                "status": "connected" if conn.session else "disconnected",
                "tools": tools_info,
            })
        return results

    # ── Individual server lifecycle (for integrations) ──────────

    def _start_server(self, server_name: str, params: dict) -> _MCPServerConn:
        """Start a single MCP server by name with given params.

        Args:
            server_name: Identifier for the server.
            params: dict with 'command', 'args', 'env'.

        Returns:
            The _MCPServerConn instance (already connected).

        Raises:
            RuntimeError if MCP SDK not available.
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP SDK not installed")

        # Build a cfg dict compatible with _MCPServerConn
        cfg = {
            "command": params["command"],
            "args": params.get("args", []),
            "env": params.get("env", {}),
        }

        if mcp_is_broken(server_name):
            raise RuntimeError(
                f"MCP server '{server_name}' is broken — too many consecutive failures. "
                f"Use /api/mcp/reset to retry."
            )

        conn = _MCPServerConn(server_name, cfg)
        self._connections[server_name] = conn

        # Run connect in the asyncio loop
        future = asyncio.run_coroutine_threadsafe(
            conn.connect(), self._loop
        )
        try:
            future.result(timeout=60)
        except Exception as exc:
            self._connections.pop(server_name, None)
            mcp_record_failure(server_name, str(exc))
            raise RuntimeError(f"Failed to start MCP server '{server_name}': {exc}") from exc

        mcp_record_success(server_name)
        logger.info("MCP server started: %s (%d tools)", server_name, len(conn.tools))
        return conn

    def _stop_server(self, server_name: str):
        """Stop a single MCP server by name."""
        conn = self._connections.pop(server_name, None)
        if conn is None:
            logger.debug("MCP server not found (already stopped?): %s", server_name)
            return

        future = asyncio.run_coroutine_threadsafe(
            conn.disconnect(), self._loop
        )
        try:
            future.result(timeout=10)
        except Exception as exc:
            logger.warning("Error stopping MCP server '%s': %s", server_name, exc)

        logger.info("MCP server stopped: %s", server_name)

    def has_server(self, server_name: str) -> bool:
        """Check if a server is currently connected."""
        return server_name in self._connections


# ── Singleton ────────────────────────────────────────────────────

_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager singleton."""
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
