"""Skills catalog and lifecycle management.

Skills are specialized system prompts that guide agent behavior.
They can be toggled on/off from the UI and are injected into the
agent's prefix when active.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("kodama")

# ── Skills directory ──────────────────────────────────────────────

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


# ── Skill catalog ─────────────────────────────────────────────────

def _load_skill_content(name: str) -> str:
    """Load skill content from a markdown file in the skills directory."""
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        logger.warning("Skill file not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8").strip()


SKILLS_CATALOG = [
    {
        "name": "debug",
        "display_name": "Debug",
        "description": "Systematic debugging process: find root cause before proposing fixes. Use when encountering any bug, test failure, or unexpected behavior.",
        "triggers": ["bug", "error", "fail", "crash", "unexpected", "wrong", "issue", "fix", "broken"],
    },
    {
        "name": "tdd",
        "display_name": "TDD",
        "description": "Test-Driven Development: write the test first, watch it fail, then write minimal code to pass. Use when implementing features or bugfixes.",
        "triggers": ["test", "implement", "feature", "bugfix", "refactor", "code"],
    },
    {
        "name": "security",
        "display_name": "Security Review",
        "description": "Security reviews and secure-by-default guidance. Identify vulnerabilities (hardcoded secrets, injection flaws, OWASP Top 10) and produce prioritized reports.",
        "triggers": ["security", "vulnerability", "injection", "xss", "sql", "auth", "secret", "owasp", "exposed", "audit"],
    },
    {
        "name": "review",
        "display_name": "Code Review",
        "description": "Systematic code review for any changeset: multi-dimensional analysis (correctness, security, quality, performance, test coverage) with severity-graded findings and cross-file impact checks.",
        "triggers": ["review", "pr", "pull request", "code review", "changeset", "diff", "changes", "audit code", "revise"],
    },
    {
        "name": "batch",
        "display_name": "Batch Processing",
        "description": "Parallel batch operations across multiple files: refactors, transformations, lint fixes, header additions. Validates a sample first, then processes with error reporting and verification.",
        "triggers": ["batch", "bulk", "mass", "all files", "every file", "multiple files", "rename", "convert all", "process all", "add to all"],
    },
    {
        "name": "scheduled_automation",
        "display_name": "Scheduled Automation",
        "description": "Create recurring automation tasks via Windows Task Scheduler. Schedule scripts to run daily, hourly, weekly, or on logon. Includes task verification and management commands.",
        "triggers": ["schedule", "automate", "every day", "every hour", "every week", "recurring", "daily", "weekly", "schtasks", "task scheduler", "background task", "run every", "cron"],
    },
    {
        "name": "rtk",
        "display_name": "RTK Token Saver",
        "description": "Compress shell command outputs (git, pytest, dir, pip, logs, etc.) by 60-90% using smart filtering, grouping, and deduplication before they enter the LLM context. Transparently pipes large outputs through rtk_filter.py.",
        "triggers": ["ahorrar tokens", "comprimir output", "filtrar salida", "rtk", "output grande", "mucho texto", "shell largo", "git status ruido", "pip list", "muchos archivos"],
    },
    {
        "name": "programming",
        "display_name": "Modo Programación",
        "description": "Perfil de trabajo de código: inspeccionar, planificar, editar de forma quirúrgica y verificar con tests antes de reportar.",
        "triggers": ["implementa", "corrige", "refactoriza", "programar", "modo programación", "código", "bug", "test", "función"],
    },
]


def get_skill(name: str) -> dict | None:
    """Return a skill definition from the catalog, with its content loaded."""
    for skill in SKILLS_CATALOG:
        if skill["name"] == name:
            content = _load_skill_content(name)
            return {**skill, "content": content}
    return None


def get_skills_catalog() -> list[dict]:
    """Return full catalog with content loaded."""
    result = []
    for skill in SKILLS_CATALOG:
        content = _load_skill_content(skill["name"])
        result.append({**skill, "content": content})
    return result


# ── SQLite helpers ────────────────────────────────────────────────

def init_skills_table(conn):
    """Create the skills table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    # Ensure all catalog skills have a row
    for skill in SKILLS_CATALOG:
        conn.execute(
            "INSERT OR IGNORE INTO skills (name, enabled) VALUES (?, 0)",
            (skill["name"],),
        )
    conn.commit()


def get_skills_status(conn) -> list[dict]:
    """Return all skills with their enabled/disabled state."""
    rows = conn.execute("SELECT name, enabled FROM skills").fetchall()
    enabled_map = {row[0]: bool(row[1]) for row in rows}
    result = []
    for skill in SKILLS_CATALOG:
        result.append({
            "name": skill["name"],
            "display_name": skill["display_name"],
            "description": skill["description"],
            "enabled": enabled_map.get(skill["name"], False),
        })
    return result


def set_skill_enabled(conn, name: str, enabled: bool):
    """Enable or disable a skill."""
    conn.execute(
        "UPDATE skills SET enabled = ? WHERE name = ?",
        (1 if enabled else 0, name),
    )
    conn.commit()


# ── Prompt injection ──────────────────────────────────────────────

def get_active_skill_prompts(conn) -> list[str]:
    """Return the full prompt text for all currently enabled skills."""
    rows = conn.execute(
        "SELECT name FROM skills WHERE enabled = 1"
    ).fetchall()
    prompts = []
    for (name,) in rows:
        skill = get_skill(name)
        if skill and skill.get("content"):
            header = f"\n\n=== SKILL: {skill['display_name']} ===\n"
            prompts.append(header + skill["content"])
    return prompts


def get_enabled_skill_names(conn) -> list[str]:
    """Return the names of the currently enabled skills."""
    rows = conn.execute("SELECT name FROM skills WHERE enabled = 1").fetchall()
    return [row[0] for row in rows]
