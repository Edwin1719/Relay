"""Guardián del prompt: no puede nombrar herramientas que no existen.

Previene tres regresiones verificadas el 2026-10-29:

1. ``edit_file`` se anunciaba en el prompt pero no se registraba:
   ``agent_factory`` usaba ``tools.update()`` sobre el dict de la herramienta
   en vez de asignarla bajo su nombre.
2. El prompt citaba ``mcp_tavily-mcp_tavily-search`` y ``mcp_fetch_fetch``, de
   servidores que ya no están en el catálogo.
3. Ese mismo ``update()`` creaba cuatro herramientas falsas: ``schema``,
   ``description``, ``risky`` y ``run``.

Alcance: valida nombres nativos y servidores MCP. No valida el nombre exacto de
cada herramienta MCP, porque el catálogo publica solo una muestra de ellas y
comprobarlo exigiría levantar cada servidor; eso no pertenece a un test unitario.
"""

import re

import pytest

from agent_core import WorkspaceContext
from agent_factory import create_agent
from integrations_manager import CATALOG

TOOL_CALL_RE = re.compile(r'<tool>\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')
MCP_TOKEN_RE = re.compile(r"mcp_[A-Za-z0-9_-]+")

PLACEHOLDERS = {"tool_name"}
JUNK_TOOL_KEYS = {"schema", "description", "risky", "run"}
CATALOG_SERVERS = {item["server_name"] for item in CATALOG}


def _cited_names(prompt: str) -> set[str]:
    """Nombres de herramienta citados en el prompt (placeholders excluidos)."""
    names = set(TOOL_CALL_RE.findall(prompt)) | set(MCP_TOKEN_RE.findall(prompt))
    return {name.rstrip("-_") for name in names} - PLACEHOLDERS


def _unresolved_native(prompt: str, tools) -> list[str]:
    """Nombres nativos citados que no están en el registro."""
    return sorted(
        name
        for name in _cited_names(prompt)
        if not name.startswith("mcp_") and name not in tools
    )


def _unknown_mcp_servers(prompt: str) -> list[str]:
    """Servidores MCP citados que no están en el catálogo."""
    servers = {
        name[4:].split("_")[0]
        for name in _cited_names(prompt)
        if name.startswith("mcp_")
    }
    return sorted(servers - CATALOG_SERVERS)


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """Agente real con la raíz fijada a ``tmp_path``.

    ``WorkspaceContext.build()`` deduce ``repo_root`` con ``git rev-parse`` y
    un ``tmp_path`` bajo el home resolvería al home: el test escribiría
    sesiones y ``KODAMA_MEMORY.md`` fuera de ``tmp_path``.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    workspace = WorkspaceContext(
        cwd=str(tmp_path),
        repo_root=str(tmp_path),
        branch="-",
        default_branch="main",
        status="",
        recent_commits=[],
        project_docs={},
    )
    monkeypatch.setattr(
        WorkspaceContext, "build", classmethod(lambda cls, cwd: workspace)
    )
    return create_agent(cwd=str(tmp_path))


def test_prompt_guide_is_injected(agent):
    """Sin el bloque guía, los demás asserts pasarían por vacuidad."""
    assert "MCP tools work like any other tool" in agent.prefix


def test_prompt_only_names_registered_native_tools(agent):
    unresolved = _unresolved_native(agent.prefix, agent.tools)
    assert not unresolved, f"el prompt nombra herramientas no registradas: {unresolved}"


def test_prompt_only_names_catalog_mcp_servers(agent):
    unknown = _unknown_mcp_servers(agent.prefix)
    assert not unknown, f"el prompt nombra servidores MCP fuera del catálogo: {unknown}"


def test_edit_file_is_registered_and_no_junk_tools(agent):
    assert "edit_file" in agent.tools
    junk = sorted(set(agent.tools) & JUNK_TOOL_KEYS)
    assert not junk, f"herramientas falsas en el registro: {junk}"


def test_guard_detects_the_known_regressions():
    """El guardián debe seguir detectando los casos que lo motivaron."""
    prompt = "\n".join([
        '<tool>{"name":"edit_file","args":{}}</tool>',
        '<tool>{"name":"mcp_tavily-mcp_tavily-search","args":{}}</tool>',
        '<tool>{"name":"mcp_fetch_fetch","args":{}}</tool>',
    ])
    assert _unresolved_native(prompt, tools={}) == ["edit_file"]
    assert _unknown_mcp_servers(prompt) == ["fetch", "tavily-mcp"]
