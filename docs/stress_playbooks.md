# Stress Scenario and Portfolio Resilience Playbooks

GeoSync must stay responsive when markets dislocate, infrastructure falters, or
strategy capital allocations need fast rebalancing. This playbook curates
high-impact stress replays, targeted fault injections, and multi-strategy
portfolio allocation recipes so engineering and quant teams can validate the
platform end-to-end before shipping changes.

---

## Table of Contents

- [Replay Catalogue: Historic Stress Events](#replay-catalogue-historic-stress-events)
- [Fault-Injection Matrix](#fault-injection-matrix)
- [Portfolio Allocation Frameworks](#portfolio-allocation-frameworks)
- [Automation and Reporting Hooks](#automation-and-reporting-hooks)

---

## Replay Catalogue: Historic Stress Events

Use deterministic backtest replays to reproduce known market regimes with
realistic execution and risk telemetry. All scenarios leverage the
`geosync_cli backtest` entrypoint with configuration bundles stored under
`configs/stress/`. Each replay exports JSON stats to `reports/stress/` and feeds
latency-aware fills through [`backtest/execution_simulation.py`](backtest_execution_simulation.md).

| Scenario | Window (UTC) | Required Data | Core Metrics | Expected System Signals |
| --- | --- | --- | --- | --- |
| **Flash Crash 2010 (U.S. Equities)** | 2010-05-06 13:00–15:00 | Level II order-book + trade ticks for `/ES` and SPY. Snapshot to Parquet via [`geosync_cli ingest`](../geosync/cli/geosync_cli.py). | Queue depth deviation, fill latency percentiles, limit-order cancel ratio. | Execution simulator must trigger `HaltMode.PARTIAL` when order-book liquidity collapses, and risk controls clamp Kelly utilization to ≤50% after `max_drawdown` breaches 5%. |
| **COVID-19 Selloff (Global FX)** | 2020-03-09 00:00–2020-03-13 23:59 | Minute bars + volatility surface for EURUSD, AUDUSD. Register artefacts with `FeatureCatalog`. | Realized volatility spike, VaR/CVaR exceedances, circuit-breaker activations. | Portfolio heat-check raises alert when 1-day CVaR > configured limit; volatility-target module shrinks exposure to keep annualized vol ≤ 18%. |
| **FTX Collapse (Crypto Perpetuals)** | 2022-11-08 00:00–2022-11-11 23:59 | WebSocket trade/mark price replay for BTC-PERP, SOL-PERP with funding rates. Persist delta snapshots every 250ms. | Funding rate swings, mark vs. spot divergence, liquidation cascade counts. | Market data adapter must fall back to cached book when WS stalls >1s and trigger `MarketHalt.DELAY`; strategy governance flags models relying on stale funding feeds for manual review. |

### Replay Workflow

1. **Provision datasets** – coordinate with the data team to stage raw feeds in
   object storage. Update `configs/stress/<scenario>.ingest.yaml` with the
   bucket URL and desired time window, then run `geosync_cli ingest`.
2. **Generate stress backtest config** – render a template via
   `geosync_cli backtest --generate-config --output configs/stress/<scenario>.backtest.yaml`
   and update:
   - `data.path` to the ingested Parquet/CSV artifact.
   - `execution.latency_profile` to reference latency/halt presets.
   - `risk.stress_checks` to enable Kelly caps and VaR/CVaR tripwires.
3. **Replay with execution simulation** – call
   `geosync_cli backtest --config configs/stress/<scenario>.backtest.yaml` and
   store outputs in `reports/stress/<scenario>.json`.
4. **Review diagnostics** – load the results into the observability dashboards
   referenced in [`docs/monitoring.md`](monitoring.md) to compare replay metrics
   against production baselines.

Document deviations in the stress runbook (`reports/stress/journal.md`) and file
remediation issues with owners and due dates.

---

## Fault-Injection Matrix

Fault injection validates that data pipelines, event processors, and execution
services fail gracefully when assumptions break. Use `toxiproxy` or
`chaos-mesh` to orchestrate disruptions; automate via `make chaos-test` when the
suite is wired into CI.

| Injection | Method | Observability Hooks | Expected Platform Response |
| --- | --- | --- | --- |
| **Market data gaps** | Drop 5–30 consecutive ticks in the feed handler via feature-flag toggle. | Prometheus counter `geosync_market_data_gaps_total`, data freshness lag, incident log. | Backtest engine applies forward-fill only within allowable tolerance, marks replay as degraded, and raises `DataGapDetected` event for downstream consumers. |
| **WebSocket latency spike** | Introduce 1–3s delay using `toxiproxy` latency filter on WS endpoint. | Grafana panel for WS RTT, alert `ws_latency_high` firing within 60s. | Execution service transitions to degraded mode, throttles order submissions, and emits `execution.latency_mode=DEGRADED` to logs. Portfolio risk module temporarily widens slippage buffers. |
| **Event reorder** | Shuffle order-book deltas using middleware that buffers and reorders 10% of messages. | Sequence gap detector metric, Jaeger trace of replay worker, structured log warnings. | Event stream normalizer reorders events using timestamp + sequence; if unable, it quarantines the batch and replays from last checkpoint without crashing the pipeline. |

### Runbook

1. **Schedule injections** during off-peak research windows; never overlap with
   production-like benchmarks.
2. **Pre-flight checks** – validate dashboards, alert routes, and rollback
   scripts. Capture baseline metrics.
3. **Execute injections** using approved tooling. Keep blast radius limited via
   namespace-scoped toggles and rate limits.
4. **Observe and log** – ensure observers capture timestamps, mitigation steps,
   and any unexpected alerts.
5. **Revert and review** – roll back toggles, confirm system health, and add
   findings to the resilience backlog.

Tie every failure mode to a regression test or alert so the response stays
repeatable.

---

## Portfolio Allocation Frameworks

Stress testing is incomplete without disciplined capital allocation across
strategies. Implement the following allocation engines in
`execution/portfolio_allocator.py` (or equivalent service) and store strategy
limits in `configs/risk/allocations.yaml`.

### 1. Kelly-Bounded Allocation

- **Inputs**: Strategy edge (`μ`), variance (`σ²`), Kelly cap per strategy.
- **Computation**: Raw weight `w = μ / σ²`. Clamp `w` between `0` and the
  configured `kelly_cap` (default 0.4). Normalize weights to sum to 1 after
  clamping.
- **Constraints**:
  - Enforce portfolio leverage ≤ 1.2× gross exposure.
  - Concentration: any single strategy ≤ 35% of capital post-normalisation.
- **Observability**: Publish `geosync_kelly_utilization{strategy=...}` gauges;
  trigger alerts when utilisation > 90% of cap.

### 2. Volatility Targeting

- **Inputs**: Rolling realized volatility per strategy (lookback 20d), desired
  portfolio volatility (e.g., 12% annualised).
- **Computation**: Target weight `w = target_vol / realized_vol`. Apply floor
  of 5% and cap at 40%. Rescale to respect gross leverage limit.
- **Constraints**:
  - Blend with Kelly weights using convex combination `w_final = α * w_kelly +
    (1 - α) * w_vol`, where `α` default 0.6.
  - Require correlation-adjusted diversification: if pairwise correlation > 0.8,
    cap combined allocation to 45%.
- **Observability**: Record realised vs. target volatility to
  `geosync_vol_target_error` histogram for each strategy cluster.

### 3. CVaR Minimisation

- **Inputs**: Scenario P&L matrix (rows = strategies, columns = stress
  scenarios), confidence level (95%), budget constraints.
- **Computation**: Solve linear program minimising portfolio CVaR subject to:
  - `w ≥ 0`, `Σ w = 1` (or ≤ leverage cap for leveraged books).
  - Budget guardrails from Kelly/vol targeting intersection.
  - Additional regulatory constraints (e.g., crypto exposure ≤ 25%).
- **Implementation Notes**:
  - Use `cvxpy` or the in-house optimisation stack located in
    [`libs/optimisation`](../libs) if available.
  - Cache scenario matrices in `data/portfolio/stress_scenarios.parquet` to
    avoid recomputing historical losses.
- **Observability**: Emit CVaR estimates and binding constraint flags to the
  risk dashboard; escalate when actual drawdowns exceed 0.75 × projected CVaR.

Document every allocation run in `reports/portfolio/allocations.md`, including
inputs, solver status, and resulting weights. Link the artefact to the stress
replay ID for traceability.

---

## Automation and Reporting Hooks

- **CI Integration** – add a nightly job `make stress-suite` that replays the
  three historic scenarios, runs the fault-injection suite in dry-run mode, and
  recomputes allocation weights using the latest metrics.
- **Artifact Registry** – version-control generated configs and reports via the
  `FeatureCatalog` and `DataVersionManager` APIs already exposed in the CLI so
  stress evidence is reproducible.
- **Status Dashboards** – extend the monitoring bundle with a "Stress &
  Allocation" panel summarising replay KPIs, outstanding faults, and capital
  allocation deltas.
- **Escalation Workflow** – when any scenario breaches predefined thresholds,
  auto-create tickets with the owning squad, referencing the specific
  configuration, dataset version, and allocation snapshot.

Following this playbook keeps stress testing actionable, operationally safe, and
fully traceable from data ingest through portfolio-level decisioning.
