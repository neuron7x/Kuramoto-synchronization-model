# Physics Module Reliability Contract

Microsoft Well-Architected reliability guidance is explicit: **expect failure,
isolate critical components, make observability visible — do not pray on
uptime.** GeoSync applies this to physics gates. A passing test proves a property
held on the cases exercised; it is *not* a statement about how the module fails,
what breaks when it does, or how to recover. That statement is this contract.

## What it enforces

Each *covered* physics module declares, in
[`governance/PHYSICS_RELIABILITY.yaml`](../../governance/PHYSICS_RELIABILITY.yaml):

| Field | Meaning |
|-------|---------|
| `invariants` | INV-* tags the module is bound to — each **must be literally present in the module source** |
| `role` | CLAUDE.md §0 gradient role: `generator` / `sustainer` / `protector` |
| `layer` | maintenance/processing layer `L0`..`L4` |
| `failure_mode` | the concrete way it produces unphysical output, grounded in the invariants' **FALSIFICATION** clause |
| `blast_radius` | named downstream consumers corrupted by the failure — not "the system" |
| `degradation_mode` | the observable degraded state that precedes hard failure |
| `recovery_command` | an executable-shaped recovery / fail-closed action, not prose |
| `fail_closed` | whether the module raises/halts on contract violation rather than silently repairing |

## Why this is "harder to lie", not "bigger"

- A `failure_mode` cannot cite an invariant the code does not actually carry —
  the checker greps the source and **fails closed** on a phantom link.
- A `recovery_command` must contain a runnable action token
  (`raise` / `return` / `rerun` / `regenerate` / `python` / `pytest` / `git` /
  `fail-closed`); aspirational prose is rejected.
- The contract **names its own backlog**: every INV-bearing module under the
  scope roots without an entry is printed by name. The artifact cannot imply
  full coverage it does not have.
- `coverage_floor` is a ratchet — covered modules may grow but never silently
  disappear.

## Running the gate

```bash
python tools/physics/check_physics_reliability.py             # human report + named backlog
python tools/physics/check_physics_reliability.py --json      # machine report
python tools/physics/check_physics_reliability.py --strict-coverage  # fail on ANY uncovered module
pytest -q tests/physics/test_physics_reliability_contract.py
```

CI runs the non-strict gate (`physics-reliability-gate`) fail-closed on the
declared entries and the ratchet. Coverage of the remaining backlog is tracked
by raising `coverage_floor` as modules are added — the same migration-backlog
pattern the Physics Kernel Gate uses for repo-wide grounding.

## Adding a module

1. Add an entry to `governance/PHYSICS_RELIABILITY.yaml` with all fields.
2. Ensure every `invariants` tag literally appears in the module source.
3. Raise `coverage_floor` to the new covered count.
4. `python tools/physics/check_physics_reliability.py && pytest -q tests/physics`.
