<!-- SPDX-License-Identifier: MIT -->
# Structured PR preflight evidence runner — closeout

**This PR is review-ready, not production-validated.**

## Summary

The local PR preflight gate is a structured Python evidence runner
(`tools/ci/pr_preflight.py`) behind a thin shell wrapper
(`scripts/test-pr-locally.sh`). Each check emits a deterministic record into a
single JSON report with per-check stdout/stderr logs, validated against a
declarative schema and a live requirements-traceability gate. This closeout
patches the remaining fail-open paths and binds every MUST requirement to a real
test.

## Why this is needed

A shell-embedded gate could not fail closed reliably: a check that crashed, a
missing tool, or an unwritable report directory could yield a misleading green.
The runner makes the failure law explicit:

```
critical failure -> FAIL or BLOCKED -> nonzero exit -> raw logs -> JSON report -> reviewer path
```

## What changed (this closeout)

- `run_preflight` now fails closed on an **invalid root**: a non-directory root
  yields a single `invalid_root` BLOCKED check and a nonzero exit — never a PASS.
- `main` now fails closed on a **report-write failure**: if the evidence report
  cannot be written (report dir is a file / unwritable), it prints a reason to
  stderr and exits 1 with no PASS.
- New fail-closed tests: report-write failure, invalid root, exit-code↔status
  invariant, and "a SKIPPED_OPTIONAL check is never critical".
- New requirements traceability (`tools/ci/pr_preflight_requirements.json`) with
  a gate (`tests/ci/test_pr_preflight_requirements.py`) that fails if any linked
  test or code path is renamed or removed.

## Production-readiness argument

This runner is a **local, fail-closed evidence gate**, not a production release
proof. Its guarantees are bounded to: deterministic report emission, preserved
logs, nonzero exit on any critical failure/block, explicit optional skips, and a
schema + requirements contract kept in lockstep with the engine. It does **not**
assert that the broad repository CI is green, nor does it replace CI.

## Failure semantics

| Situation | Status | Exit |
| --- | --- | --- |
| all critical checks pass | PASS | 0 |
| any critical check fails | FAIL | 1 |
| missing critical tool / invalid root / unwritable report | BLOCKED | 1 |
| missing optional tool (e.g. detect-secrets) | SKIPPED_OPTIONAL (non-critical) | 0 if nothing else failed |

An unspecified status defaults to BLOCKED; the schema rejects any unknown status.

## Evidence

- Report: `artifacts/pr_preflight_pr_review/preflight_report.json` (generated via
  `python tools/ci/pr_preflight.py --root . --report-dir … --skip-install --json`).
- Targeted test results: see Test plan (exact commands + exit codes in the PR
  thread / closeout JSON).

## Test plan

```
python -m pytest \
  tests/ci/test_pr_preflight_gate.py \
  tests/ci/test_pr_preflight_engine.py \
  tests/ci/test_pr_preflight_report_schema.py \
  tests/ci/test_pr_preflight_requirements.py -q
bash -n scripts/test-pr-locally.sh
python tools/ci/pr_preflight.py --root . --report-dir artifacts/pr_preflight_pr_review --skip-install --json
```

> Note on scope: the eval-cases JSONL and invariants suites referenced by some
> earlier drafts belonged to a competing implementation (PR #948), which was
> closed; its durable value (the report schema) was reconciled here. Those
> surfaces are intentionally **not** recreated.

## Risk and rollback

- Risk: low. Changes are confined to the preflight runner + its tests + the
  requirements artifact; no production code path or dependency is touched.
- Rollback: revert this PR. The runner returns to its prior behavior; no schema
  or data migration is involved.

## Reviewer checklist

- [ ] `run_preflight` fails closed on invalid root (`invalid_root` BLOCKED).
- [ ] `main` fails closed on report-write failure (stderr reason, exit 1, no PASS).
- [ ] Targeted preflight tests pass.
- [ ] `bash -n scripts/test-pr-locally.sh` passes.
- [ ] Report schema validates a generated report; enums match engine constants.
- [ ] Every MUST requirement links to a real, passing test.

> If broad local preflight (`make pr-preflight`) exits nonzero because existing
> repository checks fail, that is preserved as evidence — the structured
> preflight surfaces existing broad-check failures instead of hiding them. This
> is expected evidence behavior, not a fake-green claim.
