# Metric Governance and Experimentation Discipline

> **Purpose.** Institute a repeatable, audit-ready metrics discipline that links
> TradePulse's strategic outcomes to measurable signals, experiment controls, and
> escalation procedures. This playbook defines how we author goal trees,
> implement leading/lagging indicators, and operationalise SLOs so trading,
> research, and platform squads share a single source of truth.

---

## 1. Goal Hierarchy

We maintain an objectives tree that ties financial performance, customer trust,
platform resilience, and research velocity to measurable outcomes. Each node has
an accountable owner and explicit downstream metrics.

```
North Star: Compound risk-adjusted capital growth > 25% YoY
├── Portfolio Health (Head of Trading)
│   ├── Net Alpha Preservation ≥ 85% of simulated expectation
│   ├── Tail-Risk Exposure (95% CVaR) ≤ policy threshold
│   └── Liquidity Utilisation within venue-specific guardrails
├── Client Trust & Compliance (Chief Risk Officer)
│   ├── Regulatory Breach Count = 0
│   ├── Model Governance Reviews completed ≤ 30 days after release
│   └── Client SLA Violations ≤ 2 per quarter with root-cause reports
├── Platform Reliability (Director of SRE)
│   ├── Trade Ingestion Pipeline Availability ≥ 99.95%
│   ├── Order Execution Latency P99 ≤ 120 ms intra-region
│   └── Recovery Time Objective (RTO) ≤ 15 minutes in tier-1 sites
└── Research Throughput (Head of Quant Research)
    ├── Strategy Iteration Cycle Time ≤ 7 days (idea → validated backtest)
    ├── Experiment Reproducibility Score ≥ 95%
    └── Backtest Infrastructure Cost per Experiment ≤ budget envelope
```

> **Governance.** Goal owners review quarterly; updates propagate to all metric
> dashboards and experiment templates within five business days.

---

## 2. Indicator Catalogue

| Objective Node | Indicator Type | Metric | Definition & Formula | Cadence | Owner |
| -------------- | -------------- | ------ | -------------------- | ------- | ----- |
| Net Alpha Preservation | Leading | Signal Drift Index | Jensen-Shannon divergence between live and baseline signal distributions. | Hourly | Quant Research |
| Net Alpha Preservation | Lagging | Realised Net Alpha | (Live PnL − Simulated PnL) / Simulated PnL. | Daily | Trading Desk |
| Tail-Risk Exposure | Leading | VaR Stress Ratio | Ratio of scenario VaR to policy VaR under worst-case 5-minute window. | 5 min | Risk Ops |
| Tail-Risk Exposure | Lagging | 95% CVaR | Expected loss beyond 95th percentile, computed on daily returns. | Daily | Risk Ops |
| Regulatory Breach Count | Lagging | Breach Incidents | Number of confirmed regulatory policy breaches. | Real-time | Compliance |
| Client SLA Violations | Leading | SLA Saturation Forecast | 3-hour forecast of latency SLO burn rate via Prophet model. | 15 min | SRE |
| Client SLA Violations | Lagging | SLA Violations | Count of breaches vs. contractual latency/availability targets. | Weekly | Customer Success |
| Pipeline Availability | Leading | Error Budget Burn Rate | Rolling 1-hour burn rate derived from SLO error budget. | 5 min | SRE |
| Pipeline Availability | Lagging | Availability (%) | 1 − (Unplanned downtime / total time) across ingestion services. | Daily | SRE |
| Order Execution Latency | Leading | Queue Depth | P95 order gateway queue depth. | 1 min | Platform Eng |
| Order Execution Latency | Lagging | Execution Latency P99 | Observed latency between order submit and venue ACK. | Real-time | Platform Eng |
| Strategy Iteration Cycle | Leading | Experiment Throughput | Number of completed experiments per researcher per week. | Weekly | Quant Research |
| Strategy Iteration Cycle | Lagging | Cycle Time | Median elapsed time from ideation ticket to validated backtest. | Weekly | Quant Research |

---

## 3. Business Metrics

1. **Risk-Adjusted Return on Capital (RAROC).** Net profit after funding costs
   divided by risk capital at risk. Target ≥ 22% quarterly. Data source: risk
   warehouse; owner: Head of Trading.
2. **Capital Utilisation Efficiency.** Average deployed capital / committed
   capital; maintain within 75–90%. Owner: Treasury Ops.
3. **Client Retention Rate.** 1 − churn; measured monthly via CRM export. Target
   ≥ 98%. Owner: Client Services.
4. **Compliance Resolution Time.** Mean time to close compliance tickets. Target
   ≤ 48 hours. Owner: Compliance Lead.

Each business metric must:

- Have an authoritative data warehouse model with documented lineage.
- Include versioned definitions stored in the Metrics Registry (`analytics/metrics_registry.yaml`).
- Surface on executive dashboards with confidence intervals and annotations for
  policy changes or experiments affecting the baseline.

---

## 4. Technical & Operational SLOs

| Service | SLI | SLO Target | Error Budget | Monitoring |
| ------- | --- | ---------- | ------------ | ---------- |
| Trade Ingestion API | Availability | ≥ 99.95% monthly | 21.6 minutes | Prometheus `ingest_up`, Alertmanager escalation to L2 within 2 minutes. |
| Order Execution Engine | Latency P99 | ≤ 120 ms intra-region, ≤ 180 ms cross-region | 120 ms | OpenTelemetry traces aggregated via Tempo; alerts when 30% of budget burned in 1 hour. |
| Strategy Backtest Cluster | Job Success Rate | ≥ 99.5% per day | 0.5% failures | Argo Workflows metrics; SLO violation page to Research Ops. |
| Feature Store Sync | Freshness | ≤ 60 s lag vs. market data feed | 60 s | Data quality monitors with Great Expectations; Slack alert to Data Eng. |
| Risk Model Refit | Completion Time | ≤ 45 minutes | 5 minutes | Airflow SLA monitors; escalate to Quant Infra when >75% budget consumed. |

Operational SLO reviews happen monthly in the SRE-QuantOps forum. Adjustments
require:

- Historical SLI distributions over previous two quarters.
- Error budget consumption postmortems for any breaches.
- Simulation of downstream business impact (e.g., PnL, client satisfaction).

---

## 5. Control Groups & Experiment Design

1. **Control Selection.** For trading strategy experiments, use stratified
   sampling by venue, volatility regime, and time-of-day to create statistically
   comparable control arms. Document strata in the experiment charter.
2. **Holdout Policy.** Maintain at least 10% of flow as permanent holdout for
   regression testing; rotate quarterly to prevent drift.
3. **Instrumentation.** All treatments funnel metrics via Experiment Telemetry
   SDK (`libs/experiment`). Ensure exposure events, outcome events, and guardrail
   metrics are logged with consistent identifiers.
4. **Guardrail Metrics.** Mandatory guardrails: availability SLI, latency P99,
   regulatory breach count, and capital at risk. Experiments automatically halt
   if guardrails exceed thresholds (see Section 9).

---

## 6. Minimum Clinically Significant Effects (MCSE)

- **RAROC uplift:** MCSE = +1.5 percentage points per quarter.
- **Latency reduction:** MCSE = −15 ms on P99 relative to control.
- **Alpha preservation:** MCSE = +4% vs. control net alpha.
- **Client churn:** MCSE = −0.3 percentage points monthly.

Derive MCSEs from historical variance and business value models. Store in the
Metrics Registry to keep experiment design reproducible. Any change proposal must
include sensitivity analysis showing financial impact at MCSE.

---

## 7. Statistical Power & Sample Sizing

- **Target power:** ≥ 0.9 for primary metrics; ≥ 0.8 for guardrails.
- **Significance level:** α = 0.02 for primary outcomes (before correction).
- Use sequential testing methods (e.g., O'Brien-Fleming boundaries) for live
  experiments to reduce time-to-decision while controlling Type I error.
- Sample sizing workflow:
  1. Estimate baseline mean/variance from last 90 days of control data.
  2. Apply MCSE to derive effect size.
  3. Compute required sample using `analytics/power_tools.py` (supports t-test
     and proportion test). Peer review by Quant Research before launch.

---

## 8. Multiple Comparisons Control

- **Primary metrics:** Apply Holm-Bonferroni correction across all simultaneous
  primary outcomes in an experiment.
- **Exploratory metrics:** Control False Discovery Rate via Benjamini-Hochberg
  with q ≤ 0.1. Exploratory results require follow-up confirmation experiments.
- Document correction method and adjusted p-values in experiment reports stored
  in `reports/experiments/`.

---

## 9. Thresholds, Escalations, and Stop Criteria

| Metric | Threshold | Action | Escalation |
| ------ | --------- | ------ | ---------- |
| Error Budget Burn | ≥ 40% in 1 hour | Trigger playbook `docs/incident_playbooks.md#slo-breach`. | L2 SRE on-call; notify Head of Platform if burn ≥ 60%. |
| Regulatory Breach | > 0 incidents | Immediate halt of affected strategy; invoke compliance runbook. | CRO, Legal, CEO. |
| Latency P99 | > 150 ms for 5 consecutive minutes | Auto-disable experimental routing; failover to control path. | Platform L3 and Trading Desk lead. |
| Net Alpha Drop | > 8% vs. control for 2 consecutive trading days | Pause experiment; conduct root cause analysis. | Head of Trading, Quant Research lead. |
| Client SLA Violations | ≥ 1 major breach | Issue client advisory; escalate to Exec Steering Committee. |

**Stop Criteria:**

- **Safety stop:** Any guardrail threshold exceeded for 3 consecutive checks.
- **Futility stop:** Bayesian posterior probability of achieving MCSE < 5%.
- **Dominance stop:** Posterior probability treatment beats control by ≥ 99%.

All stops must be logged in the Experiment Control Plane with timestamp, owner,
reason, and remediation ticket.

---

## 10. Reporting & Review Cadence

- **Weekly Ops Review:** SRE, QuantOps, and Trading review leading indicators,
  MCSE adherence, and guardrail breaches. Minutes stored in Confluence.
- **Monthly Executive Review:** Business metrics, lagging indicators, and SLO
  attainment. Requires signed acknowledgement from C-level stakeholders.
- **Quarterly Calibration:** Refresh MCSEs, re-run power analyses with updated
  variance, and adjust goal tree nodes as needed.

Dashboards must highlight leading indicators alongside projected lagging impact
(e.g., forecasted RAROC drift). Maintain single source of truth in Grafana with
links to experiment charters.

---

## 11. Tooling & Automation Requirements

1. **Metrics Registry.** Central YAML schema storing definitions, MCSE, owners,
   and lineage metadata; version controlled via Git.
2. **Experiment SDK.** Enforce consistent tagging of experiments, enabling
   automatic multiple-comparison correction in `analytics/experiment_report.py`.
3. **Alert Routing.** Alertmanager configuration ensures thresholds route to
   PagerDuty schedules with escalation policies matching Section 9.
4. **Compliance Hooks.** All experiment launches require signed checklist in
   `docs/quality_gates.md` plus automated policy checks (RBAC, data residency).
5. **Data Quality Gates.** Great Expectations suites enforce schema, freshness,
   and volume checks before metrics are published to dashboards.

---

## 12. Change Management

- Proposed modifications require RFC in `docs/adr/` with impact analysis.
- Update dashboards, runbooks, and alert rules within two business days of
  approved changes.
- Conduct post-change validation by comparing pre/post metrics for 7 days to
  ensure no regressions.

---

**Revision Control**

- Document owner: Director of Analytics.
- Review cycle: Quarterly.
- Last reviewed: 2025-03-01.
