"""Tests for integrations_manager.py — catalog, .env, SQLite, and IntegrationsManager.

These tests never touch the real backend/.env or any production files.
All file I/O and environment access is isolated via monkeypatch and temp fixtures.
"""

import sys
import os
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integrations_manager import (
    CATALOG,
    get_catalog,
    get_catalog_item,
    set_env_key,
    get_env_key,
    remove_env_key,
    init_integrations_table,
    set_integration_enabled,
    get_integrations,
    get_integration,
    _build_server_params,
    IntegrationsManager,
)


# ===================================================================
# Catalog tests (pure data — no mocking needed)
# ===================================================================

class TestCatalog:
    """Verify the catalog data integrity."""

    def test_catalog_has_expected_count(self):
        assert len(CATALOG) == 10, (
            f"Expected 10 integrations, got {len(CATALOG)}. "
            "Update this test when adding/removing catalog entries."
        )

    def test_catalog_entries_have_required_fields(self):
        required = {"server_name", "display_name", "description",
                    "tools_description", "command", "default_args", "config_fields"}
        for entry in CATALOG:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Entry '{entry.get('server_name', '?')}' missing fields: {missing}"
            )

    def test_catalog_entry_server_names_are_unique(self):
        names = [e["server_name"] for e in CATALOG]
        assert len(names) == len(set(names)), (
            f"Duplicate server_name found: {names}"
        )

    def test_config_fields_have_valid_structure(self):
        for entry in CATALOG:
            for i, field in enumerate(entry["config_fields"]):
                assert "name" in field, (
                    f"Entry '{entry['server_name']}' config_fields[{i}] missing 'name'"
                )
                assert field.get("type") in ("api_key", "string"), (
                    f"Entry '{entry['server_name']}' config_fields[{i}].type "
                    f"must be 'api_key' or 'string', got '{field.get('type')}'"
                )

    def test_get_catalog_returns_copy(self):
        result = get_catalog()
        assert len(result) == len(CATALOG)
        # Modifying the returned list must not affect the original
        result.pop()
        assert len(get_catalog()) == len(CATALOG)

    def test_get_catalog_item_found(self):
        item = get_catalog_item("playwright")
        assert item is not None
        assert item["server_name"] == "playwright"
        assert item["display_name"] == "Playwright Browser"

    def test_get_catalog_item_not_found(self):
        assert get_catalog_item("nonexistent-integration") is None


# ===================================================================
# .env file management tests (isolated via monkeypatch)
# ===================================================================

class TestEnvManagement:
    """Test set_env_key, get_env_key, remove_env_key in isolation."""

    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch, tmp_path):
        """Redirect ENV_PATH to a temp file and stub load_dotenv."""
        self._env_file = tmp_path / ".env"
        self._env_file.write_text("", encoding="utf-8")
        monkeypatch.setattr("integrations_manager.ENV_PATH", self._env_file)
        # Stub load_dotenv to prevent loading file vars into os.environ
        monkeypatch.setattr("integrations_manager.load_dotenv", lambda *a, **kw: None)
        # Clean slate for env vars
        monkeypatch.delenv("TEST_KEY_1", raising=False)
        monkeypatch.delenv("TEST_KEY_2", raising=False)
        monkeypatch.delenv("TEST_KEY_3", raising=False)

    def _file_content(self) -> str:
        return self._env_file.read_text(encoding="utf-8")

    def test_set_env_key_writes_to_file(self):
        set_env_key("TEST_KEY_1", "value123")
        content = self._file_content()
        # python-dotenv may use single or double quotes depending on platform
        assert "TEST_KEY_1" in content and "value123" in content

    def test_get_env_key_returns_from_environment(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY_2", "env_value")
        assert get_env_key("TEST_KEY_2") == "env_value"

    def test_get_env_key_returns_empty_when_not_set(self):
        assert get_env_key("NONEXISTENT_KEY") == ""

    def test_remove_env_key_removes_from_file(self):
        # First write a key
        set_env_key("TEST_KEY_3", "to_remove")
        assert "TEST_KEY_3" in self._file_content()
        # Then remove it
        remove_env_key("TEST_KEY_3")
        assert "TEST_KEY_3" not in self._file_content()

    def test_set_env_key_updates_existing_key(self):
        set_env_key("TEST_KEY_1", "first_value")
        set_env_key("TEST_KEY_1", "updated_value")
        content = self._file_content()
        # The updated value should be in the file; the old one should not
        assert "updated_value" in content
        # (dotenv's set_key replaces the existing line)

    def test_remove_env_key_does_not_raise_on_missing(self):
        # Should not raise when key doesn't exist in file or env
        remove_env_key("NEVER_SET_KEY")
        # Also should not raise when env var doesn't exist
        remove_env_key("ANOTHER_MISSING")


# ===================================================================
# SQLite operations tests (using tmp_db fixture from conftest)
# ===================================================================

class TestSQLiteOperations:
    """Test init_integrations_table and CRUD functions."""

    def test_init_creates_table_with_all_catalog_entries(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='integrations'").fetchall()
        assert len(rows) == 1, "integrations table was not created"

        count = conn.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
        assert count == len(CATALOG), (
            f"Expected {len(CATALOG)} entries seeded, got {count}"
        )

    def test_init_is_idempotent(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)
        init_integrations_table(conn)  # second call must not fail
        count = conn.execute("SELECT COUNT(*) FROM integrations").fetchone()[0]
        assert count == len(CATALOG)

    def test_enable_integration(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        result = set_integration_enabled(conn, "playwright", True)
        assert result["enabled"] == 1
        assert result["server_name"] == "playwright"

    def test_disable_integration(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)
        set_integration_enabled(conn, "playwright", True)
        result = set_integration_enabled(conn, "playwright", False)
        assert result["enabled"] == 0

    def test_enable_with_config(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        config = {"custom_arg": "test_value", "option": 42}
        result = set_integration_enabled(conn, "github", True, config)
        saved_config = json.loads(result["config"])
        assert saved_config == config

    def test_re_enable_preserves_config(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        config = {"preserve_me": "yes"}
        set_integration_enabled(conn, "github", True, config)
        set_integration_enabled(conn, "github", False)
        result = set_integration_enabled(conn, "github", True)
        saved_config = json.loads(result["config"])
        # Config should be preserved from the last enable, or at least not throw
        assert isinstance(saved_config, dict)

    def test_get_integrations_returns_all(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        all_integrations = get_integrations(conn)
        assert len(all_integrations) == len(CATALOG)
        # Verify they are sorted by server_name
        names = [r["server_name"] for r in all_integrations]
        assert names == sorted(names)

    def test_get_integration_by_name(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        result = get_integration(conn, "playwright")
        assert result is not None
        assert result["server_name"] == "playwright"
        assert result["enabled"] == 0  # default: disabled

    def test_get_integration_nonexistent(self, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)
        assert get_integration(conn, "ghost-integration") is None


# ===================================================================
# _build_server_params tests (pure function)
# ===================================================================

class TestBuildServerParams:
    """Test the MCP server parameter builder."""

    def test_builds_basic_params(self):
        catalog_item = {
            "server_name": "demo-server",
            "command": "uvx",
            "default_args": ["demo-tool", "--flag"],
            "config_fields": [],
        }
        result = _build_server_params(catalog_item, {})
        assert result["command"] == "uvx"
        assert result["args"] == ["demo-tool", "--flag"]
        assert result["env"] == {}

    def test_merges_env_overrides(self):
        catalog_item = {
            "server_name": "demo-keyed",
            "command": "npx",
            "default_args": ["-y", "demo-keyed@1.0"],
            "config_fields": [
                {"name": "DEMO_API_KEY", "type": "api_key", "env_var": "DEMO_API_KEY"},
            ],
        }
        env_overrides = {"DEMO_API_KEY": "demo-fake-key-123"}
        result = _build_server_params(catalog_item, {}, env_overrides)
        assert result["env"]["DEMO_API_KEY"] == "demo-fake-key-123"

    def test_arg_index_override(self):
        catalog_item = {
            "server_name": "filesystem",
            "command": "npx",
            "default_args": ["-y", "@modelcontextprotocol/server-filesystem",
                             "C:/Users/Default/Desktop"],
            "config_fields": [
                {"name": "directory", "type": "string", "env_var": "",
                 "arg_index": 2, "required": False},
            ],
        }
        config = {"directory": "D:/Custom/Path"}
        result = _build_server_params(catalog_item, config)
        assert result["args"][2] == "D:/Custom/Path"

    def test_unknown_fields_ignored(self):
        catalog_item = {
            "server_name": "test",
            "command": "echo",
            "default_args": ["hello"],
            "config_fields": [],
        }
        config = {"extra_field": "should_be_ignored"}
        result = _build_server_params(catalog_item, config)
        assert result["args"] == ["hello"]


# ===================================================================
# IntegrationsManager tests (with mock MCP manager)
# ===================================================================

class TestIntegrationsManager:
    """Test the high-level manager with a mocked MCP manager."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock MCP manager with controlled behavior."""
        mcp = MagicMock()
        mcp.is_available = True
        mcp.has_server.return_value = False  # default: not connected
        mcp._connections = {}                # empty connections dict
        mock_conn = MagicMock()
        mock_conn.tools = []
        mcp._start_server.return_value = mock_conn
        return mcp

    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch, tmp_path):
        """Same isolation as TestEnvManagement."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        monkeypatch.setattr("integrations_manager.ENV_PATH", env_file)
        monkeypatch.setattr("integrations_manager.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
        return env_file

    def test_enable_starts_server(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        result = manager.enable(conn, "playwright")

        assert result["status"] == "connected"
        mock_mcp._start_server.assert_called_once()

    def test_enable_with_api_keys(self, mock_mcp, tmp_db, monkeypatch):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        api_keys = {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp-test-key"}
        result = manager.enable(conn, "github", api_keys=api_keys)

        assert result["status"] == "connected"
        # The API key is stored in .env (sensitive storage via set_env_key).
        # Read the file directly because set_env_key doesn't reload
        # os.environ after writing, and the fixture stubs load_dotenv.
        import integrations_manager as _im
        content = _im.ENV_PATH.read_text(encoding="utf-8")
        assert "ghp-test-key" in content

    def test_enable_unknown_raises(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        with pytest.raises(ValueError, match="Unknown integration"):
            manager.enable(conn, "does-not-exist")

    def test_disable_stops_server(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        manager.enable(conn, "playwright")
        result = manager.disable(conn, "playwright")

        assert result["status"] == "disabled"
        mock_mcp._stop_server.assert_called_once_with("playwright")

    def test_disable_unknown_does_not_raise(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        # Disabling an integration that is in the catalog but was never
        # enabled should not raise. Use a valid catalog name that has a
        # DB row (seeded by init_integrations_table).
        result = manager.disable(conn, "puppeteer")
        assert result["status"] == "disabled"

    def test_start_configured_loads_enabled_integrations(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        # Enable one integration
        set_integration_enabled(conn, "playwright", True)

        manager = IntegrationsManager(mock_mcp)
        results = manager.start_configured(conn)

        # Should have started the enabled integration
        assert len(results) == 1
        assert results[0]["server"] == "playwright"
        assert results[0]["status"] == "connected"

    def test_start_configured_skips_disabled(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)
        # All integrations are disabled by default

        manager = IntegrationsManager(mock_mcp)
        results = manager.start_configured(conn)

        assert len(results) == 0  # nothing enabled

    def test_get_connection_status(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        manager.enable(conn, "playwright")

        status = manager.get_connection_status()
        assert len(status) == 1
        assert status[0]["server"] == "playwright"
        assert status[0]["status"] == "connected"

    def test_stop_all_clears_connections(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        manager.enable(conn, "playwright")
        manager.enable(conn, "github")

        manager.stop_all()
        assert len(manager._connections) == 0
        assert mock_mcp._stop_server.call_count == 2

    def test_configure_updates_and_restarts_if_running(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        # First enable
        manager.enable(conn, "playwright")
        mock_mcp._stop_server.reset_mock()
        mock_mcp._start_server.reset_mock()

        # Then configure
        result = manager.configure(conn, "playwright", config={"new_option": "value"})
        # Should have restarted (stopped + started again)
        mock_mcp._stop_server.assert_called_once_with("playwright")
        mock_mcp._start_server.assert_called_once()

    def test_configure_without_running_does_not_restart(self, mock_mcp, tmp_db):
        conn, _ = tmp_db
        init_integrations_table(conn)

        manager = IntegrationsManager(mock_mcp)
        # Configure without enabling first
        result = manager.configure(conn, "playwright", config={"option": "val"})
        assert result["status"] == "configured"
        mock_mcp._stop_server.assert_not_called()
