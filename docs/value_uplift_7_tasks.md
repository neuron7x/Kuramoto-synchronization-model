# Value Uplift Plan: 7 tasks to push engineering value to $30k+

## Goal
Increase objective engineering quality and replacement value by shipping seven high-leverage artifacts with hard acceptance gates.

## Task 1 — Independent reference solver parity
- Build second solver implementation (different numerical path).
- Acceptance: parity error <= 1e-6 on fixed corpus.
- Value effect: strong anti-regression credibility.

## Task 2 — Property-based invariant suite
- Add Hypothesis-based tests for wrap, monotonic guard, lock semantics, determinism under seeded async.
- Acceptance: >= 1,000 generated cases / profile.
- Value effect: defect discovery depth.

## Task 3 — CI invariant gate
- Fail pipeline on invariant drift (monotonic rate drop, lock-rate explosion, parity mismatch).
- Acceptance: mandatory gate on default branch.
- Value effect: production confidence.

## Task 4 — Benchmark matrix + baseline snapshots
- Add reproducible matrix across gain/dt/jitter/dropout/topology families.
- Acceptance: JSON baseline + diff threshold checks.
- Value effect: measurable scalability evidence.

## Task 5 — Regime predictor calibration
- Add Brier score / ECE / confusion matrix for forecast layer.
- Acceptance: calibration metrics persisted and thresholded.
- Value effect: model governance maturity.

## Task 6 — Failure-injection protocol
- Simulate node loss, delayed replay, re-entry storms, stale baseline corruption.
- Acceptance: lock/recovery behavior matches declared runbook.
- Value effect: reliability under adversarial conditions.

## Task 7 — One-command reproducibility pack
- Single command creates artifacts: benchmarks, audits, valuation, calibration, and summary report.
- Acceptance: deterministic outputs under fixed seeds.
- Value effect: transferability + auditability + commercial readiness.

## Financial framing (engineering replacement-cost)
If each task is executed to acceptance with documentation and automated gates, projected replacement-cost uplift reaches/exceeds the $30k target in 2026 terms (scenario dependent).
