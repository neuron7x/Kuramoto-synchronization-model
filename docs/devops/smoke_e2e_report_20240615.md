# Smoke and E2E Regression Execution Report — 2024-06-15

## Overview
- **Operator:** Automated agent run
- **Date:** 2024-06-15
- **Environment:** Python 3.11 (containerized CI environment)
- **Data Source:** `data/sample.csv`

## Commands Executed
1. `python -m pytest tests/e2e -m "not slow and not flaky"`
2. `python scripts/smoke_e2e.py --csv data/sample.csv --output-dir /tmp/smoke-e2e`

## Pytest E2E Smoke Suite
- **Status:** ✅ Passed
- **Runtime:** ≈2.3 s
- **Deselected:** 3 scenarios marked `slow` or `flaky`

## `scripts/smoke_e2e.py` Pipeline
- **Status:** ✅ Completed successfully
- **Seed:** `20240615`
- **Ingested Ticks:** 500
- **Backtest Summary:**
  - PnL: 49.72
  - Max Drawdown: 0.0
  - Trades: 1
- **Key Metrics:**
  - R: 0.9951
  - H: 3.3375
  - ΔH: 0.00153
  - κ̄ (kappa_mean): 0.2145
  - Hurst: 0.5796
  - Phase: neutral

## Artifacts
- CLI JSON report stored at `/tmp/smoke-e2e/results.json` (ephemeral).
- Backtest report generated at `reports/backtest_smoke_e2e_20251028T211547Z.json` during run.

## Follow-up
- No remediation required. Continue monitoring nightly automation for regressions.
