# Feature Catalog Operating Model

This catalog makes feature discovery, governance, and lifecycle management explicit for the GeoSync ML and quantitative
strategy stack. It complements the dataset catalog by documenting how engineered features are defined, validated, deployed, and
retired with clear ownership and automation.

## Governance and Responsibilities

- **Feature Steward** – Accountable owner per feature (usually the originating quant or data scientist). Maintains definitions,
  quality checks, and remediation plans.
- **ML Platform Team** – Operates feature infrastructure, enforces schema/versioning policies, and runs automation for drift
  detection and documentation updates.
- **SRE** – Confirms runtime SLAs, monitors latency budgets, and integrates feature health signals into global observability.
- **Data Governance** – Ensures access controls, privacy classifications, and regulatory constraints are honoured.

Weekly syncs align stewards with platform and SRE to review drift alerts, incidents, and pending change requests.

## Metadata Schema

| Field | Description |
| --- | --- |
| **Feature Name** | Canonical name aligned with manifest (`feature:<domain>/<name>/<version>`). |
| **Owner** | Primary steward and secondary delegate with contact details. |
| **Version** | Semantic version reflecting code + configuration hash; increments on breaking changes. |
| **Business Objective** | Strategy or risk outcome improved by the feature. |
| **Source Data** | Upstream datasets and data contracts. |
| **Calculation Method** | Formal equation, windowing, and transformation steps. |
| **Infrastructure SLA** | p95/p99 latency, freshness, availability targets. |
| **Quality & Drift Monitoring** | Tests, thresholds, and alert routing. |
| **Validation Tests** | Automated tests (unit, integration, statistical) and cadence. |
| **Lineage** | Link to manifests, model versions, and downstream consumers. |
| **Access Policy** | IAM roles/groups authorised to query/use the feature. |
| **Change Request Process** | Required approvals, templates, and rollout procedure. |
| **Deactivation & Archival** | Conditions and workflow to sunset feature while preserving history. |
| **Auto Documentation Hooks** | Scripts/jobs that publish metadata to this catalog. |
| **Usage Examples** | References to notebooks, pipelines, or services consuming the feature. |

## Catalog Entries

### Core Production Features

| Feature Name | Owner | Version | Business Objective | Source Data | Calculation Method | Infrastructure SLA |
| --- | --- | --- | --- | --- | --- | --- |
| `feature:market/entropy/1.2.0` | Quant Research Guild (Priya Raman, backup: Daniel Ortiz) | `1.2.0` | Detect regime shifts and volatility clustering for adaptive position sizing. | `data/market_ticks`, `data/order_book_snapshots` | Shannon entropy over rolling 1-minute windows of mid-price returns with exponential decay factor 0.7; normalised by volatility baseline. | p95 latency ≤ 120 ms; freshness ≤ 5 s; availability 99.95%. |
| `feature:market/hurst/2.0.1` | Quant Research Guild (Noah Kim, backup: Wen Li) | `2.0.1` | Identify mean reversion vs. trend regimes feeding execution throttles. | `data/market_ticks` | Rescaled range analysis with overlapping 30, 60, 120-tick windows; aggregated via weighted geometric mean. | p95 latency ≤ 150 ms; freshness ≤ 5 s; availability 99.9%. |
| `feature:market/ricci/1.4.3` | Geometry Signals Team (Ava Becker, backup: Igor Kovacs) | `1.4.3` | Quantify market microstructure curvature to trigger spread-sensitive orders. | `data/order_book_snapshots`, `data/market_ticks` | Construct weighted price graph (levels × venues) and compute mean Ricci curvature using Ollivier-Ricci approximation; normalise by liquidity depth. | p95 latency ≤ 180 ms; freshness ≤ 6 s; availability 99.9%. |

### Operational Controls

| Feature Name | Quality & Drift Monitoring | Validation Tests | Lineage | Access Policy | Change Request Process | Deactivation & Archival | Auto Documentation Hooks | Usage Examples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `feature:market/entropy/1.2.0` | Kolmogorov–Smirnov drift test weekly; PSI alert if >0.2; Prometheus metric `geosync_feature_entropy_drift`. | Unit tests in `tests/indicators/test_entropy_feature.py`; integration test in `bench/feature_regression_runner.py`; nightly backtest replay. | Linked to manifest hash `mfst_2024_06_12` and models `alpha_hedge_v5`, `liquidity_guard_v3`. | IAM roles `role:quant`, `role:mlops`; audit via `observability/audit/feature_access.jsonl`. | Submit change via `docs/templates/feature_change_request.md`; requires steward + ML platform approval; canary deploy with 5% traffic. | Freeze in manifest, drain consumers, export historical values to `s3://geosync-features/archive/entropy/<version>/`; mark status `retired`. | Nightly job `make feature-catalog-export` parses manifests, updates `docs/feature_catalog.md` via Jinja template. | Example notebook `notebooks/alpha_signals/entropy_regime.ipynb`; service `core/trading/adapters/regime_allocator.py`. |
| `feature:market/hurst/2.0.1` | Drift detection comparing live vs. offline histograms; alert threshold PSI >0.15; Grafana panel `Feature Hurst Drift`. | Statistical regression test verifying scaling exponent; simulation harness `bench/hurst_calibration.py` monthly. | Manifest `mfst_2024_05_08`; consumed by `execution/throttle_controller` and `risk/position_limits`. | IAM roles `role:quant`, read-only `role:risk_view`. | Follow change template; requires risk review if thresholds adjust; deploy via blue/green manifest swap. | Maintain read-only archive in cold storage after 90 days; update catalog status to `archived`. | CI workflow `catalog-sync.yml` renders metadata from `configs/features` directory. | Notebook `notebooks/risk/hurst_signal_validation.ipynb`; API `apps/signal_service/routes.py`. |
| `feature:market/ricci/1.4.3` | Monitors ratio vs. liquidity baseline; triggers alert if daily mean deviates >3σ; metric `geosync_feature_ricci_anomaly_total`. | Validation pipeline in `tests/indicators/test_ricci_feature.py`; nightly replay with synthetic liquidity shocks. | Manifest `mfst_2024_07_01`; downstream `execution/liquidity_router` and `analytics/signal_attribution`. | Restricted to `role:quant_advanced` and `role:mlops`; access logged to audit stream. | Requires ARB sign-off due to exchange coupling; change windows scheduled Tue/Thu 22:00 UTC. | When retiring exchange venues, run deactivation script to backfill nulls, update lineage, and mark `deprecated`. | Automated doc updated via same workflow; attaches drift charts under `docs/assets/features/ricci/<date>.png`. | Notebook `notebooks/liquidity/ricci_curvature_analysis.ipynb`; service `core/execution/liquidity_router.py`. |

## Change Management Workflow

1. **Proposal** – Stewards raise `Feature Change Request` (FCR) using template; includes expected impact, risk assessment, rollout
   plan, and rollback steps.
2. **Review** – ML Platform + Data Governance review within 3 business days; security review required if access scope changes.
3. **Testing** – Execute unit/integration suite, offline backtests, and targeted chaos tests (cache eviction, data gap scenarios).
4. **Canary Deployment** – Route ≤10% of live traffic to updated feature; monitor drift, latency, and downstream signal delta.
5. **Promotion** – Upon success, update manifest, publish ADR (if architectural), and trigger automation to update catalog.
6. **Post-Deployment Verification** – After 48 hours, confirm metrics stable; update status log in `reports/feature_rollout.md`.

## Automatic Documentation Pipeline

- CI workflow `catalog-sync.yml` (to be added alongside automation) pulls metadata from `configs/features/*.yaml`, manifests, and
  MLflow tags to render catalog tables via a templating script in `tools/catalog/export_features.py`.
- Nightly job runs in staging to validate metadata completeness, diff the generated catalog against repository, and open PRs for
  steward review.
- Drift monitoring dashboards export PNG snapshots automatically appended to catalog via MkDocs `material` image embedding.
- Metadata lineage graphs are generated using `networkx` and exported under `docs/assets/features/lineage/`.

## Drift and Failure Test Playbook

- **Distribution Drift** – Weekly KS and PSI tests comparing live vs. offline distributions; escalate to `#feature-ops` Slack with
  runbook link.
- **Value Integrity** – Validate no null/NaN spikes, range constraints, and monotonic properties where applicable.
- **Latency Budget** – Synthetic load tests ensure pipeline stays within SLA under 5× burst; log to `reports/features/perf/<date>.md`.
- **Chaos Drills** – Quarterly eviction of feature cache / Redis cluster failover to validate warm-up logic and fallback heuristics.

## Deactivation and Archival Governance

- Use a two-step process: **Deprecation Notice** (communicated ≥4 weeks in advance) and **Retirement** (after consumers migrate).
- Maintain archived feature values with schema metadata for ≥12 months for audit/compliance.
- Update lineage graphs and dependent models; re-train or freeze models referencing retired features.
- Record final state, sign-offs, and reason in `reports/features/retirement_log.md`.

## Access Control Policies

- Role-based controls enforced at feature store (online + offline) with fine-grained entitlements.
- All access requests funnel through the Access Governance workflow; approvals recorded in IAM audit logs and appended to catalog.
- Sensitive features (market impact, proprietary alpha) require two-factor access and quarterly review by security + product.

## Usage Examples & Discovery

- Provide ready-to-run notebooks in `notebooks/feature_walkthroughs/` with reproducible pipelines.
- Surface features in internal portal with search facets (domain, owner, SLA, drift status).
- Tag features in catalog with `strategy:<name>` labels to map to portfolio usage.

This operating model ensures every feature powering GeoSync trading decisions remains observable, well-governed, and auditable.
