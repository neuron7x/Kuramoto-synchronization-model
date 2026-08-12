# GeoSync architectural import contracts

Source-of-truth: [`.importlinter`](../../.importlinter)
Validator: `lint-imports` (from `import-linter`, declared as a dev dep)
Test: [`tests/workflows/test_import_boundaries.py`](../../tests/workflows/test_import_boundaries.py)

## Why this exists

Audit v2 finding **F04** (HIGH): GeoSync had 200+ Python sub-packages with
no declarative boundary contract. Architecture diagrams implied layering;
nothing enforced it. The 2026-04-26 audit recorded this as the canonical
"system borrows correctness from documentation" failure mode.

This document ships the minimum enforceable contracts that match the
*observed* layering of the current codebase, plus a tracked allowlist for
the existing cross-layer imports that the contracts cannot mechanically
heal in this PR.

## Contracts (5)

| ID | Rule |
|---|---|
| C1 `core-independence` | `core.*` may not import from `application`, `apps`, `execution`, `runtime`. |
| C2 `core-physics-hardened` | `core.physics.*` may not import from `application`, `apps`, `execution`, `runtime`, `interfaces`, `libs`. |
| C3 `core-kuramoto-hardened` | `core.kuramoto.*` may not import from `application`, `apps`, `execution`. |
| C4 `apps-no-core` | `apps.*` (the Python apps; `apps/web` is TS) may not import from `core` directly. |
| C5 `execution-no-application` | `execution.*` may not import from `application`. |

These are **forbidden-import** contracts (negative invariants). The
positive direction (e.g. "`application` may import from `core`") is left
implicit, which is the import-linter idiomatic style.

## What is NOT a contract here

- `tests` may import anything except generated private audit artefacts.
  Encoded as the absence of a contract.
- `tools` and `scripts` are excluded. Many of them are repository chores
  that legitimately import from many places; gating them here would create
  noise without surfacing real risk.
- `docs/` is excluded.

## Pre-existing violations (TRACKED, not BLESSED)

The contracts catch eight pre-existing imports that violate Contract 1.
They are listed in `[importlinter:contract:core-independence]
ignore_imports` with one-line rationale comments:

- `core.architecture_integrator.adapters` → `application.system{,_orchestrator}` (×2)
- `core.integration.adapters` → `application.microservices.{base,registry}` (×2)
- `core.integration.system_integrator` → `application.{microservices.registry,system,system_orchestrator}` (×3)
- `core.agent.registry` → `runtime.misanthropic_agent` (×1)

These are paid-down by separate hardening PRs that introduce the right
abstraction in `core` and remove the cross-layer import. **Do not add new
entries to this list to escape a real architectural regression.** Adding
an entry requires a rationale comment in the config and gets review
pushback.

## Running the validator

```bash
# CI / pre-commit:
lint-imports

# Suppress the cache (recommended in CI):
lint-imports --no-cache

# Run the test that proves the contract actually catches violations:
python -m pytest tests/workflows/test_import_boundaries.py -q
```

Exit code is `0` when all contracts are kept, non-zero when any contract
is broken or any ignore_import entry no longer matches a real path.

## How the test proves the contracts work

`tests/workflows/test_import_boundaries.py` does two things:

1. Runs `lint-imports` against the live tree and asserts exit-code 0.
2. Builds a temporary copy of the source packages + `.importlinter`,
   injects `from application import api` into a freshly-created
   `core/physics/_injected_for_lintest.py`, and asserts `lint-imports`
   exits non-zero against the temporary copy. The live tree is never
   mutated.

This is the load-bearing regression test for **Contract 2**: it proves
the contract is not just a YAML decoration — it actually flags the kind
of import it claims to forbid.

## Adding a contract

1. Decide what the new contract should forbid. Phrase it as a
   *forbidden-direction* rule (e.g. "`X.*` may not import from `Y.*`").
2. Add a `[importlinter:contract:...]` block to `.importlinter`.
3. Run `lint-imports`. If it fails with violations, decide whether to:
   (a) fix the violations now, or
   (b) add them to `ignore_imports` with a comment and open a paydown
       issue.
4. Update this document's contract table.
5. Update `tests/workflows/test_import_boundaries.py` if the contract
   needs an injection test of its own.

## Removing an ignore_imports entry

When a repayment PR removes the underlying cross-layer import:

1. Run `lint-imports --no-cache` first to confirm the ignore is now
   redundant.
2. Delete the line from `ignore_imports`.
3. Re-run `lint-imports` — both old and new state should pass.

If `import-linter` ever reports an ignore line as unused, remove it from
the config. Stale ignores hide real intent.

## Why we did not pin a stricter `core.*` rule

`core.integration.*` and `core.architecture_integrator.*` are explicitly
named integration modules — i.e. their job is to bridge layers. The audit
found that their current implementation reaches *up* into `application`,
which inverts the dependency direction. The right repayment is to
introduce a registration / port-style abstraction in `core` that the
`application` layer plugs into, so the inversion goes away. That work
belongs in a separate PR.

## Why we picked these five contracts and not more

The task brief required 3–5 contracts that reflect real architecture and
warned against overfitting. Five hits the upper bound. Each contract was
chosen because:

- it forbids a direction that **happens to be empty in the current tree**
  (so the contract is tight and meaningful, not aspirational), or
- it forbids a direction with at most a small, named set of known
  exceptions that can be tracked.

A larger contract surface invites two failure modes:

1. broad rules with broad ignore lists (decoration);
2. brittle rules that break on every renames (theatre).

We optimise for **few rules, no broad allowlists, real injection
test**.
