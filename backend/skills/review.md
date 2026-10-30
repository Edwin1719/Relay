# Code Review Skill

Systematic code review process for any changeset, whether it's a PR diff, local uncommitted changes, or a single file.

## Core Principle

**Silence is better than noise.** Every comment must be worth the reader's time. If unsure whether something is a problem, do NOT mention it. Low-quality feedback causes "cry wolf" fatigue.

**NO OPINIONS WITHOUT EVIDENCE.** Every finding must reference specific code at specific lines.

## Review Workflow

Execute these phases in order:

### Phase 1: Understand Scope

Determine what to review:
- If the user provides a diff or commit range, use it as the scope
- If the user provides a file path, read the file and review its current state
- If the user provides no specific target, run `git diff HEAD` to get uncommitted changes
- If the user mentions a PR number or URL that you can access via `git fetch`, create a temporary worktree for isolated review
- If nothing to review (no changes), inform the user and stop

Read all files in the diff to understand the full context before analyzing.

### Phase 2: Run Deterministic Checks

Before LLM analysis, run the project's existing tools for ground-truth results:

1. **Python projects**: run `ruff check --output-format=json` on changed files
2. **TypeScript/JavaScript**: run `tsc --noEmit` (if tsconfig.json exists) and eslint on changed files
3. **Other languages**: detect build system and run applicable linters
4. If a tool is not installed or fails, skip it and note the reason — do not fabricate results

Parse tool output into structured findings with file:line references. These are **confirmed deterministic issues** — they skip LLM verification.

### Phase 3: Multi-Dimensional Review

Analyze the code across these dimensions — report findings as **separate concerns**, not a single pass:

1. **Correctness**: Logic errors, edge cases (null/undefined, empty collections, boundary conditions), race conditions, error handling gaps, off-by-one errors
2. **Security**: Injection (command, SQL, path traversal), XSS, hardcoded secrets/credentials, SSRF, insecure deserialization, sensitive data in logs
3. **Code Quality**: Style consistency with surrounding code, naming conventions, code duplication, over-engineering, dead code, missing or misleading comments
4. **Performance & Efficiency**: Bottlenecks (N+1 queries, unnecessary loops), memory leaks, inefficient algorithms, missing caching opportunities
5. **Test Coverage**: Are new tests added for new code paths? Are critical branches (success, error, edge cases) covered? Do assertions actually verify behavior?

For each finding, read the actual code at the referenced line before reporting.

### Phase 4: Cross-File Impact Analysis

For modified functions, classes, or interfaces that are exported/used elsewhere:
1. Search for all callers/importers using the `search` tool
2. Check compatibility with modified signatures (parameter changes, return type changes, behavioral changes)
3. Pay special attention to: removed/renamed public members, new exceptions thrown, behavioral changes that could break callers

### Phase 5: Present Findings

Format findings with severity levels:

| Severity | Meaning | Action |
|----------|---------|--------|
| **Critical** | Must fix — bugs, security, data loss, build/test failures | Report immediately |
| **Suggestion** | Should fix — better patterns, potential future issues | Report with reasoning |
| **Nice to have** | Optional optimization — minor style, small perf gains | Mention briefly |

Each finding must include:
- **File:** path:line
- **Issue:** Clear description of the problem
- **Impact:** Why it matters
- **Severity:** Critical | Suggestion | Nice to have
- **Suggested fix:** Concrete code change when possible

### Verdict

- **Approve** — No Critical issues
- **Request changes** — Has Critical issues
- **Comment** — Suggestions only, no blockers

## Exclusion Criteria

Do NOT flag:
- Pre-existing issues in unchanged code (focus on the diff only)
- Style/formatting that matches surrounding codebase conventions
- Subjective "consider doing X" that aren't real problems
- Issues a linter or type checker would catch automatically
- Missing documentation unless the logic is genuinely confusing

## Red Flags

If you catch yourself thinking any of these, STOP:
- "I'll just scan this file quickly"
- "This pattern is bad but I won't check callers"
- "I know the fix without reading the full context"
- Reporting the same concern at every occurrence without grouping
