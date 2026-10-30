"""Tests for session_db.py — SQLite session CRUD operations.

These are integration-light tests: they use a real SQLite file in a temp
directory (monkeypatched so session_db writes there instead of .kodama/).
"""

import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from session_db import (
    init_db,
    create_session,
    get_session,
    list_sessions,
    update_session,
    delete_session,
)


@pytest.fixture(autouse=True)
def _patch_db_path(monkeypatch):
    """Redirect session_db's DB_DIR to a temporary directory.

    This ensures tests never touch the real .kodama/sessions.db.
    """
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("session_db.DB_DIR", Path(tmp))
    monkeypatch.setattr("session_db.DB_PATH", Path(tmp) / "sessions.db")
    init_db()
    yield
    # Cleanup
    for f in Path(tmp).iterdir():
        try:
            os.unlink(f)
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════
# Session CRUD
# ═══════════════════════════════════════════════════════════════

class TestCreateSession:
    """create_session() inserts a row and returns it with an id."""

    def test_creates_with_minimal_fields(self):
        session = create_session(name="test", workspace="/tmp/test")
        assert session["id"] is not None
        assert session["name"] == "test"
        assert session["workspace"] == "/tmp/test"
        assert session["message_count"] == 0

    def test_creates_with_all_fields(self):
        session = create_session(
            name="full-test",
            workspace="/tmp/full",
            model="deepseek-v4-flash",
            provider="deepseek",
            miniagent_session_id="mini-001",
        )
        assert session["model"] == "deepseek-v4-flash"
        assert session["provider"] == "deepseek"
        assert session["miniagent_session_id"] == "mini-001"

    def test_id_is_unique(self):
        s1 = create_session(name="a", workspace="/tmp/a")
        s2 = create_session(name="b", workspace="/tmp/b")
        assert s1["id"] != s2["id"]

    def test_name_defaults_to_folder_name(self):
        session = create_session(workspace="/tmp/MiProyecto")
        assert session["name"] == "MiProyecto"


class TestGetSession:
    """get_session() retrieves a session by id."""

    def test_returns_existing_session(self):
        created = create_session(name="get-me", workspace="/tmp/get")
        fetched = get_session(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["name"] == "get-me"

    def test_returns_none_for_missing(self):
        assert get_session("nonexistent-id") is None


class TestListSessions:
    """list_sessions() returns sessions ordered by updated_at desc."""

    def test_returns_most_recent_first(self):
        s1 = create_session(name="older", workspace="/tmp/a")
        s2 = create_session(name="newer", workspace="/tmp/b")
        sessions = list_sessions(limit=10)
        assert len(sessions) >= 2
        # s2 should come first (most recent)
        assert sessions[0]["id"] == s2["id"]

    def test_respects_limit(self):
        for i in range(5):
            create_session(name=f"test-{i}", workspace=f"/tmp/{i}")
        sessions = list_sessions(limit=3)
        assert len(sessions) == 3

    def test_empty_db_returns_empty_list(self):
        sessions = list_sessions(limit=10)
        assert sessions == []


class TestUpdateSession:
    """update_session() updates mutable fields."""

    def test_updates_fields(self):
        created = create_session(name="upd", workspace="/tmp/upd")
        update_session(
            created["id"],
            model="deepseek-v4-pro",
            provider="deepseek",
            last_message="hello",
            message_count=5,
        )
        updated = get_session(created["id"])
        assert updated["model"] == "deepseek-v4-pro"
        assert updated["last_message"] == "hello"
        assert updated["message_count"] == 5

    def test_updates_miniagent_session_id(self):
        created = create_session(name="mini", workspace="/tmp/mini")
        update_session(created["id"], miniagent_session_id="new-mini-id")
        updated = get_session(created["id"])
        assert updated["miniagent_session_id"] == "new-mini-id"

    def test_does_not_affect_other_sessions(self):
        s1 = create_session(name="first", workspace="/tmp/1")
        s2 = create_session(name="second", workspace="/tmp/2")
        update_session(s1["id"], last_message="only first")
        assert get_session(s1["id"])["last_message"] == "only first"
        assert get_session(s2["id"])["last_message"] == ""

    def test_last_message_truncated_to_120_chars(self):
        created = create_session(name="trunc", workspace="/tmp/t")
        long_msg = "x" * 500
        update_session(created["id"], last_message=long_msg)
        updated = get_session(created["id"])
        assert len(updated["last_message"]) == 120


class TestDeleteSession:
    """delete_session() removes a session by id."""

    def test_deletes_existing(self):
        created = create_session(name="del", workspace="/tmp/del")
        delete_session(created["id"])
        assert get_session(created["id"]) is None

    def test_delete_nonexistent_does_not_raise(self):
        delete_session("i-dont-exist")  # should not raise
