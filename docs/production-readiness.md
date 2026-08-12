# Production Readiness Assessment

GeoSync is feature-rich for research and backtesting workflows, but several critical capabilities are still missing before the platform can be considered production-grade. This document captures the current gaps and the work required to close them. Treat it as a living checklist that should be reviewed before promising live-trading availability to stakeholders.

## Current Status

- ✅ **GitHub release readiness**: The repository contains reproducible setups, CI pipelines, and documentation sufficient for open-source distribution.
- ✅ **E2E smoke gating**: Pull-request CI now exercises the CLI smoke path (`tests/e2e/ -m "not slow and not flaky"`), while the slower full-pipeline regression stays marked `slow` for scheduled and manual runs.
- ⚠️ **Pre-production maturity**: Core execution paths exist, but they rely on simulated data sources and mocked connectors.
- ❌ **Production readiness**: Live trading is not yet safe; operational guardrails, integrations, and verification workflows are incomplete.

## Critical Gaps

1. **Live Trading Execution**
   - Implement a resilient live execution loop that manages order lifecycle events, reconnections, and state recovery.
   - ✅ Document warm/cold start procedures and operational runbooks for the execution engine in [docs/runbook_live_trading.md](runbook_live_trading.md).

2. **Exchange Integrations**
   - Deliver real exchange adapters under `interfaces/` (REST and WebSocket) with API key management, authentication retries, and rate-limit handling.
   - Provide environment variable contracts and secret management guidelines for configuring API keys.

3. **Data Validation and Benchmarking**
   - Replace synthetic fixtures with real-market datasets in the test harness.
   - Add benchmark suites that measure latency, throughput, and slippage under realistic loads.

4. **Risk & Compliance Controls**
   - Introduce risk checks (max exposure, kill switches, circuit breakers) and log/audit pipelines.
   - Document ethical trading policies and governance review steps.

5. **Documentation Completeness**
   - Expand the developer and operator manuals with deployment scenarios, troubleshooting trees, and SLA expectations.
   - Publish interface contracts (OpenAPI, AsyncAPI) and keep schema docs in sync with implementations.

6. **User Interface & Monitoring**
   - Build a UI dashboard that visualises strategy state, P&L, execution metrics, and alerts.
   - Integrate dashboards with historical drill-downs and anomaly detection overlays.

## Module Production Contracts (TACL + GeoSync Hydro v2)

This section defines the minimum production contracts for the `tacl/` and
`geosync_hydro/` modules. These contracts establish deterministic behavior,
bounded latency, and fail-safe behavior for degradation scenarios.

### Experimental Flags Review

- **`tacl/`**: No `experimental` labels or feature flags detected in the module.
- **`geosync_hydro/`**: No `experimental` labels or feature flags detected in the module.

### Minimum Production Contracts

| Contract | TACL (Thermodynamic Autonomic Control Layer) | GeoSync Hydro v2 |
| --- | --- | --- |
| Deterministic outputs | Energy scoring and risk gating are deterministic for identical inputs. | `RealTimeMonitor` executes in `eval()` mode; inference should be deterministic for identical inputs and weights. |
| Bounded latency | Pre-action gating must complete within policy timeout; on breach, fallback returns fail-safe decision. | Window inference must complete within policy timeout; on breach, fallback emits fail-safe payload and alerts. |
| Fail-safe | Degradation policy enforces conservative action (block + rollback + safe policy). | Degradation policy emits conservative payload (high-risk flood class + degraded alert) and marks compliance false. |

### Standard Degradation Handling

- **Timeouts**: `tacl.degradation.DegradationPolicy.timeout_s` and
  `geosync_hydro.degradation.DegradationPolicy.timeout_s` provide bounded latency
  for pre-action checks and inference.
- **Fallback policy**: `tacl.degradation.apply_degradation` and
  `geosync_hydro.degradation.apply_degradation` return conservative defaults and
  structured degradation reports to keep pipelines fail-safe.

## Recommended Next Steps

1. **Hardening Sprint**
   - Prioritise live trading loop, exchange connectors, and risk gates.
   - Establish an end-to-end test matrix covering ingestion → signal generation → execution on recorded datasets.

2. **Operational Readiness Review**
   - Run tabletop exercises simulating exchange outages, API key rotation, and abnormal market conditions.
   - Create incident response documentation and escalation paths.

3. **Quality Gates**
   - Add CI jobs for benchmark regression tracking and data-quality validation.
   - Require sign-off from risk/compliance stakeholders before promoting releases to production environments.

Maintaining this checklist will keep GeoSync aligned with industry expectations for safety-critical trading systems and provide transparency on the work remaining before the first production deployment.
