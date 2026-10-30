"""Tests for agent_stream.py — planning phase (Item 1) and smart retries (Item 6)."""

import re
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for conftest

from agent_stream import ask_stream, resolve_client, clip
from conftest import MockAgent  # type: ignore[import-untyped]


# ── Helpers ──────────────────────────────────────────────────

def event_type(events: list[dict], target: str) -> list[dict]:
    """Filter events by type."""
    return [e for e in events if e["type"] == target]


class TestDenialAndFallbacks:
    """Denegación sin reintento, final vacío y honestidad del planificador."""

    def test_denied_tool_is_not_marked_for_retry(self):
        agent = MockAgent(
            model_responses=[
                "<plan>1. Run it</plan>",
                '<tool>{"name":"run_shell","args":{"command":"ls"}}</tool>',
            ],
            parse_results=[
                ("tool", {"name": "run_shell", "args": {"command": "ls"}}),
            ],
            tool_results={"run_shell": "error: approval denied for run_shell"},
        )
        events = list(ask_stream(agent, "lista archivos"))
        results = event_type(events, "tool_result")
        assert "Do NOT retry" in results[0]["data"]["result"]
        assert "Retry 1/3" not in results[0]["data"]["result"]

    def test_empty_final_gets_a_message(self):
        agent = MockAgent(max_steps=0)
        events = list(ask_stream(agent, "hola"))
        final = event_type(events, "final")[0]["data"]["content"]
        assert final.strip()
        assert "No pude completar" in final

    def test_planner_forbids_answering_file_contents_from_memory(self):
        agent = MockAgent(
            model_responses=["<final>ok</final>"],
            parse_results=[("final", "ok")],
        )
        list(ask_stream(agent, "lee x.py"))
        assert "Never answer from memory" in agent.model_client.calls[0]


# ═══════════════════════════════════════════════════════════════
# Item 1: Planning phase
# ═══════════════════════════════════════════════════════════════

class TestPlanningPhase:
    """The planning phase injects a planning instruction on the first model call,
    extracts <plan> tags from the response, yields a 'plan' SSE event, and
    stores the plan in agent memory."""

    def test_yields_plan_event_when_plan_tags_present(self):
        """If the model output contains <plan>...</plan>, ask_stream yields a plan event."""
        agent = MockAgent(
            model_responses=[
                "<plan>1. Read file\n2. Edit it</plan>"
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
            ],
            parse_results=[("tool", {"name": "read_file", "args": {"path": "x.py"}})],
        )
        events = list(ask_stream(agent, "edit x.py"))
        plan_events = event_type(events, "plan")
        assert len(plan_events) == 1
        assert "1. Read file" in plan_events[0]["data"]["steps"]
        assert "2. Edit it" in plan_events[0]["data"]["steps"]

    def test_no_plan_event_when_no_plan_tags(self):
        """If the model output lacks <plan> tags, no plan event is yielded."""
        agent = MockAgent(
            model_responses=[
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
            ],
            parse_results=[("tool", {"name": "read_file", "args": {"path": "x.py"}})],
        )
        events = list(ask_stream(agent, "read x.py"))
        plan_events = event_type(events, "plan")
        assert len(plan_events) == 0

    def test_plan_injected_into_agent_memory(self):
        """The plan text is appended to agent.session['memory']['notes']."""
        agent = MockAgent(
            model_responses=[
                "<plan>Read first</plan>"
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
            ],
            parse_results=[("tool", {"name": "read_file", "args": {"path": "x.py"}})],
        )
        list(ask_stream(agent, "edit x.py"))
        notes = agent.session["memory"]["notes"]
        assert any("[PLAN]" in n and "Read first" in n for n in notes)

    def test_planning_only_on_first_iteration(self):
        """The planning instruction is injected only on the first model call."""
        agent = MockAgent(
            model_responses=[
                # First response: plan + tool
                "<plan>Step 1</plan>"
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                # Second response: another tool (no plan expected)
                '<tool>{"name":"write_file","args":{"path":"y.py","content":"ok"}}</tool>',
            ],
            parse_results=[
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "write_file", "args": {"path": "y.py", "content": "ok"}}),
            ],
        )
        events = list(ask_stream(agent, "do things"))
        plan_events = event_type(events, "plan")
        assert len(plan_events) == 1

    def test_event_flow_order(self):
        """The event sequence should be: start → model_response → plan → tool_call."""
        agent = MockAgent(
            model_responses=[
                "<plan>Step 1</plan>"
                '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            ],
            parse_results=[("tool", {"name": "list_files", "args": {"path": "."}})],
        )
        events = list(ask_stream(agent, "list files"))
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert "model_response" in types
        assert "plan" in types
        assert "tool_call" in types
        # plan should come before tool_call
        assert types.index("plan") < types.index("tool_call")


# ═══════════════════════════════════════════════════════════════
# Item 6: Smart retries on tool failure
# ═══════════════════════════════════════════════════════════════

class TestSmartRetries:
    """When a tool returns an error string (prefixed with 'error:'), ask_stream
    tracks retries per tool, appends retry guidance, and instructs a strategy
    change after max_retries_per_tool (3) consecutive failures."""

    def test_error_detected_and_retry_appended(self):
        """A tool result starting with 'error:' gets retry metadata appended."""
        agent = MockAgent(
            model_responses=[
                '<tool>{"name":"read_file","args":{"path":"nonexistent.py"}}</tool>',
            ],
            parse_results=[("tool", {"name": "read_file", "args": {"path": "nonexistent.py"}})],
            tool_results={"read_file": "error: invalid arguments for read_file: path is not a file"},
        )
        events = list(ask_stream(agent, "read a file"))
        tool_results = event_type(events, "tool_result")
        assert len(tool_results) == 1
        result = tool_results[0]["data"]["result"]
        # translate_error() may have replaced "error:" prefix with Spanish text,
        # but the retry metadata [SYSTEM] should still be present
        assert "Retry 1/3" in result

    def test_retry_counter_increments(self):
        """Consecutive failures of the same tool increment retry from 1/3 to 3/3."""
        agent = MockAgent(
            model_responses=[
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                "<final>giving up</final>",
            ],
            parse_results=[
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("final", "giving up"),
            ],
            tool_results={"read_file": "error: some error"},
        )
        events = list(ask_stream(agent, "read file 3 times"))
        tool_results = event_type(events, "tool_result")
        assert len(tool_results) == 3
        assert "Retry 1/3" in tool_results[0]["data"]["result"]
        assert "Retry 2/3" in tool_results[1]["data"]["result"]
        assert "Retry 3/3" in tool_results[2]["data"]["result"]

    def test_max_retries_triggers_strategy_change(self):
        """After 4 consecutive failures (> max_retries_per_tool), model is told to change strategy."""
        agent = MockAgent(
            model_responses=[
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                "<final>giving up</final>",
            ],
            parse_results=[
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("final", "giving up"),
            ],
            tool_results={"read_file": "error: some error"},
        )
        events = list(ask_stream(agent, "read file"))
        tool_results = event_type(events, "tool_result")
        # First 3: Retry 1/3, 2/3, 3/3
        assert "Retry 1/3" in tool_results[0]["data"]["result"]
        assert "Retry 2/3" in tool_results[1]["data"]["result"]
        assert "Retry 3/3" in tool_results[2]["data"]["result"]
        # 4th: Do NOT retry
        last_result = tool_results[3]["data"]["result"]
        assert "Do NOT retry" in last_result

    def test_retry_counter_resets_on_success(self):
        """A successful call between two failures resets the counter."""
        # We need different results per call. Use a list-based strategy:
        # Override MockAgent's run_tool to be call-index-aware.
        call_log = []

        class SmartMockAgent(MockAgent):
            def run_tool(self, name, args):
                call_log.append(name)
                # fail, succeed, fail → retry should be 1/3, then 0 (success), then 1/3
                if len(call_log) == 1:
                    return "error: first failure"
                elif len(call_log) == 2:
                    return "succeeded on second try"
                elif len(call_log) == 3:
                    return "error: third failure"
                return "ran tool"

        agent = SmartMockAgent(
            model_responses=[
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                '<tool>{"name":"read_file","args":{"path":"x.py"}}</tool>',
                "<final>done</final>",
            ],
            parse_results=[
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("tool", {"name": "read_file", "args": {"path": "x.py"}}),
                ("final", "done"),
            ],
        )
        events = list(ask_stream(agent, "do stuff"))
        tool_results = event_type(events, "tool_result")
        assert len(tool_results) == 3
        # First: error → Retry 1/3
        assert "Retry 1/3" in tool_results[0]["data"]["result"]
        # Second: success → no retry message
        assert "Retry" not in tool_results[1]["data"]["result"]
        assert "succeeded" in tool_results[1]["data"]["result"]
        # Third: error again → Retry 1/3 (reset after success)
        assert "Retry 1/3" in tool_results[2]["data"]["result"]


# ═══════════════════════════════════════════════════════════════
# Helper function tests
# ═══════════════════════════════════════════════════════════════

class TestClip:
    """clip() truncates text with a notice when it exceeds the limit."""

    def test_short_text_unchanged(self):
        t = "Hello, world!"
        assert clip(t, 100) == t

    def test_long_text_truncated(self):
        t = "x" * 200
        result = clip(t, 100)
        assert len(result) < len(t)
        assert "truncated" in result


class TestResolveClient:
    """resolve_client() builds the client declared by the provider registry."""

    def test_deepseek_models(self):
        from model_clients import OpenAICompatibleClient
        assert isinstance(resolve_client("deepseek-v4-flash"), OpenAICompatibleClient)

    def test_ollama_cloud_models(self):
        from agent_stream import ChatModelClient
        assert isinstance(resolve_client("gpt-oss:120b-cloud"), ChatModelClient)

    def test_case_insensitive_routing(self):
        from model_clients import OpenAICompatibleClient
        assert isinstance(resolve_client("DeepSeek-V4-PRO"), OpenAICompatibleClient)

    def test_local_ollama_model_is_rejected(self):
        """Locally-run models are not routable: Kodama no longer exposes them."""
        from providers import UnknownModelError
        with pytest.raises(UnknownModelError):
            resolve_client("qwen3.5:4b")

    def test_unknown_model_is_rejected(self):
        from providers import UnknownModelError
        with pytest.raises(UnknownModelError):
            resolve_client("totally-made-up")

# ═══════════════════════════════════════════════════════════════
# Multiple tool calls per response
# ═══════════════════════════════════════════════════════════════

class TestMultiToolCalls:
    """A single model response with several <tool> blocks must execute all of
    them (native tool-calling models like gpt-oss emit several calls per turn;
    dropping the extras makes the model believe they ran)."""

    def test_all_tool_calls_in_one_response_executed(self):
        agent = MockAgent(
            model_responses=[
                "Voy a navegar y buscar.",  # planning phase: no tags → fall through
                '<tool>{"name":"mcp_a","args":{"url":"https://x.com"}}</tool>'
                '<tool>{"name":"mcp_b","args":{"text":"Contact"}}</tool>',
                "<final>Listo</final>",
            ],
            parse_results=[
                ("tool", {"name": "mcp_a", "args": {"url": "https://x.com"}}),
                ("final", "Listo"),
            ],
        )
        events = list(ask_stream(agent, "hazlo"))

        assert agent.tool_call_count == {"mcp_a": 1, "mcp_b": 1}
        assert len(event_type(events, "tool_result")) == 2
        finals = event_type(events, "final")
        assert finals and finals[0]["data"]["content"] == "Listo"

    def test_both_calls_recorded_in_history(self):
        agent = MockAgent(
            model_responses=[
                "sin plan",
                '<tool>{"name":"a","args":{}}</tool>'
                '<tool>{"name":"b","args":{"x":1}}</tool>',
                "<final>ok</final>",
            ],
            parse_results=[
                ("tool", {"name": "a", "args": {}}),
                ("final", "ok"),
            ],
        )
        list(ask_stream(agent, "dos calls"))
        tool_entries = [h for h in agent.session["history"] if h["role"] == "tool"]
        assert [h["name"] for h in tool_entries] == ["a", "b"]

    def test_extract_tool_calls_ignores_junk_and_xml_style(self):
        from agent_core import KodamaAgent

        raw = (
            'narración <tool>{"name":"a","args":{"x":1}}</tool> '
            '<tool>{"name":"b","args":{}}</tool> '
            '<tool name="write_file" path="x.py"><content>no</content></tool> '
            "<final>ok</final>"
        )
        assert KodamaAgent.extract_tool_calls(raw) == [
            {"name": "a", "args": {"x": 1}},
            {"name": "b", "args": {}},
        ]

        raw_bad = '<tool>{"name":"a"</tool><tool>{"bad": true}</tool>'
        assert KodamaAgent.extract_tool_calls(raw_bad) == []
