"""Streaming wrapper around KodamaAgent — SSE event loop and re-exports.

Layer map:
  prompt_builder.py: build_system_prompt, build_edit_file_tool,
    translate_error, estimate, truncate
  model_registry.py: ChatModelClient, resolve_client, detect_model_tier,
    list_ollama_models, list_available_models, switch_model
  agent_factory.py: create_agent
"""

import re
import logging

from agent_core import clip, now, KodamaAgent
from prompt_builder import (
    translate_error, estimate_prompt_tokens, truncate_conversation_history,
)
from agent_factory import create_agent
from model_registry import (
    list_available_models, switch_model, resolve_client, ChatModelClient,
    build_ollama_tools,
)
from model_clients import BillingError

logger = logging.getLogger("kodama")

MAX_TOOL_OUTPUT = 6000
max_retries_per_tool = 3


# ── Post-tool validation ──────────────────────────────────────

def verify_tool_result(agent, name, args, result):
    """Post-execution validation for critical tools.

    Returns (result, is_valid). If is_valid is False, *result* has been
    augmented with a ``[VERIFY]`` warning or an ``error:`` prefix so the
    model knows the tool may not have worked as expected.

    Latency: <3ms per call. Only touches the filesystem for write/read tools.
    """
    # Never re-validate an already-failed tool
    if isinstance(result, str) and result.startswith("error:"):
        return result, False

    try:
        # ── write_file ────────────────────────────────────
        if name == "write_file":
            target = agent.path(args["path"])
            if not target.exists():
                return (
                    f"{result}\n\n[VERIFY] WARNING: file '{args['path']}' "
                    f"does not exist after write_file. The content may not "
                    f"have been saved. Retry with the correct path.",
                    False,
                )
            expected = str(args.get("content", ""))
            actual = target.read_text(encoding="utf-8", errors="replace")
            if len(expected) > 50 and len(actual) < len(expected) * 0.5:
                return (
                    f"{result}\n\n[VERIFY] WARNING: written content "
                    f"({len(actual)} chars) is much shorter than expected "
                    f"({len(expected)} chars). The file may be truncated. "
                    f"Rewrite the file completely.",
                    False,
                )

        # ── patch_file ────────────────────────────────────
        elif name == "patch_file":
            target = agent.path(args["path"])
            if not target.exists():
                return f"error: file '{args['path']}' does not exist — cannot patch", False

        # ── read_file ─────────────────────────────────────
        elif name == "read_file":
            target = agent.path(args["path"])
            if not target.exists():
                return f"error: file '{args['path']}' does not exist", False
            if target.stat().st_size == 0:
                return (
                    f"{result}\n\n[VERIFY] NOTE: file '{args['path']}' is empty.",
                    True,  # valid but worth noting
                )

        # ── run_shell ─────────────────────────────────────
        elif name == "run_shell":
            if isinstance(result, str):
                lower = result.lower()
                # Common shell error indicators
                if any(
                    marker in lower
                    for marker in (
                        "command not found",
                        "permission denied",
                        "cannot find",
                        "is not recognized",
                        "no such file",
                        "error:",
                        "traceback",
                        "exception",
                    )
                ):
                    return (
                        f"{result}\n\n[VERIFY] Shell command may have failed. "
                        f"Check the output above for errors before proceeding.",
                        False,
                    )

        # ── MCP tools ─────────────────────────────────────
        elif name.startswith("mcp_"):
            if isinstance(result, str) and result.strip() == "":
                return (
                    "error: MCP tool returned empty result — "
                    "the server may be disconnected or the query returned nothing.",
                    False,
                )

    except Exception as exc:
        logger.warning("verify_tool_result failed for %s: %s", name, exc)

    return result, True


# ── ask_stream ──────────────────────────────────────────────

def ask_stream(agent, user_message, images=None):
    """Run the agent's ask() loop but yield SSE events for each step.

    Enhanced with:
      - Planning phase (Item 1): model generates a plan before executing tools.
        The plan is injected into agent memory so subsequent iterations have context.
        Small models (<10B local) use a lightweight ~400 tok prompt instead
        of the full ~3000 tok prefix for faster planning decisions.
      - Smart retries (Item 6): failed tool calls (error strings returned by
        run_tool) are tracked per tool; after 3 consecutive failures the model
        is instructed to change strategy.
      - Multimodal: optional *images* (list of base64 strings) are passed
        to the model client for vision-capable models (e.g. gemma3:4b).

    Yields dicts:
      {"type": "start", "data": {"max_steps": N}}
      {"type": "plan", "data": {"steps": "..."}}
      {"type": "model_response", "data": {"raw": "..."}}
      {"type": "tool_call", "data": {"name": "...", "args": {...}}}
      {"type": "tool_result", "data": {"name": "...", "result": "..."}}
      {"type": "final", "data": {"content": "..."}}
      {"type": "error", "data": {"message": "..."}}
    """
    memory = agent.session["memory"]
    if not memory["task"]:
        memory["task"] = clip(user_message.strip(), 300)

    agent.record({"role": "user", "content": user_message, "created_at": now()})

    tool_steps = 0
    attempts = 0
    max_attempts = max(agent.max_steps * 3, agent.max_steps + 4)

    # ── Item 6: Track retries per tool ──
    tool_retries = {}
    max_retries_per_tool = 3

    # ── Item 1: Planning phase runs once per user message ──
    planning_done = False

    # Bump token budget when images are attached (multimodal descriptions need more room)
    effective_max_tokens = agent.max_new_tokens
    if images:
        effective_max_tokens = max(agent.max_new_tokens, 2048)

    # ── Native tool calling for Ollama ──
    # Ollama cloud proxies are trained for OpenAI-style tool_calls and do not
    # reliably emit Relay's <tool> text protocol. Pass the tools natively to
    # /api/chat and translate the returned tool_calls into <tool> JSON so
    # parse() stays unchanged. OpenAI-compatible providers keep the text
    # protocol, which DeepSeek follows reliably.
    native_tools = None
    if isinstance(agent.model_client, ChatModelClient):
        native_tools = build_ollama_tools(agent.tools)

    yield {"type": "start", "data": {"max_steps": agent.max_steps}}

    final = ""  # Ensure final is always defined, even if the loop exits via step limit

    while tool_steps < agent.max_steps and attempts < max_attempts:
        attempts += 1

        # ── Planning phase (first iteration only) ──
        if not planning_done:
            planning_done = True
            plan_prompt = (
                agent.prefix + "\n\n"
                "[SYSTEM] Decide how to handle this request:\n"
                "- If you can answer from your own knowledge, respond with <final>your answer</final>\n"
                "- If the request requires tools (files, commands, search, email, etc.), "
                "output a step-by-step plan inside <plan>...</plan> tags.\n"
                "- Never answer from memory about a file's contents: if the request "
                "mentions a file, path or project action, you MUST output a <plan>.\n"
                "Example plan: <plan>1. Read src/config.py\n2. Modify line 42</plan>\n"
                "Do NOT call tools inside <plan> tags. No explanations outside the tags.\n"
                f"User request: {user_message}"
            )
            # Shorter timeout for the plan call: if planning stalls, skip it
            # and go straight to the execution loop.
            original_timeout = agent.model_client.timeout
            agent.model_client.timeout = 60
            try:
                raw = agent.model_client.complete(plan_prompt, effective_max_tokens, images=images)
            except BillingError:
                raise
            except Exception as exc:
                logger.warning("Planning phase failed (%s). Proceeding without plan.", exc)
                yield {"type": "plan", "data": {"steps": translate_error("(planning skipped: %s)" % str(exc))}}
                continue
            finally:
                agent.model_client.timeout = original_timeout

            yield {"type": "model_response", "data": {"raw": raw}}

            # Check for direct <final> answer (simple question — no tools needed)
            final_match = re.search(r'<final>(.*?)</final>', raw, re.DOTALL | re.IGNORECASE)
            if final_match:
                final = final_match.group(1).strip()
                yield {"type": "final", "data": {"content": final}}
                agent.record({
                    "role": "assistant",
                    "content": final,
                    "created_at": now(),
                })
                return

            # Check for <plan> (complex request — needs tools)
            plan_match = re.search(r'<plan>(.*?)</plan>', raw, re.DOTALL | re.IGNORECASE)
            if plan_match:
                plan_text = plan_match.group(1).strip()
                # Parse numbered steps for checklist rendering in the UI
                step_lines = [s.strip() for s in plan_text.split('\n') if s.strip()]
                steps = [{"text": s, "done": False} for s in step_lines]
                yield {"type": "plan", "data": {"steps": plan_text, "checklist": steps}}
                # Inject plan into agent memory so execution loop has context
                agent.session["memory"]["notes"].append(f"[PLAN] {plan_text[:500]}")

            # Record the plan in conversation history for continuity
            plan_content = plan_match.group(1).strip() if plan_match else "(no explicit plan)"
            agent.record({
                "role": "assistant",
                "content": f"[Plan]\n{plan_content}",
                "created_at": now(),
            })
            continue  # Next iteration → normal execution with plan in memory

        # Normal model call: full prompt with conversation history + plan in memory notes
        # Stream when the client supports it, for incremental feedback.
        stream_kwargs = {}
        if native_tools is not None:
            stream_kwargs["tools"] = native_tools

        if hasattr(agent.model_client, 'complete_stream'):
            full_raw = ""
            for chunk in agent.model_client.complete_stream(
                agent.prompt(user_message), effective_max_tokens, images=images,
                system_prefix=getattr(agent, 'prefix', ''),
                **stream_kwargs,
            ):
                full_raw += chunk
                yield {"type": "model_response", "data": {"chunk": chunk}}
            raw = full_raw
        else:
            raw = agent.model_client.complete(
                agent.prompt(user_message), effective_max_tokens, images=images,
                system_prefix=getattr(agent, 'prefix', ''),
                **stream_kwargs,
            )
            yield {"type": "model_response", "data": {"raw": raw}}

        # Extract plan if present in normal response (unusual but harmless)
        plan_match = re.search(r'<plan>(.*?)</plan>', raw, re.DOTALL | re.IGNORECASE)
        if plan_match:
            plan_text = plan_match.group(1).strip()
            yield {"type": "plan", "data": {"steps": plan_text}}
            agent.session["memory"]["notes"].append(f"[PLAN] {plan_text[:500]}")

        kind, payload = agent.parse(raw)

        if kind == "tool":
            # Native tool-calling models (gpt-oss via Ollama) emit several
            # <tool> calls per response. Execute ALL of them so none is
            # dropped — a dropped call makes the model believe it ran,
            # which is the root cause of hallucinated results and stuck loops.
            calls = KodamaAgent.extract_tool_calls(raw) or [payload]
            for call in calls:
                tool_steps += 1
                if tool_steps > agent.max_steps:
                    break
                name = call.get("name", "")
                args = call.get("args", {})

                # Mark slow tools as background tasks so the UI shows progress
                SLOW_TOOLS = {"run_shell", "write_file", "mcp_tavily-mcp_tavily-search",
                              "mcp_playwright", "mcp_puppeteer", "mcp_filesystem"}
                is_slow = name in SLOW_TOOLS or name.startswith("mcp_")
                if is_slow:
                    yield {"type": "background_start", "data": {"name": name, "args": args}}

                yield {"type": "tool_call", "data": {"name": name, "args": args}}

                # ── Item 6: Detect tool failure and track retries ──
                result = agent.run_tool(name, args)

                # ── Post-tool validation: verify critical tools actually worked ──
                result, _verified = verify_tool_result(agent, name, args, result)

                if is_slow:
                    yield {"type": "background_result", "data": {"name": name, "status": "done"}}
                is_error = isinstance(result, str) and result.startswith("error:")
                denied = isinstance(result, str) and result.startswith("error: approval denied")
                if denied:
                    result = translate_error(result) + (
                        "\n[SYSTEM] The user denied this action. Do NOT retry it; "
                        "propose an alternative or ask the user."
                    )
                elif is_error:
                    # Translate technical error prefix before appending retry metadata
                    result = translate_error(result)
                    tool_retries[name] = tool_retries.get(name, 0) + 1
                    retry_count = tool_retries[name]
                    if retry_count > max_retries_per_tool:
                        result += (
                            f"\n[SYSTEM] This tool has failed {retry_count} times. "
                            "Do NOT retry this tool with the same approach. "
                            "Use a completely different strategy or return a final answer."
                        )
                    else:
                        result += (
                            f"\n[SYSTEM] Retry {retry_count}/{max_retries_per_tool} "
                            f"for '{name}'. Fix the parameters and try again."
                        )
                else:
                    tool_retries[name] = 0  # reset retry counter on success

                agent.record({
                    "role": "tool",
                    "name": name,
                    "args": args,
                    "content": result,
                    "created_at": now(),
                })
                agent.note_tool(name, args, result)

                yield {"type": "tool_result", "data": {"name": name, "result": result}}
            continue

        if kind == "retry":
            agent.record({
                "role": "assistant",
                "content": payload,
                "created_at": now(),
            })
            continue

        final = (payload or raw).strip()
        agent.record({
            "role": "assistant",
            "content": final,
            "created_at": now(),
        })
        agent.remember(memory["notes"], clip(final, 220), 5)
        truncate_conversation_history(agent)
        yield {"type": "final", "data": {"content": final}}
        return

    if not final:
        final = (
            f"No pude completar la tarea en {agent.max_steps} pasos. "
            "Dime cómo continuar o reformula la petición."
        )
    agent.record({"role": "assistant", "content": final, "created_at": now()})
    truncate_conversation_history(agent)
    yield {"type": "final", "data": {"content": final}}


