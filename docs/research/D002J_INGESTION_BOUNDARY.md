# D-002J-P3 — Ingestion Boundary

PR-lineage: `D-002G -> D-002H REFUSED -> D-002I -> D-002J P0 -> P1 -> P1A REJECTED -> P1B -> P2 -> P2.5 -> P3`.

## §0 Mission

Define **what may be ingested**, by **which adapter**, from **which P1B-audit-surviving source**, for **which P2 crisis window**, under **what license/access boundary**, with **what anti-lookahead constraints**.

P3 is a **contract** phase. P3 does NOT execute any ingestion. P3 does NOT fetch a single byte. P3 does NOT model anything. P3 does NOT authorise any canonical run. P3 does NOT rewrite the P1B source registry or the P2 crisis window registry — both parents are sha256-pinned in the manifest's `parent_*_sha256` fields.

The artifact `artifacts/d002j/ingestion/ingestion_manifest_v1.json` is the single source of truth. Every machine-verifiable invariant in this document is tested in `tests/systemic_risk/test_d002j_ingestion_manifest.py`.

## §1 Adapter class taxonomy

Five adapter classes are admissible. Each binds one or more P1B-surviving `source_id` records to one or more P2 `window_id` records.

| Class | Purpose | Fetch mechanism | Bytes ingested at P5+? |
|-------|---------|-----------------|------------------------|
| `static_csv_adapter` | One-shot static CSV from official archive | HTTP GET on a static URL or bulk archive | Yes (file contents) |
| `official_api_adapter` | Official provider API call | Authenticated or free-key REST/SDMX request | Yes (JSON or CSV) |
| `metadata_only_adapter` | Documentation/metadata only — NEVER the underlying micro data | HTTP GET on documentation page | Metadata bytes only (data NEVER fetched) |
| `literature_reference_adapter` | Academic paper / preprint reference | Reference declaration only — DOIs, arXiv IDs, citation records | Reference record only |
| `manual_event_registry_adapter` | Manual entry from official timeline / postmortem report | Hand-curated event records from public record | Hand-curated event JSON |

The class is **fail-closed** with respect to fetch semantics: a `metadata_only_adapter` is forbidden from ever pulling the underlying micro data, even if a future P3.5 author writes that code. The test surface in `tests/systemic_risk/test_d002j_ingestion_manifest.py` blocks any adapter from declaring `restricted_microdata: true` with status `READY`.

## §2 Adapter status taxonomy

| Status | Meaning | Permitted next move |
|--------|---------|---------------------|
| `READY` | Adapter scaffolded, endpoint live, license public, ready for P3.5 implementation | P3.5 may implement fetch |
| `STUB_ONLY` | Placeholder; binding declared but no fetch logic yet | P3.5 may implement after promotion to READY |
| `REQUIRES_MANUAL_DOWNLOAD` | Humans-only path; no public ingestible endpoint | Manual download SOP must precede P3.5 |
| `REQUIRES_LICENSE_REVIEW` | License unclear, blocked until review | License review must precede status change |
| `REJECTED` | Adapter cannot be built (source died, license forbids, etc.) | Permanently retained as truthful negative artifact |

At P3-emit time NO adapter is `READY`. The honest baseline is `STUB_ONLY` for sources with public ingestible endpoints, `REQUIRES_MANUAL_DOWNLOAD` for sources requiring archive download outside a stable API, and `REQUIRES_LICENSE_REVIEW` for sources gated by vendor licence or microdata restriction. **Status inflation is the most likely failure mode of this PR and is explicitly tested.**

## §3 Anti-lookahead invariants

Every adapter declares a `lookahead_invariants` list. The invariants are stated in pseudo-code and tested both at the manifest layer (every adapter MUST declare the baseline) and as a contract that downstream ingestion at P3.5+ MUST verify per-row.

The baseline (applies to every adapter that pulls observation-bearing data):

- `observation_date <= decision_date` — the underlying event MUST have already happened by the time a precursor decision is taken.
- `release_date <= decision_date` — the data MUST have already been published by the time a precursor decision is taken.

For vintage-aware sources (`vintage_required: true`), the extra invariant:

- `vintage_release_date <= decision_date` — the specific vintage release MUST have been the one available at decision time.

For forecast/expectation sources (`forecast_required: true`), the extra invariant:

- `forecast_horizon_end_date > observation_date` — the forecast must look forward, not backward.

These four invariants are encoded as enumerated strings inside the manifest JSON; the test suite parses them and checks structural conformance per source class.

## §4 License boundary handling

Every adapter carries a `license_boundary` string copied verbatim from the parent P1B source record. The boundary is mapped to one of four `access_boundary` values:

| `access_boundary` | Meaning | Adapter classes allowed |
|-------------------|---------|-------------------------|
| `public` | Public redistribution permitted with attribution | any |
| `registered` | Free API key registration required (FRED) | `official_api_adapter` |
| `paywall` | Paywalled content — adapter forbidden | none — must be `REJECTED` |
| `license_review` | Licence ambiguous or vendor-licensed — review required | `metadata_only_adapter` at most |

The combination `(access_boundary == "license_review", status == "READY")` is forbidden by test.

## §5 Max-download-size policy

Every adapter declares a `max_download_bytes` cap. The repo-wide default is 5 MB (5 000 000 bytes). Metadata-only and literature-reference adapters cap at 0.5 MB. Any adapter requesting a larger cap MUST justify the override in its schema contract document (P3.5 territory) and is rejected at this layer.

The cap is fail-closed: at P3.5+ a fetch that exceeds the cap aborts without writing partial output.

## §6 Determinism contract

Every adapter declares:

- `deterministic_replay: true` — given the same `decision_date`, the same vintage / forecast inputs, and the same endpoint state, the adapter MUST produce a byte-identical output to the previously pinned sha256 in `source_hash_manifest_v1.json`.
- `wall_clock_dependent: false` — no adapter may include wall-clock time in its output canonicalisation. All time stamps are decision-time-relative.
- `rate_limit_policy`: provider-stated rate limit (e.g. `fred_api_120_req_per_min_per_key`) or `null` if not documented.

A `deterministic_replay: false` adapter is forbidden at P3.5+ unless and until a separate falsifier PR shows the non-determinism is inherent and quantified.

## §7 Forbidden ingestion

Three categories are forbidden at every adapter:

- `private_data: true` — no adapter may ingest private (non-public) data.
- `restricted_microdata: true` — no adapter may ingest microdata under aggregates-only restriction (ECB MMSR class). Metadata-only path is permitted; the underlying micro data is NOT.
- Paywall scraping — no adapter may bypass a paywall; vendor-licensed sources MUST go through the licence review path.

Every adapter explicitly declares these flags. The test surface enforces both `private_data` and `restricted_microdata=ready` exclusion.

## §8 Per-adapter table

The full table is the `adapters` array in `artifacts/d002j/ingestion/ingestion_manifest_v1.json`. Below is the human-readable summary at PR-emit time. **Vintage-aware** and **forecast** flags follow §3.

| adapter_id | class | status | source_id | vintage | forecast | access |
|---|---|---|---|---|---|---|
| `adapter_fred_vixcls_v1` | `official_api_adapter` | `STUB_ONLY` | `CBOE_VIX` | no | no | public |
| `adapter_fred_stlfsi_v1` | `official_api_adapter` | `STUB_ONLY` | `STLFSI` | no | no | public |
| `adapter_fred_kcfsi_v1` | `official_api_adapter` | `STUB_ONLY` | `KCFSI` | no | no | public |
| `adapter_fred_h15_treasury_v1` | `official_api_adapter` | `STUB_ONLY` | `FED_H15` | no | no | public |
| `adapter_fred_michigan_inflation_expect_v1` | `official_api_adapter` | `STUB_ONLY` | `FRED` | no | **yes** | public |
| `adapter_fred_ofr_fsi_v1` | `official_api_adapter` | `STUB_ONLY` | `OFR_FSI` | no | no | public |
| `adapter_alfred_gdp_vintage_v1` | `official_api_adapter` | `STUB_ONLY` | `ALFRED` | **yes** | no | public |
| `adapter_alfred_unemp_vintage_v1` | `official_api_adapter` | `STUB_ONLY` | `ALFRED` | **yes** | no | public |
| `adapter_philly_fed_rtdsm_gdp_v1` | `static_csv_adapter` | `REQUIRES_MANUAL_DOWNLOAD` | `PHILLY_FED_RTDSM` | **yes** | no | public |
| `adapter_bis_cbs_v1` | `static_csv_adapter` | `REQUIRES_MANUAL_DOWNLOAD` | `BIS_CBS` | no | no | public |
| `adapter_ecb_cbd_v1` | `official_api_adapter` | `STUB_ONLY` | `ECB_CBD` | no | no | public |
| `adapter_ofr_repo_dashboard_v1` | `static_csv_adapter` | `STUB_ONLY` | `OFR_REPO_DATA` | no | no | public |
| `adapter_ecb_mmsr_metadata_v1` | `metadata_only_adapter` | `REQUIRES_LICENSE_REVIEW` | `ECB_MMSR` | no | no | license_review |
| `adapter_icap_move_metadata_v1` | `metadata_only_adapter` | `REQUIRES_LICENSE_REVIEW` | `ICAP_MOVE` | no | no | license_review |
| `adapter_lit_interbank_contagion_v1` | `literature_reference_adapter` | `STUB_ONLY` | `LIT_INTERBANK_CONTAGION` | no | no | public |
| `adapter_lit_network_recon_v1` | `literature_reference_adapter` | `STUB_ONLY` | `LIT_NETWORK_RECON` | no | no | public |
| `adapter_fed_timeline_events_v1` | `manual_event_registry_adapter` | `STUB_ONLY` | `FED_TIMELINE` | no | no | public |
| `adapter_fred_nber_recession_v1` | `official_api_adapter` | `STUB_ONLY` | `NBER_RECESSION` | no | no | public |

18 adapters total. Floors met: 7 macro-financial-bound (>=6 required), 5 BIS/ECB/OFR-bound (>=3 required), 2 metadata_only (>=2 required), 2 literature_reference (>=2 required), 3 vintage-aware (>=1 required), 1 forecast (>=1 required).

No adapter is `READY`. This is honest: P3 ships the CONTRACT, not the pipeline. P3.5 may promote a STUB_ONLY adapter to READY only after the endpoint is verified live, the schema contract document is written, and the local-replay test produces a deterministic sha256.

Claim boundary: this document describes adapter CONTRACTS. It does NOT describe results. It does NOT authorise canonical run. It does NOT rescue D-002H. The whole D-002J lineage remains at decision boundary "no prediction, no bank-level validation".
