# D-002J Source Downgrade Log

This log carries every source-level downgrade or rejection across the
D-002J registry-audit history. P1A entries are preserved verbatim as a
permanent audit truth; the P1B section records the repair outcomes
applied on top of that audit truth.

---

## P1A (audit, decision SOURCE_REGISTRY_REJECTED — RETAINED)

Records every source that audit P1A demoted from its registry status. Entries only for DOWNGRADED and REJECTED. PARTIAL entries are tracked in `D002J_SOURCE_PROVENANCE_AUDIT.md` (companion).

| Source ID | Registry status (before) | Audit status (after) | Downgrade reason | Recommended next action |
|-----------|--------------------------|----------------------|------------------|--------------------------|
| ECB_CBD | USABLE_NOW | DOWNGRADED | official_url `https://sdw.ecb.europa.eu/browse.do?node=9691593` returns DNS NXDOMAIN (SDW decommissioned); documentation_url HTTP 404; ECB migrated to `data.ecb.europa.eu` portal; access_method `public_sdw_api` is stale | P2 must re-pin official_url + documentation_url to `https://data.ecb.europa.eu/data-collection/cbd` and update access_method to reflect the new Data Portal API |
| ICAP_MOVE | CANDIDATE_REQUIRES_LICENSE_REVIEW | DOWNGRADED | both URLs return HTTP 404; `theice.com/iba/move-index` and `theice.com/publicdocs/MOVE_Index_Methodology.pdf` are dead; ICE BofA reorganised methodology pages | P2 to either re-pin official_url to current ICE MOVE methodology page (verify before pinning) or accept DOWNGRADED status permanently and use only the FRED public partial-history mirror |
| BIS_QR_NETWORK | USABLE_NOW | DOWNGRADED | official_url `https://www.bis.org/publ/qtrpdf/` returns HTTP 404; BIS reorganised QR PDF tree; documentation_url `bis.org/statistics/` still 200 | P2 to re-pin official_url to `https://www.bis.org/quarterlyreviews.htm` or canonical issue-listing index; verify before pinning |
| FED_TIMELINE | USABLE_NOW | DOWNGRADED | both URLs return HTTP 404; `federalreserve.gov/aboutthefed/educational-tools/foia-financial-crisis-timeline.htm` and `monetarypolicy/financial-stability.htm` are dead; FRB reorganised educational tools tree | P2 to re-pin to current FRB financial-stability report landing `https://www.federalreserve.gov/publications/financial-stability-report.htm` plus FOMC archive paths |
| BOE_LDI_REVIEW | USABLE_NOW | DOWNGRADED | both URLs return HTTP 404; `bankofengland.co.uk/financial-stability-report/2022` and `/working-paper` are dead; BoE moved FSR slug + WP path | P2 to re-pin to current BoE Financial Stability Report path and `bankofengland.co.uk/working-paper/staff-working-papers`; pin BoE WP 1019 (Czech-Huang-Silva-Vause 2022) directly |

### P1A aggregate

5 sources DOWNGRADED. 0 sources REJECTED. Note however: the registry as a whole receives `SOURCE_REGISTRY_REJECTED` because the `information_constraint` mechanism-family floor (≥2 verified/partial) is not met (ALFRED is the only source carrying that mechanism and its audit_status is PARTIAL).

### P1A repair scope (for the follow-up fix PR)

A `fix(x10r,D-002J-P1)` PR must:

1. Re-pin the 5 downgraded sources' URL fields to live canonical pages, verified by HEAD probe at the time of writing.
2. Either add ≥1 new `information_constraint` source (e.g. Philadelphia Fed Real-Time Data Set, Atlanta Fed GDPNow vintages, BIS Long Series real-time data) or amend the prereg's mechanism-family floor with explicit, dated, signed justification.
3. Re-run the P1A audit script (or its successor) to confirm the decision flips to VERIFIED or PARTIALLY_VERIFIED.
4. The fix PR is registry repair, not new science — locked governance shas must remain byte-exact.

### P1A boundary clauses

- Does NOT ingest any data
- Does NOT claim real-bank validation
- Does NOT reopen D-002H (REFUSED remains canonical)
- Does NOT pre-empt D-002I investigation
- Does NOT authorise a canonical run
- Does NOT modify the P1 registry JSON file (audit-only)

---

## P1B (repair, decision SOURCE_REGISTRY_PARTIALLY_VERIFIED — APPLIED ON TOP OF P1A)

The five sources DOWNGRADED in P1A received the following repair outcomes in P1B. Repair outcomes are one of `REPIN_CANONICAL_URL` (provider still exists, official URL changed), `REPLACE_WITH_STRONGER_SOURCE` (provider abandoned, swap for equivalent official source), or `REJECT_AND_RECORD` (no recovery path). Each repair was HEAD-verified at the time of the P1B audit run (2026-05-14).

| Source ID | P1A audit status | P1B repair outcome | New official_url (HEAD 200) | New documentation_url (HEAD 200) | New audit status |
|-----------|------------------|---------------------|------------------------------|----------------------------------|------------------|
| ECB_CBD | DOWNGRADED | REPIN_CANONICAL_URL | `https://data.ecb.europa.eu/data/datasets/CBD2` | `https://data.ecb.europa.eu/methodology/consolidated-banking-data` | VERIFIED |
| ICAP_MOVE | DOWNGRADED | REPIN_CANONICAL_URL | `https://www.theice.com/iba` (redirects to `ice.com/iba`) | `https://www.ice.com/products` | PARTIAL (MOVE-specific methodology PDF not relocatable; license-bound; status remains CANDIDATE_REQUIRES_LICENSE_REVIEW) |
| BIS_QR_NETWORK | DOWNGRADED | REPIN_CANONICAL_URL | `https://www.bis.org/publ/quarterly.htm` (redirects to current issue `r_qt2603.htm`) | `https://www.bis.org/statistics/` (unchanged — already 200 in P1A) | VERIFIED |
| FED_TIMELINE | DOWNGRADED | REPIN_CANONICAL_URL | `https://www.federalreserve.gov/publications/financial-stability-report.htm` | `https://www.federalreservehistory.org/essays/great-recession-of-200709` (peer-reviewed FRB historical research) | VERIFIED |
| BOE_LDI_REVIEW | DOWNGRADED | REPIN_CANONICAL_URL | `https://www.bankofengland.co.uk/financial-stability-report/2022/december-2022` (canonical FSR Dec 2022; covers LDI episode) | `https://www.bankofengland.co.uk/working-paper/staff-working-papers` | VERIFIED |

### P1B new source added

| Source ID | Provider | Class | Mechanistic relevance | Reason for addition |
|-----------|----------|-------|----------------------|---------------------|
| PHILLY_FED_RTDSM | Federal Reserve Bank of Philadelphia | macro_financial | `real_time_information_constraint`, `vintage_anti_leakage_baseline` | Required to satisfy the `information_constraint` mechanism-family floor (≥ 2 verified/partial). Philly Fed Real-Time Data Set for Macroeconomists (Croushore & Stark 1999, 2003) is the canonical academic source for vintage US macro data; complements ALFRED with non-FRED-native series. official_url and documentation_url both HEAD 200 at P1B audit time. |

### P1B aggregate

- 5 sources repaired via REPIN_CANONICAL_URL (4 flip to VERIFIED, ICAP_MOVE stays PARTIAL due to MOVE-specific methodology page being unrecoverable).
- 1 new source added (PHILLY_FED_RTDSM, VERIFIED).
- Total sources: 25 (P1) → 26 (P1B).
- 0 DOWNGRADED, 0 REJECTED.
- Mechanism-family `information_constraint`: 1 (P1A) → 2 (P1B). Floor ≥ 2 now PASS.
- Audit decision: `SOURCE_REGISTRY_REJECTED` (P1A) → `SOURCE_REGISTRY_PARTIALLY_VERIFIED` (P1B).

### P1B repair discipline

- All URL repairs HEAD-verified via Python `urllib.request.Request(url, method='HEAD')` with 10s timeout and GET-Range (4 KB cap) fallback. No large GET downloads. No private data fetched.
- No D-002J prereg edit (byte-exact at `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0`).
- No D-002C ledger edit; no D-002G/D-002H/D-002I prereg/acceptance edits.
- No `research/systemic_risk/*.py` edits.
- No taxonomy collapse (`information_constraint` family retained as a separate mechanism family).
- No prereg floor weakening (mechanism-family floor unchanged at ≥ 2 verified/partial).
- No canonical run authorised (`canonical_run_authorized: false`).
- No ingestion performed.
- New parent_registry sha256 (P1B): `570ca2e219a8a398f9e6819516905623d73d08c7c135d2f6048686b46f5dbbf8`.

### P1B boundary clauses

- Does NOT ingest any data
- Does NOT claim real-bank validation
- Does NOT reopen D-002H (REFUSED remains canonical)
- Does NOT pre-empt D-002I investigation
- Does NOT authorise a canonical run
- Does NOT modify the D-002J prereg
- Does NOT weaken or collapse the `information_constraint` mechanism family
- Does NOT remove or rewrite the P1A REJECTED audit verdict — the P1A section above is preserved verbatim as banked truth

### Lineage

`D-002G → D-002H REFUSED → D-002I → D-002J prereg #694 → P1 #695 → P1A #697 REJECTED → P1B (this repair, PARTIALLY_VERIFIED)`

Next legal PR: `feat(x10r,D-002J-P2): implement crisis window registry v1`.
