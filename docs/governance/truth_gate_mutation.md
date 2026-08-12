# Mutation Testing for Truth Gates (keystone)

**Research question.** Are the repository's truth gates actually enforced, or are
they green-but-decorative?

**Hypothesis.** If a gate's test suite does not fail when the gate's own logic is
broken, the gate is decorative — it proves nothing.

## Mechanism

[`tools/governance/mutate_truth_gates.py`](../../tools/governance/mutate_truth_gates.py)
injects a **named lie** into each truth gate's source (the exact failure mode the
gate exists to catch) and asserts the gate's guard test FAILS — i.e. the mutant
is killed. A surviving mutant means no test exercises that gate logic; the
harness fails closed. Each `find` anchor must occur **exactly once**, so a
refactor that moves the logic turns the mutation stale (hard fail) rather than a
silent no-op.

| Mutation | Lie injected | Gate it proves |
|----------|--------------|----------------|
| `collision_never_detected` | lane-collision detection disabled | WP-01 collision gate |
| `reliability_phantom_invariant_allowed` | a `failure_mode` may cite an invariant the code lacks | physics reliability contract |
| `dependency_floor_bypass_undetected` | a manifest floor below the security policy is not flagged | dependency all-strict gate |
| `scorecard_partial_marked_ready` | a release marked ready while a required dimension is below CI_VERIFIED | physics release scorecard gate |

Scope: the four truth gates on `main`. As more gates land, add a mutation per
gate and the harness names its own scope.

## What it already found

On first run, `reliability_phantom_invariant_allowed` **SURVIVED**: the test
`test_declared_invariants_are_present_in_module_source` re-derived the data
independently and never exercised the checker's `inv not in present` branch. The
hole was closed by making `check()` accept an injected contract and adding
`test_phantom_invariant_is_rejected_by_checker`, which kills the mutant. Score is
now 3/3. This is the whole point: the keystone earns its keep by finding holes
the guard tests miss.

## Running

```bash
python tools/governance/mutate_truth_gates.py         # mutation run (fail-closed)
python tools/governance/mutate_truth_gates.py --json
python tools/governance/mutate_truth_gates.py --list
pytest -q tests/governance/test_truth_gate_mutation.py  # harness self-test
```

The harness self-test runs a hermetic toy gate to prove the harness correctly
classifies killed / survived / stale — so the keystone itself is not decorative.
