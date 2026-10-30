"""SQLite-backed session store for Relay.

Manages session metadata (name, workspace, model, timestamps, last message)
so the UI can list, switch, create, and delete sessions without relying on
the MiniAgent JSON session files for navigation.
"""

"""SQLite-backed session store for Relay.

Manages session metadata (name, workspace, model, timestamps, last message)
so the UI can list, switch, create, and delete sessions without relying on
the MiniAgent JSON session files for navigation.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DB_DIR = Path(__file__).resolve().parent / ".kodama"
DB_PATH = DB_DIR / "sessions.db"


# ── Connection management ──────────────────────────────────────

def _get_connection():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """Context manager: provides a SQLite connection and auto-closes it."""
    conn = _get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ── Schema ─────────────────────────────────────────────────────

def init_db():
    """Create the sessions table and integrations table if they don't exist."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                workspace   TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL DEFAULT '',
                provider    TEXT NOT NULL DEFAULT 'ollama',
                last_message TEXT DEFAULT '',
                message_count INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        # Add miniagent_session_id column if it doesn't exist (migration-safe)
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN miniagent_session_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already exists
        # Seed integrations table (from integrations_manager)
        try:
            from integrations_manager import init_integrations_table
            init_integrations_table(conn)
        except ImportError:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS integrations (
                    server_name TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    config TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
            """)
        # Seed skills table
        try:
            from skills_manager import init_skills_table
            init_skills_table(conn)
        except ImportError:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    name TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0
                )
            """)
        # MCP server health (circuit breaker)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_health (
                server_name         TEXT PRIMARY KEY,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                broken              INTEGER NOT NULL DEFAULT 0,
                last_error          TEXT DEFAULT '',
                last_attempt        TEXT DEFAULT ''
            )
        """)
        conn.commit()


# ── CRUD ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_session(workspace="", model="", provider="ollama", name=None, miniagent_session_id=""):
    """Insert a new session and return its full record."""
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    now = _now()
    if not name:
        folder = Path(workspace).name if workspace else "Nueva sesión"
        name = folder
    with _conn() as conn:
        conn.execute(
            """INSERT INTO sessions (id, name, workspace, model, provider, created_at, updated_at, miniagent_session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, name, workspace, model, provider, now, now, miniagent_session_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row)


def list_sessions(limit=20):
    """Return sessions ordered by most-recently updated."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_session(session_id):
    """Return a single session or None."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def update_session(session_id, workspace=None, model=None, provider=None,
                   last_message=None, message_count=None, name=None,
                   miniagent_session_id=None):
    """Update mutable fields of a session."""
    now = _now()
    fields = ["updated_at = ?"]
    values = [now]
    if workspace is not None:
        fields.append("workspace = ?")
        values.append(workspace)
    if model is not None:
        fields.append("model = ?")
        values.append(model)
    if provider is not None:
        fields.append("provider = ?")
        values.append(provider)
    if last_message is not None:
        fields.append("last_message = ?")
        values.append(last_message[:120])  # keep it short
    if message_count is not None:
        fields.append("message_count = ?")
        values.append(message_count)
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if miniagent_session_id is not None:
        fields.append("miniagent_session_id = ?")
        values.append(miniagent_session_id)

    values.append(session_id)
    with _conn() as conn:
        conn.execute(
            f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None


def delete_session(session_id):
    """Remove a session by id."""
    with _conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return True


# ── Circuit breaker for MCP servers ─────────────────────────────

MAX_CONSECUTIVE_FAILURES = 5


def mcp_record_failure(server_name: str, error: str = ""):
    """Record a connection failure for an MCP server. Marks as broken after 5 consecutive."""
    with _conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO mcp_health (server_name, consecutive_failures, broken, last_error, last_attempt)
            VALUES (?, 1, 0, ?, ?)
            ON CONFLICT(server_name) DO UPDATE SET
                consecutive_failures = consecutive_failures + 1,
                broken = CASE WHEN consecutive_failures + 1 >= ? THEN 1 ELSE broken END,
                last_error = excluded.last_error,
                last_attempt = excluded.last_attempt
        """, (server_name, error, now, MAX_CONSECUTIVE_FAILURES))
        conn.commit()


def mcp_record_success(server_name: str):
    """Reset failure counter after a successful MCP connection."""
    with _conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO mcp_health (server_name, consecutive_failures, broken, last_error, last_attempt)
            VALUES (?, 0, 0, '', ?)
            ON CONFLICT(server_name) DO UPDATE SET
                consecutive_failures = 0,
                broken = 0,
                last_error = '',
                last_attempt = excluded.last_attempt
        """, (server_name, now))
        conn.commit()


def mcp_is_broken(server_name: str) -> bool:
    """Check if an MCP server is in broken state (circuit breaker open)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT broken FROM mcp_health WHERE server_name = ?", (server_name,)
        ).fetchone()
        return bool(row and row["broken"])


def mcp_reset_server(server_name: str):
    """Manually reset/repair an MCP server (clear broken state)."""
    with _conn() as conn:
        conn.execute("""
            INSERT INTO mcp_health (server_name, consecutive_failures, broken, last_error, last_attempt)
            VALUES (?, 0, 0, '', '')
            ON CONFLICT(server_name) DO UPDATE SET
                consecutive_failures = 0,
                broken = 0,
                last_error = '',
                last_attempt = ''
        """, (server_name,))
        conn.commit()


# ── App settings (key-value) ──────────────────────────────────────

def _ensure_settings_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """)


def get_setting(key: str, default: str = "") -> str:
    """Read a setting value by key. Returns default if not found."""
    with _conn() as conn:
        _ensure_settings_table(conn)
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    """Write (insert or update) a setting value."""
    with _conn() as conn:
        _ensure_settings_table(conn)
        conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()


def mcp_get_health(server_name: str = None) -> list[dict]:
    """Get health status for all MCP servers, or a specific one."""
    with _conn() as conn:
        if server_name:
            rows = conn.execute(
                "SELECT * FROM mcp_health WHERE server_name = ?", (server_name,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM mcp_health").fetchall()
        return [dict(r) for r in rows]
