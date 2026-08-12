# Risk, Signals, and Observability Control Blueprint

This blueprint consolidates the safeguards required to keep GeoSync's live
trading stack defensible under volatile market regimes. It groups controls across
risk management, machine-learning signal governance, online monitoring, and
observability so that engineering, quant, and SRE teams can execute a coordinated
rollout.

---

## 1. Portfolio and Position Risk Controls

| Control | Description | Implementation Notes | Success Metrics |
| --- | --- | --- | --- |
| **Value at Risk (VaR) / Conditional VaR (CVaR)** | Daily and intraday VaR/CVaR estimates for each strategy and at the consolidated book level. | Use historical simulation with rolling 250-day window and Cornish-Fisher adjustment for fat tails. Schedule recomputation every 15 minutes; expose Prometheus gauges (`geosync_var_usd`, `geosync_cvar_usd`). | VaR exceedances ≤ Basel traffic-light thresholds; alert if realized loss > 0.75 × CVaR. |
| **Kelly Fraction Cap** | Bound leverage and bet sizing by a configurable Kelly fraction (default 0.4). | Compute Kelly using forecast edge and payoff ratios; clamp allocations via `min(forecast_kelly, kelly_cap)`. Store per-strategy cap in `configs/risk/kelly.yaml`. | No positions exceed configured cap; on breach, orders are automatically resized. |
| **Max Drawdown Guard** | Halt risk-on activity when realized drawdown breaches limits. | Track rolling 30/90-day drawdown via equity curve; add Prometheus counter `geosync_drawdown_halts_total`. Integrate with risk service to trigger kill-switch (see below). | Drawdown recoveries occur within policy window; zero trades bypass halt state. |
| **Stop Schemas** | Enforce standardized stop-loss/playbook templates (volatility, time, trailing). | Provide schema definitions in `configs/risk/stops.yaml`; ensure execution engine attaches schema metadata to orders for auditability. | 100% of live orders reference an approved stop schema ID. |
| **Correlation & Concentration Limits** | Prevent overexposure to correlated symbols and single-asset concentration. | Maintain rolling correlation matrix from market data service; enforce `max_pairwise_corr` and `max_symbol_weight` thresholds per portfolio. Publish metrics `geosync_corr_limit_hits_total`. | Correlation breaches resolved < 5 minutes; concentration per symbol < policy cap. |
| **Kill-Switch & Flat Degradation** | Safety brake that squares positions and rejects new risk when triggered. | Implement manual trigger (CLI/API) and automatic trigger tied to drawdown, VaR breach, or monitoring alerts. Execution service should submit market-close orders and confirm flat via reconciliation. | Kill-switch activation to flat state < 120 seconds; automated notification to incident channel. |

### Operational Playbooks

1. **Intraday Risk Review** – Every hour, review VaR/CVaR dashboards, correlation
   heatmaps, and Kelly utilization. Document overrides in the risk journal.
2. **Drawdown Escalation** – If drawdown > 70% of limit, notify Head of Trading
   and place platform in "warm" state (reduced position sizes) pending analysis.
3. **Kill-Switch Drills** – Quarterly failover exercises to validate "flat" mode
   by simulating exchange outages and verifying reconciliation scripts.

---

## 2. Signal Engineering Pipeline

| Stage | Guardrails | Tooling |
| --- | --- | --- |
| **Feature Ingestion** | Enforce schema validation (`pydantic`) and timestamp monotonicity. Version features in `data/features/<feature_set>/<version>` with metadata manifest. | Automated CI job `make validate-features` to run schema + freshness checks. |
| **Labeling (Triple-Barrier)** | Implement López de Prado triple-barrier labeling with configurable horizons (time, profit target, stop). Persist barrier parameters for reproducibility. | `libs/signals/labeling.py` supplies reusable function; store configs under `configs/signals/barriers.yaml`. |
| **Cross-Validation** | Walk-forward cross-validation with purging/embargo to remove leakage. Support combinatorial CV for regime-specific models. | Extend `backtest/cv.py` to produce fold manifests; log coverage via MLflow. |
| **Leakage Guards** | Validate no future data leakage via feature-lag audit, lookahead tests, and embargo enforcement. Add CI assertions that training features precede labels by ≥ 1 bar. | `tests/leakage/test_feature_lag.py` with property-based cases; integrate in `pytest` suite. |
| **Model Registry Integration** | Store trained models with metadata (feature set hash, label config, drift thresholds). | Use existing registry in `core/registry` or extend to include drift baseline statistics. |
| **Feature Signature Compatibility** | Enforce forward/backward compatibility across feature sets and serving schemas. | Model registry stores `feature_signature` describing column order, data types, and acceptable nullability ranges. Deploy pipeline blocks promotion when incoming scoring payload signature deviates beyond tolerance (e.g., missing/extra fields, distributional shifts outside guardrails). |

### Pipeline CI/CD Requirements

- `make signals-lint` ensures feature manifests and barrier configs pass validation.
- Training jobs must export cross-validation reports (`reports/signals/<model>/cv.json`).
- Enforce approval workflow for new feature sets via pull request templates referencing leakage tests and labeling configs.

---

## 3. Online Evaluation and Drift Monitoring

| Component | Responsibilities | Metrics & Alerts |
| --- | --- | --- |
| **Prediction Monitoring** | Track real-time prediction distribution vs. training baseline. | Population Stability Index (PSI) per feature and per model output; alert when PSI > 0.2 for two consecutive windows. |
| **Performance Monitoring** | Measure realized vs. expected returns and classification metrics (precision/recall for signal direction). | Rolling KS statistic on residuals; alert if KS p-value < 0.01. Maintain Prometheus summaries (`geosync_signal_return_residual`). |
| **Drift Dashboard** | Grafana board combining PSI, KS, hit rate, and drawdown overlay. | Auto-annotate with deployment timestamps from model registry. |
| **Automated Rollback** | Triggered when drift + performance breaches occur simultaneously or kill-switch engaged. | Deployment pipeline includes rollback playbook calling `core/models/registry.rollback_to(version)`. Record events in `reports/models/rollback_log.md`. |
| **Model Audit Trail** | Maintain append-only ledger for scoring configs, barrier parameters, and alert acknowledgements. | Use `observability/audit/model_events.jsonl`; review weekly. |
| **Drift Guardrails** | Pair PSI/JS divergence thresholds with feature-signature compatibility checks before scoring. | Streaming job validates that live payloads satisfy registry-stored guardrails; breaches quarantine payloads, raise PagerDuty alerts, and log drift context for retraining triage. |
| **Auto-Requalification** | Automate retraining/validation jobs when drift persists after manual acknowledgement. | Trigger ML pipeline (`make retrain-model MODEL=<id>`) once drift metric stays above tolerance for N windows; require registry update with new baseline stats before re-enabling traffic. |

### Online Evaluation Loop

1. **Ingest Live Metrics** – Export scoring payloads to Kafka topic `signals.monitoring`.
2. **Compute PSI/JS Divergence** – Streaming job calculates drift stats every 15 minutes; write
   to Prometheus via Pushgateway when running off-schedule. JS divergence is reserved
   for dense/continuous features where PSI is less sensitive.
3. **Drift Guard Checkpoint** – Before forwarding payloads to the scoring service,
   validate feature signatures against registry guardrails. On breach, send payloads
   to a quarantine queue and flip the trading stack into "warm" state until resolved.
4. **Alert Routing** – Route drift alerts to on-call quant via PagerDuty with
   runbook link. Escalate to trading desk if combined with drawdown alert.
5. **Rollback or Requalify** – Incident commander checks registry metadata to select
   stable prior model; orchestrate redeploy and confirm metrics revert to baseline.
   If drift persists but performance remains acceptable, schedule auto-requalification
   run and keep quarantine queue under review.

### Trade Halt Channel

- **Automatic Halt** – When drift guardrails or PSI/JS divergence exceed
  "stop-trading" thresholds, execution service receives a signed command from the
  monitoring pipeline to pause new orders and gracefully flatten risk exposure.
- **Manual Override** – Authorized operators may override the halt via secure CLI
  that writes an immutable record to `observability/audit/halt_overrides.jsonl`
  capturing user, reason, and time. Overrides require dual approval within 15
  minutes or the halt reasserts.
- **Audit Trail** – Weekly audit reviews reconcile overrides against incident
  tickets and confirm that auto-halt conditions were addressed before resuming
  normal trading.

### Causal Signal Validation

1. **A/B + CUPED** – Run holdout-based experiments for new signals with CUPED
   variance reduction to detect small effects while controlling for market noise.
   Store CUPED covariates and pre-exposure summaries in `reports/signals/ab/`.
2. **Difference-in-Differences (DiD)** – For macro regime shifts or venue changes,
   evaluate signal impact using DiD over relevant pre/post periods and matched
   controls. Document assumptions and balance metrics in the model registry entry.
3. **Placebo Tests** – Apply placebo interventions (e.g., randomized deployment
   dates or non-treated symbols) to ensure observed lifts are causal and not
   driven by drift or exogenous factors.
4. **Stability Selection** – During model development, use stability selection to
   confirm feature robustness across bootstrap samples. Only promote features
   whose inclusion frequency clears policy thresholds.
5. **Temporal SHAP Diagnostics** – Generate time-series SHAP explanations with
   caution: smooth over intraday noise, clip outlier attributions, and compare to
   baseline regimes. Annotate reports with warnings to prevent over-interpretation
   during volatile periods.

---

## 4. Observability Coverage (Prometheus)

Ensure every pipeline stage and control loop exposes metrics with consistent
labels (`env`, `strategy`, `model_version`, `exchange`).

| Domain | Required Metrics | Implementation Details |
| --- | --- | --- |
| **Ingest** | `geosync_ingest_events_total`, `geosync_ingest_lag_seconds`, `geosync_ingest_errors_total`. | Instrument data connectors; add histogram for lag. |
| **Backtest** | `geosync_backtest_duration_seconds`, `geosync_backtest_jobs_in_progress`, `geosync_backtest_failures_total`. | Wrap CLI/backtest runners with instrumentation decorator. |
| **Execution** | `geosync_orders_submitted_total`, `geosync_order_latency_seconds`, `geosync_execution_errors_total`, `geosync_position_notional`. | Extend existing execution service metrics; include label for risk halt state. |
| **Risk Controls** | `geosync_var_usd`, `geosync_cvar_usd`, `geosync_kelly_utilization_ratio`, `geosync_drawdown_percent`. | Emit from risk service after each evaluation cycle. |
| **Model Serving** | `geosync_signal_latency_seconds`, `geosync_scoring_requests_total`, `geosync_scoring_failures_total`. | Wrap inference endpoints; add quantiles (p50/p95/p99). |
| **Alerts & Kill-Switch** | `geosync_kill_switch_state` (gauge: 0=off,1=warm,2=flat), `geosync_kill_switch_events_total`. | Update when kill-switch toggled; attach `reason` label. |

### Observability Operationalization

- Store alert rules in `observability/prometheus/rules/risk_signals.yml` with
  runbook links for each alert.
- `make observability-verify` lints rules and validates recording expressions.
- Grafana dashboards should be versioned under `observability/grafana/dashboards/`
  with JSONNet templates to reduce drift.
- Include synthetic canaries that submit mock trades to validate latency and risk
  metrics every 5 minutes.

---

## 5. Execution Timeline

| Phase | Duration | Key Deliverables |
| --- | --- | --- |
| **Design Finalization** | 2 weeks | Confirm VaR models, stop schema catalogue, barrier configs, drift thresholds. |
| **Implementation** | 4–6 weeks | Ship risk service enhancements, signal pipeline tooling, Prometheus metrics. |
| **Hardening** | 2 weeks | Run GameDay kill-switch drills, backtest validations, and drift simulations. |
| **Go-Live** | 1 week | Enable alerts, monitor adoption, document lessons learned. |

Dependencies across teams (quant, platform, SRE) should be tracked via the
engineering program board. Review progress during weekly risk council meetings.

---

## 6. Runbook Checklist

- [ ] VaR/CVaR dashboards validated against historical incidents.
- [ ] Kelly cap and concentration limits configured per strategy.
- [ ] Triple-barrier labeling functions unit-tested and versioned.
- [ ] Drift jobs produce PSI/KS reports with baselines stored.
- [ ] Prometheus alerts map to escalation policies with acknowledged owners.
- [ ] Kill-switch rollback test completed in staging within the last quarter.

Keeping these controls active and audited ensures GeoSync reacts to market
stress, model drift, and operational failures without compromising capital or
trust.
