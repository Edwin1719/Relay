"""FastAPI backend for Relay — local coding agent with MCP support."""

import json
import os
import secrets
import asyncio
import datetime
import difflib
import threading
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from tempfile import NamedTemporaryFile
import subprocess

from dotenv import load_dotenv

# Load .env from the backend directory (API keys for DeepSeek, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from agent_stream import (
    create_agent, ask_stream, clip,
    list_available_models, switch_model,
    translate_error,
)
from http_client import resolve_env_var
from agent_core import is_within_root
from mcp_manager import get_mcp_manager, MCP_AVAILABLE
from model_registry import default_model
from providers import (
    PROVIDERS, UnknownModelError, provider_of,
    clear_api_key, refresh_apinex_models, save_api_key,
)
from workspace_manager import set_workspace_root, get_workspace_root
from session_db import init_db, create_session, list_sessions, get_session, update_session, delete_session
from integrations_manager import (
    IntegrationsManager, get_catalog, get_catalog_item,
    get_integrations as db_get_integrations,
    get_integration as db_get_integration,
    get_preflight_results,
)
from skills_manager import (
    get_skills_catalog, get_skills_status, set_skill_enabled,
    get_active_skill_prompts, get_enabled_skill_names, init_skills_table,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kodama")


# ── Auth token ────────────────────────────────────────────────────

AUTH_ENABLED = os.environ.get("KODAMA_NO_AUTH", "").strip().lower() not in ("1", "true", "yes")
AUTH_TOKEN = ""
TOKEN_FILE = Path(__file__).resolve().parent / ".kodama_token"

if AUTH_ENABLED:
    if TOKEN_FILE.exists():
        AUTH_TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
    else:
        AUTH_TOKEN = secrets.token_hex(32)
        TOKEN_FILE.write_text(AUTH_TOKEN, encoding="utf-8")
        # Restrict permissions on the token file (owner-only read)
        try:
            import stat
            TOKEN_FILE.chmod(stat.S_IREAD | stat.S_IWRITE)
        except Exception:
            pass
    logger.info("🔐 Auth enabled. Token stored in %s", TOKEN_FILE)
else:
    logger.info("🔓 Auth disabled (KODAMA_NO_AUTH=1)")


# ── Global state ─────────────────────────────────────────────────
agent = None
mcp_status = []
workspace_root = get_workspace_root()
current_session_id = None
integrations_mgr = None
_integrations_conn = None  # SQLite conn for integrations access

# One streaming turn at a time: the agent, its history and its session file
# are shared, so two concurrent chats would interleave records on disk.
_chat_lock = threading.Lock()


def _ensure_chat_idle(action: str):
    """Reject agent mutations while a chat stream is running."""
    if _chat_lock.locked():
        raise HTTPException(409, f"No puedes {action} mientras el agente responde.")


def _programming_enabled() -> bool:
    """True when Modo Programación is active; risky tools then ask first."""
    try:
        conn = _get_iconn()
        try:
            return "programming" in get_enabled_skill_names(conn)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not read enabled skills: %s", exc)
        return False


# Single pending approval (one chat at a time thanks to _chat_lock).
_approval = {"event": threading.Event(), "approved": False, "pending": False}


def _approval_diff(agent, name, args):
    """Unified diff preview for a write tool, computed before it executes."""
    if name == "run_shell":
        return f"$ {args.get('command', '')}"
    if name not in {"write_file", "patch_file", "edit_file"}:
        return ""
    try:
        path = agent.path(args.get("path", ""))
    except (ValueError, OSError):
        return ""
    old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    new = str(args.get("content", ""))
    if name == "patch_file":
        old_text = str(args.get("old_text", ""))
        if old_text not in old:
            return "(el texto a reemplazar no está en el archivo)"
        new = old.replace(old_text, str(args.get("new_text", "")), 1)
    elif name == "edit_file":
        lines = old.splitlines(keepends=True)
        start = max(int(args.get("start_line", 1)) - 1, 0)
        end = int(args.get("end_line", start + 1))
        new = "".join(lines[:start]) + str(args.get("new_text", "")) + "".join(lines[end:])
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"a/{args.get('path')}", tofile=f"b/{args.get('path')}", lineterm="",
    )
    return clip("\n".join(diff), 6000)


def _make_approver(agent, queue, loop):
    """Bridge the engine's approve() to the UI over the chat SSE stream."""

    def approve(name, args):
        if agent.depth > 0 or agent.approval_policy != "ask":
            return True
        _approval["approved"] = False
        _approval["pending"] = True
        _approval["event"].clear()
        try:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {
                    "type": "approval_required",
                    "data": {"tool": name, "args": args,
                             "diff": _approval_diff(agent, name, args)},
                },
            )
        except Exception:
            _approval["pending"] = False
            return False
        _approval["event"].wait(timeout=60)
        _approval["pending"] = False
        return _approval["approved"]

    return approve


def rebuild_agent(cwd=None, skill_prompts=None, resume_session_id=None):
    """Recreate the agent, optionally with a new workspace root and skill prompts.

    If a previous agent exists with an active conversation AND the workspace
    stays the same, its session history and memory are migrated to the new
    agent so the conversation continues uninterrupted after model changes.
    When the workspace changes, history is NOT migrated — old context from
    a different project would confuse the model with conflicting information.
    """
    global agent, workspace_root

    # Capture previous agent's session before replacement
    prev_history = []
    prev_memory = {}
    prev_session_id = None
    prev_workspace = None
    prev_model = ""
    if agent is not None:
        try:
            prev_session = getattr(agent, "session", {})
            prev_history = prev_session.get("history", [])
            prev_memory = prev_session.get("memory", {})
            prev_session_id = prev_session.get("id", None)
            prev_workspace = getattr(agent.workspace, "repo_root", None)
            prev_model = getattr(agent.model_client, "model", "")
        except Exception as exc:
            logger.warning("Could not capture previous agent session: %s", exc)

    if cwd:
        workspace_root = set_workspace_root(cwd)
    mcp_mgr = get_mcp_manager()
    mcp_tools = mcp_mgr.get_all_mcp_tools() if mcp_mgr.is_available else {}

    # Prefer explicit resume_session_id over captured one
    effective_resume = resume_session_id or prev_session_id
    agent = create_agent(cwd=workspace_root, model=prev_model, mcp_tools=mcp_tools,
                         skill_prompts=skill_prompts,
                         approval="ask" if _programming_enabled() else "auto",
                         resume_session_id=effective_resume)

    # Restore conversation context into the new agent — only when the
    # workspace did NOT change. History from a different project would
    # conflict with the new workspace context and confuse the model.
    # When resume_session_id is set, from_session() already loaded the
    # correct history from disk — do NOT overwrite it.
    if prev_history and not resume_session_id:
        old_root = Path(prev_workspace).resolve() if prev_workspace else None
        new_root = Path(workspace_root).resolve()
        if old_root and old_root == new_root:
            agent.session["history"] = prev_history
            agent.session["memory"] = prev_memory
            logger.info("Migrated %d history entries (same workspace)", len(prev_history))
        elif old_root:
            logger.info(
                "Workspace changed (%s → %s) — discarding %d history entries",
                old_root, new_root, len(prev_history),
            )
    return agent


def get_agent():
    global agent
    if agent is None:
        rebuild_agent()
    return agent


# ── Session auto-management ──────────────────────────────────────

def ensure_session_for_workspace(workspace: str, model: str = "") -> str:
    """Find an existing session for *workspace* or create one.

    Returns the session id.
    """
    global current_session_id
    all_sessions = list_sessions(50)
    for s in all_sessions:
        if s["workspace"] == workspace:
            current_session_id = s["id"]
            # If this session has a stored MiniAgent ID, try to resume it
            miniagent_id = s.get("miniagent_session_id", "") or ""
            if miniagent_id:
                rebuild_agent(resume_session_id=miniagent_id)
            logger.info("Reusing session %s for workspace %s", s["id"][:12], workspace)
            return s["id"]
    provider = _detect_provider(model)
    current_agent = get_agent()
    miniagent_id = current_agent.session.get("id", "")
    session = create_session(
        name=Path(workspace).name,
        workspace=workspace,
        model=model,
        provider=provider,
        miniagent_session_id=miniagent_id,
    )
    current_session_id = session["id"]
    logger.info("Created session %s for workspace %s", session["id"][:12], workspace)
    return session["id"]


def _update_session_after_chat(user_message: str):
    """Update the current session's metadata after a chat turn."""
    global current_session_id
    if not current_session_id:
        return
    current_agent = get_agent()
    model = getattr(current_agent.model_client, "model", "")
    history_len = len(current_agent.session.get("history", []))
    msg_count = history_len // 2  # approximate: user + assistant pairs
    miniagent_id = current_agent.session.get("id", "")
    update_session(
        current_session_id,
        model=model,
        provider=_detect_provider(model),
        last_message=clip(user_message.strip(), 120),
        message_count=msg_count,
        miniagent_session_id=miniagent_id,
    )


def _detect_provider(model: str) -> str:
    """Provider name for *model*, via the catalog (``""`` if unknown)."""
    try:
        return provider_of(model)
    except UnknownModelError:
        return ""


def _get_active_workspace() -> str | None:
    """Return the workspace tied to the current session, or None for chat-only.

    Unlike current_agent.workspace.repo_root (which always points to a real
    directory), this returns the *session's* stored workspace. Chat-only
    sessions (saved via the "+" dialog without loading a folder) have
    workspace="" and should NOT show the file explorer.
    """
    global current_session_id
    if not current_session_id:
        return None
    session = get_session(current_session_id)
    if not session:
        return None
    return session.get("workspace") or None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_status, current_session_id, integrations_mgr, _integrations_conn
    # Initialize session database (fast, SQLite)
    init_db()
    logger.info("Session database ready")

    # Verify APInex's free catalog before the agent picks a default model, so
    # the picker never lists a model that stopped being free.
    if PROVIDERS["apinex"].configured:
        refresh_apinex_models()

    # Pre-warm agent — NO session auto-load on startup.
    # Sessions are created when:
    #   - User loads a workspace (POST /api/workspace/set)
    #   - User clicks "+" in the Sessions tab
    #   - User clicks a saved session
    # This way the UI starts clean and the user controls which session to activate.
    get_agent()
    logger.info("Agent ready — no session loaded (clean start)")

    # Launch MCP and integrations in background (non-blocking)
    _start_mcp_and_integrations()

    yield  # ← HTTP server starts accepting requests HERE

    # After yield = server is shutting down
    if integrations_mgr:
        integrations_mgr.stop_all()
    mcp_mgr = get_mcp_manager()
    if mcp_mgr.is_available:
        mcp_mgr.stop()
    if _integrations_conn:
        try:
            _integrations_conn.close()
        except Exception:
            pass
    logger.info("Relay shutdown complete")


# ── Background startup (non-blocking) ────────────────────────────

def _start_mcp_and_integrations():
    """Connect MCP servers and configured integrations in a background thread.

    This runs *after* the HTTP server is already accepting requests,
    so users see the UI immediately while servers connect progressively.
    """
    global mcp_status, integrations_mgr, _integrations_conn
    import threading
    import time

    def _bg():
        global mcp_status, integrations_mgr, _integrations_conn
        mcp_mgr = get_mcp_manager()
        if mcp_mgr.is_available:
            logger.info("[background] Starting MCP servers...")
            # Only connect servers whose integrations are enabled in SQLite
            from session_db import _get_connection as _db_conn
            from integrations_manager import get_integrations
            try:
                db = _db_conn()
                enabled_set = {r["server_name"] for r in get_integrations(db) if r["enabled"]}
                logger.info("[background] Enabled MCP servers: %s", enabled_set)
            except Exception:
                enabled_set = None  # fallback: connect all
            mcp_status = mcp_mgr.start(enabled_servers=enabled_set)
            for s in mcp_status:
                if s["status"] == "connected":
                    logger.info("  ✓ [bg] %s: %d tools", s["server"], len(s.get("tools", [])))
                else:
                    logger.warning("  ✗ [bg] %s: %s", s["server"], s.get("error", "unknown"))

            # Load MCP config env vars into os.environ (with ${VAR} resolution)
            try:
                mcp_config_path = Path(__file__).parent / "mcp_config.json"
                if mcp_config_path.exists():
                    with open(mcp_config_path) as f:
                        mcp_cfg = json.load(f)
                    for _name, _cfg in mcp_cfg.get("mcpServers", {}).items():
                        for _key, _val in _cfg.get("env", {}).items():
                            resolved = resolve_env_var(_val)
                            if resolved and _key not in os.environ:
                                os.environ[_key] = resolved
                    logger.info("[background] Loaded MCP config env vars into environment")
            except Exception as exc:
                logger.warning("[background] Could not load MCP config env: %s", exc)
        else:
            logger.info("[background] MCP SDK not installed — skipping MCP servers")

        # Initialize integrations manager and start configured integrations
        integrations_mgr = IntegrationsManager(mcp_mgr)
        from session_db import _get_connection
        _integrations_conn = _get_connection()
        if integrations_mgr:
            integration_results = integrations_mgr.start_configured(_integrations_conn)
            for r in integration_results:
                if r["status"] == "connected":
                    logger.info("  ✓ [bg] Integration %s: %d tools", r["server"], len(r.get("tools", [])))
                else:
                    logger.warning("  ✗ [bg] Integration %s: %s", r["server"], r.get("error", "unknown"))

        # Refresh MCP status — integrations may have started additional MCP
        # servers (e.g. filesystem, gmail, google-maps) beyond the initial
        # mcp_mgr.start() batch. Without this refresh, the badge in the UI
        # shows a stale count like "4/4" instead of the real total.
        if mcp_mgr.is_available:
            mcp_status = mcp_mgr.get_status()
            logger.info("[background] MCP status refreshed: %d servers total", len(mcp_status))

        # Notify agent about MCP tools now that they're available
        skill_prompts = get_active_skill_prompts(_integrations_conn)
        rebuild_agent(skill_prompts=skill_prompts)

    thread = threading.Thread(target=_bg, daemon=True, name="mcp-bg-startup")
    thread.start()
    logger.info("Background MCP/integrations startup launched — server is live now")


app = FastAPI(
    title="Relay",
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs",
)

# Rate limiting: 5 requests/second per IP on /api/chat
limiter = Limiter(key_func=get_remote_address, default_limits=["5/second"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:1420",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Validate Bearer token on all /api/* routes (except /api/auth-token)."""
    if not AUTH_ENABLED:
        return await call_next(request)

    path = request.url.path
    # Allow health-check, auth-token, and non-API paths through
    if not path.startswith("/api/") or path in ("/api/auth-token", "/api/status"):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "Missing or invalid Authorization header. Use: Bearer <token>"},
        )

    token = auth_header[7:]  # strip "Bearer "
    if token != AUTH_TOKEN:
        return JSONResponse(
            status_code=403,
            content={"error": "Invalid access token"},
        )

    return await call_next(request)


@app.get("/api/auth-token")
async def get_auth_token(request: Request):
    """Return the auth token — only accessible from localhost."""
    if not AUTH_ENABLED:
        return {"auth_enabled": False, "token": None}

    # Only serve token to localhost origins
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Token only available from localhost")

    return {"auth_enabled": True, "token": AUTH_TOKEN}


# ── Models ───────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    images: list[str] = []

class ModelSelect(BaseModel):
    name: str

class WorkspaceSet(BaseModel):
    path: str

class SessionCreate(BaseModel):
    name: str = ""
    workspace: str = ""
    model: str = ""

class IntegrationEnable(BaseModel):
    server_name: str
    api_keys: dict[str, str] = {}
    config: dict = {}

class IntegrationConfigure(BaseModel):
    server_name: str
    api_keys: dict[str, str] = {}
    config: dict = {}

class MCPReset(BaseModel):
    server_name: str


# ── Endpoints ────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    current_agent = get_agent()
    model = (
        current_agent.model_client.model
        if hasattr(current_agent.model_client, "model")
        else "unknown"
    )
    return {
        "session_id": current_agent.session["id"],
        "current_session_id": current_session_id,
        "workspace": current_agent.workspace.repo_root,
        "session_workspace": _get_active_workspace(),
        "branch": current_agent.workspace.branch,
        "model": model,
        "provider": _detect_provider(model),
        "approval": current_agent.approval_policy,
        "max_steps": current_agent.max_steps,
        "mcp_available": MCP_AVAILABLE,
        "mcp_servers": mcp_status,
        "version": "0.3.0",
    }


@app.post("/api/chat")
@limiter.limit("5/second")
async def chat(request: Request, req: ChatRequest):
    """SSE streaming endpoint for agent chat."""
    current_agent = get_agent()
    if _chat_lock.locked():
        raise HTTPException(409, "Ya hay una respuesta en curso. Espera o pulsa Detener.")

    async def event_generator():
        # The acquire inside the generator is what makes the lock safe: it is
        # held exactly while the stream runs and released in its finally,
        # including when the client disconnects or the user presses Detener.
        if not _chat_lock.acquire(blocking=False):
            message = "Ya hay una respuesta en curso. Espera o pulsa Detener."
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': message}})}\n\n"
            yield "data: [DONE]\n\n"
            return
        # Thread-safe bridge: ask_stream() runs in a daemon thread and pushes
        # each event into an asyncio.Queue via call_soon_threadsafe, so the
        # async generator can yield SSE lines immediately as they arrive.
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        loop = asyncio.get_event_loop()
        done = threading.Event()

        def run():
            try:
                for event in ask_stream(current_agent, req.message, images=req.images or None):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel: ok
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                # Released by the worker, not by the generator: if the client
                # disconnects, the worker can still be mutating the agent.
                _chat_lock.release()

        current_agent.approve = _make_approver(current_agent, queue, loop)
        thread = threading.Thread(target=run, daemon=True)
        try:
            thread.start()
        except Exception:
            _chat_lock.release()
            raise

        try:
            while True:
                event = await queue.get()
                if event is None:          # normal completion
                    break
                if isinstance(event, Exception):
                    raise event
                yield f"data: {json.dumps(event)}\n\n"

            # Update session metadata after successful chat
            try:
                _update_session_after_chat(req.message)
            except Exception:
                logger.warning("Failed to update session after chat", exc_info=True)

        except Exception as exc:
            logger.exception("Chat error")
            yield (
                f"data: {json.dumps({'type': 'error', 'data': {'message': str(exc)}})}\n\n"
            )
        finally:
            done.set()
            _approval["event"].set()  # unblock a pending approval on disconnect
            thread.join(timeout=5)
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class ApprovalRequest(BaseModel):
    approved: bool


@app.post("/api/approve")
def approve_tool(req: ApprovalRequest):
    """Allow or deny the risky tool the running chat is waiting on."""
    if not _approval["pending"]:
        raise HTTPException(409, "No hay ninguna aprobación pendiente.")
    _approval["approved"] = bool(req.approved)
    _approval["event"].set()
    return {"status": "ok", "approved": _approval["approved"]}


@app.post("/api/reset")
def reset_session():
    _ensure_chat_idle("reiniciar la conversación")
    current_agent = get_agent()
    current_agent.reset()
    return {"status": "ok", "message": "session reset"}


@app.get("/api/workspace")
def get_workspace():
    current_agent = get_agent()
    return {
        "root": current_agent.workspace.repo_root,
        "cwd": current_agent.workspace.cwd,
        "branch": current_agent.workspace.branch,
        "status": current_agent.workspace.status,
    }


@app.post("/api/workspace/set")
def set_workspace(req: WorkspaceSet):
    """Change the agent's workspace to a new directory."""
    _ensure_chat_idle("cambiar de workspace")
    try:
        logger.info("Workspace set requested: %s", req.path)
        rebuild_agent(cwd=req.path)
        new_agent = get_agent()
        logger.info("Workspace set -> repo_root: %s", new_agent.workspace.repo_root)
        # Auto-create or reuse a session for this workspace
        model = getattr(new_agent.model_client, "model", "")
        ensure_session_for_workspace(new_agent.workspace.repo_root, model)
        return {
            "status": "ok",
            "root": new_agent.workspace.repo_root,
            "cwd": new_agent.workspace.cwd,
            "branch": new_agent.workspace.branch,
        }
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Failed to set workspace")
        raise HTTPException(500, str(exc))


@app.get("/api/workspace/pick")
def pick_workspace_folder():
    """Open native OS folder picker dialog and return the selected path."""
    try:
        if os.name == "nt":
            ps_script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = \"Seleccionar carpeta del proyecto\"
$dialog.ShowNewFolderButton = $false
$result = $dialog.ShowDialog()
if ($result -eq \"OK\") {
    Write-Output $dialog.SelectedPath
} else {
    Write-Output \"__CANCELED__\"
}
"""
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=600,
            )
            path = result.stdout.strip()
            if path == "__CANCELED__" or not path:
                return {"path": None, "canceled": True}
            return {"path": path, "canceled": False}
        else:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            folder = filedialog.askdirectory(title="Seleccionar carpeta del proyecto")
            root.destroy()
            if folder:
                return {"path": folder, "canceled": False}
            return {"path": None, "canceled": True}
    except Exception as exc:
        logger.warning("Folder picker failed: %s", exc)
        raise HTTPException(500, f"Folder picker not available: {exc}")


@app.get("/api/workspace/files")
def list_workspace_files(path: str = "."):
    current_agent = get_agent()
    root = Path(current_agent.workspace.repo_root)
    base = (root / path).resolve()
    if not is_within_root(root, base):
        raise HTTPException(403, "Path traversal denied")
    logger.debug("Listing files at %s (repo_root=%s, cwd=%s)", base, current_agent.workspace.repo_root, current_agent.workspace.cwd)
    if not base.exists() or not base.is_dir():
        raise HTTPException(404, f"Directory not found: {path}")
    entries = []
    for entry in sorted(base.iterdir()):
        entries.append({
            "name": entry.name,
            "path": str(entry.relative_to(root)),
            "type": "dir" if entry.is_dir() else "file",
        })
    return {"path": path, "entries": entries}


@app.get("/api/workspace/read")
def read_workspace_file(path: str):
    current_agent = get_agent()
    root = Path(current_agent.workspace.repo_root)
    full = (root / path).resolve()
    if not is_within_root(root, full):
        raise HTTPException(403, "Path traversal denied")
    if not full.exists() or not full.is_file():
        raise HTTPException(404, f"File not found: {path}")
    content = full.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": content}


@app.get("/api/session")
def get_current_session():
    current_agent = get_agent()
    return {
        "id": current_agent.session["id"],
        "path": str(current_agent.session_path),
        "history_count": len(current_agent.session["history"]),
    }


@app.get("/api/memory")
def get_memory():
    current_agent = get_agent()
    return current_agent.session.get("memory", {})


@app.get("/api/session/history")
def get_session_history():
    """Return the current agent's full chat history for UI restore."""
    current_agent = get_agent()
    history = current_agent.session.get("history", [])
    # Convert to frontend-friendly Message format
    messages = []
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append({
                "id": f"hist-user-{entry.get('created_at', '')}",
                "role": "user",
                "content": content,
                "timestamp": entry.get("created_at", ""),
            })
        elif role == "assistant":
            messages.append({
                "id": f"hist-assistant-{entry.get('created_at', '')}",
                "role": "assistant",
                "content": content,
                "timestamp": entry.get("created_at", ""),
            })
        elif role == "tool":
            # Tool entries are tool_call + tool_result pairs in the UI
            pass
    return {"messages": messages}


# ── Models ───────────────────────────────────────────────────────

@app.get("/api/models")
def get_models():
    return {"models": list_available_models()}


@app.post("/api/models/select")
def select_model(req: ModelSelect):
    _ensure_chat_idle("cambiar de modelo")
    current_agent = get_agent()
    try:
        switch_model(current_agent, req.name)
    except UnknownModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "ok",
        "model": req.name,
        "session_id": current_agent.session["id"],
    }


# ── Providers ────────────────────────────────────────────────────


class ProviderCredentials(BaseModel):
    name: str
    api_key: str = ""


def _provider_summary(spec) -> dict:
    models = [m for m in list_available_models() if m["provider"] == spec.name]
    return {
        "name": spec.name,
        "label": spec.label,
        "backend": spec.backend,
        "base_url": spec.base_url,
        "env_key": spec.env_key,
        "requires_key": spec.requires_key,
        "configured": spec.configured,
        "docs_url": spec.docs_url,
        "tier": "deep" if spec.backend == "openai" else "fast",
        "models": [m["name"] for m in models],
    }


@app.get("/api/providers")
def get_providers():
    """Every provider with its configuration state and available models."""
    return {"providers": [_provider_summary(spec) for spec in PROVIDERS.values()]}


@app.post("/api/providers/configure")
def configure_provider(req: ProviderCredentials):
    """Save a provider API key, verify its catalog and rebuild the agent."""
    spec = PROVIDERS.get(req.name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {req.name}")
    if not spec.requires_key:
        raise HTTPException(status_code=400, detail=f"{spec.label} does not use an API key")

    key = req.api_key.strip()
    if key:
        save_api_key(spec.name, key)
    else:
        clear_api_key(spec.name)

    if spec.name == "apinex" and key:
        refresh_apinex_models()

    # Rebuild so the new provider can serve the next turn. rebuild_agent()
    # keeps the current model when it is still routable, else picks a default.
    rebuild_agent()
    return {"provider": _provider_summary(spec), "models": list_available_models()}


# ── Onboarding ────────────────────────────────────────────────────

@app.get("/api/onboarding/status")
def onboarding_status():
    """Return whether the onboarding wizard has been completed."""
    from session_db import get_setting
    completed = get_setting("onboarding_completed", "false") == "true"
    return {"completed": completed}


@app.post("/api/onboarding/complete")
def onboarding_complete():
    """Mark the onboarding wizard as completed."""
    from session_db import set_setting
    set_setting("onboarding_completed", "true")
    return {"status": "ok"}


# ── MCP ──────────────────────────────────────────────────────────

@app.get("/api/mcp/status")
def get_mcp_status():
    # Merge circuit breaker health info into server status
    from session_db import mcp_get_health
    health = {h["server_name"]: h for h in mcp_get_health()}
    enriched = []
    for s in mcp_status:
        s_copy = dict(s)
        # Translate technical error messages
        if s_copy.get("error"):
            s_copy["error"] = translate_error(s_copy["error"])
        h = health.get(s["server"])
        if h:
            s_copy["consecutive_failures"] = h["consecutive_failures"]
            s_copy["broken"] = bool(h["broken"])
            s_copy["last_error"] = h["last_error"]
        enriched.append(s_copy)
    return {
        "available": MCP_AVAILABLE,
        "servers": enriched,
    }


@app.post("/api/mcp/reset")
def reset_mcp_server(req: MCPReset):
    """Reset the circuit breaker for a specific MCP server."""
    from session_db import mcp_reset_server as reset_cb
    reset_cb(req.server_name)
    logger.info("Circuit breaker reset for MCP server: %s", req.server_name)
    return {"status": "ok", "server": req.server_name}


@app.post("/api/mcp/reconnect")
def reconnect_mcp():
    """Reconnect all MCP servers (e.g., after a config change)."""
    global mcp_status
    mcp_mgr = get_mcp_manager()
    if not mcp_mgr.is_available:
        raise HTTPException(400, "MCP SDK not installed")
    # Stop existing connections
    mcp_mgr.stop()
    # Re-create and re-start
    from mcp_manager import get_mcp_manager as fresh_mgr
    new_mgr = fresh_mgr()
    mcp_status = new_mgr.start()
    # Rebuild agent with new MCP tools
    global agent
    mcp_tools = new_mgr.get_all_mcp_tools()
    agent = create_agent(cwd=workspace_root, mcp_tools=mcp_tools,
                         approval="ask" if _programming_enabled() else "auto")
    return {"status": "ok", "servers": mcp_status}


# ── Skills ───────────────────────────────────────────────────────

@app.get("/api/skills")
def api_list_skills():
    """Return all skills with their enabled/disabled state."""
    conn = _get_iconn()
    try:
        return {"skills": get_skills_status(conn)}
    finally:
        conn.close()


@app.post("/api/skills/toggle")
def api_toggle_skill(req: ModelSelect):
    """Toggle a skill on or off. Expects {"name": "debug"}."""
    from session_db import _get_connection
    conn = _get_connection()
    try:
        current = get_skills_status(conn)
        skill = next((s for s in current if s["name"] == req.name), None)
        if not skill:
            raise HTTPException(404, f"Skill not found: {req.name}")
        set_skill_enabled(conn, req.name, not skill["enabled"])

        # Rebuild agent with updated skill prompts
        skill_prompts = get_active_skill_prompts(conn)
        rebuild_agent(skill_prompts=skill_prompts)

        return {"status": "ok", "name": req.name, "enabled": not skill["enabled"]}
    finally:
        conn.close()



# ── Integrations / Marketplace ─────────────────────────────────

def _get_iconn():
    """Get a fresh SQLite connection for integrations access."""
    from session_db import _get_connection
    return _get_connection()


@app.get("/api/integrations/catalog")
def api_integrations_catalog():
    """Return the catalog of all known integrations."""
    return {"catalog": get_catalog()}


@app.get("/api/integrations")
def api_list_integrations():
    """Return the user's integration config (enabled/disabled state)."""
    conn = _get_iconn()
    try:
        records = db_get_integrations(conn)
        # Check which ones are actually connected via MCP manager
        mcp_mgr = get_mcp_manager()
        # Merge catalog info into each record for the UI
        preflight = get_preflight_results()
        result = []
        for rec in records:
            catalog_item = get_catalog_item(rec["server_name"])
            if catalog_item:
                rec["display_name"] = catalog_item["display_name"]
                rec["description"] = catalog_item["description"]
                rec["tools_description"] = catalog_item["tools_description"]
                rec["config_fields"] = catalog_item["config_fields"]
                # Report actual connection status from MCP manager
                is_connected = mcp_mgr.is_available and mcp_mgr.has_server(rec["server_name"])
                if is_connected:
                    rec["connected"] = True
                    # Attach actual tools from the MCP connection
                    for sv in mcp_mgr.get_status():
                        if sv["server"] == rec["server_name"]:
                            rec["tools"] = sv.get("tools", [])
                            break
                else:
                    rec["connected"] = False
                    # Surface the last recorded failure so the UI can show why
                    # an enabled integration is not connected, instead of a
                    # perpetual "connecting" spinner.
                    if rec["enabled"]:
                        from session_db import mcp_get_health
                        for h in mcp_get_health():
                            if h["server_name"] == rec["server_name"] and h["last_error"]:
                                rec["error"] = h["last_error"]
                                break
                # Never expose actual API key values — just report if set
                from integrations_manager import get_env_key
                for field in catalog_item["config_fields"]:
                    if field["type"] == "api_key":
                        val = get_env_key(field["env_var"])
                        rec[f"_has_{field['env_var']}"] = bool(val)
                # Preflight: dependency availability badge
                pf = preflight.get(rec["server_name"], {})
                rec["preflight"] = {
                    "command": pf.get("command", ""),
                    "available": pf.get("available", False),
                    "path": pf.get("path", ""),
                }
                if "chrome_available" in pf:
                    rec["preflight"]["chrome_available"] = pf["chrome_available"]
                    rec["preflight"]["chrome_path"] = pf.get("chrome_path", "")
            result.append(rec)
        return {"integrations": result}
    finally:
        conn.close()


@app.post("/api/integrations/enable")
def api_enable_integration(req: IntegrationEnable):
    """Enable an integration with optional API keys and config.

    API keys are written to .env (secure storage). Non-sensitive
    config goes to SQLite. The MCP server starts immediately.
    """
    global integrations_mgr, _integrations_conn
    if not integrations_mgr:
        raise HTTPException(500, "Integrations manager not initialized")

    catalog_item = get_catalog_item(req.server_name)
    if not catalog_item:
        raise HTTPException(404, f"Unknown integration: {req.server_name}")

    # Check required fields
    for field in catalog_item.get("config_fields", []):
        if field.get("required"):
            env_val = req.api_keys.get(field["env_var"], "")
            if not env_val:
                raise HTTPException(400, f"'{field['label']}' is required to enable this integration")

    conn = _get_iconn()
    try:
        result = integrations_mgr.enable(
            conn, req.server_name,
            api_keys=req.api_keys or None,
            config=req.config or None,
        )
        # Rebuild agent to pick up new MCP tools
        rebuild_agent()
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    finally:
        conn.close()


@app.post("/api/integrations/disable")
def api_disable_integration(req: IntegrationEnable):
    """Disable an integration. Stops the MCP server, keeps config."""
    global integrations_mgr
    if not integrations_mgr:
        raise HTTPException(500, "Integrations manager not initialized")

    conn = _get_iconn()
    try:
        result = integrations_mgr.disable(conn, req.server_name)
        # Rebuild agent to remove MCP tools
        rebuild_agent()
        return result
    finally:
        conn.close()


@app.post("/api/integrations/configure")
def api_configure_integration(req: IntegrationConfigure):
    """Update API keys or config for an integration. Restarts if active."""
    global integrations_mgr
    if not integrations_mgr:
        raise HTTPException(500, "Integrations manager not initialized")

    catalog_item = get_catalog_item(req.server_name)
    if not catalog_item:
        raise HTTPException(404, f"Unknown integration: {req.server_name}")

    conn = _get_iconn()
    try:
        result = integrations_mgr.configure(
            conn, req.server_name,
            api_keys=req.api_keys or None,
            config=req.config or None,
        )
        # Rebuild agent to refresh MCP tools
        rebuild_agent()
        return result
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    finally:
        conn.close()


# ── Production: serve built frontend ─────────────────────────────

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


# ── Sessions ──────────────────────────────────────────────────────

@app.get("/api/sessions")
def api_list_sessions():
    """Return all sessions (most recent first)."""
    return {"sessions": list_sessions(limit=50)}


@app.post("/api/sessions")
def api_create_session(req: SessionCreate):
    """Create a new session and optionally switch to it.

    When all fields are empty (e.g. "+" button in sidebar), a fresh
    session is created with a unique name and independent conversation
    history — not a clone of the current session.
    """
    current_agent = get_agent()
    model = req.model or getattr(current_agent.model_client, "model", "")
    provider = "deepseek" if model.lower().startswith("deepseek-") else "ollama"
    # When the frontend creates a session without specifying a workspace
    # (e.g. "+" button or "Save conversation" dialog), don't tie it to
    # the current workspace_root — the session is workspace-free.
    workspace = req.workspace or ""
    is_fresh = not req.name and not req.workspace and not req.model

    if is_fresh:
        # New blank session — don't inherit current agent's conversation
        miniagent_id = ""
        name = f"Sesión {datetime.datetime.now().strftime('%H:%M')}"
    else:
        miniagent_id = current_agent.session.get("id", "")
        name = req.name or Path(workspace).name

    session = create_session(
        name=name,
        workspace=workspace,
        model=model,
        provider=provider,
        miniagent_session_id=miniagent_id,
    )
    # Activate the newly created session so the UI shows it as selected
    global current_session_id
    current_session_id = session["id"]
    return {"session": session}


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    """Delete a session."""
    delete_session(session_id)
    return {"status": "ok"}


@app.post("/api/sessions/{session_id}/switch")
def api_switch_session(session_id: str):
    """Switch to an existing session (changes workspace + reloads agent)."""
    _ensure_chat_idle("cambiar de sesión")
    global current_session_id
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")

    # Rebuild agent with this session's workspace and restore conversation history
    ws = session["workspace"]
    miniagent_id = session.get("miniagent_session_id", "") or ""
    resume_kwargs = {"resume_session_id": miniagent_id} if miniagent_id else {}
    if ws and Path(ws).exists():
        rebuild_agent(cwd=ws, **resume_kwargs)
    else:
        rebuild_agent(**resume_kwargs)

    # Switch model if the session had one
    current_agent = get_agent()
    if session["model"]:
        try:
            switch_model(current_agent, session["model"])
        except Exception:
            logger.warning("Could not switch to model '%s' for session %s", session["model"], session_id)

    current_session_id = session_id
    return {
        "status": "ok",
        "session": session,
        "workspace": current_agent.workspace.repo_root,
        "model": getattr(current_agent.model_client, "model", ""),
    }


# ── Production: serve built frontend ─────────────────────────────
if FRONTEND_DIST.exists():
    logger.info("Serving frontend from %s", FRONTEND_DIST)
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    logger.info("No frontend/dist found — dev mode (expect Vite on :5173)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
