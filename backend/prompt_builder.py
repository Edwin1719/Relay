"""Prompt builder and error translation utilities for Relay."""
import re
import json
import logging
from typing import Any
from agent_core import clip, MAX_TOOL_OUTPUT
from providers import context_limit_of

logger = logging.getLogger("kodama")

ERROR_TRANSLATIONS = [
    # Tool errors from agent_core.py
    (r"error: unknown tool '(\w+)'",
     "La herramienta '{0}' no esta disponible. Prueba con otra accion."),
    (r"error: invalid arguments for (\w+): (.*)",
     "Los parametros para '{0}' no son validos: {1}. Revisa el formato e intenta de nuevo."),
    (r"error: repeated identical tool call for (\w+);",
     "Ya intentaste '{0}' con los mismos parametros. Usa otra estrategia o pide el resultado final."),
    (r"error: approval denied for (\w+)",
     "La accion '{0}' requiere confirmacion. No se ejecuto por seguridad."),
    (r"error: tool (\w+) failed: (.*)",
     "La herramienta '{0}' fallo: {1}. Puede ser un problema temporal. Intenta de nuevo."),

    # Workspace/path errors
    (r"path escapes workspace boundary",
     "No puedes acceder a archivos fuera de tu proyecto. Usa rutas dentro del workspace."),
    (r"permission denied",
     "No tienes permisos para acceder a ese archivo o directorio."),
    (r"[Nn]o such file or directory",
     "El archivo o directorio no existe. Revisa la ruta e intenta de nuevo."),
    (r"[Ff]ile not found",
     "El archivo no se encontro. Verifica que el nombre y la ruta sean correctos."),

    # Shell/command errors
    (r"command not found: (\w+)",
     "El comando '{0}' no esta instalado en tu sistema. Instalalo o usa otra herramienta."),
    (r"[Cc]ould not reach Ollama",
     "No se pudo conectar al motor local (Ollama). Asegurate de que este corriendo: ejecuta 'ollama serve'."),
    (r"Ollama request failed",
     "El motor local (Ollama) encontro un error. Revisa que el modelo este descargado y funcionando."),
    (r"[Mm]odel.*not found",
     "El modelo de IA solicitado no se encontro. Descargalo primero o selecciona otro modelo disponible."),

    # MCP / Integration errors
    (r"Failed to start MCP server",
     "No se pudo iniciar el conector. Revisa que las dependencias (npx, uvx) esten instaladas."),
    (r"MCP SDK not installed",
     "El sistema de conectores no esta instalado. Ejecuta: pip install mcp"),
    (r"Circuit breaker open",
     "Este conector esta bloqueado por fallos repetidos. Usa el panel de conectores para reactivarlo."),

    # API / Auth errors
    (r"rate limit exceeded",
     "Has enviado demasiadas solicitudes. Espera unos segundos antes de continuar."),
    (r"API key.*invalid",
     "La clave de API no es valida. Revisa tu configuracion en el archivo .env."),
    (r"[Rr]ate limit",
     "Limite de velocidad alcanzado. Espera unos segundos antes de intentar de nuevo."),

    # Network errors
    (r"[Cc]onnection refused",
     "No se pudo conectar al servicio. Esta corriendo el servidor?"),
    (r"[Tt]imeout",
     "La operacion tardo demasiado. Revisa tu conexion e intentalo de nuevo."),
    (r"[Nn]ame or service not known",
     "No se pudo resolver la direccion. Revisa tu conexion a internet."),
]


def translate_error(message: str) -> str:
    """Translate a technical error message to natural Spanish.

    Uses regex patterns from ERROR_TRANSLATIONS. Returns the original
    message if no translation matches.
    """
    if not isinstance(message, str):
        return message

    for pattern, template in ERROR_TRANSLATIONS:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return template.format(*match.groups())
            except (IndexError, KeyError):
                return template
    return message


# ── edit_file tool factory (line-based surgical editing) ──

def build_edit_file_tool(agent) -> dict[str, Any]:
    """Return a tool entry dict for line-based editing.

    The returned ``run`` closure uses ``agent.path()`` for path resolution,
    so the agent must have a ``path()`` method (standard KodamaAgent interface).
    """
    def _run(args):
        path = agent.path(args["path"])
        if not path.exists():
            return f"error: path '{args['path']}' does not exist"
        if not path.is_file():
            return f"error: path '{args['path']}' is not a file"

        start_line = int(args.get("start_line", 1))
        end_line = int(args.get("end_line", start_line))
        new_text = str(args.get("new_text", ""))

        if start_line < 1:
            return "error: start_line must be >= 1"
        if end_line < start_line:
            return "error: end_line must be >= start_line"

        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        total = len(all_lines)

        if start_line > total:
            return (
                f"error: start_line {start_line} exceeds file length "
                f"({total} lines)"
            )

        end_line = min(end_line, total)
        before = "".join(all_lines[:start_line - 1])
        after = "".join(all_lines[end_line:])
        new_content = before + new_text
        if after:
            # Ensure a newline between new_text and the remaining content
            # when new_text doesn't end with one (preserves file line structure).
            # Skip when new_text is empty (line deletion).
            if new_text and not new_text.endswith("\n"):
                new_content += "\n"
            new_content += after

        path.write_text(new_content, encoding="utf-8")

        old_count = end_line - start_line + 1
        new_count = len(new_text.splitlines())
        diff = new_count - old_count
        diff_desc = (
            f"({'+' if diff > 0 else ''}{diff} lines)" if diff != 0
            else "(same line count)"
        )
        return (
            f"patched {path} — replaced line"
            f"{'s' if old_count > 1 else ''} {start_line}-{end_line} "
            f"with {new_count} line{'s' if new_count != 1 else ''} {diff_desc}"
        )

    return {
        "schema": {
            "path": "str",
            "start_line": "int",
            "end_line": "int",
            "new_text": "str",
        },
        "description": (
            "Edit a file by replacing a range of lines with new text. "
            "Always read the file first to see line numbers, then call this tool. "
            "Example: edit_file(path='src/main.py', start_line=10, end_line=12, "
            "new_text='def new_function():\\n    pass')"
        ),
        "risky": True,
        "run": _run,
    }


# ── Prompt utilities ──────────────────────────────────────────


def estimate_prompt_tokens(agent) -> int:
    """Estimate total tokens in the agent's current prompt (approximate).

    Uses the simple heuristic of ~4 characters per token.
    """
    full = "\n\n".join([
        agent.prefix,
        agent.memory_text(),
        "Transcript:\n" + agent.history_text(),
    ])
    return len(full) // 4


# Half of the model's context is available for history; the rest holds the
# system prompt, memory, tool output and the response. MAX_HISTORY_TOKENS
# bounds cost and latency for very large windows.
MAX_HISTORY_TOKENS = 64_000


def _history_budget(agent) -> int:
    model = getattr(getattr(agent, "model_client", None), "model", "")
    limit = context_limit_of(model)
    return min(MAX_HISTORY_TOKENS, limit // 2)


def truncate_conversation_history(agent, max_tokens=None):
    """Remove oldest history entries when estimated tokens exceed *max_tokens*.

    Preserves the system prompt, memory, and most recent exchanges intact.
    Only removes from ``agent.session["history"]`` (conversation transcript).

    If *max_tokens* is ``None``, derives the budget from the active model's
    declared context window (half of it, capped at ``MAX_HISTORY_TOKENS``),
    so a 1M-token model does not send unbounded prompts.

    Returns:
        int: number of entries removed.
    """
    if max_tokens is None:
        max_tokens = _history_budget(agent)

    history = agent.session["history"]
    initial_count = len(history)
    if initial_count <= 2:
        return 0

    # Single estimate to decide if truncation is needed
    estimated = estimate_prompt_tokens(agent)
    if estimated <= max_tokens:
        return 0

    # Remove history in bulk chunks (25% at a time) to minimize expensive
    # prompt reconstructions — O(log n) instead of O(n) full rebuilds.
    while len(history) > 2:
        chunk = max(2, len(history) // 4)
        del history[:chunk]
        if estimate_prompt_tokens(agent) <= max_tokens:
            break

    removed = initial_count - len(history)
    if removed:
        logger.info(
            "Truncated %d old history entries (%d\u2192%d) to keep prompt under %dK tokens "
            "(est. %dK \u2192 %dK)",
            removed, initial_count, len(history), max_tokens // 1000,
            estimated // 1000, estimate_prompt_tokens(agent) // 1000,
        )
    return removed



# ── System prompt builder ──────────────────────────────────────

def build_system_prompt(base_prefix: str, skill_prompts: list[str] | None = None) -> str:
    """Build the complete system prompt with critical rules, formatting, and MCP guide.

    Args:
        base_prefix: The base prefix from ``MiniAgent.build_prefix()``
                     (contains tool schemas, base behavioral rules).
        skill_prompts: Optional list of active skill prompt strings to inject
                       at the very beginning (highest priority).
    """
    prefix = base_prefix

    # 1. Inject active skill prompts (highest priority \u2014 placed first in prefix)
    if skill_prompts:
        skill_block = "\n\n".join(skill_prompts)
        prefix = skill_block + "\n\n" + prefix

    # ================================================================
    # 2. CRITICAL RULES (placed at the start of prefix for maximum attention)
    # ================================================================
    critical_rules = """
CRITICAL RULE \u2014 ANSWER FROM KNOWLEDGE FIRST:
- If you can answer the user's question from your own knowledge WITHOUT using any tool,
  respond directly with <final>. Do NOT plan, do NOT search the web, do NOT call tools.
- Only use tools when the user explicitly asks you to: create/edit/read files, run commands,
  send emails/WhatsApp messages, browse a specific URL, or search for current/real-time info.
- For questions like "what is X?", "how does Y work?", "can you do Z?", "explain W"
  \u2014 answer directly from your knowledge with <final>.

CRITICAL RULE \u2014 FILE ACCESS:
- You have NATIVE tools (list_files, read_file) that ONLY work inside the project workspace.
- You have MCP tools (mcp_filesystem_*) that work on ANY path on the computer.
- When the user asks about files on Desktop, Downloads, or any path OUTSIDE the project,
  SKIP the native tools entirely. Use mcp_filesystem_list_directory or mcp_filesystem_read_file directly.
- If a native tool fails with "path escapes workspace", do NOT retry it.
  Switch to the mcp_filesystem_* equivalent immediately.

CRITICAL RULE \u2014 EMAIL:
- For sending or reading emails, use mcp_gmail_* tools.
  Examples: mcp_gmail_enviar_correo, mcp_gmail_revisar_recibidos

CRITICAL RULE \u2014 PROJECT SEARCH (grep):
- To find code patterns, imports, function definitions INSIDE this project:
  use the native search tool (grep) — NOT web search, NOT delegate.
  Example: search(pattern="import flask", path=".") to find Flask imports.
- "investigate in this project" means search + read_file, NOT web search.
- Only use web_search for external/current information, not for code.

CRITICAL RULE \u2014 WEB SEARCH:
- First try the search tool of an enabled search integration (e.g. Wigolo).
- If it is not available or fails, fall back to the native `web_search`
  (DuckDuckGo, no API key needed, no setup).
- Never invent a tool name to search the web.

CRITICAL RULE \u2014 PERSISTENT MEMORY (KODAMA_MEMORY.md):
- KODAMA_MEMORY.md is a file in the workspace root that persists across sessions.
- When the user says "recuerda esto", "guarda esto", "ten en cuenta", or similar:
  Use write_file to append to or update KODAMA_MEMORY.md.
- When asked about project conventions, preferences, or past decisions,
  read KODAMA_MEMORY.md first.
- Format: plain Markdown with sections (##) for different topics.
  Example content: preferred libraries, coding conventions, project rules.
- The content of KODAMA_MEMORY.md is already injected into your system prompt
  at the start of each session — you don't need to read it unless asked.

CRITICAL RULE \u2014 DELEGATION (sub-agent):
- delegate() spawns a child agent for a COMPLEX sub-task.
- Do NOT use delegate for simple grep/search — use the native search tool directly.
- Available only for cloud and large local models.
- Single task: delegate(task="investigate X", max_steps=4).
- Parallel tasks (2-3 at once): delegate(tasks=["search A", "list B"], max_steps=3).
- Only delegate subtasks that are self-contained. The child does NOT see this conversation.
- Always review and synthesize the child's results yourself. Never return raw delegate output.
"""
    prefix = critical_rules + prefix

    # 3. Replace the "concise" rule with instructions for professional, structured answers
    prefix = prefix.replace(
        "- Keep answers concise and concrete.",
        "- Provide professional, well-structured answers using clean Markdown formatting.\n"
        "- Use section headers (## or ###) to organize information logically.\n"
        "- Use Markdown tables (| columns |) for structured data: file lists, comparisons, configs, results.\n"
        "  Example table:\n"
        "  | Archivo | Tipo | Descripci\u00f3n |\n"
        "  |---------|------|-------------|\n"
        "  | report.pdf | PDF | Informe mensual |\n"
        "- Use relevant emojis sparingly as visual cues: \U0001f4c1 folder, \U0001f4c4 file, \u2705 success, \u26a0\ufe0f warning, \u274c error, \u2139\ufe0f info, \U0001f6e0\ufe0f tool, \U0001f4ca data.\n"
        "- Start with a brief 1-2 sentence summary of what you found or did.\n"
        "- Present details in organized sections with tables or lists.\n"
        "- End with an actionable follow-up question when appropriate.\n"
        "- When using tools, explain the results in natural language \u2014 do not dump raw tool output.\n"
        "- Keep tone professional but friendly. Avoid raw JSON, code dumps, or overly technical verbosity unless explicitly asked.",
    )

    # 4. Add MCP tool examples and strategic guidance
    mcp_guide = """
- MCP tools work like any other tool — use the same <tool> JSON format, with the
  exact tool name that appears in your tools list (pattern: mcp_<server>_<tool>).

- IMPORTANT: When a native tool (list_files, read_file) says "path escapes workspace",
  it means the path is OUTSIDE the current project. Do NOT retry the native tool.
  Instead, use the filesystem integration if it is enabled.

- Tool selection guide (use an integration only if it is enabled; every available
  tool appears in your tools list):
  * Web search -> native web_search (DuckDuckGo); if a search integration is
    enabled, its own search tool first and web_search as fallback
  * Library documentation -> Context7 integration
  * Read a web page -> the fetch tool of an enabled web integration (e.g. Wigolo)
  * Browser automation -> playwright or puppeteer integration
  * Files/folders outside the project -> filesystem integration
  * Send/read emails -> gmail integration
  * Send WhatsApp -> whatsapp integration
  * GitHub operations -> github integration
  * Google Maps places/directions -> google-maps integration
  * Single investigation -> delegate(task="investigate X", max_steps=4)
  * Parallel tasks -> delegate(tasks=["task 1", "task 2", "task 3"], max_steps=3)
  * Persistent memory -> write_file(path="KODAMA_MEMORY.md", content=...)
  * Read project memory -> read_file(path="KODAMA_MEMORY.md")

- If a tool is not in your tools list, it does not exist: do not invoke it.
  Use the closest available alternative, or say the integration is not enabled.

- EDIT_FILE tool (use instead of write_file for surgical edits):
  Read the file first, then call edit_file with exact line numbers.
  Example: <tool>{"name":"edit_file","args":{"path":"src/main.py","start_line":10,"end_line":12,"new_text":"def new_function():\\n    pass"}}</tool>
  XML style (preferred for multi-line): <tool name="edit_file" path="src/main.py" start_line="10" end_line="12"><new_text>def new_function():
    pass</new_text></tool>"""
    prefix = prefix.replace(
        "Valid response examples:",
        "Valid response examples:" + mcp_guide,
    )

    return prefix

