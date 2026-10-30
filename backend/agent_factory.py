"""Agent factory for Relay — creates and configures KodamaAgent instances."""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from typing import Any
from agent_core import KodamaAgent, WorkspaceContext, SessionStore, OllamaModelClient, MAX_TOOL_OUTPUT, clip, is_within_root
from prompt_builder import build_system_prompt, build_edit_file_tool
from model_registry import resolve_client, default_model
from providers import UnknownModelError, PROVIDERS, get_model_spec

logger = logging.getLogger("kodama")


def _read_files_batch(args: dict, agent_root: Path) -> str:
    """Read multiple files in parallel.

    Tool-friendly signature: accepts ``args["paths"]`` (list of file paths)
    and returns a formatted string of all file contents.
    """
    paths = args.get("paths", [])
    if not paths:
        return "error: paths list is required (e.g. {'paths': ['file1.py', 'file2.py']})"

    if not isinstance(paths, list):
        paths = [paths]

    results: dict[str, tuple[str, str]] = {}
    agent_root = Path(agent_root)

    def _read_one(p: str) -> tuple[str, str]:
        try:
            full = (agent_root / p).resolve()
            if not is_within_root(agent_root, full):
                return p, "error: path escapes workspace boundary"
            content = full.read_text(encoding="utf-8", errors="replace")
            return p, clip(content, MAX_TOOL_OUTPUT)
        except FileNotFoundError:
            return p, f"error: file not found: {p}"
        except Exception as exc:
            return p, f"error: {exc}"

    with ThreadPoolExecutor(max_workers=min(len(paths), 8)) as executor:
        futures = {executor.submit(_read_one, p): p for p in paths}
        for future in as_completed(futures):
            p, content = future.result()
            results[p] = content

    out = [f"=== {p} ===\n{results.get(p, 'error: not read')}" for p in paths]
    return "\n\n".join(out)


def _resolve_model(model: str) -> str:
    """Pick a routable model, falling back to the best available one."""
    if model:
        try:
            get_model_spec(model)  # validates against the catalog
            return model
        except UnknownModelError as exc:
            logger.warning("%s Falling back to the default model.", exc)
    fallback = default_model()
    if not fallback:
        raise RuntimeError(
            "No model available. Set DEEPSEEK_API_KEY or APINEX_API_KEY in "
            "backend/.env, or pull an Ollama cloud model."
        )
    logger.info("Using default model %s", fallback)
    return fallback


def create_agent(cwd=".", model="", approval="auto", max_steps=6,
                 max_new_tokens=1024, temperature=0.2, top_p=0.9,
                 mcp_tools=None, skill_prompts=None,
                 resume_session_id=None) -> KodamaAgent:
    """Create a KodamaAgent instance with the given configuration.

    Args:
        model: Any catalog model. Empty or unknown → ``default_model()``.
        mcp_tools: Optional dict of MCP tools to merge into the agent.
        skill_prompts: Optional list of prompt strings to inject from active skills.
        resume_session_id: Optional session ID to restore conversation history.
    """
    model = _resolve_model(model)

    # Build workspace context and session store (vendorized in agent_core)
    workspace = WorkspaceContext.build(cwd)
    store = SessionStore(Path(workspace.repo_root) / ".mini-coding-agent" / "sessions")

    # Create a temporary client so KodamaAgent.__init__ can build its prompt.
    # It is replaced with the real one below, once the agent exists.
    temp_client = OllamaModelClient(
        model=model, host=PROVIDERS["ollama"].base_url,
        temperature=temperature, top_p=top_p,
        timeout=300,
    )

    agent_kwargs = dict(
        model_client=temp_client,
        workspace=workspace,
        session_store=store,
        mcp_tools=mcp_tools,
        approval_policy=approval,
        max_steps=max_steps,
        max_depth=2,
        max_new_tokens=max_new_tokens,
    )

    if resume_session_id:
        try:
            agent = KodamaAgent.from_session(
                **agent_kwargs,
                session_id=resume_session_id,
            )
        except Exception as exc:
            logger.warning(
                "Could not resume session '%s': %s. Creating fresh agent.",
                resume_session_id, exc,
            )
            agent = KodamaAgent(**agent_kwargs)
    else:
        agent = KodamaAgent(**agent_kwargs)

    agent.model_client = resolve_client(
        model=model,
        temperature=temperature,
        top_p=top_p,
        timeout=agent.model_client.timeout,
    )

    if mcp_tools:
        agent.tools.update(mcp_tools)
        agent.prefix = agent.build_prefix()

    # Register edit_file tool (line-based surgical editing)
    agent.tools["edit_file"] = build_edit_file_tool(agent)

    # Register batch read_files tool (parallel file access)
    agent.tools["read_files"] = {
        "description": (
            "Read multiple files in parallel. Use this instead of calling read_file "
            "multiple times when you need to read several files at once. "
            "Example: read_files(paths=['src/main.py', 'src/utils.py', 'config.json'])"
        ),
        "schema": {"paths": "list[str]"},
        "risky": False,
        "run": lambda args: _read_files_batch(args, Path(agent.root)),
    }

    # Rebuild prefix so new tools appear in the model's tool list
    agent.prefix = agent.build_prefix()

    # Build the complete system prompt with critical rules, formatting, MCP guide, and skills
    agent.prefix = build_system_prompt(
        base_prefix=agent.prefix,
        skill_prompts=skill_prompts,
    )

    # ── Inject / auto-create KODAMA_MEMORY.md (persistent memory across sessions) ──
    kodama_memory_path = Path(workspace.repo_root) / "KODAMA_MEMORY.md"
    if not kodama_memory_path.exists():
        kodama_memory_path.write_text(
            "# KODAMA Memory\n\n"
            "Memoria persistente entre sesiones. "
            "Actualizado por el agente cuando el usuario dice 'recuerda esto'.\n",
            encoding="utf-8",
        )
        logger.info("Created KODAMA_MEMORY.md (seed template)")
    memory_content = kodama_memory_path.read_text(encoding="utf-8", errors="replace").strip()
    if memory_content:
        agent.prefix += (
            f"\n\n## Persistent Memory (KODAMA_MEMORY.md)\n"
            f"The user has stored the following persistent memory "
            f"(survives across sessions, updated via 'recuerda esto'):\n"
            f"{memory_content}\n"
        )
        logger.info("Loaded KODAMA_MEMORY.md (%d chars)", len(memory_content))

    return agent


