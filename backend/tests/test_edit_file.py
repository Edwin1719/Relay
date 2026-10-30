"""Tests for edit_file — surgical line-based editing tool (Item 2).

Uses ``build_edit_file_tool()`` with a minimal agent-like mock that
provides ``path()`` — no need for ``create_agent()`` or MiniAgent.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_builder import build_edit_file_tool


SAMPLE = "line1\nline2\nline3\nline4\nline5\n"


class _FakeAgent:
    """Minimal duck-typed agent with just path() for edit_file testing."""

    def __init__(self, root: str):
        self._root = Path(root).resolve()

    def path(self, p: str) -> Path:
        return (self._root / p).resolve()


@pytest.fixture
def tool_with_file(tmp_workspace):
    """Return (tool_run, test_file_path) for testing."""
    test_file = Path(tmp_workspace) / "test.py"
    test_file.write_text(SAMPLE)
    agent = _FakeAgent(tmp_workspace)
    tool = build_edit_file_tool(agent)
    yield tool["run"], test_file


# ═══════════════════════════════════════════════════════════════

class TestEditFile:

    def test_replaces_lines(self, tool_with_file):
        """Replace lines 2-4 with shorter content."""
        run, path = tool_with_file
        result = run({
            "path": "test.py", "start_line": 2, "end_line": 4,
            "new_text": "NEW2\nNEW3",
        })
        assert "patched" in result
        assert path.read_text() == "line1\nNEW2\nNEW3\nline5\n"

    def test_replaces_single_line(self, tool_with_file):
        """Replace line 3 only."""
        run, path = tool_with_file
        result = run({
            "path": "test.py", "start_line": 3, "end_line": 3,
            "new_text": "MODIFIED",
        })
        assert "patched" in result
        assert path.read_text() == "line1\nline2\nMODIFIED\nline4\nline5\n"

    def test_inserts_at_top(self, tool_with_file):
        """Replace line 1 with different content (insert at top)."""
        run, path = tool_with_file
        result = run({
            "path": "test.py", "start_line": 1, "end_line": 1,
            "new_text": "# HEADER\nline1",
        })
        assert "patched" in result
        assert path.read_text() == "# HEADER\nline1\nline2\nline3\nline4\nline5\n"

    def test_deletes_lines(self, tool_with_file):
        """Replace a range with empty string to delete lines."""
        run, path = tool_with_file
        result = run({
            "path": "test.py", "start_line": 2, "end_line": 4,
            "new_text": "",
        })
        assert "patched" in result
        assert path.read_text() == "line1\nline5\n"

    def test_expands_lines(self, tool_with_file):
        """Replace 2 lines with 5 lines (expansion)."""
        run, path = tool_with_file
        result = run({
            "path": "test.py", "start_line": 3, "end_line": 4,
            "new_text": "A\nB\nC\nD\nE",
        })
        assert "patched" in result
        assert "+3 lines" in result
        assert path.read_text() == "line1\nline2\nA\nB\nC\nD\nE\nline5\n"

    def test_file_not_found(self, tool_with_file):
        """Non-existent file returns error."""
        run, _ = tool_with_file
        result = run({
            "path": "nope.py", "start_line": 1, "end_line": 1,
            "new_text": "x",
        })
        assert result.startswith("error:")

    def test_start_line_exceeds_length(self, tool_with_file):
        """start_line > total lines returns error."""
        run, _ = tool_with_file
        result = run({
            "path": "test.py", "start_line": 999, "end_line": 999,
            "new_text": "x",
        })
        assert "exceeds" in result

    def test_invalid_range(self, tool_with_file):
        """end_line < start_line returns error."""
        run, _ = tool_with_file
        result = run({
            "path": "test.py", "start_line": 5, "end_line": 3,
            "new_text": "x",
        })
        assert result.startswith("error:")

    def test_tool_schema(self, tool_with_file):
        """Tool entry has correct schema and risk flag."""
        run, _ = tool_with_file
        # Re-build to check schema
        agent = _FakeAgent("/tmp")
        entry = build_edit_file_tool(agent)
        assert entry["risky"] is True
        assert "path" in entry["schema"]
        assert "start_line" in entry["schema"]
        assert "end_line" in entry["schema"]
        assert "new_text" in entry["schema"]
