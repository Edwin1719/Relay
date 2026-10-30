"""Tests for mcp_manager.py — MCP server lifecycle and tool bridging.

These tests mock the real MCP SDK and subprocess I/O. No real servers are started.
All async operations are mocked or replaced with synchronous equivalents.
"""

import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_mcp_sdk(monkeypatch):
    """Mock the entire mcp SDK so mcp_manager can be imported cleanly."""
    fake_mcp = MagicMock()
    fake_client = MagicMock()
    fake_stdio = MagicMock()
    fake_mcp.ClientSession = fake_client
    fake_mcp.StdioServerParameters = MagicMock()
    fake_mcp.client.stdio.stdio_client = fake_stdio
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", MagicMock())
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", MagicMock())
    # Force MCP_AVAILABLE = True
    import mcp_manager
    monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", True)

    # Mock circuit breaker functions (added in session #1 improvements)
    # so tests don't need a real mcp_health SQLite table
    monkeypatch.setattr(mcp_manager, "mcp_is_broken", lambda name: False)
    monkeypatch.setattr(mcp_manager, "mcp_record_success", lambda name: None)
    monkeypatch.setattr(mcp_manager, "mcp_record_failure", lambda name, error="": None)
    monkeypatch.setattr(mcp_manager, "mcp_reset_server", lambda name: None)

    return mcp_manager


@pytest.fixture
def fresh_manager(monkeypatch):
    """Return a clean MCPManager singleton (reset _manager global)."""
    import mcp_manager
    # Force MCP_AVAILABLE before creating manager
    monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", True)
    monkeypatch.setattr(mcp_manager, "_manager", None)
    return mcp_manager.get_mcp_manager()


@pytest.fixture
def temp_mcp_config(tmp_path):
    """Create a temporary mcp_config.json and return its path."""
    config = {
        "mcpServers": {
            "test-server-1": {
                "command": "node",
                "args": ["server1.js"],
                "env": {"NODE_ENV": "test"},
            },
            "test-server-2": {
                "command": "python",
                "args": ["-m", "server2"],
                "env": {},
            },
        }
    }
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(json.dumps(config))
    return str(config_path)


@pytest.fixture
def mock_conn_connect(monkeypatch):
    """Replace _MCPServerConn.connect() with a synchronous mock."""
    import mcp_manager

    async def fake_connect(self):
        self.session = MagicMock()
        # Create mock tools
        tool1 = MagicMock()
        tool1.name = "tool_a"
        tool1.description = "Tool A does something useful"
        tool1.inputSchema = {
            "properties": {"param1": {"type": "string"}},
            "required": ["param1"],
        }
        tool2 = MagicMock()
        tool2.name = "tool_b"
        tool2.description = None
        tool2.inputSchema = None
        self.tools = [tool1, tool2]

    monkeypatch.setattr(mcp_manager._MCPServerConn, "connect", fake_connect)


@pytest.fixture
def mock_conn_disconnect(monkeypatch):
    """Replace _MCPServerConn.disconnect() with a no-op mock."""
    import mcp_manager

    async def fake_disconnect(self):
        self.session = None
        self.tools = []

    monkeypatch.setattr(mcp_manager._MCPServerConn, "disconnect", fake_disconnect)


# ── Singleton tests ─────────────────────────────────────────────

class TestSingleton:
    """MCPManager singleton pattern."""

    def test_get_mcp_manager_returns_same_instance(self, mock_mcp_sdk):
        import mcp_manager
        mgr1 = mcp_manager.get_mcp_manager()
        mgr2 = mcp_manager.get_mcp_manager()
        assert mgr1 is mgr2

    def test_is_available_when_sdk_present(self, mock_mcp_sdk):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        assert mgr.is_available is True

    def test_is_available_when_sdk_missing(self, monkeypatch):
        """Simulate MCP SDK not installed."""
        import mcp_manager
        monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", False)
        monkeypatch.setattr(mcp_manager, "_manager", None)
        mgr = mcp_manager.get_mcp_manager()
        assert mgr.is_available is False


# ── Config loading tests ────────────────────────────────────────

class TestConfigLoading:
    """Tests for start() with various config scenarios."""

    def test_start_loads_config_and_connects(self, mock_mcp_sdk, mock_conn_connect,
                                              mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        results = mgr.start(temp_mcp_config)

        assert len(results) == 2
        server_names = [r["server"] for r in results]
        assert "test-server-1" in server_names
        assert "test-server-2" in server_names
        assert all(r["status"] == "connected" for r in results)

        # Each server should have 2 mock tools
        for r in results:
            assert len(r["tools"]) == 2

        mgr.stop()

    def test_start_config_not_found(self, mock_mcp_sdk, fresh_manager):
        results = fresh_manager.start("/nonexistent/config.json")
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "not found" in results[0]["error"]

    def test_start_no_servers_configured(self, mock_mcp_sdk, fresh_manager, tmp_path):
        config_path = tmp_path / "empty_config.json"
        config_path.write_text(json.dumps({"mcpServers": {}}))
        results = fresh_manager.start(str(config_path))
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "No MCP servers" in results[0]["error"]

    def test_start_when_sdk_unavailable(self, monkeypatch):
        """When MCP SDK is not installed, start() returns error immediately."""
        import mcp_manager
        monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", False)
        monkeypatch.setattr(mcp_manager, "_manager", None)
        mgr = mcp_manager.get_mcp_manager()
        results = mgr.start()
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "not installed" in results[0]["error"]

    def test_start_connection_error(self, mock_mcp_sdk, monkeypatch,
                                     temp_mcp_config, fresh_manager):
        """When a server fails to connect, its status is 'error'."""
        import mcp_manager

        async def fake_connect_error(self):
            raise RuntimeError("Connection refused")

        monkeypatch.setattr(mcp_manager._MCPServerConn, "connect", fake_connect_error)

        results = fresh_manager.start(temp_mcp_config)
        assert len(results) == 2
        assert all(r["status"] == "error" for r in results)
        assert all("Connection refused" in r.get("error", "") for r in results)

        fresh_manager.stop()


# ── Tool formatting tests ───────────────────────────────────────

class TestToolFormatting:
    """Tests for get_all_mcp_tools() — namespacing, schema, description."""

    def test_tool_namespacing(self, mock_mcp_sdk, mock_conn_connect,
                               mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        tools = mgr.get_all_mcp_tools()
        expected_names = [
            "mcp_test-server-1_tool_a",
            "mcp_test-server-1_tool_b",
            "mcp_test-server-2_tool_a",
            "mcp_test-server-2_tool_b",
        ]
        for name in expected_names:
            assert name in tools

        mgr.stop()

    def test_tool_schema_extraction(self, mock_mcp_sdk, mock_conn_connect,
                                     mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        tools = mgr.get_all_mcp_tools()
        # tool_a has inputSchema with param1 (required)
        tool_a = tools["mcp_test-server-1_tool_a"]
        assert tool_a["schema"] == {"param1": "string"}
        assert tool_a["risky"] is True
        assert "[MCP:test-server-1]" in tool_a["description"]

        # tool_b has no inputSchema
        tool_b = tools["mcp_test-server-1_tool_b"]
        assert tool_b["schema"] == {}

        mgr.stop()

    def test_description_truncation(self, mock_mcp_sdk, monkeypatch,
                                     mock_conn_disconnect, temp_mcp_config, fresh_manager):
        """Descriptions longer than 100 chars are truncated with '...'."""
        import mcp_manager

        async def fake_connect_long_desc(self):
            self.session = MagicMock()
            tool = MagicMock()
            tool.name = "long_desc_tool"
            tool.description = "A" * 150 + "B" * 50  # 200 chars
            tool.inputSchema = None
            self.tools = [tool]

        monkeypatch.setattr(mcp_manager._MCPServerConn, "connect", fake_connect_long_desc)

        fresh_manager.start(temp_mcp_config)
        tools = fresh_manager.get_all_mcp_tools()

        desc = tools["mcp_test-server-1_long_desc_tool"]["description"]
        assert len(desc) <= 100 + len("[MCP:test-server-1] ")
        assert desc.endswith("...")

        fresh_manager.stop()

    def test_tools_empty_when_no_connections(self, mock_mcp_sdk, fresh_manager):
        tools = fresh_manager.get_all_mcp_tools()
        assert tools == {}

    def test_tools_empty_when_sdk_unavailable(self, monkeypatch):
        import mcp_manager
        monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", False)
        monkeypatch.setattr(mcp_manager, "_manager", None)
        mgr = mcp_manager.get_mcp_manager()
        tools = mgr.get_all_mcp_tools()
        assert tools == {}


# ── Status tests ────────────────────────────────────────────────

class TestStatus:
    """Tests for get_status()."""

    def test_status_connected(self, mock_mcp_sdk, mock_conn_connect,
                               mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        status = mgr.get_status()
        assert len(status) == 2
        for s in status:
            assert s["status"] == "connected"
            assert len(s["tools"]) == 2

        mgr.stop()

    def test_status_empty_when_no_servers(self, mock_mcp_sdk, fresh_manager):
        status = fresh_manager.get_status()
        assert status == []


# ── Individual server lifecycle tests ───────────────────────────

class TestServerLifecycle:
    """Tests for _start_server(), _stop_server(), has_server()."""

    def test_has_server(self, mock_mcp_sdk, mock_conn_connect,
                         mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        assert mgr.has_server("test-server-1") is True
        assert mgr.has_server("test-server-2") is True
        assert mgr.has_server("nonexistent") is False

        mgr.stop()

    def test_stop_server_removes_from_connections(self, mock_mcp_sdk, mock_conn_connect,
                                                    mock_conn_disconnect, temp_mcp_config):
        import mcp_manager
        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        assert mgr.has_server("test-server-1") is True
        mgr._stop_server("test-server-1")
        assert mgr.has_server("test-server-1") is False
        assert mgr.has_server("test-server-2") is True

        mgr.stop()

    def test_stop_server_nonexistent_does_not_raise(self, mock_mcp_sdk, fresh_manager):
        # Should not raise
        fresh_manager._stop_server("nonexistent")

    def test_start_server_requires_sdk(self, monkeypatch, fresh_manager):
        """_start_server raises RuntimeError if MCP SDK not available."""
        import mcp_manager
        monkeypatch.setattr(mcp_manager, "MCP_AVAILABLE", False)
        with pytest.raises(RuntimeError, match="MCP SDK not installed"):
            fresh_manager._start_server("test", {"command": "echo", "args": []})

    def test_start_server_connects_after_start(self, mock_mcp_sdk, mock_conn_connect,
                                                mock_conn_disconnect, temp_mcp_config,
                                                fresh_manager):
        """_start_server adds a new server after start() has initialized the loop."""
        # start() initializes the event loop + connects configured servers
        fresh_manager.start(temp_mcp_config)

        params = {"command": "python", "args": ["-c", "pass"]}
        try:
            conn = fresh_manager._start_server("extra-server", params)
            assert conn is not None
            assert fresh_manager.has_server("extra-server") is True
            assert fresh_manager.has_server("test-server-1") is True  # from start()
        finally:
            fresh_manager.stop()


# ── Tool runner tests ───────────────────────────────────────────

class TestToolRunner:
    """Tests for _make_tool_runner() and tool execution via call_tool()."""

    def test_make_tool_runner_returns_callable(self, mock_mcp_sdk, fresh_manager):
        runner = fresh_manager._make_tool_runner("test-server", "my_tool")
        assert callable(runner)

    def test_tool_runner_error_when_not_running(self, mock_mcp_sdk, fresh_manager):
        """Tool runner returns error when event loop is not running."""
        runner = fresh_manager._make_tool_runner("test-server", "my_tool")
        result = runner({})
        assert "not running" in result

    def test_tool_runner_calls_tool(self, mock_mcp_sdk, mock_conn_connect,
                                     mock_conn_disconnect, temp_mcp_config, monkeypatch):
        """Tool runner executes the tool through the MCP bridge."""
        import mcp_manager

        # Make call_tool synchronous for testing
        async def fake_call_tool(self, tool_name, arguments):
            return f"Result from {tool_name}: {arguments}"

        monkeypatch.setattr(mcp_manager._MCPServerConn, "call_tool", fake_call_tool)

        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        runner = mgr._make_tool_runner("test-server-1", "tool_a")
        result = runner({"param1": "hello"})
        assert "tool_a" in result or "hello" in result

        mgr.stop()

    def test_tool_runner_handles_non_dict_args(self, mock_mcp_sdk, mock_conn_connect,
                                                 mock_conn_disconnect, temp_mcp_config, monkeypatch):
        """Tool runner converts non-dict args to empty dict."""
        import mcp_manager

        async def fake_call_tool(self, tool_name, arguments):
            return f"called with {type(arguments).__name__}: {arguments}"

        monkeypatch.setattr(mcp_manager._MCPServerConn, "call_tool", fake_call_tool)

        mgr = mcp_manager.get_mcp_manager()
        mgr.start(temp_mcp_config)

        runner = mgr._make_tool_runner("test-server-1", "tool_a")
        result = runner("not_a_dict")
        # Should not crash — non-dict converted to {}
        assert isinstance(result, str)

        mgr.stop()


# ── _MCPServerConn tests ────────────────────────────────────────

class TestMCPServerConn:
    """Tests for _MCPServerConn call_tool and disconnect."""

    def test_call_tool_when_disconnected(self, mock_mcp_sdk):
        import mcp_manager
        conn = mcp_manager._MCPServerConn("test", {"command": "echo"})
        with pytest.raises(RuntimeError, match="not connected"):
            # Need to run in event loop; we test the guard condition
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(conn.call_tool("test_tool", {}))
            finally:
                loop.close()

    def test_call_tool_error_handling(self, mock_mcp_sdk, monkeypatch):
        """call_tool returns error string when tool execution fails."""
        import mcp_manager

        conn = mcp_manager._MCPServerConn("test", {"command": "echo"})
        conn.session = MagicMock()

        async def failing_call(tool_name, arguments):
            raise ValueError("Tool execution failed")

        conn.session.call_tool = failing_call

        import asyncio

        async def run():
            result = await conn.call_tool("broken_tool", {})
            assert "Error" in result
            assert "Tool execution failed" in result

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_call_tool_text_content(self, mock_mcp_sdk, monkeypatch):
        """call_tool extracts text content from tool result."""
        import mcp_manager

        conn = mcp_manager._MCPServerConn("test", {"command": "echo"})
        conn.session = MagicMock()

        result_mock = MagicMock()
        text_item = MagicMock()
        text_item.text = "Hello World"
        result_mock.content = [text_item]

        async def success_call(tool_name, arguments):
            return result_mock

        conn.session.call_tool = success_call

        import asyncio

        async def run():
            result = await conn.call_tool("my_tool", {"key": "val"})
            assert result == "Hello World"

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_call_tool_non_text_content(self, mock_mcp_sdk, monkeypatch):
        """call_tool handles content items without .text attribute."""
        import mcp_manager

        conn = mcp_manager._MCPServerConn("test", {"command": "echo"})
        conn.session = MagicMock()

        result_mock = MagicMock()
        raw_item = MagicMock()
        del raw_item.text  # no .text attribute
        result_mock.content = [42]  # non-MagicMock without .text

        async def success_call(tool_name, arguments):
            return result_mock

        conn.session.call_tool = success_call

        import asyncio

        async def run():
            result = await conn.call_tool("my_tool", {})
            assert "42" in result  # str() fallback

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_disconnect_clears_state(self, mock_mcp_sdk, monkeypatch):
        """disconnect() clears session and tools."""
        import mcp_manager

        conn = mcp_manager._MCPServerConn("test", {"command": "echo"})
        conn.session = MagicMock()
        conn.tools = [MagicMock(), MagicMock()]
        conn._session_ctx = MagicMock()
        conn._stdio_ctx = MagicMock()

        # Mock the async context manager exits
        async def fake_aexit(*args):
            pass
        conn._session_ctx.__aexit__ = fake_aexit
        conn._stdio_ctx.__aexit__ = fake_aexit

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(conn.disconnect())
        finally:
            loop.close()

        assert conn.session is None
        assert conn.tools == []
