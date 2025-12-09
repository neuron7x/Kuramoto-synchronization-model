# TradePulse Test Plan - Current Reality vs Aspirations

This document maps test coverage across TradePulse capabilities. **As of December 2025**, 
we have consolidated to a minimal, always-green CI pipeline focused on the core engine.

## Status Legend
- ✅ **ENFORCED NOW** - Running in `.github/workflows/release-gate.yml` (required for merge)
- ⚠️ **IMPLEMENTED BUT NOT ENFORCED** - Tests exist but not in release gate (too slow/flaky)
- 📋 **PLANNED** - Aspirational, not yet implemented or not yet stable

---

## Implemented Now (CI Enforced)

These tests run in the release-gate workflow and MUST pass for merge:

### Core Engine Tests
| Capability | Test Files | Status |
|-----------|------------|--------|
| **Backtest unit tests** | `tests/unit/backtest/` | ✅ ENFORCED |
| **Execution unit tests** | `tests/unit/execution/` | ✅ ENFORCED |
| **Execution integration** | `tests/execution/` | ✅ ENFORCED |
| **Core runtime** | `tests/core/` (excluding agent/orchestrator) | ✅ ENFORCED |
| **Backtest integration** | `tests/integration/test_backtest.py` | ✅ ENFORCED |

### Code Quality
| Check | Tool | Status |
|-------|------|--------|
| **Python linting** | ruff, black | ✅ ENFORCED |
| **Type checking (core)** | mypy on core modules | ✅ ENFORCED |

**Exclusions:** Tests marked as `slow`, `heavy_math`, `nightly`, or `flaky` are NOT run in release gate.

---

## Implemented But Not Enforced (Exists, Too Heavy for Gate)

These capabilities have tests but are excluded from the release gate due to speed/flakiness:

### Previous Comprehensive Matrix

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

### Legacy Capabilities (Aspirational)
| Capability | Status | Notes |
|-----------|--------|-------|
| Market data ingestion | ⚠️ Implemented | Not in release gate - too many dependencies |
| Backfill & resampling | ⚠️ Implemented | Not in release gate - flaky |
| Feature engineering & signals | ⚠️ Implemented | Not in release gate - heavy |
| Strategy evaluation | ⚠️ Implemented | Partially covered by enforced backtest tests |
| Execution connectors & risk | ⚠️ Implemented | Partially covered by enforced execution tests |
| Indicator accelerators | ⚠️ Implemented | Not in release gate - optional dependencies |
| Portfolio accounting | ⚠️ Implemented | Partially covered by enforced execution tests |
| Governance & security checks | ⚠️ Implemented | Separate security workflow |
| Performance envelopes | ⚠️ Implemented | Not in release gate - experimental |
| Resilience scenarios | ⚠️ Implemented | Not in release gate - slow |

---

## Planned (Future Roadmap)

These items are aspirational goals from `docs/improvement_plan.md`:

- 📋 Property-based testing with Hypothesis (exists but flaky)
- 📋 Mutation testing enforcement (90% kill rate)
- 📋 Coverage enforcement (98% for critical modules) 
- 📋 Full E2E scenarios with docker-compose
- 📋 Golden dataset regression tests
- 📋 Performance budget enforcement

---

## How to Use This Plan

### For Developers
1. **Before pushing:** Run the release gate locally:
   ```bash
   # See docs/RELEASE_GATES.md for exact commands
   make test  # or use the pytest command from RELEASE_GATES.md
   ```
2. **For feature work:** If your changes touch core engine, ensure relevant tests pass
3. **For experimental work:** Tests outside release gate scope won't block merge

### For Reviewers
1. Verify release gate passes (check PR status)
2. For core engine changes, ensure appropriate test coverage exists
3. Risk assessment provided by `pr-release-gate.yml` (informational only)

### For Release Captains
1. Verify release-gate workflow is green on target branch
2. Optionally run experimental workflows manually before release
3. All required checks must pass (see `docs/RELEASE_GATES.md`)

---

**Last Updated:** 2025-12-09 - Separated enforced vs aspirational test coverage
