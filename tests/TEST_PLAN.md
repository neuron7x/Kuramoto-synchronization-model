# GeoSync Regression Test Matrix

This matrix maps core capabilities to automated coverage so reviewers can verify that
critical behaviours are exercised before a release. It is derived from the initiatives
outlined in [`docs/improvement_plan.md`](../docs/improvement_plan.md) under the "Testing
Practices" track and is intended to stay synchronized with that roadmap.

| Capability | Primary Risks Covered | Automated Suites | Key Fixtures / Data | Notes |
| --- | --- | --- | --- | --- |
| Market data ingestion | Schema drift, missing candles, duplicate ticks | `tests/integration/test_ingestion_feature_signal_pipeline.py`, `tests/unit/data/test_quality_control.py`, `tests/unit/test_ingestion_adapters.py` | `tests/fixtures/ohlcv_sample.csv`, `tests/utils/factories.py` | Integration test exercises CSV ingestion into feature frame; unit tests guard schema enforcement and adapter fallbacks. |
| Backfill & resampling | Gap detection errors, incorrect interpolation | `tests/integration/test_backfill_gap_fill.py`, `tests/unit/data/test_backfill.py`, `tests/unit/data/test_backfill_and_resampling.py` | Synthetic caches via `tests/utils/caches.py` | Validates planner coverage, idempotent application, and merged updates. |
| Feature engineering & signals | Leakage, metadata drift, inconsistent horizons | `tests/integration/test_pipeline.py`, `tests/integration/test_ingestion_feature_signal_pipeline.py`, `tests/unit/test_indicator_pipeline.py` | `tests/fixtures/synthetic_features.parquet`, randomised frames | Confirms supervised frame construction and asynchronous Ricci features. |
| Strategy evaluation | Walk-forward consistency, scoring stability | `tests/integration/test_backtest.py`, `tests/integration/test_extended_pipeline.py`, `tests/unit/test_execution_system.py::test_walkforward_evaluation` | `backtest/configs/*.yaml`, `tests/fixtures/strategy_config.yaml` | Covers end-to-end walk-forward evaluation with execution mocks. |
| Execution connectors & risk | Exchange outages, retries, risk kill-switch | `tests/integration/test_live_loop.py`, `tests/integration/test_live_runner.py`, `tests/unit/test_execution_system.py`, `tests/unit/test_risk_controls.py` | Stub connectors in `tests/utils/execution.py` | Exercises retry plans, failure plan permutations, and kill-switch semantics. |
| Indicator accelerators | Numerical stability, fallback path parity | `tests/unit/test_indicators_ricci.py`, `tests/unit/test_indicators_temporal_ricci.py`, `tests/unit/test_performance_optimizations.py` | Synthetic graphs via `tests/utils/graph_factory.py` | Ensures chunked Ricci curvature matches baseline and warns when SciPy unavailable. |
| Portfolio accounting | Unrealized PnL drift, fee application | `tests/unit/test_portfolio_accounting.py`, `tests/integration/test_backtest.py::test_apply_accounting_updates` | `tests/fixtures/accounting_transactions.csv` | Validates mark-to-market and fee adjustments inside the backtester. |
| Governance & security checks | Configuration tampering, schema regressions | `tests/security/test_role_policies.py`, `tests/unit/data/test_quality_control.py::test_validate_and_quarantine_integrates_schema`, `tests/unit/test_config_loader.py` | Policies under `security/`, schema files under `schemas/` | Prevents privileged escalation and ensures quarantined datasets respect schema contracts. |
| Performance envelopes | Regression thresholds, chunking heuristics | `tests/performance/test_indicator_portability.py`, `tests/unit/test_performance_optimizations.py`, `tests/nightly/test_heavy_workflows.py` | Performance fixtures under `tests/performance/fixtures/` | Benchmarks key algorithms and asserts guardrail metrics when optional plugins are available. |
| Resilience scenarios | Restart safety, cache recovery | `tests/integration/test_market_cassettes.py`, `tests/unit/test_kuramoto_ricci_composite.py`, `tests/nightly/test_heavy_workflows.py::test_failover_recovery` | Market cassette recordings in `tests/fixtures/market_cassettes/` | Simulates degraded network and verifies signal history idempotency. |

## How to use this matrix

1. **Before feature work** – identify the capability row(s) impacted and ensure the
   corresponding suites run in CI for your branch.
2. **During review** – reference the relevant rows in PR descriptions and document new
   coverage if you add or deprecate tests.
3. **Release readiness** – the release captain should verify every capability row has
   green builds on the target release branch. If a suite is flaky or blocked by missing
   dependencies (e.g. optional Hypothesis-based property tests), document the reason in
   the release checklist and link to follow-up remediation tasks.

Update this matrix whenever tests move, new capabilities are added, or coverage shifts.
