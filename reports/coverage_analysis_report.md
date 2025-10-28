# Test Coverage Analysis Report
**Generated**: February 14, 2025  
**Repository**: neuron7x/TradePulse  
**Coverage Tool**: pytest-cov v7.0.0

## Executive Summary
The latest regression run focused on the reliability-critical surface area that guards live trading cutovers: the Kuramoto
indicator stack, SLO auto-rollback guard, and secret-detection utilities. Targeted unit suites now push these modules to **93.09 %
coverage**, up from 88.63 % in the previous audit, and validate GPU fallbacks, cooldown semantics, and masked security findings.
This closes the outstanding actions in Issue #90 for the infra/monitoring/deploy/security scope, while highlighting the remaining
gaps across the broader platform (execution, data ingestion, and strategy orchestration still sit well below the 98 % roadmap).

### Coverage Snapshot – Reliability-Critical Modules

| Metric | Value |
|--------|-------|
| **Total Coverage** | **93.09 %** |
| **Total Statements** | 275 |
| **Covered Lines** | 256 |
| **Missing Lines** | 19 |
| **Target Coverage (critical surface)** | 90 % |
| **Gap to Target** | +3.09 % |

_Source_: `pytest tests/unit/indicators/test_kuramoto_fallbacks.py tests/unit/utils/test_security.py tests/unit/utils/test_slo.py --cov=core.indicators.kuramoto --cov=core.utils.security --cov=core.utils.slo`【c97d7a†L1-L8】

### Module-Level Breakdown

| Module | Coverage | Lines Covered | Missing Lines | Delta vs. Previous | Notes |
|--------|----------|---------------|---------------|--------------------|-------|
| `core.indicators.kuramoto` | 92.00 % | 92 / 100 | 8 | ▲ +8.42 pp | GPU and FFT fallbacks plus feature wrappers covered.【F:tests/unit/indicators/test_kuramoto_fallbacks.py†L1-L166】 |
| `core.utils.slo` | 93.86 % | 107 / 114 | 7 | ▲ +64.91 pp | AutoRollbackGuard evaluated for per-request, snapshot, cooldown, and percentile logic.【F:tests/unit/utils/test_slo.py†L1-L104】 |
| `core.utils.security` | 93.44 % | 57 / 61 | 4 | ▲ +72.13 pp | SecretDetector and CLI wrapper validated with masked output and ignore rules.【F:tests/unit/utils/test_security.py†L1-L60】 |
| `application.api.service` (`divconv` heuristics) | 42.14 % | 397 / 942 | 545 | — | Divergence/convergence balance logic inside the online forecaster remains under-tested; existing cases cover directional penalties and alignment rewards only.【F:application/api/service.py†L920-L1039】【F:tests/unit/api/test_online_signal_forecaster.py†L243-L291】【8d0dcb†L4-L8】【3ed262†L1-L6】 |

## Detailed Findings

### `core.indicators.kuramoto`
* **What improved**: New tests exercise CPU FFT fallback, CuPy GPU execution, GPU failure rollback, multi-asset aggregation, and
  float32 metadata paths, ensuring degraded modes emit metrics and remain numerically stable.【F:tests/unit/indicators/test_kuramoto_fallbacks.py†L1-L166】【F:core/indicators/kuramoto.py†L1-L189】
* **Residual risk**: Import-time SciPy availability and log-level assertions (lines 17–18, 33, 66, 74, 77, 120–121) remain
  untested; integrate smoke tests in CI that toggle SciPy presence to reach full coverage.

### `core.utils.slo`
* **What improved**: Sliding-window pruning, latency/error-rate breaches, cooldown enforcement, percentile helper, and negative
  latency validation now have deterministic coverage via fixed timestamps and callback assertions.【F:tests/unit/utils/test_slo.py†L1-L104】【F:core/utils/slo.py†L1-L204】
* **Residual risk**: Logging enrichment and external metrics adapters (lines 134, 136, 140, 151–152) still rely on manual QA —
  backfill integration tests once Prometheus wiring stabilises.

### `core.utils.security`
* **What improved**: SecretDetector scans, ignore patterns, masked output, directory recursion, and CLI helper paths are covered
  using filesystem sandboxes, ensuring on-call teams receive actionable but sanitised alerts.【F:tests/unit/utils/test_security.py†L1-L60】【F:core/utils/security.py†L1-L154】
* **Residual risk**: The CLI still prints to stdout without structured logging (lines 53, 82–84, 111); consider surfacing findings
  via JSON for automation pipelines.

### `application.api.service` (`divconv` heuristics)
* **Coverage status**: Line coverage sits at **42.14 %** (397 / 942 statements) against the newly established **85 % divconv guardrail**, leaving a **42.86 pp** deficit at the module level.【8d0dcb†L4-L8】【3ed262†L1-L6】
* **SLO comparison**: The project-wide 98 % coverage SLO amplifies the urgency—the divconv surface is **55.86 pp** below that objective, making it the weakest link among forecaster dependencies.【F:reports/release_readiness.md†L12-L15】【3ed262†L1-L6】
* **What is covered today**: Targeted unit tests exercise divergence-dominated and convergence-aligned scenarios to ensure the balance term dampens runaway MACD spreads and rewards agreement.【F:tests/unit/api/test_online_signal_forecaster.py†L243-L291】 These cases map directly to the scoring mechanics baked into the online forecaster’s `macd_balance` correction.【F:application/api/service.py†L920-L1039】
* **Next steps**: Expand coverage across edge conditions (flat MACD, oscillating histogram, zero-confidence clamps, and telemetry metadata) and isolate the divconv math into a focused module so the guardrail can track it independently of ancillary API wiring.

## Next Steps
1. **Extend coverage uplift to surrounding modules** – replicate the targeted strategy for `core.indicators.temporal_ricci`,
   `core/data/ingestion`, and execution strategy orchestration to bring the end-to-end stack closer to the 98 % goal highlighted in
   the release readiness report.【F:reports/release_readiness.md†L19-L44】
2. **Automate coverage guardrails** – ✅ Achieved. The CI workflow now runs
   `python -m tools.coverage.guardrail` with
   `configs/quality/critical_surface.toml` to ensure the Kuramoto indicator,
   SLO guard, and secret detector stay above their agreed thresholds before
   code can merge.【F:.github/workflows/ci.yml†L33-L54】
3. **Document measurement scope** – update developer docs to clarify which modules fall under the reliability-critical coverage
   objective versus experimental areas awaiting tests.
