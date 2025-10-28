# TradePulse Internal Penetration Review — 2025-10-28

## Scope

An internal security assessment focused on Python services under `core/`.
Static application security testing (SAST) was executed with `bandit` 1.8.6
using the default profile. The review targeted high-risk constructs that could
lead to logic bypass or unsafe deserialization.

## Findings and Remediations

### 1. Assertion-Based Type Enforcement in `StrategyEngine`

- **Location:** `core/strategies/engine.py`
- **Issue:** Runtime assertions enforced the payload type for
  `StrategyEventType.SIGNAL` events. Python strips `assert` statements when the
  interpreter is invoked with optimisations (`python -O`), allowing malformed or
  malicious payloads to propagate to risk evaluation. This weakens security
  guardrails during hardened deployments.
- **Fix:** Replaced the assertion with an explicit `isinstance` check that raises
  `TypeError` when the payload is not a `StrategySignal`, ensuring validation is
  always active.

### 2. Assertion Guard in Equity Curve Sampling

- **Location:** `core/utils/metrics.py`
- **Issue:** An assertion protected against `None` values when NumPy was
  unavailable. Optimised Python builds would skip the assertion, potentially
  causing `TypeError` downstream.
- **Fix:** Added an explicit defensive check that raises `RuntimeError` if the
  list is unexpectedly missing, keeping telemetry routines safe in optimised
  environments.

### 3. Parameter Validation for `P2Quantile`

- **Location:** `core/neuro/quantile.py`
- **Issue:** Quantile bounds relied on an assertion. When stripped, invalid
  quantiles (≤0 or ≥1) could compromise statistical calculations used by ML
  pipelines.
- **Fix:** Converted the assertion into a `ValueError` guard to preserve input
  validation regardless of optimisation flags.

## Verification

- `bandit -r core`

Re-running the scanner confirms the assertion-related findings are remediated.

