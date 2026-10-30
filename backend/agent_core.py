"""Relay Agent Core — vendorized from mini-coding-agent.

This module contains the essential agent infrastructure that was previously
imported from the external ``mini-coding-agent`` package. By owning this code,
Relay is fully self-contained and immune to upstream API changes.

Vendorized components:
  - Constants: MAX_TOOL_OUTPUT, MAX_HISTORY, IGNORED_PATH_NAMES, DOC_NAMES
  - Utilities: now(), clip()
  - WorkspaceContext — git-aware repo scanner
  - SessionStore — JSON-file session persistence
  - OllamaModelClient — base class for ChatModelClient
  - KodamaAgent — the full agent with prompt, tools, parsing, and memory

Original source: https://github.com/rasbt/mini-coding-agent
Copyright 2026 Sebastian Raschka — licensed under the Apache License, Version 2.0.
Vendorized on: 2026-05-22. Modified by the Relay project: prompt, tools,
parsing, session handling and workspace boundaries were adapted for Relay.
See THIRD_PARTY_NOTICES.md and LICENSES/Apache-2.0.txt at the repository root.
"""

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import http_client
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────

MAX_TOOL_OUTPUT = 4000
MAX_HISTORY = 12000
IGNORED_PATH_NAMES = {
    ".git", ".mini-coding-agent", ".kodama",
    "__pycache__", ".pytest_cache", ".ruff_cache",
    ".venv", "venv",
}
DOC_NAMES = ("AGENTS.md", "README.md", "pyproject.toml", "package.json")


# ── Utility helpers ─────────────────────────────────────────────

def now() -> str:
    """UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def clip(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """Truncate *text* to *limit* chars with a truncation notice."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def is_within_root(root, candidate) -> bool:
    """True when *candidate* resolves inside *root*.

    ``resolve()`` collapses ``..`` and symlinks before comparing, and the
    comparison requires the path separator, so a sibling directory sharing
    the prefix (``proyecto-evil`` vs ``proyecto``) is rejected.
    """
    try:
        root_path = os.path.normcase(str(Path(root).resolve()))
        candidate_path = os.path.normcase(str(Path(candidate).resolve()))
    except (OSError, ValueError):
        return False
    prefix = root_path if root_path.endswith(os.sep) else root_path + os.sep
    return candidate_path == root_path or candidate_path.startswith(prefix)


# ── Workspace context ───────────────────────────────────────────

class WorkspaceContext:
    """Scans a git repository for branch, status, commits, and project docs."""

    def __init__(self, cwd, repo_root, branch, default_branch,
                 status, recent_commits, project_docs):
        self.cwd = cwd
        self.repo_root = repo_root
        self.branch = branch
        self.default_branch = default_branch
        self.status = status
        self.recent_commits = recent_commits
        self.project_docs = project_docs

    @classmethod
    def build(cls, cwd):
        cwd = Path(cwd).resolve()

        def git(args, fallback=""):
            try:
                result = subprocess.run(
                    ["git", *args], cwd=cwd,
                    capture_output=True, text=True, check=True, timeout=5,
                )
                return result.stdout.strip() or fallback
            except Exception:
                return fallback

        # The workspace root is the folder the user selected. Git metadata
        # (branch, status, commits) is read from the repository that contains
        # it, but it never widens the sandbox: a .git in a parent directory
        # (e.g. the user's home) must not turn that parent into the root.
        repo_root = cwd

        docs = {}
        for name in DOC_NAMES:
            path = cwd / name
            if not path.exists():
                continue
            docs[str(path.relative_to(repo_root))] = clip(
                path.read_text(encoding="utf-8", errors="replace"), 1200
            )

        return cls(
            cwd=str(cwd),
            repo_root=str(repo_root),
            branch=git(["branch", "--show-current"], "-") or "-",
            default_branch=(
                git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], "origin/main")
                or "origin/main"
            ).removeprefix("origin/"),
            status=clip(git(["status", "--short"], "clean") or "clean", 1500),
            recent_commits=[line for line in git(["log", "--oneline", "-5"]).splitlines() if line],
            project_docs=docs,
        )

    def text(self):
        commits = "\n".join(f"- {line}" for line in self.recent_commits) or "- none"
        docs = "\n".join(
            f"- {path}\n{snippet}" for path, snippet in self.project_docs.items()
        ) or "- none"
        return "\n".join([
            "Workspace:",
            f"- cwd: {self.cwd}",
            f"- repo_root: {self.repo_root}",
            f"- branch: {self.branch}",
            f"- default_branch: {self.default_branch}",
            "- status:",
            self.status,
            "- recent_commits:",
            commits,
            "- project_docs:",
            docs,
        ])


# ── Session store (JSON files) ──────────────────────────────────

class SessionStore:
    """Persists agent sessions as JSON files on disk."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, session_id):
        return self.root / f"{session_id}.json"

    def save(self, session):
        path = self.path(session["id"])
        path.write_text(json.dumps(session, indent=2), encoding="utf-8")
        return path

    def load(self, session_id):
        return json.loads(self.path(session_id).read_text(encoding="utf-8"))

    def latest(self):
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime)
        return files[-1].stem if files else None


# ── Ollama model client (base for ChatModelClient) ──────────────

class OllamaModelClient:
    """Talks to Ollama's /api/generate endpoint.

    Relay's ``ChatModelClient`` (in agent_stream.py) inherits from this
    and overrides ``complete()`` to use /api/chat instead.
    """

    def __init__(self, model, host, temperature, top_p, timeout):
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.top_p = top_p
        self.timeout = timeout

    def complete(self, prompt, max_new_tokens, **kwargs):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "raw": False,
            "think": False,
            "options": {
                "num_predict": max_new_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
            },
        }
        request = urllib.request.Request(
            self.host + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with http_client.open_request(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama request failed with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Could not reach Ollama.\n"
                "Make sure `ollama serve` is running and the model is available.\n"
                f"Host: {self.host}\n"
                f"Model: {self.model}"
            ) from exc

        if data.get("error"):
            raise RuntimeError(f"Ollama error: {data['error']}")
        return data.get("response", "")


# ── Relay Agent (vendorized MiniAgent) ─────────────────────────

class KodamaAgent:
    """The core agent: prompt construction, tool execution, response parsing.

    This is a vendorized and slightly simplified version of ``MiniAgent``
    from the ``mini-coding-agent`` package. The CLI-specific code
    (build_agent, build_arg_parser, main, ask) has been removed because
    Relay uses its own ``ask_stream()`` loop in agent_stream.py.
    """

    def __init__(
        self,
        model_client,
        workspace,
        session_store,
        session=None,
        approval_policy="ask",
        max_steps=6,
        max_new_tokens=512,
        depth=0,
        max_depth=1,
        read_only=False,
        mcp_tools=None,
    ):
        self.model_client = model_client
        self.workspace = workspace
        self.root = Path(workspace.repo_root)
        self.session_store = session_store
        self.approval_policy = approval_policy
        self.max_steps = max_steps
        self.max_new_tokens = max_new_tokens
        self.depth = depth
        self.max_depth = max_depth
        self.read_only = read_only
        self.mcp_tools = mcp_tools or {}
        self.session = session or {
            "id": datetime.now().strftime("%Y%m%d-%H%M%S")
            + "-"
            + uuid.uuid4().hex[:6],
            "created_at": now(),
            "workspace_root": workspace.repo_root,
            "history": [],
            "memory": {"task": "", "files": [], "notes": []},
        }
        self.tools = self.build_tools()
        self.prefix = self.build_prefix()
        self.session_path = self.session_store.save(self.session)

    @classmethod
    def from_session(cls, model_client, workspace, session_store,
                     session_id, **kwargs):
        return cls(
            model_client=model_client,
            workspace=workspace,
            session_store=session_store,
            session=session_store.load(session_id),
            **kwargs,
        )

    # ── Memory helpers ──────────────────────────────────────────

    @staticmethod
    def remember(bucket, item, limit):
        """LRU deduplicating append to *bucket*, capped at *limit*."""
        if not item:
            return
        if item in bucket:
            bucket.remove(item)
        bucket.append(item)
        del bucket[:-limit]

    # ── Prompt construction ─────────────────────────────────────

    def build_tools(self):
        tools = {
            "list_files": {
                "schema": {"path": "str='.'"},
                "risky": False,
                "description": "List files in the workspace.",
                "run": self.tool_list_files,
            },
            "read_file": {
                "schema": {"path": "str", "start": "int=1", "end": "int=200"},
                "risky": False,
                "description": "Read a UTF-8 file by line range.",
                "run": self.tool_read_file,
            },
            "search": {
                "schema": {"pattern": "str", "path": "str='.'"},
                "risky": False,
                "description": "Search the workspace with rg or a simple fallback.",
                "run": self.tool_search,
            },
            "run_shell": {
                "schema": {"command": "str", "timeout": "int=20"},
                "risky": True,
                "description": "Run a shell command in the repo root.",
                "run": self.tool_run_shell,
            },
            "write_file": {
                "schema": {"path": "str", "content": "str"},
                "risky": True,
                "description": "Write a text file.",
                "run": self.tool_write_file,
            },
            "patch_file": {
                "schema": {"path": "str", "old_text": "str", "new_text": "str"},
                "risky": True,
                "description": "Replace one exact text block in a file.",
                "run": self.tool_patch_file,
            },
            "web_search": {
                "schema": {"query": "str", "max_results": "int=5"},
                "risky": False,
                "description": "Search the web via DuckDuckGo (no API key needed). "
                               "Works out of the box; no external search API required.",
                "run": self.tool_web_search,
            },
        }
        if self.depth < self.max_depth:
            tools["delegate"] = {
                "schema": {"task": "str", "tasks": "list[str]", "max_steps": "int=3"},
                "risky": False,
                "description": "Ask a child agent to investigate. "
                               "For a single task: task='...'. "
                               "For parallel tasks: tasks=['...', '...'] (up to 3).",
                "run": self.tool_delegate,
            }
        return tools

    def build_prefix(self):
        tool_lines = []
        for name, tool in self.tools.items():
            # Support dict tools (native/MCP) and callable tools
            if not isinstance(tool, dict):
                tool_lines.append(f"- {name}() [safe] {getattr(tool, '__doc__', '') or ''}")
                continue
            # Support both native tools (schema) and MCP tools (parameters)
            schema = tool.get("schema", tool.get("parameters", {}))
            if isinstance(schema, dict):
                fields = ", ".join(f"{key}: {value}" for key, value in schema.items() if key != "type")
            else:
                fields = str(schema)
            risk = "approval required" if tool.get("risky") else "safe"
            desc = tool.get("description", tool.get("name", name))
            tool_lines.append(f"- {name}({fields}) [{risk}] {desc}")
        tool_text = "\n".join(tool_lines)
        examples = "\n".join([
            '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":80}}</tool>',
            '<tool name="write_file" path="binary_search.py"><content>def binary_search(nums, target):\n    return -1\n</content></tool>',
            '<tool name="patch_file" path="binary_search.py"><old_text>return -1</old_text><new_text>return mid</new_text></tool>',
            '<tool>{"name":"run_shell","args":{"command":"uv run --with pytest python -m pytest -q","timeout":20}}</tool>',
            "<final>Done.</final>",
        ])
        rules = "\n".join([
            "- Use tools instead of guessing about the workspace.",
            "- Return exactly one <tool>...</tool> or one <final>...</final>.",
            "- Tool calls must look like:",
            '  <tool>{"name":"tool_name","args":{...}}</tool>',
            "- For write_file and patch_file with multi-line text, prefer XML style:",
            '  <tool name="write_file" path="file.py"><content>...</content></tool>',
            "- Final answers must look like:",
            "  <final>your answer</final>",
            "- Never invent tool results.",
            "- Keep answers concise and concrete.",
            "- If the user asks you to create or update a specific file and the path is clear, "
            "use write_file or patch_file instead of repeatedly listing files.",
            "- Before writing tests for existing code, read the implementation first.",
            "- When writing tests, match the current implementation unless the user "
            "explicitly asked you to change the code.",
            "- New files should be complete and runnable, including obvious imports.",
            "- Do not repeat the same tool call with the same arguments if it did not help. "
            "Choose a different tool or return a final answer.",
            "- Required tool arguments must not be empty. Do not call read_file, "
            "write_file, patch_file, run_shell, or delegate with args={}.",
        ])
        return "\n\n".join([
            "You are Relay, a personal AI assistant with agentic capabilities. You plan, use tools on the user's project, and ask before writing or executing.",
            "Rules:\n" + rules,
            "Tools:\n" + tool_text,
            "Valid response examples:\n" + examples,
            self.workspace.text(),
        ])

    def memory_text(self):
        memory = self.session["memory"]
        notes = "\n".join(f"- {note}" for note in memory["notes"]) or "- none"
        return "\n".join([
            "Memory:",
            f"- task: {memory['task'] or '-'}",
            f"- files: {', '.join(memory['files']) or '-'}",
            "- notes:",
            notes,
        ])

    def history_text(self):
        history = self.session["history"]
        if not history:
            return "- empty"

        lines = []
        seen_reads = set()
        recent_start = max(0, len(history) - 6)
        for index, item in enumerate(history):
            recent = index >= recent_start
            if item["role"] == "tool" and item["name"] in ("write_file", "patch_file"):
                path = str(item["args"].get("path", ""))
                seen_reads.discard(path)
            if item["role"] == "tool" and item["name"] == "read_file" and not recent:
                path = str(item["args"].get("path", ""))
                if path in seen_reads:
                    continue
                seen_reads.add(path)

            if item["role"] == "tool":
                limit = 900 if recent else 180
                lines.append(
                    f"[tool:{item['name']}] "
                    f"{json.dumps(item['args'], sort_keys=True)}"
                )
                lines.append(clip(item["content"], limit))
            else:
                limit = 900 if recent else 220
                lines.append(f"[{item['role']}] {clip(item['content'], limit)}")

        return clip("\n".join(lines), MAX_HISTORY)

    def prompt(self, user_message):
        return "\n\n".join([
            self.prefix,
            self.memory_text(),
            "Transcript:\n" + self.history_text(),
            "Current user request:\n" + user_message,
        ])

    # ── Session management ──────────────────────────────────────

    def record(self, item):
        self.session["history"].append(item)
        self.session_path = self.session_store.save(self.session)

    def note_tool(self, name, args, result):
        memory = self.session["memory"]
        path = args.get("path")
        if name in {"read_file", "write_file", "patch_file"} and path:
            self.remember(memory["files"], str(path), 8)
        note = f"{name}: {clip(str(result).replace(chr(10), ' '), 220)}"
        self.remember(memory["notes"], note, 5)

    def reset(self):
        self.session["history"] = []
        self.session["memory"] = {"task": "", "files": [], "notes": []}
        self.session_store.save(self.session)

    # ── Tool execution ──────────────────────────────────────────

    def run_tool(self, name, args):
        tool = self.tools.get(name)
        if tool is None:
            return f"error: unknown tool '{name}'"
        try:
            self.validate_tool(name, args)
        except Exception as exc:
            example = self.tool_example(name)
            message = f"error: invalid arguments for {name}: {exc}"
            if example:
                message += f"\nexample: {example}"
            return message
        if self.repeated_tool_call(name, args):
            return (
                f"error: repeated identical tool call for {name}; "
                "choose a different tool or return a final answer"
            )
        if tool["risky"] and not self.approve(name, args):
            return f"error: approval denied for {name}"
        try:
            return clip(tool["run"](args))
        except Exception as exc:
            return f"error: tool {name} failed: {exc}"

    def repeated_tool_call(self, name, args):
        tool_events = [
            item for item in self.session["history"] if item["role"] == "tool"
        ]
        if len(tool_events) < 2:
            return False
        recent = tool_events[-2:]
        return all(
            item["name"] == name and item["args"] == args for item in recent
        )

    def tool_example(self, name):
        examples = {
            "list_files": '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            "read_file": '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":80}}</tool>',
            "search": '<tool>{"name":"search","args":{"pattern":"binary_search","path":"."}}</tool>',
            "run_shell": '<tool>{"name":"run_shell","args":{"command":"uv run --with pytest python -m pytest -q","timeout":20}}</tool>',
            "write_file": '<tool name="write_file" path="binary_search.py"><content>def binary_search(nums, target):\n    return -1\n</content></tool>',
            "patch_file": '<tool name="patch_file" path="binary_search.py"><old_text>return -1</old_text><new_text>return mid</new_text></tool>',
            "delegate": '<tool>{"name":"delegate","args":{"task":"inspect README.md","max_steps":3}}</tool>',
        }
        return examples.get(name, "")

    def validate_tool(self, name, args):
        args = args or {}

        if name == "list_files":
            path = self.path(args.get("path", "."))
            if not path.is_dir():
                raise ValueError("path is not a directory")
            return

        if name == "read_file":
            path = self.path(args["path"])
            if not path.is_file():
                raise ValueError("path is not a file")
            start = int(args.get("start", 1))
            end = int(args.get("end", 200))
            if start < 1 or end < start:
                raise ValueError("invalid line range")
            return

        if name == "search":
            pattern = str(args.get("pattern", "")).strip()
            if not pattern:
                raise ValueError("pattern must not be empty")
            self.path(args.get("path", "."))
            return

        if name == "run_shell":
            command = str(args.get("command", "")).strip()
            if not command:
                raise ValueError("command must not be empty")
            timeout = int(args.get("timeout", 20))
            if timeout < 1 or timeout > 120:
                raise ValueError("timeout must be in [1, 120]")
            return

        if name == "write_file":
            path = self.path(args["path"])
            if path.exists() and path.is_dir():
                raise ValueError("path is a directory")
            if "content" not in args:
                raise ValueError("missing content")
            return

        if name == "patch_file":
            path = self.path(args["path"])
            if not path.is_file():
                raise ValueError("path is not a file")
            old_text = str(args.get("old_text", ""))
            if not old_text:
                raise ValueError("old_text must not be empty")
            if "new_text" not in args:
                raise ValueError("missing new_text")
            text = path.read_text(encoding="utf-8")
            count = text.count(old_text)
            if count != 1:
                raise ValueError(f"old_text must occur exactly once, found {count}")
            return

        if name == "delegate":
            if self.depth >= self.max_depth:
                raise ValueError("delegate depth exceeded")
            task = str(args.get("task", "")).strip()
            if not task:
                raise ValueError("task must not be empty")
            return

    def approve(self, name, args):
        if self.read_only:
            return False
        # Child agents (depth > 0) always auto-approve risky tools
        # unless they are explicitly read-only
        if self.depth > 0:
            return not self.read_only
        if self.approval_policy == "auto":
            return True
        if self.approval_policy == "never":
            return False
        try:
            answer = input(
                f"approve {name} {json.dumps(args, ensure_ascii=True)}? [y/N] "
            )
        except EOFError:
            return False
        return answer.strip().lower() in {"y", "yes"}

    # ── Response parsing ────────────────────────────────────────

    @staticmethod
    def parse(raw):
        raw = str(raw)
        # JSON-style <tool> tag
        if "<tool>" in raw and (
            "<final>" not in raw or raw.find("<tool>") < raw.find("<final>")
        ):
            body = KodamaAgent.extract(raw, "tool")
            try:
                payload = json.loads(body)
            except Exception:
                return "retry", KodamaAgent.retry_notice(
                    "model returned malformed tool JSON"
                )
            if not isinstance(payload, dict):
                return "retry", KodamaAgent.retry_notice(
                    "tool payload must be a JSON object"
                )
            if not str(payload.get("name", "")).strip():
                return "retry", KodamaAgent.retry_notice(
                    "tool payload is missing a tool name"
                )
            args = payload.get("args", {})
            if args is None:
                payload["args"] = {}
            elif not isinstance(args, dict):
                return "retry", KodamaAgent.retry_notice()
            return "tool", payload

        # XML-style <tool name="..." ...>
        if "<tool" in raw and (
            "<final>" not in raw or raw.find("<tool") < raw.find("<final>")
        ):
            payload = KodamaAgent.parse_xml_tool(raw)
            if payload is not None:
                return "tool", payload
            return "retry", KodamaAgent.retry_notice()

        # <final> tag
        if "<final>" in raw:
            final = KodamaAgent.extract(raw, "final").strip()
            if final:
                return "final", final
            return "retry", KodamaAgent.retry_notice(
                "model returned an empty <final> answer"
            )

        # Raw text fallback
        raw = raw.strip()
        if raw:
            return "final", raw
        return "retry", KodamaAgent.retry_notice(
            "model returned an empty response"
        )

    @staticmethod
    def extract_tool_calls(raw):
        """Extract every JSON-style ``<tool>...</tool>`` block from *raw*.

        Native tool-calling models (gpt-oss via Ollama) emit several calls per
        response. ``parse()`` returns only the first; ask_stream uses this to
        execute ALL of them so no call is silently dropped (a dropped call
        makes the model believe it ran — the root cause of hallucinated
        results and stuck loops).
        """
        calls = []
        for match in re.finditer(r"<tool>(.*?)</tool>", str(raw), re.DOTALL):
            try:
                payload = json.loads(match.group(1))
            except Exception:
                continue
            if not isinstance(payload, dict) or not str(payload.get("name", "")).strip():
                continue
            args = payload.get("args", {})
            if args is None:
                args = {}
            if not isinstance(args, dict):
                continue
            calls.append({"name": payload["name"], "args": args})
        return calls

    @staticmethod
    def retry_notice(problem=None):
        prefix = "Runtime notice"
        if problem:
            prefix += f": {problem}"
        else:
            prefix += ": model returned malformed tool output"
        return (
            f"{prefix}. Reply with a valid <tool> call or a non-empty "
            "<final> answer. For multi-line files, prefer "
            '<tool name="write_file" path="file.py"><content>...</content></tool>.'
        )

    @staticmethod
    def parse_xml_tool(raw):
        match = re.search(
            r"<tool(?P<attrs>[^>]*)>(?P<body>.*?)</tool>", raw, re.S
        )
        if not match:
            return None
        attrs = KodamaAgent.parse_attrs(match.group("attrs"))
        name = str(attrs.pop("name", "")).strip()
        if not name:
            return None

        body = match.group("body")
        args = dict(attrs)
        for key in (
            "content", "old_text", "new_text",
            "command", "task", "pattern", "path",
        ):
            if f"<{key}>" in body:
                args[key] = KodamaAgent.extract_raw(body, key)

        body_text = body.strip("\n")
        if name == "write_file" and "content" not in args and body_text:
            args["content"] = body_text
        if name == "delegate" and "task" not in args and body_text:
            args["task"] = body_text.strip()
        return {"name": name, "args": args}

    @staticmethod
    def parse_attrs(text):
        attrs = {}
        for match in re.finditer(
            r"""([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""", text
        ):
            attrs[match.group(1)] = (
                match.group(2) if match.group(2) is not None else match.group(3)
            )
        return attrs

    @staticmethod
    def extract(text, tag):
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start = text.find(start_tag)
        if start == -1:
            return text
        start += len(start_tag)
        end = text.find(end_tag, start)
        if end == -1:
            return text[start:].strip()
        return text[start:end].strip()

    @staticmethod
    def extract_raw(text, tag):
        start_tag = f"<{tag}>"
        end_tag = f"</{tag}>"
        start = text.find(start_tag)
        if start == -1:
            return text
        start += len(start_tag)
        end = text.find(end_tag, start)
        if end == -1:
            return text[start:]
        return text[start:end]

    # ── Path resolution ────────────────────────────────────────

    def path_is_within_root(self, resolved):
        return is_within_root(self.root, resolved)

    def path(self, raw_path):
        path = Path(raw_path)
        path = path if path.is_absolute() else self.root / path
        resolved = path.resolve()
        if not self.path_is_within_root(resolved):
            raise ValueError(f"path escapes workspace: {raw_path}")
        return resolved

    # ── Tool implementations ────────────────────────────────────

    def tool_list_files(self, args):
        path = self.path(args.get("path", "."))
        if not path.is_dir():
            raise ValueError("path is not a directory")
        entries = [
            item
            for item in sorted(
                path.iterdir(),
                key=lambda item: (item.is_file(), item.name.lower()),
            )
            if item.name not in IGNORED_PATH_NAMES
        ]
        lines = []
        for entry in entries[:200]:
            kind = "[D]" if entry.is_dir() else "[F]"
            lines.append(f"{kind} {entry.relative_to(self.root)}")
        return "\n".join(lines) or "(empty)"

    def tool_read_file(self, args):
        path = self.path(args["path"])
        if not path.is_file():
            raise ValueError("path is not a file")
        start = int(args.get("start", 1))
        end = int(args.get("end", 200))
        if start < 1 or end < start:
            raise ValueError("invalid line range")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        body = "\n".join(
            f"{number:>4}: {line}"
            for number, line in enumerate(lines[start - 1:end], start=start)
        )
        return f"# {path.relative_to(self.root)}\n{body}"

    def tool_search(self, args):
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            raise ValueError("pattern must not be empty")
        path = self.path(args.get("path", "."))

        if shutil.which("rg"):
            result = subprocess.run(
                ["rg", "-n", "--smart-case", "--max-count", "200", pattern, str(path)],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip() or result.stderr.strip() or "(no matches)"

        matches = []
        files = (
            [path]
            if path.is_file()
            else [
                item
                for item in path.rglob("*")
                if item.is_file()
                and not any(
                    part in IGNORED_PATH_NAMES
                    for part in item.relative_to(self.root).parts
                )
            ]
        )
        for file_path in files:
            for number, line in enumerate(
                file_path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if pattern.lower() in line.lower():
                    matches.append(
                        f"{file_path.relative_to(self.root)}:{number}:{line}"
                    )
                    if len(matches) >= 200:
                        return "\n".join(matches)
        return "\n".join(matches) or "(no matches)"

    def tool_run_shell(self, args):
        command = str(args.get("command", "")).strip()
        if not command:
            raise ValueError("command must not be empty")
        timeout = int(args.get("timeout", 20))
        if timeout < 1 or timeout > 120:
            raise ValueError("timeout must be in [1, 120]")
        result = subprocess.run(
            command,
            cwd=self.root,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return "\n".join([
            f"exit_code: {result.returncode}",
            "stdout:",
            result.stdout.strip() or "(empty)",
            "stderr:",
            result.stderr.strip() or "(empty)",
        ])

    def tool_write_file(self, args):
        path = self.path(args["path"])
        content = str(args["content"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"wrote {path.relative_to(self.root)} ({len(content)} chars)"

    def tool_patch_file(self, args):
        path = self.path(args["path"])
        if not path.is_file():
            raise ValueError("path is not a file")
        old_text = str(args.get("old_text", ""))
        if not old_text:
            raise ValueError("old_text must not be empty")
        if "new_text" not in args:
            raise ValueError("missing new_text")
        text = path.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count != 1:
            raise ValueError(f"old_text must occur exactly once, found {count}")
        path.write_text(
            text.replace(old_text, str(args["new_text"]), 1), encoding="utf-8"
        )
        return f"patched {path.relative_to(self.root)}"

    def tool_web_search(self, args):
        query = str(args.get("query", "")).strip()
        if not query:
            return "error: query is required"
        max_results = int(args.get("max_results", 5))
        if max_results < 1 or max_results > 20:
            max_results = 5
        try:
            from ddgs import DDGS
            results = list(DDGS().text(query, max_results=max_results))
            if not results:
                return "No se encontraron resultados."
            formatted = []
            for r in results:
                formatted.append(f"{r['title']}\n{r['href']}\n{r['body']}")
            return "\n\n---\n\n".join(formatted)
        except Exception as e:
            return f"error: web_search fallo — {e}"

    def tool_delegate(self, args):
        if self.depth >= self.max_depth:
            raise ValueError("delegate depth exceeded")

        # Parallel mode: tasks is a list of 2+ strings
        tasks_list = args.get("tasks")
        if tasks_list and isinstance(tasks_list, list) and len(tasks_list) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            cap = min(len(tasks_list), 3)
            from model_registry import detect_model_tier
            from providers import FAST
            # Fast-tier models delegate read-only: they inspect and report,
            # the parent performs the writes.
            ro = detect_model_tier(getattr(self.model_client, "model", "")) == FAST
            step_cap = min(int(args.get("max_steps", 3)), 3)
            tok_cap = min(self.max_new_tokens, 256)
            ctx = clip(self.history_text(), 300)

            def _spawn(t):
                c = KodamaAgent(self.model_client, self.workspace, self.session_store,
                                mcp_tools=self.mcp_tools, approval_policy="auto",
                                max_steps=step_cap, max_new_tokens=tok_cap,
                                depth=self.depth + 1, max_depth=self.max_depth,
                                read_only=ro)
                c.session["memory"]["task"] = t[:200]
                c.session["memory"]["notes"] = [ctx]
                if self.mcp_tools:
                    c.tools.update(self.mcp_tools)
                    c.prefix = c.build_prefix()
                return c.run_one_shot(t)

            out = []
            with ThreadPoolExecutor(max_workers=cap) as ex:
                fs = {ex.submit(_spawn, t): t for t in tasks_list[:cap]}
                for f in as_completed(fs):
                    out.append(f.result())
            return "parallel_delegate_result:\n" + "\n\n---\n\n".join(out)

        # Single-task mode (existing logic)
        task = str(args.get("task", "")).strip()
        if not task:
            raise ValueError("task must not be empty")

        from model_registry import detect_model_tier
        from providers import FAST
        model_name = getattr(self.model_client, "model", "")
        requested_steps = int(args.get("max_steps", 5))

        # Fast-tier models delegate read-only; deep-tier children may write.
        child_read_only = detect_model_tier(model_name) == FAST
        child_steps = min(requested_steps, 5)
        child_tokens = min(self.max_new_tokens, 256)

        child = KodamaAgent(
            model_client=self.model_client,
            workspace=self.workspace,
            session_store=self.session_store,
            mcp_tools=self.mcp_tools,
            approval_policy="auto",
            max_steps=child_steps,
            max_new_tokens=child_tokens,
            depth=self.depth + 1,
            max_depth=self.max_depth,
            read_only=child_read_only,
        )
        child.session["memory"]["task"] = task
        child.session["memory"]["notes"] = [clip(self.history_text(), 300)]
        if self.mcp_tools:
            child.tools.update(self.mcp_tools)
            child.prefix = child.build_prefix()

        child.session["history"] = []
        child.record({"role": "user", "content": task, "created_at": now()})

        results = []
        for step in range(child_steps):
            try:
                raw = child.model_client.complete(
                    child.prompt(task), child.max_new_tokens,
                    system_prefix=getattr(child, "prefix", ""),
                )
            except Exception as exc:
                results.append(f"step {step + 1} error: {exc}")
                break

            kind, payload = child.parse(raw)

            if kind == "tool":
                name = payload.get("name", "")
                args_dict = payload.get("args", {})
                try:
                    result = child.run_tool(name, args_dict)
                except Exception as exc:
                    result = f"error: {exc}"
                child.record({
                    "role": "tool", "name": name, "args": args_dict,
                    "content": result, "created_at": now(),
                })
                results.append(f"[{name}] {result[:500]}")
            elif kind == "retry":
                continue
            else:
                final_text = (payload or raw).strip()
                results.append(f"[final] {final_text[:500]}")
                break

        return "delegate_result:\n" + "\n".join(results)

    def run_one_shot(self, user_message):
        """Single-turn ask: model call → parse → execute. Used by delegate."""
        raw = self.model_client.complete(
            self.prompt(user_message), self.max_new_tokens
        )
        kind, payload = self.parse(raw)

        if kind == "tool":
            name = payload.get("name", "")
            args = payload.get("args", {})
            result = self.run_tool(name, args)
            return result

        return (payload or raw).strip()
