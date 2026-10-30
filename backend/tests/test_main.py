"""Tests for main.py — FastAPI endpoints.

All external dependencies (agent_stream, mcp_manager, session_db,
workspace_manager, integrations_manager, skills_manager) are monkeypatched
BEFORE ``main`` is imported, so module-level ``from X import Y`` statements
capture the mocked versions. No real I/O, subprocesses, or network calls.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════
# Mock classes
# ═══════════════════════════════════════════════════════════════

class MockWorkspace:
    """Mimics MiniAgent's workspace attribute."""

    def __init__(self, root: str):
        self.repo_root = root
        self.cwd = root
        self.branch = "main"
        self.status = "clean"


class MockModelClient:
    """Mimics MiniAgent's model_client attribute."""

    model = "deepseek-v4-flash"

    @staticmethod
    def complete(prompt: str, max_new_tokens: int = 1024, images=None) -> str:
        return "<final>Mock response</final>"


class MockAgent:
    """Controllable mock for what main.py reads from the agent."""

    def __init__(self, root: str = "/tmp/test-workspace"):
        self.workspace = MockWorkspace(root)
        self.model_client = MockModelClient()
        self.session = {
            "id": "agent-session-001",
            "history": [],
            "memory": {"task": "", "files": [], "notes": []},
        }
        self.session_path = Path("/tmp/test-session.json")
        self.approval_policy = "auto"
        self.max_steps = 10

    def reset(self):
        self.session["history"] = []
        self.session["memory"] = {"task": "", "files": [], "notes": []}


def _make_mock_session(session_id, workspace, model="deepseek-v4-flash", provider="deepseek"):
    """Build a dict matching the session DB row shape."""
    return {
        "id": session_id,
        "name": Path(workspace).name if workspace else "test",
        "workspace": workspace,
        "model": model,
        "provider": provider,
        "last_message": "",
        "message_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "miniagent_session_id": "miniagent-001",
    }


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_agent():
    """Fresh MockAgent per test."""
    return MockAgent()


@pytest.fixture
def mock_mcp_mgr():
    """Mock MCP manager that reports unavailable."""
    mcp = MagicMock()
    mcp.is_available = False
    mcp.get_all_mcp_tools.return_value = {}
    return mcp


@pytest.fixture
def client(monkeypatch, mock_agent, mock_mcp_mgr, tmp_path):
    """FastAPI TestClient with all external dependencies patched.

    Patches are applied BEFORE importing ``main`` so module-level
    imports see the mocked versions.  After import, globals are
    reset so the lifespan starts with a clean slate.
    """
    # -- agent_stream --
    monkeypatch.setattr(
        "agent_stream.create_agent",
        lambda **kw: mock_agent,
    )
    monkeypatch.setattr(
        "agent_stream.ask_stream",
        lambda agent, msg, images=None: [
            {"type": "start", "data": {"max_steps": 6}},
            {"type": "model_response", "data": {"raw": "<final>ok</final>"}},
            {"type": "final", "data": {"content": "Mock final answer"}},
        ],
    )
    monkeypatch.setattr(
        "agent_stream.clip",
        lambda text, limit=1000: str(text)[:limit],
    )
    monkeypatch.setattr(
        "agent_stream.list_available_models",
        lambda: [
            {"name": "deepseek-v4-flash", "provider": "deepseek",
             "provider_label": "DeepSeek", "tier": "deep",
             "context_limit": 131072, "size": "-", "modified": "-"},
        ],
    )
    monkeypatch.setattr(
        "agent_stream.switch_model",
        lambda agent, name, **kw: None,
    )

    # -- mcp_manager --
    monkeypatch.setattr("mcp_manager.get_mcp_manager", lambda: mock_mcp_mgr)
    monkeypatch.setattr("mcp_manager.MCP_AVAILABLE", False)

    # -- workspace_manager --
    monkeypatch.setattr(
        "workspace_manager.get_workspace_root",
        lambda: str(tmp_path),
    )
    def _mock_set_workspace_root(path):
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")
        return str(resolved)

    monkeypatch.setattr(
        "workspace_manager.set_workspace_root",
        _mock_set_workspace_root,
    )

    # -- session_db --
    monkeypatch.setattr("session_db.init_db", lambda: None)

    _sessions_store: dict[str, dict] = {}

    def _mock_list_sessions(limit=50):
        return list(_sessions_store.values())[:limit]

    def _mock_create_session(**kw):
        sid = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        record = _make_mock_session(
            sid,
            kw.get("workspace", str(tmp_path)),
            kw.get("model", "deepseek-v4-flash"),
            kw.get("provider", "deepseek"),
        )
        record["name"] = kw.get("name", Path(record["workspace"]).name)
        _sessions_store[sid] = record
        return dict(record)

    def _mock_get_session(sid):
        return _sessions_store.get(sid)

    monkeypatch.setattr("session_db.list_sessions", _mock_list_sessions)
    monkeypatch.setattr("session_db.create_session", _mock_create_session)
    monkeypatch.setattr("session_db.get_session", _mock_get_session)
    monkeypatch.setattr("session_db.update_session",
                        lambda *a, **kw: None)
    monkeypatch.setattr("session_db.delete_session",
                        lambda sid: _sessions_store.pop(sid, None))
    monkeypatch.setattr("session_db._get_connection",
                        lambda: MagicMock())

    # -- integrations_manager --
    monkeypatch.setattr("integrations_manager.get_catalog", lambda: [
        {
            "server_name": "playwright",
            "display_name": "Playwright Browser",
            "description": "Browser automation",
            "tools_description": "navigate, click, snapshot",
            "command": "npx",
            "default_args": ["@playwright/mcp@latest"],
            "config_fields": [],
        },
        {
            "server_name": "github",
            "display_name": "GitHub",
            "description": "Repositories, pull requests, issues",
            "tools_description": "create_pr, list_issues, review_code",
            "command": "npx",
            "default_args": ["-y", "@modelcontextprotocol/server-github"],
            "config_fields": [
                {"name": "GITHUB_PERSONAL_ACCESS_TOKEN", "label": "GitHub Token",
                 "type": "api_key", "env_var": "GITHUB_PERSONAL_ACCESS_TOKEN",
                 "required": True, "placeholder": "ghp_..."},
            ],
        },
    ])

    _catalog_items = {
        "playwright": {
            "server_name": "playwright", "display_name": "Playwright Browser",
            "description": "Browser automation",
            "tools_description": "navigate, click, snapshot",
            "command": "npx",
            "default_args": ["@playwright/mcp@latest"],
            "config_fields": [],
        },
        "github": {
            "server_name": "github", "display_name": "GitHub",
            "description": "Repositories, pull requests, issues",
            "tools_description": "create_pr, list_issues, review_code",
            "command": "npx",
            "default_args": ["-y", "@modelcontextprotocol/server-github"],
            "config_fields": [
                {"name": "GITHUB_PERSONAL_ACCESS_TOKEN", "label": "GitHub Token",
                 "type": "api_key", "env_var": "GITHUB_PERSONAL_ACCESS_TOKEN",
                 "required": True, "placeholder": "ghp_..."},
            ],
        },
    }

    monkeypatch.setattr(
        "integrations_manager.get_catalog_item",
        lambda name: _catalog_items.get(name),
    )
    monkeypatch.setattr("integrations_manager.init_integrations_table",
                        lambda conn: None)
    monkeypatch.setattr("integrations_manager.get_env_key",
                        lambda key: "")
    monkeypatch.setattr("integrations_manager.set_env_key",
                        lambda key, val: val)
    monkeypatch.setattr("integrations_manager.get_integrations",
                        lambda conn: [])
    monkeypatch.setattr("integrations_manager.get_integration",
                        lambda conn, name: None)

    _mock_int_mgr_instance = MagicMock()
    _mock_int_mgr_instance.enable.return_value = {
        "server": "playwright", "status": "connected", "tools": [], "config": {},
    }
    _mock_int_mgr_instance.disable.return_value = {
        "server": "playwright", "status": "disabled",
    }
    _mock_int_mgr_instance.configure.return_value = {
        "server": "playwright", "status": "configured", "config": {},
    }
    _mock_int_mgr_instance.start_configured.return_value = []
    _mock_int_mgr_instance.get_connection_status.return_value = []
    _mock_int_mgr_instance.stop_all.return_value = None
    monkeypatch.setattr(
        "integrations_manager.IntegrationsManager",
        lambda mcp: _mock_int_mgr_instance,
    )

    # -- skills_manager --
    monkeypatch.setattr(
        "skills_manager.get_skills_catalog",
        lambda: [{"name": "debug", "description": "Debug skill",
                  "enabled": False}],
    )
    monkeypatch.setattr(
        "skills_manager.get_skills_status",
        lambda conn: [{"name": "debug", "description": "Debug skill",
                       "enabled": False}],
    )
    monkeypatch.setattr("skills_manager.set_skill_enabled",
                        lambda conn, name, enabled: None)
    monkeypatch.setattr("skills_manager.get_active_skill_prompts",
                        lambda conn: [])
    monkeypatch.setattr("skills_manager.init_skills_table",
                        lambda conn: None)

    # Disable auth middleware for tests
    monkeypatch.setenv("KODAMA_NO_AUTH", "1")

    # ── Import main AFTER patches ──────────────────────────────
    import main

    # Bind the mocks on ``main`` explicitly: if another module imported it
    # during collection, its module-level ``from agent_stream import ...``
    # names point at the real implementations and the patches above never
    # reach them (that made the chat tests hit the network and flake).
    _mock_events = [
        {"type": "start", "data": {"max_steps": 6}},
        {"type": "model_response", "data": {"raw": "<final>ok</final>"}},
        {"type": "final", "data": {"content": "Mock final answer"}},
    ]
    monkeypatch.setattr(main, "create_agent", lambda **kw: mock_agent)
    monkeypatch.setattr(
        main, "ask_stream",
        lambda agent, msg, images=None: list(_mock_events),
    )

    # Reset module-level globals so the lifespan starts clean
    main.agent = None
    main.current_session_id = None
    main.mcp_status = []
    main.integrations_mgr = None
    main._integrations_conn = None

    with TestClient(main.app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════
# Status endpoint
# ═══════════════════════════════════════════════════════════════

class TestStatus:
    """GET /api/status"""

    def test_status_returns_expected_fields(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "workspace" in data
        assert "model" in data
        assert "provider" in data
        assert "branch" in data
        assert "mcp_available" in data
        assert "max_steps" in data
        assert data["provider"] in ("ollama", "deepseek")
        assert data["mcp_available"] is False

    def test_status_model(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert data["model"] == "deepseek-v4-flash"


# ═══════════════════════════════════════════════════════════════
# Chat endpoint (SSE streaming)
# ═══════════════════════════════════════════════════════════════

class TestChat:
    """POST /api/chat — SSE streaming"""

    def test_chat_returns_sse(self, client):
        resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert "data: " in resp.text
        assert "data: [DONE]" in resp.text

    def test_chat_event_types(self, client):
        resp = client.post("/api/chat", json={"message": "test"})
        events = []
        for line in resp.text.strip().split("\n"):
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[6:])["type"])
        assert "start" in events
        assert "final" in events

    def test_chat_empty_message(self, client):
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 200
        assert "[DONE]" in resp.text

    def test_chat_special_chars(self, client):
        resp = client.post("/api/chat",
                           json={"message": "Hello! ¿Cómo estás? <>&\""})
        assert resp.status_code == 200
        assert "[DONE]" in resp.text

    def test_chat_rejects_concurrent_request(self, client):
        """Un segundo chat mientras hay uno activo devuelve 409, no corrompe."""
        import main
        assert main._chat_lock.acquire(blocking=False)
        try:
            resp = client.post("/api/chat", json={"message": "Hello"})
            assert resp.status_code == 409
        finally:
            main._chat_lock.release()

    def test_chat_releases_lock_when_done(self, client):
        import time
        import main
        resp = client.post("/api/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        # The lock is released by the worker thread; on a slow runner that
        # happens a few milliseconds after the response is consumed.
        deadline = time.monotonic() + 5
        while main._chat_lock.locked() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert main._chat_lock.locked() is False

    def test_workspace_set_rejected_while_chatting(self, client, tmp_path):
        import main
        assert main._chat_lock.acquire(blocking=False)
        try:
            resp = client.post("/api/workspace/set", json={"path": str(tmp_path)})
            assert resp.status_code == 409
        finally:
            main._chat_lock.release()


# ═══════════════════════════════════════════════════════════════
# Reset endpoint
# ═══════════════════════════════════════════════════════════════

class TestApprove:
    """POST /api/approve — aprobación de herramientas riesgosas"""

    def test_approve_without_pending_returns_409(self, client):
        import main
        main._approval["pending"] = False
        resp = client.post("/api/approve", json={"approved": True})
        assert resp.status_code == 409

    def test_approve_sets_decision_and_unblocks(self, client):
        import main
        main._approval["pending"] = True
        main._approval["approved"] = False
        main._approval["event"].clear()
        try:
            resp = client.post("/api/approve", json={"approved": True})
            assert resp.status_code == 200
            assert main._approval["approved"] is True
            assert main._approval["event"].is_set() is True
        finally:
            main._approval["pending"] = False
            main._approval["event"].clear()

    def test_programming_profile_controls_approval(self, client, monkeypatch):
        import main

        class _Conn:
            def close(self):
                pass

        monkeypatch.setattr(main, "_get_iconn", lambda: _Conn())
        monkeypatch.setattr(main, "get_enabled_skill_names", lambda conn: [])
        assert main._programming_enabled() is False
        monkeypatch.setattr(main, "get_enabled_skill_names", lambda conn: ["programming"])
        assert main._programming_enabled() is True


class TestApprovalDiff:
    """_approval_diff — vista previa del cambio antes de aprobar"""

    def _agent(self, root):
        class _Agent:
            def __init__(self, r):
                self.root = r

            def path(self, p):
                return (self.root / p).resolve()

        return _Agent(root)

    def test_new_file_shows_additions(self, tmp_path):
        import main
        diff = main._approval_diff(self._agent(tmp_path), "write_file",
                                   {"path": "a.txt", "content": "hola"})
        assert "+hola" in diff

    def test_overwrite_shows_both_sides(self, tmp_path):
        import main
        (tmp_path / "a.txt").write_text("viejo\n", encoding="utf-8")
        diff = main._approval_diff(self._agent(tmp_path), "write_file",
                                   {"path": "a.txt", "content": "nuevo"})
        assert "-viejo" in diff and "+nuevo" in diff

    def test_patch_missing_text_is_reported(self, tmp_path):
        import main
        (tmp_path / "a.txt").write_text("uno\n", encoding="utf-8")
        diff = main._approval_diff(
            self._agent(tmp_path), "patch_file",
            {"path": "a.txt", "old_text": "no-existe", "new_text": "x"},
        )
        assert "no está" in diff

    def test_run_shell_shows_the_command(self):
        import main
        assert main._approval_diff(None, "run_shell", {"command": "ls"}) == "$ ls"

    def test_outside_root_has_no_diff(self):
        import main

        class _Agent:
            def path(self, p):
                raise ValueError("escape")

        assert main._approval_diff(_Agent(), "write_file",
                                   {"path": "../x", "content": "y"}) == ""


class TestReset:
    """POST /api/reset"""

    def test_reset_returns_ok(self, client):
        resp = client.post("/api/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# Workspace endpoints
# ═══════════════════════════════════════════════════════════════

class TestWorkspace:
    """GET /api/workspace, POST /api/workspace/set,
    GET /api/workspace/files, GET /api/workspace/read"""

    def test_get_workspace(self, client):
        resp = client.get("/api/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert "root" in data
        assert "cwd" in data
        assert "branch" in data
        assert "status" in data

    def test_set_workspace_valid(self, client, tmp_path):
        resp = client.post("/api/workspace/set",
                           json={"path": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_set_workspace_nonexistent(self, client):
        resp = client.post("/api/workspace/set",
                           json={"path": "/nonexistent/path"})
        assert resp.status_code == 400

    def test_list_files(self, client, tmp_path):
        (tmp_path / "file1.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested",
                                                         encoding="utf-8")
        # Point agent workspace to tmp_path
        import main
        main.agent.workspace.repo_root = str(tmp_path)

        resp = client.get("/api/workspace/files?path=.")
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()["entries"]]
        assert "file1.txt" in names
        assert "subdir" in names

    def test_list_files_nested(self, client, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested",
                                                         encoding="utf-8")
        import main
        main.agent.workspace.repo_root = str(tmp_path)

        resp = client.get("/api/workspace/files?path=subdir")
        names = [e["name"] for e in resp.json()["entries"]]
        assert "nested.txt" in names

    def test_list_files_nonexistent(self, client):
        resp = client.get("/api/workspace/files?path=nonexistent")
        assert resp.status_code == 404

    def test_read_file(self, client, tmp_path):
        (tmp_path / "hello.txt").write_text("Hello World!", encoding="utf-8")
        import main
        main.agent.workspace.repo_root = str(tmp_path)

        resp = client.get("/api/workspace/read?path=hello.txt")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Hello World!"

    def test_read_file_nonexistent(self, client):
        resp = client.get("/api/workspace/read?path=nonexistent.txt")
        assert resp.status_code == 404

    def test_read_file_path_traversal(self, client):
        resp = client.get("/api/workspace/read?path=../outside.txt")
        assert resp.status_code in (403, 404)

    def test_read_file_rejects_sibling_prefix(self, client, tmp_path):
        """Una carpeta vecina con el mismo prefijo no pertenece al workspace."""
        workspace = tmp_path / "proyecto"
        sibling = tmp_path / "proyecto-evil"
        workspace.mkdir()
        sibling.mkdir()
        (sibling / "secreto.txt").write_text("NO-DEBE-LEERSE", encoding="utf-8")
        import main
        main.agent.workspace.repo_root = str(workspace)

        resp = client.get("/api/workspace/read?path=../proyecto-evil/secreto.txt")
        assert resp.status_code == 403

    def test_list_files_rejects_sibling_prefix(self, client, tmp_path):
        workspace = tmp_path / "proyecto"
        sibling = tmp_path / "proyecto-evil"
        workspace.mkdir()
        sibling.mkdir()
        (sibling / "secreto.txt").write_text("NO-DEBE-LEERSE", encoding="utf-8")
        import main
        main.agent.workspace.repo_root = str(workspace)

        resp = client.get("/api/workspace/files?path=../proyecto-evil")
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# Session endpoints
# ═══════════════════════════════════════════════════════════════

class TestSessions:
    """CRUD /api/sessions/*"""

    def test_list_sessions(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert "sessions" in resp.json()

    def test_create_session(self, client):
        resp = client.post("/api/sessions", json={
            "name": "Test Session", "workspace": "/tmp/test-ws",
        })
        assert resp.status_code == 200
        assert resp.json()["session"]["name"] == "Test Session"

    def test_create_session_defaults(self, client):
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 200
        assert resp.json()["session"]["id"] is not None

    def test_delete_session(self, client):
        created = client.post("/api/sessions",
                              json={"name": "To Delete"}).json()
        sid = created["session"]["id"]
        resp = client.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_switch_session_nonexistent(self, client):
        resp = client.post("/api/sessions/nonexistent/switch")
        assert resp.status_code == 404

    def test_switch_session_valid(self, client, tmp_path):
        created = client.post("/api/sessions", json={
            "name": "Switch Test", "workspace": str(tmp_path),
        }).json()
        sid = created["session"]["id"]

        # Re-patch get_session to find the session just created
        import session_db as sdb
        original_get = sdb.get_session
        sdb.get_session = lambda sid_arg: (
            created["session"] if sid_arg == sid else None
        )

        resp = client.post(f"/api/sessions/{sid}/switch")
        sdb.get_session = original_get  # restore
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════
# Models endpoints
# ═══════════════════════════════════════════════════════════════

class TestModels:
    """GET /api/models, POST /api/models/select"""

    def test_list_models(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        models = resp.json()["models"]
        assert len(models) >= 1
        assert models[0]["name"] == "deepseek-v4-flash"

    def test_select_model(self, client):
        resp = client.post("/api/models/select", json={"name": "new-model"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "new-model"


# ═══════════════════════════════════════════════════════════════
# MCP endpoints
# ═══════════════════════════════════════════════════════════════

class TestMCP:
    """GET /api/mcp/status, POST /api/mcp/reconnect"""

    def test_mcp_status(self, client):
        resp = client.get("/api/mcp/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert "servers" in data

    def test_mcp_reconnect_not_available(self, client):
        resp = client.post("/api/mcp/reconnect")
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Integrations endpoints
# ═══════════════════════════════════════════════════════════════

class TestIntegrations:
    """GET /api/integrations/catalog, GET /api/integrations,
    POST /api/integrations/enable|disable|configure"""

    def test_catalog(self, client):
        resp = client.get("/api/integrations/catalog")
        assert resp.status_code == 200
        assert len(resp.json()["catalog"]) >= 1

    def test_list_integrations(self, client):
        resp = client.get("/api/integrations")
        assert resp.status_code == 200
        assert "integrations" in resp.json()

    def test_enable_nonexistent(self, client):
        resp = client.post("/api/integrations/enable",
                           json={"server_name": "ghost"})
        assert resp.status_code == 404

    def test_enable_missing_required(self, client):
        """github requires GITHUB_PERSONAL_ACCESS_TOKEN."""
        resp = client.post("/api/integrations/enable",
                           json={"server_name": "github"})
        assert resp.status_code == 400

    def test_enable_no_config(self, client):
        resp = client.post("/api/integrations/enable",
                           json={"server_name": "playwright"})
        assert resp.status_code == 200

    def test_disable(self, client):
        resp = client.post("/api/integrations/disable",
                           json={"server_name": "playwright"})
        assert resp.status_code == 200

    def test_configure(self, client):
        resp = client.post("/api/integrations/configure",
                           json={"server_name": "playwright",
                                 "config": {"key": "val"}})
        assert resp.status_code == 200

    def test_configure_nonexistent(self, client):
        resp = client.post("/api/integrations/configure",
                           json={"server_name": "ghost",
                                 "config": {}})
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Skills endpoints
# ═══════════════════════════════════════════════════════════════

class TestSkills:
    """GET /api/skills, POST /api/skills/toggle"""

    def test_list_skills(self, client):
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        assert "skills" in resp.json()

    def test_toggle_skill(self, client):
        resp = client.post("/api/skills/toggle", json={"name": "debug"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_toggle_nonexistent(self, client):
        resp = client.post("/api/skills/toggle",
                           json={"name": "ghost-skill"})
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Session / Memory info endpoints
# ═══════════════════════════════════════════════════════════════

class TestInfo:
    """GET /api/session, GET /api/memory"""

    def test_current_session(self, client):
        resp = client.get("/api/session")
        assert resp.status_code == 200
        assert resp.json()["id"] == "agent-session-001"

    def test_memory(self, client):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


# ═══════════════════════════════════════════════════════════════
# 404 handling
# ═══════════════════════════════════════════════════════════════

class Test404:
    def test_nonexistent_route(self, client):
        resp = client.get("/api/nonexistent-route")
        assert resp.status_code == 404
