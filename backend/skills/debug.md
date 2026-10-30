# Debug Skill

Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes.

## Core Principle

ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

BEFORE attempting ANY fix:

1. **Read Error Messages Carefully** — Don't skip past errors. Read stack traces completely. Note line numbers, file paths, error codes.
2. **Reproduce Consistently** — Can you trigger it reliably? What are the exact steps? If not reproducible → gather more data, don't guess.
3. **Check Recent Changes** — Git diff, recent commits, new dependencies, config changes, environmental differences.
4. **Gather Evidence in Multi-Component Systems** — When system has multiple components, add diagnostic logging at each component boundary to identify WHERE it breaks before investigating WHY.
5. **Trace Data Flow** — When error is deep in call stack, trace backward to find where the bad value originates. Fix at source, not at symptom.

### Phase 2: Pattern Analysis

1. Find working examples in the same codebase
2. Read reference implementations completely — don't skim
3. Identify differences between working and broken code
4. Understand dependencies, config, and environment assumptions

### Phase 3: Hypothesis and Testing

1. Form a single hypothesis: "I think X is the root cause because Y"
2. Make the smallest possible change to test it — one variable at a time
3. Verify before continuing. If it didn't work, form a NEW hypothesis.

### Phase 4: Implementation

1. Create a failing test case first (simplest possible reproduction)
2. Implement a single fix addressing the root cause — ONE change at a time
3. Verify the fix: test passes, no other tests broken, issue resolved
4. If 3+ fixes have failed: STOP and question the architecture (pattern indicates architectural problem, not a failed hypothesis)

## Red Flags

If you catch yourself thinking any of these, STOP and return to Phase 1:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
