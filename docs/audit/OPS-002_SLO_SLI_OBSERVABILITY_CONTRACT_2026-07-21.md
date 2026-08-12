# OPS-002 — SLO/SLI and observability contract (2026-07-21)

Scope note: GeoSync is a **research-verification** platform with the live-capital/venue path
frozen (OPS-001). So classic production SLOs (order-ack latency, venue uptime, fill ratio) are
**N/A by design** — this contract defines SLIs for the thing that IS in production: the
**verification pipeline** and the system's observability surface. When live execution is ever
unfrozen, a §5 live-SLO addendum is required (tracked, not faked).

## 1. Service Level Indicators (measurable today)
| SLI | definition | measurement source |
|---|---|---|
| gate-pass-rate | fraction of `scripts/ci/check_*` gates GREEN on `main` | `scripts/ci/run_all_gates.py` (gates-all-meta CI job) |
| integrity-suite pass | integrity-gates pytest pass count / total | `.gitlab-ci.yml` integrity-gates job |
| determinism | replay-hash identical across two runs of a sealed pipeline | `scripts/ci/check_reproducible_archive.py`, determinism_kit (Law T6) |
| invariant-teeth floor | # BOUND_GREEN invariants ≥ frozen floor (53) | `scripts/ci/audit_invariant_teeth.py` + baseline |
| ledger-honesty | closed⟹PASS-signed ∧ evidence present | `scripts/ci/check_remediation_ledger.py` |
| lint/type cleanliness | ruff 0, mypy 0 errors across the tree | lint CI job |

## 2. Service Level Objectives (targets on `main`)
- gate-pass-rate: **100%** of non-baseline-allowlisted gates GREEN (the meta-ratchet fails
  closed on any NEW red — the SLO is enforced, not merely reported).
- integrity-suite: **≥ 99%** pass (current 355/358; the 3 are release-context, documented).
- determinism: **100%** — a sealed pipeline MUST reproduce bit-identically (T6 is fail-closed).
- invariant-teeth floor: **≥ 53** BOUND_GREEN, never regress (ratcheted).
- ledger-honesty: **100%** — a single closed-without-PASS or dangling-evidence item is RED.
- lint/type: **0 / 0** — enforced in CI.

Error budget: because the meta-ratchet and integrity gates are **fail-closed**, the effective
error budget for the enforced SLIs is **zero on merge** — a violation blocks the pipeline rather
than spending a budget. This is stricter than a percentage SLO and matches the project's
verification-first identity.

## 3. Observability surface (what emits signal)
- `core/telemetry.py` (36 symbols) — the core telemetry/metrics collector.
- `execution/metrics.py` — execution-layer counters.
- `runtime/thermo_performance.py` — runtime thermodynamic-performance counters.
- Structured logging: kwargs-only structured logger (per the repo logging contract) — every
  clamp/repair on a physics surface is logged (PRODUCTION CODE rule in CLAUDE.md), so a silent
  numeric repair is observable, not hidden.
- Audit trail: `runtime/audit_logger.py`, `execution/audit.py`; tombstones + remediation ledger
  provide the governance-event trail (RES-014 preserves negatives).

These are the modules the RTM's NFR-001 (Observability) row now correctly binds to (fixed
2026-07-21: the mapped tests actually import `core.telemetry` / `execution.metrics`).

## 4. Alerting / gating policy
There is no paging (no live venue). The "alert" is a **RED CI gate**: the meta-ratchet, integrity
gates, ledger gate, teeth floor, and security-regression gate each fail the pipeline on breach.
`false_confidence_detector` runs advisory (TRACK-then-ENFORCE staging).

## 5. Live-SLO addendum — NOT YET APPLICABLE
Latency/uptime/fill-ratio SLOs are deliberately absent while OPS-001 (live-capital freeze) holds.
Adding them is a precondition of unfreezing, tracked under OPS-007 (deployment rehearsal) /
OPS-008 (operational-readiness review) — stated as a boundary, not faked as satisfied.

This document is the OPS-002 evidence artifact.
