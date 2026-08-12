# D-002J-P3 — Point-in-Time Discipline

PR-lineage: `D-002G -> D-002H REFUSED -> D-002I -> D-002J P0 -> P1 -> P1A REJECTED -> P1B -> P2 -> P2.5 -> P3`.

## §0 Why this matters

Look-ahead leakage is the single most common silent failure of crisis-precursor claims. A precursor at decision date `t` is only meaningful if the precursor was computable from data available at `t` — not from data first published at `t + Δ`, and not from a later vintage that revised the underlying number after `t`.

This document makes point-in-time discipline **executable** for the first time in the D-002J lineage. The contract is enforced via three machine-checkable flags in `ingestion_manifest_v1.json` (`vintage_required`, `forecast_required`, `lookahead_invariants`) plus a fail-closed test `test_revisable_sources_require_vintage_adapter` in `tests/systemic_risk/test_d002j_ingestion_manifest.py`.

Literature precedent:

- Croushore & Stark 1999/2003 — the Philadelphia Fed Real-Time Data Set for Macroeconomists (RTDSM) is the canonical anti-leakage anchor for US macro variables.
- Brunetti et al. 2019 (e-MID interbank) — uses contemporaneous tick-level interbank data only; never revised aggregates.
- FRED ALFRED — supplies vintage-dated FRED-native series via the `realtime_start` / `realtime_end` API parameters.

A precursor claim trained on post-hoc revised data is a **biographic** model of the crisis, not a **predictive** one. The vintage-aware discipline is non-negotiable.

## §1 Vintage-aware sources

A source is **vintage-aware** when its underlying observation is subject to revision after first publication. In the P1B-surviving registry, two sources carry an explicit `vintage_anti_leakage_baseline` or `real_time_information_constraint` flag in their `mechanistic_relevance` field:

| source_id | mechanistic_relevance | vintage adapter |
|-----------|-----------------------|------------------|
| `ALFRED` | `real_time_information_constraint` | `adapter_alfred_gdp_vintage_v1`, `adapter_alfred_unemp_vintage_v1` |
| `PHILLY_FED_RTDSM` | `real_time_information_constraint`, `vintage_anti_leakage_baseline` | `adapter_philly_fed_rtdsm_gdp_v1` |

The mapping is one-source-to-one-or-more-vintage-adapters. Each vintage adapter MUST declare:

- `vintage_required: true`
- `vintage_field: "vintage_release_date"` (or the schema-specific field name)
- The lookahead invariant `vintage_release_date <= decision_date`

The test `test_revisable_sources_require_vintage_adapter` enforces:
1. Every P1B source whose `mechanistic_relevance` contains `real_time_information_constraint` or `vintage_anti_leakage_baseline` is bound by at least one adapter with `vintage_required: true`.
2. Every adapter with `vintage_required: true` declares a non-null `vintage_field`.
3. Every adapter with `vintage_required: true` lists the `vintage_release_date <= decision_date` invariant.

## §2 Forecast / expectation sources

A source is a **forecast or expectation** source when the underlying datum is a forward-looking statement (consumer inflation expectations, professional forecasters' survey, breakeven implied inflation, etc.).

Adapters bound to forecast/expectation series MUST declare:

- `forecast_required: true`
- `forecast_date_field: "forecast_horizon_end_date"` (or schema-specific)
- The lookahead invariant `forecast_horizon_end_date > observation_date` AND the baseline `release_date <= decision_date`

At P3-emit time the only forecast-flagged adapter is `adapter_fred_michigan_inflation_expect_v1` (FRED MICH — University of Michigan Consumer Sentiment 1-year-ahead inflation expectations). The Philly Fed SPF could be added in a follow-up if P1B is expanded; the present registry does not include it as a distinct source. The honest baseline today is one (>=1 required) forecast adapter.

The test `test_forecast_sources_require_forecast_date_field` enforces that every `forecast_required: true` adapter declares a non-null `forecast_date_field`.

## §3 Decision-date semantics

Three timestamps are distinguished:

| Timestamp | Semantics | Manifest field |
|-----------|-----------|----------------|
| `observation_date` | When the underlying event happened | `observation_date_field` |
| `release_date` | When the data was first published | `release_date_field` |
| `decision_date` | The latest date at which the precursor can use the data | `decision_date_field` |

A precursor evaluated at `decision_date = T` MUST use only rows where `observation_date <= T` AND `release_date <= T`. For vintage-aware sources the constraint additionally requires `vintage_release_date <= T`.

`decision_date` is NOT a row attribute of the underlying source — it is the precursor-evaluation parameter. Every adapter MUST declare it explicitly so downstream ingestion can perform the inequality check.

## §4 Lookahead invariants per source class

| source_class | Required invariants |
|--------------|---------------------|
| `banking` | `observation_date <= decision_date`, `release_date <= decision_date` |
| `repo` | `observation_date <= decision_date`, `release_date <= decision_date` |
| `macro_financial` (non-vintage) | `observation_date <= decision_date`, `release_date <= decision_date` |
| `macro_financial` (vintage-aware) | `observation_date <= decision_date`, `release_date <= decision_date`, `vintage_release_date <= decision_date` |
| `macro_financial` (forecast) | `observation_date <= decision_date`, `release_date <= decision_date`, `forecast_horizon_end_date > observation_date` |
| `market_structure` | `observation_date <= decision_date`, `release_date <= decision_date` |
| `crisis_window` (event-registry) | `event_date <= decision_date`, `release_date <= decision_date` |
| `literature_support` | `publication_date <= decision_date` |

The crisis_window class uses `event_date` in place of `observation_date` because the row attribute is an official event timestamp. The literature_support class collapses observation/release into `publication_date`.

The tests `test_observation_date_lte_decision_date_invariant` and `test_release_date_lte_decision_date_invariant` enforce that every applicable adapter declares the baseline invariants verbatim.

## §5 Test surface

`tests/systemic_risk/test_d002j_ingestion_manifest.py` ships the following point-in-time tests (each `>=2` assertions):

- `test_revisable_sources_require_vintage_adapter` — the **single most important test in this PR**.
- `test_forecast_sources_require_forecast_date_field`
- `test_observation_date_lte_decision_date_invariant`
- `test_release_date_lte_decision_date_invariant`

The first test is fail-closed: any future PR that promotes ALFRED or PHILLY_FED_RTDSM to a non-vintage adapter (or removes the `vintage_required: true` flag on an existing one) breaks the build immediately.

## §6 Failure modes

| Failure mode | How it manifests | What catches it |
|--------------|------------------|------------------|
| Current FRED used in place of ALFRED for in-window decision | A precursor reads revised GDP at decision date | `test_revisable_sources_require_vintage_adapter` |
| Vintage drift inside RTDSM (definition change) | Series definition changes between two vintage releases | `vintage_required: true` adapter MUST log vintage every row; P3.5 enforcement |
| FOMC release timing collapsed to observation date | Decision rule fires before the FOMC press release crosses the wire | `release_date <= decision_date` invariant |
| Survey of Professional Forecasters used without forecast horizon | Forecast horizon flattened to observation date | `test_forecast_sources_require_forecast_date_field` |
| Paywalled vendor history used in lieu of public range | Vendor data substituted silently | `access_boundary == "license_review"` blocks `READY` status |

Every failure mode above maps to a concrete invariant in the manifest plus a concrete test in the test suite. Point-in-time discipline is no longer prose — it is a fail-closed gate.

Claim boundary: this document encodes the point-in-time CONTRACT. It does NOT execute any ingestion. It does NOT confirm a precursor signal. It does NOT authorise a canonical run. The discipline lives at the boundary; the boundary now has teeth.
