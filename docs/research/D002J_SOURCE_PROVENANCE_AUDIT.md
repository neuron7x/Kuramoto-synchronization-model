# D-002J Source Registry Provenance Audit

**Schema:** `D002J-SOURCE-PROVENANCE-AUDIT-v1`
**Parent registry (P1B):** `artifacts/d002j/data_registry/source_registry_v1.json` (sha256 `570ca2e219a8a398f9e6819516905623d73d08c7c135d2f6048686b46f5dbbf8`)
**Parent registry (P1A historical):** sha256 `0fae24d4c3ef3165509166bec89d6dc5eee806888f352358ad77851e51079b7b`
**Audit JSON:** `artifacts/d002j/data_registry/source_provenance_audit_v1.json`
**Smoke JSON:** `artifacts/d002j/data_registry/source_access_smoke_v1.json`
**Evidence lock JSON:** `artifacts/d002j/data_registry/source_evidence_lock_v1.json`
**Summary JSON:** `artifacts/d002j/data_registry/source_registry_audit_summary_v1.json`
**Companion docs:** [`D002J_SOURCE_DOWNGRADE_LOG.md`](D002J_SOURCE_DOWNGRADE_LOG.md), [`D002J_P1A_AUDIT_BOUNDARY.md`](D002J_P1A_AUDIT_BOUNDARY.md)

P1A was the first verification gate of the D-002J Frontier Benchmark Program. P1A did not add sources. P1A did not trust well-formatted metadata. P1A AUDITED the 25 sources committed in PR #695 and DOWNGRADED anything that failed one of ten verification dimensions (provider, official URL, documentation URL, access method, license boundary, coverage window, frequency, variables, crisis-window relevance, mechanistic relevance). P1A landed as a TRUTHFUL `SOURCE_REGISTRY_REJECTED` verdict at merge sha `4b64faf67f4c1bec48a66d20eeddbdf6931e762d`.

P1B (this audit) is the **repair gate**. P1B does the surgical repair of the structural defects surfaced by P1A — adding one source to satisfy the `information_constraint` mechanism-family floor and repairing five broken URL pins via HEAD-verified canonical URLs — and re-runs the P1A audit machinery against the repaired registry. P1B does NOT weaken rules, does NOT amend the D-002J prereg, does NOT fold the taxonomy, does NOT authorise a canonical run, does NOT ingest any data.

## Summary table — P1B audit (26 sources)

| Source ID | Class | Registry status (before) | Audit status (P1B) | Δ vs P1A |
|-----------|-------|--------------------------|--------------------|----------|
| BIS_CBS | banking | USABLE_NOW | VERIFIED | (same) |
| FDIC_CALL_REPORTS | banking | USABLE_NOW | VERIFIED | (same) |
| ECB_CBD | banking | USABLE_NOW | **VERIFIED** | DOWNGRADED → VERIFIED (URL repaired) |
| FED_Y9C | banking | USABLE_NOW | PARTIAL | (same) |
| NYFED_SOFR | repo | USABLE_NOW | VERIFIED | (same) |
| OFR_REPO_DATA | repo | USABLE_NOW | VERIFIED | (same) |
| FED_H15 | repo | USABLE_NOW | VERIFIED | (same) |
| ECB_MMSR | repo | CANDIDATE_REQUIRES_LICENSE_REVIEW | PARTIAL | (same) |
| FRED | macro_financial | USABLE_NOW | VERIFIED | (same) |
| ALFRED | macro_financial | USABLE_NOW | PARTIAL | (same) |
| **PHILLY_FED_RTDSM** | **macro_financial** | **USABLE_NOW** | **VERIFIED** | **NEW IN P1B** |
| OFR_FSI | macro_financial | USABLE_NOW | VERIFIED | (same) |
| STLFSI | macro_financial | USABLE_NOW | VERIFIED | (same) |
| KCFSI | macro_financial | USABLE_NOW | PARTIAL | (same) |
| CBOE_VIX | market_structure | USABLE_NOW | PARTIAL | (same) |
| ICAP_MOVE | market_structure | CANDIDATE_REQUIRES_LICENSE_REVIEW | **PARTIAL** | DOWNGRADED → PARTIAL (URL repaired but MOVE-specific methodology PDF unrecoverable) |
| BIS_QR_NETWORK | market_structure | USABLE_NOW | **VERIFIED** | DOWNGRADED → VERIFIED (URL repaired) |
| OFR_WP_NETWORK | market_structure | USABLE_NOW | VERIFIED | (same) |
| NBER_RECESSION | crisis_window | USABLE_NOW | VERIFIED | (same) |
| FED_TIMELINE | crisis_window | USABLE_NOW | **VERIFIED** | DOWNGRADED → VERIFIED (URL repaired) |
| ECB_FSR | crisis_window | USABLE_NOW | VERIFIED | (same) |
| BOE_LDI_REVIEW | crisis_window | USABLE_NOW | **VERIFIED** | DOWNGRADED → VERIFIED (URL repaired) |
| FDIC_SVB_POSTMORTEM | crisis_window | USABLE_NOW | PARTIAL | (same) |
| LIT_INTERBANK_CONTAGION | literature_support | USABLE_NOW | VERIFIED | (same) |
| LIT_NETWORK_RECON | literature_support | USABLE_NOW | VERIFIED | (same) |
| LIT_REPO_FUNDING | literature_support | USABLE_NOW | PARTIAL | (same) |

**P1B aggregate:** 18 VERIFIED, 8 PARTIAL, 0 DOWNGRADED, 0 REJECTED (26 total).
**verified_or_partial = 26** (floor 18 — PASS).
**verified_usable_now = 18** (floor 12 — PASS).

**Crisis-window retention (≥3 verified/partial each):** CW1 21, CW2 16, CW3 17, CW4 19, CW5 12, CW6 16 — PASS.

**Mechanism-family retention (≥2 verified/partial each):**

| Mechanism family | Verified+partial (P1A) | Verified+partial (P1B) |
|------------------|------------------------|------------------------|
| balance_sheet | 3 | 4 |
| contagion | 4 | 5 |
| information_constraint | **1 (FAIL)** | **2 (PASS)** |
| liquidity_funding | 7 | 7 |
| market_wide_stress | 6 | 7 |
| official_response | 5 | 7 |

The `information_constraint` family now carries two sources (`ALFRED` and `PHILLY_FED_RTDSM`), satisfying the ≥ 2 floor. The audit decision flips from `SOURCE_REGISTRY_REJECTED` (P1A) to `SOURCE_REGISTRY_PARTIALLY_VERIFIED` (P1B) — eight sources remain PARTIAL (documentation_url regressions on substantively-alive products + ICAP_MOVE methodology page unrecoverable), but the decision is PARTIALLY rather than VERIFIED.

## P1B repair detail (5 URLs + 1 new source)

Each P1B repair was HEAD-verified against the live live URL at audit time via Python `urllib.request.Request(url, method='HEAD')` with a 10-second timeout and a 4 KB GET-Range fallback for servers that reject HEAD. The probe results are recorded in `source_access_smoke_v1.json`.

- **ECB_CBD** — `REPIN_CANONICAL_URL`. SDW (`sdw.ecb.europa.eu`) was decommissioned; ECB migrated CBD to the new ECB Data Portal. official_url repinned to `https://data.ecb.europa.eu/data/datasets/CBD2` (HEAD 200) and documentation_url to `https://data.ecb.europa.eu/methodology/consolidated-banking-data` (HEAD 200). access_method updated from `public_sdw_api` → `public_ecb_data_portal_api`. Audit flips DOWNGRADED → VERIFIED.

- **ICAP_MOVE** — `REPIN_CANONICAL_URL`. Both legacy URLs HTTP 404. official_url repinned to `https://www.theice.com/iba` (HEAD 200, redirects to `ice.com/iba`) and documentation_url to `https://www.ice.com/products` (HEAD 200). The MOVE-specific methodology PDF is no longer relocatable on the live ICE site as of the P1B HEAD probe — full methodology now sits in the ICE Indices subscriber portal. Audit flips DOWNGRADED → **PARTIAL** because the substantive ICE IBA umbrella + ICE products index verify but the MOVE-specific methodology page does not. Registry status remains `CANDIDATE_REQUIRES_LICENSE_REVIEW` so the existing forbidden_use clauses still bound redistribution.

- **BIS_QR_NETWORK** — `REPIN_CANONICAL_URL`. Legacy `/publ/qtrpdf/` directory listing HTTP 404 after BIS site reorganisation. official_url repinned to `https://www.bis.org/publ/quarterly.htm` (HEAD 200, redirects to current issue `r_qt2603.htm`). documentation_url `bis.org/statistics/` unchanged (already 200 in P1A). Audit flips DOWNGRADED → VERIFIED.

- **FED_TIMELINE** — `REPIN_CANONICAL_URL`. Both legacy URLs HTTP 404 after FRB site reorganisation. official_url repinned to `https://www.federalreserve.gov/publications/financial-stability-report.htm` (HEAD 200) — the canonical FRB Financial Stability Report landing — and documentation_url to `https://www.federalreservehistory.org/essays/great-recession-of-200709` (HEAD 200, title verified as "The Great Recession") — peer-reviewed FRB historical research. Audit flips DOWNGRADED → VERIFIED.

- **BOE_LDI_REVIEW** — `REPIN_CANONICAL_URL`. Both legacy URLs HTTP 404 after BoE slug reorganisation. official_url repinned to `https://www.bankofengland.co.uk/financial-stability-report/2022/december-2022` (HEAD 200, title verified as "Financial Stability Report - December 2022") — this issue carries the canonical LDI episode post-mortem — and documentation_url to `https://www.bankofengland.co.uk/working-paper/staff-working-papers` (HEAD 200). Audit flips DOWNGRADED → VERIFIED.

- **PHILLY_FED_RTDSM** — `ADDED_NEW_INFORMATION_CONSTRAINT_SOURCE`. New source: Philadelphia Fed Real-Time Data Set for Macroeconomists. official_url `https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists` (HEAD 200), documentation_url `https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-full-documentation` (HEAD 200). Canonical academic source for vintage US macro data since Croushore & Stark (1999, 2003). Complements ALFRED with non-FRED-native macro variables (GNP-era pre-1992 definitions, multiple GDP definitional regimes). Mechanistic relevance: `real_time_information_constraint` + `vintage_anti_leakage_baseline`. Audit status: VERIFIED.

## By source class — P1B

### Banking (4 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| BIS_CBS | VERIFIED | bis.org/statistics/consstats.htm HEAD 200 | provider + URLs + 1983Q4 origin + variables all live |
| FDIC_CALL_REPORTS | VERIFIED | cdr.ffiec.gov/public/ 200; fdic.gov/resources/bankers/call-reports/ 200 | FFIEC CDR portal + 1976Q1 origin + schedule RC/RC-E/RC-N all live |
| ECB_CBD | **VERIFIED** (was DOWNGRADED) | data.ecb.europa.eu/data/datasets/CBD2 200; methodology page 200 | P1B repair: SDW migrated to ECB Data Portal; both URLs repinned and HEAD-verified |
| FED_Y9C | PARTIAL | federalreserve.gov/apps/mdrm/data-dictionary 200; ffiec.gov nicpubweb Y9CMain 404 | MDRM dictionary live (substantive anchor); FFIEC NIC Y-9C page moved to /npw/FinancialReport |

### Repo (4 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| NYFED_SOFR | VERIFIED | newyorkfed.org/markets/reference-rates/sofr 200 | full pin chain live; 2018-04-02 origin; percentile bands + volume in docs |
| OFR_REPO_DATA | VERIFIED | financialresearch.gov/short-term-funding-monitor/ 200 | dashboard + CSV export live since 2014-01-01 |
| FED_H15 | VERIFIED | federalreserve.gov/releases/h15/ 200 | 1962-01-02 origin; daily; FRED mirror DGS10/DFF/DPRIME |
| ECB_MMSR | PARTIAL | ecb.europa.eu money_market/html/index.en.html 200; mmsr/html/index.en.html 404 | aggregate ESTR + volumes public; mmsr nav URL moved under data.ecb portal |

### Macro-financial (6 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| FRED | VERIFIED | fred.stlouisfed.org/ 200; API docs 200 | API docs live; all listed series verifiable |
| ALFRED | PARTIAL | alfred.stlouisfed.org/ 200; docs/api/alfred/ unreachable HEAD | landing live; documentation surface partially unreachable from sandbox |
| **PHILLY_FED_RTDSM** | **VERIFIED** | **philadelphiafed.org RTDSM landing 200; documentation page 200** | **NEW IN P1B: canonical vintage US macro source; satisfies information_constraint floor** |
| OFR_FSI | VERIFIED | financialresearch.gov/financial-stress-index/ 200 | 2000-01-04 origin; 5 regions; subcomponents match Monin 2017 |
| STLFSI | VERIFIED | fred.stlouisfed.org/series/STLFSI4 200; Kliesen-Smith 2010 200 | Kliesen-Smith 2010 doc live; LIBOR-replacement break documented |
| KCFSI | PARTIAL | fred.stlouisfed.org/series/KCFSI 200; KC Fed measuring-financial-stress page 404 | series live on FRED; KC Fed paper landing moved |

### Market structure (4 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| CBOE_VIX | PARTIAL | fred.stlouisfed.org/series/VIXCLS 200; cboe.com vix_historical_data 403 | FRED-mirrored series is the redistributable surface; CBOE site blocks bot |
| ICAP_MOVE | **PARTIAL** (was DOWNGRADED) | theice.com/iba 200; ice.com/products 200 | P1B repair: ICE IBA umbrella + products index repinned; MOVE-specific methodology page remains unrecoverable so PARTIAL not VERIFIED |
| BIS_QR_NETWORK | **VERIFIED** (was DOWNGRADED) | bis.org/publ/quarterly.htm 200 | P1B repair: canonical QR landing repinned (redirects to current issue) |
| OFR_WP_NETWORK | VERIFIED | financialresearch.gov/working-papers/ 200 | index live; methodology references not raw data correctly forbidden |

### Crisis window (5 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| NBER_RECESSION | VERIFIED | nber.org/research/business-cycle-dating 200 | BCD Committee page live; 1854 origin; USREC FRED mirror canonical |
| FED_TIMELINE | **VERIFIED** (was DOWNGRADED) | federalreserve.gov/publications/financial-stability-report.htm 200; federalreservehistory.org/essays/great-recession-of-200709 200 | P1B repair: FRB FSR + FRB History Great Recession essay both HEAD-verified |
| ECB_FSR | VERIFIED | ecb.europa.eu pub/financial-stability/fsr/html/index.en.html 200 | semi-annual since 2004; Nov 2022 covers UK LDI |
| BOE_LDI_REVIEW | **VERIFIED** (was DOWNGRADED) | bankofengland.co.uk/financial-stability-report/2022/december-2022 200 (title "Financial Stability Report - December 2022"); working-paper/staff-working-papers 200 | P1B repair: canonical 2022 LDI FSR + WP staff index repinned |
| FDIC_SVB_POSTMORTEM | PARTIAL | fdic.gov press 2023 200; fdicoig.gov MLR path 404 | docs URL live; official_url MLR path moved; substantive OIG product canonical |

### Literature support (3 sources)

| Source | Status | Key evidence | Reason |
|--------|--------|--------------|--------|
| LIT_INTERBANK_CONTAGION | VERIFIED | jstor.org/ 200; nber.org/papers 200 | Eisenberg-Noe / Battiston / Glasserman-Young / Anand / Aldasoro-Alves / Brunnermeier all preprint-available |
| LIT_NETWORK_RECON | VERIFIED | bundesbank.de discussion-papers 200; ssrn.com 200 | Upper-Worms / Mistrulli / Anand-Craig-von-Peter / Battiston 2016 all verifiable |
| LIT_REPO_FUNDING | PARTIAL | nber.org/papers 200; federalreserve.gov/econres/feds.htm 404 | NBER lit anchors live; FEDS index path reorganised |

## How audit_status is assigned

Per master doc §5/§6:

* **VERIFIED** — all 10 verification dimensions are "yes": provider, official_url, documentation, access_method, license_boundary, coverage, frequency, variables, crisis_window_relevance, mechanistic_relevance.
* **PARTIAL** — most dimensions yes, 1–2 partial, none fail; typical case is a stale documentation_url with the substantive product still reachable.
* **DOWNGRADED** — at least one dimension fails AND at least one other is fine; source stays in registry but flagged for restricted use.
* **REJECTED** — multiple dimensions fail OR provenance fundamentally broken.

P1B surfaced **0 DOWNGRADED** and **0 REJECTED** sources because every defect P1A surfaced was either repaired (5 sources flip to VERIFIED, except ICAP_MOVE which remains PARTIAL for the MOVE-specific methodology page) or absorbed into the PARTIAL bucket where the substantive product is alive but a documentation_url is moved.

## Decision

`SOURCE_REGISTRY_PARTIALLY_VERIFIED`. The audit affirms 26/26 sources hold (VERIFIED+PARTIAL ≥ floor 18), `verified_usable_now=18` clears the floor 12, all six crisis windows retain ≥ 12 verified/partial sources, and all six mechanism families retain ≥ 2 verified/partial sources (information_constraint specifically went from 1 to 2 via the PHILLY_FED_RTDSM addition). The `SOURCE_REGISTRY_REJECTED` verdict from P1A is preserved as banked truth in `D002J_SOURCE_DOWNGRADE_LOG.md` — P1B does not rewrite history; it repairs forward.

## Locked invariants (byte-exact)

* `docs/governance/D002C_CLAIM_LEDGER.yaml` — `eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387`
* `docs/governance/D002G_PREREGISTRATION.yaml` — `1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04`
* `docs/governance/D002G_ACCEPTANCE_RULES.md` — `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31`
* `docs/governance/D002H_PREREGISTRATION.yaml` — `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec`
* `docs/governance/D002I_PREREGISTRATION.yaml` — `b646989c032dc0e29f9b791e0b68209ff22b40f4757737712badc8656cf2db5f`
* `docs/governance/D002J_PREREGISTRATION.yaml` — `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0`
* `artifacts/d002j/data_registry/source_registry_v1.json` (P1B repaired) — `570ca2e219a8a398f9e6819516905623d73d08c7c135d2f6048686b46f5dbbf8`

P1B modifies registry v1.json (registry repair) and the audit/smoke/lock/summary artifacts. P1B does NOT modify the six governance/prereg shas above. Tests `test_d002j_prereg_not_modified` / `test_d002c_ledger_not_modified` / `test_systemic_risk_source_code_not_modified` / `test_no_prereg_floor_weakened` / `test_no_taxonomy_collapse` enforce this byte-exactly.

## Lineage

`D-002G → D-002H REFUSED → D-002I → D-002J #694 (prereg) → P1 #695 (registry) → P1A #697 REJECTED → P1B (this PR; PARTIALLY_VERIFIED)`

Next legal PR: `feat(x10r,D-002J-P2): implement crisis window registry v1`.
