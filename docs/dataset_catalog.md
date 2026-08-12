# Dataset Catalog

This catalog provides a single source of truth for datasets powering GeoSync analytics, feature engineering, risk management,
and reporting. It documents business context, ownership, SLAs, quality controls, lineage, and change processes to guarantee that
data products remain discoverable, trustworthy, and auditable across their lifecycle.

## Governance & Stewardship

- **Dataset Steward** – Accountable owner responsible for data quality, documentation, and remediation.
- **Data Platform** – Maintains pipelines, storage infrastructure, and schema evolution tooling.
- **Risk & Compliance** – Reviews access controls, regulatory constraints, and retention mandates.
- **Observability** – Operates monitoring for ingestion delays, data drift, and validation failures.

Monthly stewardship council reviews metrics, incidents, and backlog items. Critical datasets undergo quarterly audits aligned
with the Architecture Review Program.

## Metadata Schema

| Field | Description |
| --- | --- |
| **Dataset Name** | Canonical identifier (`dataset:<domain>/<name>/<version>`). |
| **Owner** | Steward and delegate with contact details. |
| **Version** | Semantic version tied to schema hash; increments on structural changes. |
| **Description** | Business purpose and analytical use cases. |
| **Source Systems** | Upstream producers (exchanges, internal services, third parties). |
| **Calculation / Transformation** | Aggregations, enrichments, or derivations performed. |
| **SLA** | Freshness, availability, and retention requirements. |
| **Quality & Drift Monitoring** | Metrics, alerts, and thresholds. |
| **Validation Tests** | Automated checks (schema, statistical, reconciliation) and cadence. |
| **Lineage** | Downstream consumers, feature manifests, and models. |
| **Access Policy** | IAM roles, privacy classification, and approval workflow. |
| **Change Request Process** | Approvals, templates, rollout plans. |
| **Deactivation & Archival** | Sunset conditions, archival storage, retention duration. |
| **Auto Documentation Hooks** | Automation producing catalog updates and lineage artefacts. |
| **Usage Examples** | Notebooks, dashboards, or services using the dataset. |

## Catalog Entries

### Market & Trading Data

| Dataset Name | Owner | Version | Description | Source Systems | Calculation / Transformation | SLA |
| --- | --- | --- | --- | --- | --- | --- |
| `dataset:market/ticks/3.5.0` | Market Data Team (Lead: Sara Ilyin, backup: Mateo Ruiz) | `3.5.0` | Real-time consolidated tick stream for equities, futures, and crypto venues; basis for intraday analytics and feature computation. | Direct exchange FIX/ITCH feeds via ingestion workers, vendor REST fallbacks. | Normalise timestamps to UTC, harmonise symbol taxonomy, enrich with venue liquidity tiers, deduplicate duplicates within 5 ms window. | Freshness ≤ 1 s, availability 99.99%, retention 30 days hot + 12 months cold. |
| `dataset:market/order_book_snapshots/2.2.1` | Market Microstructure Guild (Lead: Chen Wei, backup: Laura Singh) | `2.2.1` | Level 2 order book snapshots at 100 ms cadence supporting Ricci and liquidity features. | Exchange depth feeds, aggregator microservice. | Harmonise depth levels, compute implied spread, annotate with venue micro-tag and regulatory flags. | Freshness ≤ 2 s, availability 99.95%, retention 14 days hot + 12 months cold. |
| `dataset:execution/orders/1.9.4` | Execution Engineering (Lead: Andre Costa, backup: Mei Nakamura) | `1.9.4` | Authoritative ledger of routed orders and fills powering compliance, P&L, and risk reporting. | Execution service Kafka topics, clearing broker drop copies. | Join order lifecycle events, enrich with strategy tags, compute latency metrics, and reconcile fills vs. broker statements. | Freshness ≤ 5 s, availability 99.9%, retention 7 years (regulatory). |

### Analytics & Observability Data

| Dataset Name | Owner | Version | Description | Source Systems | Calculation / Transformation | SLA |
| --- | --- | --- | --- | --- | --- | --- |
| `dataset:analytics/backtest_metrics/1.6.0` | Quant Platform (Lead: Lila Roberts, backup: Omar Nasser) | `1.6.0` | Aggregated metrics from backtesting runs (P&L, drawdown, Sharpe) enabling strategy comparison. | Backtest engine exports, MLflow artifacts. | Aggregate per strategy/run, compute rolling risk metrics, align with manifest versions, store in parquet. | Freshness ≤ 15 min post-run, availability 99.5%, retention 24 months. |
| `dataset:observability/pipeline_health/2.0.2` | SRE (Lead: Mark Jensen, backup: Alice Petrov) | `2.0.2` | Pipeline reliability metrics and alerts metadata used for operational reporting. | Prometheus scrape exports, alertmanager webhooks. | Normalise metric labels, compute SLA adherence, tag with service ownership. | Freshness ≤ 1 min, availability 99.9%, retention 90 days. |
| `dataset:risk/exposure_limits/1.3.5` | Risk Office (Lead: Fatima Khan, backup: Eric Lowell) | `1.3.5` | Intraday exposure, VaR, and concentration limits referenced by execution guardrails. | Risk calculation engine, reference data service. | Combine exposures with limit thresholds, calculate breach deltas, annotate with regulatory category. | Freshness ≤ 5 min, availability 99.9%, retention 5 years. |

### Operational Controls

| Dataset Name | Quality & Drift Monitoring | Validation Tests | Lineage | Access Policy | Change Request Process | Deactivation & Archival | Auto Documentation Hooks | Usage Examples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dataset:market/ticks/3.5.0` | Monitor tick arrival rate, out-of-order ratio, and venue coverage; alert if PSI >0.1 or gap >3 s; metric `geosync_ticks_processed_total`. | Schema validation via `tests/data/test_market_ticks_schema.py`; reconciliation with exchange volume daily; Great Expectations suite hourly. | Downstream features (`entropy`, `hurst`, `ricci`), services (`apps/signal_service`), dashboards `dashboards/market_heatmap`. | IAM roles `role:market_data`, `role:quant`; GDPR classification `Confidential`. | Submit Data Change Request (DCR) using `docs/templates/data_change_request.md`; approvals: Data Platform + Risk; change window Wed/Sat 21:00 UTC. | Archive to `s3://geosync-archive/market_ticks/<version>/`; retain metadata 12 months; mark deprecated once consumers migrate. | CI workflow `catalog-sync.yml` ingests schema registry + manifest metadata and updates tables. | Notebook `notebooks/data_quality/tick_health.ipynb`; API `core/data/feeds/tick_store.py`. |
| `dataset:market/order_book_snapshots/2.2.1` | Track depth completeness and spread accuracy; alert if >5% missing levels or spread drift >2σ; Grafana panel `Order Book Health`. | Validation script `tests/data/test_order_book_snapshot_pipeline.py`; nightly synthetic replay verifying book reconstruction. | Feeds `ricci` feature, liquidity analytics, risk stress tests. | Access restricted to `role:quant_advanced`, `role:mlops`; contains venue-sensitive info. | DCR with ML Platform review due to feature coupling; requires ARB notification. | Archive snapshots to cold storage with encryption-at-rest; maintain lineage pointers in `reports/datasets/lineage.json`. | Automation attaches depth heatmaps under `docs/assets/datasets/order_book/<date>.png`. | Notebook `notebooks/liquidity/order_book_quality.ipynb`; service `core/execution/liquidity_router.py`. |
| `dataset:execution/orders/1.9.4` | Reconcile order counts vs. broker statements; alert on latency >250 ms or unmatched fills; metric `geosync_order_reconcile_errors`. | Tests `tests/data/test_execution_order_consistency.py`; daily settlement reconciliation. | Consumed by risk exposure, compliance reporting, settlement pipeline. | Access limited to `role:compliance`, `role:risk`, `role:mlops`; PII classification `Restricted`. | DCR requires Compliance + Legal approval; ADR if schema changes; use release checklist with rollback plan. | Retain per regulatory requirement (7 years) in WORM storage; deprecate only when new ledger approved; maintain pointer in catalog. | Nightly job publishes doc updates + retention attestations to catalog; attaches compliance attestation PDF. | Dashboards `reports/execution/performance.md`; service `apps/compliance_reporting`. |
| `dataset:analytics/backtest_metrics/1.6.0` | Monitor metric completeness; alert if run coverage <95%; metric `geosync_backtest_metrics_missing_total`. | Tests `tests/data/test_backtest_metrics_pipeline.py`; cross-check with MLflow metrics. | Input to analytics dashboards, model selection notebooks, improvement plan. | IAM `role:quant`, read-only `role:product_insights`. | Change requests go through Quant Platform + Product; include rollback and communication plan. | Archive per release cycle; maintain lineage in `reports/analytics/backtest_lineage.json`. | Automation renders summary tables + sparkline images in catalog via templating. | Notebook `notebooks/backtests/pnl_comparison.ipynb`; dashboard `reports/backtest_summary.md`. |
| `dataset:observability/pipeline_health/2.0.2` | Alerts on SLA breach rate >0.5% weekly; monitors missing metrics, label cardinality; metric `geosync_pipeline_health_alerts_total`. | Tests `tests/data/test_pipeline_health_extract.py`; contract tests for Prometheus schema. | Drives operational runbooks, reliability dashboards, executive scorecards. | Access `role:sre`, `role:mlops`, `role:leadership_view`; classification `Internal`. | DCR handled by SRE; requires change log update and communication in weekly ops review. | Retain 12 months for trend analysis; compress older data; mark dataset `archived` when replaced. | Automation pipeline attaches heatmaps to catalog and refreshes metadata nightly. | Dashboard `monitoring.md`; runbook `runbook_live_trading.md`. |
| `dataset:risk/exposure_limits/1.3.5` | Drift monitor comparing exposures vs. forecast; alert if >10% delta; metric `geosync_risk_limit_drift_total`. | Validation `tests/data/test_risk_limit_pipeline.py`; reconciliation with treasury system daily. | Downstream risk guardrails, execution limiters, compliance filings. | Access restricted `role:risk`, `role:compliance`, `role:exec`. | DCR requires Risk Committee approval; maintain ADR for methodology shifts. | Archive monthly snapshots to secure vault; keep lineage with version tags. | Catalog automation includes regulatory attestation links + limit diagrams. | Notebook `notebooks/risk/exposure_limit_review.ipynb`; service `core/risk/limit_engine.py`. |

## Change Management & Automation

- Use standard **Data Change Request (DCR)** template capturing motivation, impact analysis, rollout steps, and rollback plan.
- Integrate DCR workflow with Jira; tickets tagged `data-catalog` auto-populate review agenda.
- Automation pipeline `catalog-sync.yml` (shared with feature catalog) harvests metadata from schema registry, manifests, and
  validation reports to regenerate catalog tables; output reviewed before merge.
- Git pre-commit hook validates YAML metadata completeness and ensures dataset versions increment when schema changes.

## Drift Monitoring & Failure Testing

- **Distribution Drift** – PSI and KS tests between live ingestion and historical baselines; anomalies escalate to `#data-ops`.
- **Freshness** – Checkpoint-lag alerts ensure ingestion delay stays below SLA thresholds.
- **Integrity** – Referential integrity checks across datasets (e.g., orders referencing valid instruments) executed daily.
- **Chaos Exercises** – Quarterly ingestion disruption drills verifying failover pipelines and data replay.

## Deactivation & Archival

- Publish deprecation notice ≥30 days in advance with migration guide.
- Freeze upstream pipelines, ensure downstream consumers have migrated, and lock dataset to read-only mode.
- Archive to immutable storage, update catalog status to `retired`, and capture final validation report.
- Maintain retention schedule per regulatory requirements and document destruction approvals.

## Access & Change Request Workflow

1. Request access via IAM portal referencing dataset name/version; approvals logged with expiry date.
2. Quarterly access recertification performed by Data Governance + Security.
3. Schema or SLA changes require ARB visibility when cross-cutting architectural components are affected.
4. Emergency changes follow expedited process with post-hoc review.

## Usage & Discovery Enablement

- Provide query snippets in `notebooks/data_walkthroughs/`.
- Surface dataset cards in internal portal with filters (domain, SLA, owner, compliance tag).
- Link datasets to features/models in lineage graphs stored under `docs/assets/datasets/lineage/`.
- Embed usage metrics (query volume, top consumers) updated monthly.

These practices ensure GeoSync datasets remain governed, observable, and aligned with the broader architectural review cadence.
