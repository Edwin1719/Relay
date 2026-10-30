# TDD Skill

CRITICAL: You MUST follow the Red-Green-Refactor cycle IN ORDER. Do NOT skip steps. Do NOT show implementation before the test.

## Core Rule

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**
If you didn't watch the test fail, you don't know if it tests the right thing.

Writing code before the test is a VIOLATION. Delete it and start over.

## Strict Response Protocol

Your response MUST follow this structure in THIS order:

### Step 1 — RED: Show the test file
Show the test file content that defines the expected behavior. The test imports a function that does NOT exist yet.

### Step 2 — VERIFY RED: Execute the test
Run the test. Show that it FAILS with the expected error (function not found, assertion failed, etc.).

### Step 3 — GREEN: Show the implementation
Write the MINIMAL code needed to pass the test. No extra features.

### Step 4 — VERIFY GREEN: Execute the test again
Run the test and show that it now PASSES.

### Step 5 — REFACTOR (optional)
Only if needed. Keep tests green.

## IMPORTANT: Workspace state

If files from a previous task already exist in the workspace, you MUST:
- Read them first to understand what exists
- Delete or overwrite them if they are NOT relevant to the current task
- Start the TDD cycle fresh: delete old test files and implementation files first

## DO NOT:
- Show the implementation before the test
- Skip test execution
- Write multiple tests at once (one per cycle)
- Add features beyond what the test requires
- Say "I'll write the test after" — this is a violation
- Get stuck in a loop — after VERIFY RED, ALWAYS proceed to GREEN

## Red Flags

If you catch yourself doing any of these, STOP:
- Writing code before the test
- Explaining the implementation before showing the failing test
- Skipping test execution
- Adding extra features not required by the test
