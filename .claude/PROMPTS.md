# Claude Code Prompt Templates — Physics-Grounded Tasks

> Copy-paste these when delegating to Claude Code.
> The key insight: Claude Code reads CLAUDE.md automatically, but you
> still need to ACTIVATE the physics reasoning with the right framing.

---

## Template 1: Write Physics Tests for Module

```
Task: Write physics-grounded tests for [MODULE_PATH].

Before writing any code:
1. Read .claude/physics/INVARIANTS.yaml — find ALL invariants for this module
2. Read .claude/physics/[THEORY]_THEORY.md for the relevant theory
3. Read .claude/physics/TEST_TAXONOMY.md for test type guidance
4. Read .claude/physics/EXAMPLES.md for before/after patterns

Requirements:
- Every test function docstring MUST include INV-* reference
- Every assertion error message MUST include: invariant ID, expected, observed, why
- P0 invariants first, then P1, then P2
- Use hypothesis/property-based testing for universal invariants
- Use finite-size-aware thresholds (ε = C/√N, not magic numbers)

After writing, run: python .claude/physics/validate_tests.py [TEST_FILE]
Fix any issues before presenting results.

Report which invariants you tested and which theory file you consulted.
```

---

## Template 2: Fix Failing Physics Test

```
Task: Fix the failing test in [TEST_FILE], function [FUNCTION_NAME].

Before touching code:
1. Read the test — does it have an INV-* reference in docstring?
2. If yes → read that invariant in .claude/physics/INVARIANTS.yaml
3. Read the relevant theory in .claude/physics/[THEORY]_THEORY.md

Determine: is the PHYSICS wrong (implementation bug) or is the TEST wrong?
- If implementation violates the invariant → fix the implementation
- If test uses wrong threshold/method → fix the test
- NEVER "fix" by loosening a physics bound without explaining WHY

If the test has no INV-* reference, it needs a rewrite, not just a fix.
Apply the patterns from .claude/physics/EXAMPLES.md.
```

---

## Template 3: Add Physics Validation to Existing Module

```
Task: Add physics validation to [MODULE_PATH].

Step 1: Read the module source. Identify what physical quantities it computes.
Step 2: Read .claude/physics/INVARIANTS.yaml — map quantities to invariants.
Step 3: For each invariant, determine if a test already exists:
        grep -r "INV-[relevant]" tests/
Step 4: Write MISSING tests following .claude/physics/TEST_TAXONOMY.md.
Step 5: Run python .claude/physics/validate_tests.py [TEST_DIR]

Coverage target:
- 100% of P0 invariants must have at least one test
- 80% of P1 invariants should have tests
- P2 is optional but appreciated

Report: table of invariant → test function → pass/fail status.
```

---

## Template 4: Refactor Tests from Code-Level to Physics-Level

```
Task: Refactor [TEST_FILE] from code-level to physics-level tests.

Current state: tests check numbers and shapes, not physics.
Target state: every test checks a specific physical invariant.

Process:
1. Read .claude/physics/EXAMPLES.md — study the before/after patterns
2. Read .claude/physics/INVARIANTS.yaml — find applicable invariants
3. For each existing test function:
   a. What is it actually checking?
   b. Does this correspond to a physics invariant?
   c. If yes → rewrite with INV-* reference, theory-derived thresholds, 
      and proper error messages
   d. If no → it's a shape/type test, mark as non-physics and leave as-is

4. Add MISSING invariant tests that don't exist yet
5. Run validate_tests.py to confirm

Preserve: all existing test semantics. Don't break what works.
Add: physics grounding to what already passes.
```

---

## Template 5: Physics Contract Review

```
Task: Review [MODULE_PATH] for physics contract compliance.

Check each physical computation against .claude/physics/INVARIANTS.yaml:

For each invariant that applies to this module:
1. Is the invariant satisfied by the implementation? 
   (Read theory file to understand what "satisfied" means)
2. Is there a test that would CATCH a violation?
3. Is the test using correct thresholds and methods?

Output format:
| Invariant | Satisfied? | Test exists? | Test quality | Notes |
|-----------|-----------|-------------|-------------|-------|
| INV-K1    | ✅        | ✅          | P0 correct  |       |
| INV-K2    | ✅        | ❌          | MISSING     | Need convergence test |
| ...       |           |             |             |       |

For any MISSING tests, write them following TEST_TAXONOMY.md.
For any WRONG tests, fix them following EXAMPLES.md patterns.
```

---

## Template 6: New Physics Module Implementation

```
Task: Implement [NEW_MODULE] with physics grounding.

Before writing implementation:
1. Define the physics contract:
   - What physical quantities does this module compute?
   - What invariants MUST hold? (Add to .claude/physics/INVARIANTS.yaml)
   - What are the falsification criteria?
   - What are common implementation bugs?

2. Write the INVARIANTS first (add to INVARIANTS.yaml)
3. Write P0 tests FIRST (test-driven by physics)
4. Then implement the module to PASS the physics tests
5. Add P1 and P2 tests
6. Run validate_tests.py

The implementation is correct when ALL P0 invariants pass.
Not when the code runs. Not when it returns a number.
When the physics holds.
```

---

## Anti-Patterns: What NOT to Tell Claude Code

❌ "Write tests for this module" (no physics activation)
❌ "Make sure all tests pass" (passes != correct)
❌ "Increase test coverage to 90%" (coverage ≠ physics coverage)
❌ "Fix this test by adjusting the threshold" (may hide physics violation)

✅ "Write physics-grounded tests for this module using the invariants in .claude/physics/"
✅ "This test fails — determine if it's a physics violation or a test bug"
✅ "Add missing P0 invariant tests for the Kuramoto module"
✅ "Review this module for physics contract compliance"
