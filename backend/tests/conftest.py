"""Shared fixtures for Kodama backend tests."""

import sys
import os
import json
import tempfile
import sqlite3
from pathlib import Path
from typing import Any
from collections import UserDict

import pytest

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Mock agent for unit-testing agent_stream helpers ────────────

class MockAgent:
    """A controllable MiniAgent-like object for testing ask_stream().

    Key behaviors are controlled via constructor parameters:
      * max_steps, max_new_tokens
      * parse_results — list of (kind, payload) tuples returned by parse()
      * model_responses — list of strings returned by model_client.complete()
      * tool_results — dict mapping tool name -> result string
    """

    def __init__(
        self,
        max_steps: int = 6,
        max_new_tokens: int = 1024,
        parse_results: list[tuple[str, Any]] | None = None,
        model_responses: list[str] | None = None,
        tool_results: dict[str, str] | None = None,
    ):
        self.max_steps = max_steps
        self.max_new_tokens = max_new_tokens
        self._parse_results = parse_results or [("final", "ok")]
        self._parse_idx = 0
        self._model_responses = model_responses or ["<final>ok</final>"]
        self._model_idx = 0
        self._tool_results = tool_results or {}
        self._tool_call_count: dict[str, int] = {}

        self.session = {
            "id": "test-session-001",
            "memory": {
                "task": "",
                "files": [],
                "notes": [],
            },
            "history": [],
        }
        self.prefix = (
            "You are Mini-Coding-Agent, a small local coding agent.\n"
            "Rules:\n- Use tools instead of guessing.\n"
            "- Return exactly one <tool>...</tool> or <final>...</final>.\n"
            "Tools:\n- list_files, read_file, search, run_shell, write_file, patch_file, delegate\n"
        )
        self.model_client = _MockModelClient(self)
        self.approval_policy = "auto"

    def prompt(self, user_message: str) -> str:
        return f"prefix\n\n{user_message}"

    def parse(self, raw: str) -> tuple[str, Any]:
        if self._parse_idx < len(self._parse_results):
            result = self._parse_results[self._parse_idx]
            self._parse_idx += 1
            return result
        return ("final", "ok")

    def run_tool(self, name: str, args: dict) -> str:
        self._tool_call_count[name] = self._tool_call_count.get(name, 0) + 1
        return self._tool_results.get(name, f"ran {name}")

    def record(self, entry: dict) -> None:
        self.session["history"].append(entry)

    def note_tool(self, name: str, args: dict, result: str) -> None:
        self.session["memory"]["notes"].append(f"{name}: {result[:100]}")

    @staticmethod
    def remember(bucket: list, item: str, limit: int) -> None:
        """LRU-like deduplicating bounded list (mirrors MiniAgent.remember)."""
        if not item:
            return
        if item in bucket:
            bucket.remove(item)
        bucket.append(item)
        del bucket[:-limit]

    def reset(self) -> None:
        self.session["memory"]["task"] = ""
        self.session["memory"]["files"] = []
        self.session["memory"]["notes"] = []
        self.session["history"] = []

    def memory_text(self) -> str:
        """Mirrors MiniAgent.memory_text() for truncation logic in ask_stream."""
        memory = self.session["memory"]
        notes = "\n".join(f"- {note}" for note in memory["notes"]) or "- none"
        return "\n".join([
            "Memory:",
            f"- task: {memory['task'] or '-'}",
            f"- files: {', '.join(memory['files']) or '-'}",
            "- notes:",
            notes,
        ])

    def history_text(self) -> str:
        """Mirrors MiniAgent.history_text() for truncation logic in ask_stream."""
        history = self.session["history"]
        if not history:
            return "- empty"
        lines = []
        for item in history:
            role = item.get("role", "?")
            content = item.get("content", "")[:200]
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    @property
    def tool_call_count(self) -> dict[str, int]:
        return dict(self._tool_call_count)


class _MockModelClient:
    """Returns pre-configured responses from MockAgent."""

    def __init__(self, agent: MockAgent):
        self._agent = agent
        self.timeout = 120  # seconds — read/written by planning phase in ask_stream()
        self.calls: list[str] = []

    @property
    def model(self) -> str:
        return "mock-model"

    def complete(self, prompt: str, max_new_tokens: int, images=None, system_prefix=None) -> str:
        self.calls.append(prompt)
        idx = self._agent._model_idx
        responses = self._agent._model_responses
        if idx < len(responses):
            self._agent._model_idx += 1
            return responses[idx]
        return "<final>done</final>"


# ── Temporary SQLite database fixture ───────────────────────────

@pytest.fixture
def tmp_db():
    """Yield a (connection, path) tuple backed by a tempfile.

    The tables are created automatically. The file is cleaned up
    after the test finishes.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    try:
        yield conn, db_path
    finally:
        conn.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


# ── Temp workspace directory fixture ────────────────────────────

@pytest.fixture
def tmp_workspace():
    """Yield a temporary directory path that serves as a workspace root.

    The directory is cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as d:
        yield d


# ── Capture log output fixture ──────────────────────────────────

@pytest.fixture
def caplog_kodama(caplog):
    """Configure caplog to capture kodama logger output."""
    import logging
    caplog.set_level(logging.INFO, logger="kodama")
    return caplog
