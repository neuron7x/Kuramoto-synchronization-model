# D-002J — Source Selection Rationale (P1)

Pre-registration anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
PR lineage: D-002J-P1 (`feat/x10r-d002j-p1-data-source-registry-v1`)
Date: 2026-05-14
Machine-readable registry: `artifacts/d002j/data_registry/source_registry_v1.json`

## Selection methodology

The 25 sources in the D-002J-P1 registry are selected against six
public-source axes:

1. **Mechanistic coverage** — each of the seven W4 mechanism
   families named in D-002J prereg §3 / §5 has at least one source
   that observes (or proxies) its key observable.
2. **Crisis-window coverage** — each of the six crisis windows
   CW1..CW6 has at least five corroborating public sources at
   appropriate frequency.
3. **License boundary** — every source has an explicit license
   classification: `public_domain_us_government_work`,
   `public_domain_with_attribution_required`, or
   `public_redistribution_permitted_with_attribution`. Two sources
   sit in `CANDIDATE_REQUIRES_LICENSE_REVIEW` because their full
   history is vendor-licensed (`ICAP_MOVE`) or because their micro
   layer is restricted (`ECB_MMSR`).
4. **Provenance discipline** — every source has an official URL,
   a documentation URL, and an `access_method` description. No
   source is in the registry without a public landing page.
5. **Literature anchor** — six methodology references back the
   substrate / null-model design at the level of canonical papers
   (Eisenberg-Noe 2001; Battiston et al. 2012; Brunnermeier 2009;
   Mistrulli 2011; Gorton-Metrick 2012; Anand et al. 2018).
6. **Provenance-not-promise discipline** — the registry is
   documentation, not validation. A source's presence in the
   registry does NOT imply ingestion has occurred or that any
   downstream claim has been tested against it.

The registry deliberately excludes:

- Vendor-paywalled feeds where neither public summary nor preprint
  exists (e.g. Compustat-Banks full panel, SNL / S&P Capital IQ,
  Bloomberg terminal data).
- Sources where the methodology owner does not permit redistribution
  even of derived series (e.g. proprietary CDS indices in their
  full daily form).
- Internal regulatory micro-data that is not public (e.g. FR Y-14
  CCAR submissions, ECB AnaCredit, supervisory stress-test
  submissions).

These exclusions are intentional and are tracked under
`REJECTED_NONPUBLIC_OR_RESTRICTED`. Currently zero sources sit in
this bucket because such sources were not added — the boundary is
enforced at selection time, not at audit time.

---

## §9 Selection matrix — all 25 sources

The matrix below appears EXHAUSTIVE: every source in the registry
appears in exactly one row. `next_pr_use` lists the downstream PR
tag (D-002J-W*) where the source is intended to be ingested.

| source_id                  | provider                          | source_class       | mechanistic_relevance                            | crisis_window_relevance | status                              | why_include                                                                  | why_not_enough_alone                                                                | next_pr_use            |
|----------------------------|-----------------------------------|--------------------|--------------------------------------------------|-------------------------|-------------------------------------|------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|------------------------|
| `BIS_CBS`                  | Bank for International Settlements | banking            | interbank_exposure_concentration; cross_border   | CW1..CW6                | USABLE_NOW                          | Deepest public cross-border banking time series; canonical Anand 2018 input  | Quarterly; jurisdiction-aggregate only; no counterparty resolution                  | D-002J-W4              |
| `FDIC_CALL_REPORTS`        | FDIC                              | banking            | funding_maturity_mismatch; uninsured_deposit_run | CW1, CW6                | USABLE_NOW                          | Canonical US per-bank balance-sheet; SVB 2023 attribute source               | Quarterly; US-only; off-balance-sheet partial                                       | D-002J-W4              |
| `ECB_CBD`                  | European Central Bank             | banking            | interbank_exposure_concentration; capital_buffer | CW2, CW4                | USABLE_NOW                          | Canonical euro-area consolidated banking source                              | Post-2007 only; semi-annual for some indicators                                     | D-002J-W4              |
| `FED_Y9C`                  | Federal Reserve Board             | banking            | derivatives_concentration; rehypothecation_proxy | CW1, CW3, CW6           | USABLE_NOW                          | US BHC consolidated holding-company view; trading book breakdown             | Threshold raised 2015 — breaks panel; off-balance-sheet aggregated                  | D-002J-W4              |
| `NYFED_SOFR`               | Federal Reserve Bank of New York  | repo               | liquidity_rollover_stress; repo_haircut          | CW3, CW4, CW6           | USABLE_NOW                          | Canonical 2019 repo-spike daily signal                                       | Post-2018 only; aggregates three repo segments                                      | D-002J-W4              |
| `OFR_REPO_DATA`            | OFR                               | repo               | repo_haircut; rehypothecation; rollover_stress   | CW3, CW4, CW6           | USABLE_NOW                          | Tri-party repo volumes + haircut distribution                                | Bilateral uncleared partial; haircut aggregated not per-ISIN                         | D-002J-W4              |
| `FED_H15`                  | Federal Reserve Board             | repo               | term_structure; discount_window                   | CW1..CW6                | USABLE_NOW                          | Canonical US interest-rate universe back to 1962                             | LIBOR cessation 2023 breaks some series                                              | D-002J-W4              |
| `ECB_MMSR`                 | European Central Bank             | repo               | rollover_stress; secured_unsecured_spread        | CW5                     | CANDIDATE_REQUIRES_LICENSE_REVIEW   | Daily euro-area secured / unsecured aggregates                               | Aggregates only public; micro data restricted; post-2016 only                       | D-002J-W4 (review)     |
| `FRED`                     | Federal Reserve Bank of St. Louis | macro_financial    | market_wide_deleveraging; credit_spread; term    | CW1..CW6                | USABLE_NOW                          | De facto public macro-financial backbone                                     | Aggregator — upstream revisions propagate; some series attribution-only             | D-002J-W2 + W4         |
| `ALFRED`                   | Federal Reserve Bank of St. Louis | macro_financial    | real_time_information_constraint                  | CW1..CW6                | USABLE_NOW                          | Vintage-dated FRED for honest real-time replication                          | Vintages only back to first release date; non-FRED-native series not vintaged       | D-002J-W2              |
| `PHILLY_FED_RTDSM`         | Federal Reserve Bank of Philadelphia | macro_financial | real_time_information_constraint; vintage_anti_leakage_baseline | CW1..CW6 | USABLE_NOW                          | Canonical vintage US macro data since Croushore-Stark; satisfies information_constraint floor | US-only; macro-only; quarterly vintage cadence                                       | D-002J-W2              |
| `OFR_FSI`                  | OFR                               | macro_financial    | market_wide_stress; external_window_anchor       | CW1..CW6                | USABLE_NOW                          | Daily five-region stress composite plus sub-indices                          | Composite — circular if used as y-label with same constituents in x                 | D-002J-W2              |
| `STLFSI`                   | Federal Reserve Bank of St. Louis | macro_financial    | us_financial_stress_anchor                        | CW1, CW2, CW3, CW4, CW6 | USABLE_NOW                          | US-specific stress series back to 1993                                       | Weekly; STLFSI / STLFSI2 / STLFSI4 redesigns break continuity                       | D-002J-W2              |
| `KCFSI`                    | Federal Reserve Bank of Kansas City | macro_financial  | us_financial_stress_alternative                   | CW1, CW2                | USABLE_NOW                          | Long-history monthly US stress series back to 1990                           | Monthly — too coarse for repo-spike or COVID dynamics                               | D-002J-W2              |
| `CBOE_VIX`                 | CBOE via FRED VIXCLS              | market_structure   | market_wide_deleveraging; risk_off_episode        | CW1..CW6                | USABLE_NOW                          | Fastest market-wide stress proxy with daily data back to 1990               | Implied not realised; US-equity focus; 2003 methodology break                       | D-002J-W2              |
| `ICAP_MOVE`                | ICE BofA partial via FRED          | market_structure   | fixed_income_specific_stress                      | CW1..CW6                | CANDIDATE_REQUIRES_LICENSE_REVIEW   | Treasury implied volatility; LDI-window cross-check                          | Full history vendor-licensed; US treasuries only                                    | D-002J-W2 (review)     |
| `BIS_QR_NETWORK`           | BIS                               | market_structure   | global_banking_network; non_bank_intermediation   | CW1..CW6                | USABLE_NOW                          | Quarterly narrative + associated CSV for cross-border banking network        | Narrative PDF — extraction pipeline required                                        | D-002J-W4              |
| `OFR_WP_NETWORK`           | OFR                               | market_structure   | interbank_reconstruction_methodology              | CW1, CW2, CW3, CW4      | USABLE_NOW                          | Public methodology anchor for max-entropy / sparse reconstruction            | Methodology, not raw data                                                            | D-002J-W4 (literature) |
| `NBER_RECESSION`           | NBER                              | crisis_window      | external_crisis_window_anchor                     | CW1, CW4                | USABLE_NOW                          | Canonical US recession label (FRED USREC)                                    | US-only; dating lag; covers recessions not all financial stress                      | D-002J-W2              |
| `FED_TIMELINE`             | Federal Reserve                   | crisis_window      | facility_announcements; intervention_event_study  | CW1, CW3, CW4, CW6      | USABLE_NOW                          | Canonical US central-bank action chronology                                  | Narrative PDF — extraction required                                                  | D-002J-W2              |
| `ECB_FSR`                  | European Central Bank             | crisis_window      | euro_area_narrative; vulnerability_anchor          | CW1, CW2, CW4, CW5      | USABLE_NOW                          | Canonical euro-area FSR narrative                                            | Semi-annual narrative; euro-area focus                                              | D-002J-W2              |
| `BOE_LDI_REVIEW`           | Bank of England                   | crisis_window      | ldi_collateral_call; pension_fund_liquidity      | CW5                     | USABLE_NOW                          | Canonical 2022 LDI chronology                                                | Narrative PDF; post-mortem only                                                     | D-002J-W2              |
| `FDIC_SVB_POSTMORTEM`      | FDIC OIG                          | crisis_window      | uninsured_deposit_run_dynamics; supervisory       | CW1, CW6                | USABLE_NOW                          | Canonical 2023 SVB / First Republic public post-mortem                       | Narrative PDF; post-mortem only                                                     | D-002J-W2              |
| `LIT_INTERBANK_CONTAGION`  | Academic / NBER / SSRN            | literature_support | DebtRank; max_entropy; repo_funding_fragility    | CW1, CW2, CW3, CW4      | USABLE_NOW                          | Methodology anchors for W4 substrate design                                  | Methodology, not data                                                                | D-002J-W4 (literature) |
| `LIT_NETWORK_RECON`        | Academic / Bundesbank / SSRN      | literature_support | network_reconstruction_method; max_entropy_bias  | CW1, CW2                | USABLE_NOW                          | Mistrulli 2011 + Anand-Craig-vonPeter 2015 anchors                          | Methodology, not data                                                                | D-002J-W4 (literature) |
| `LIT_REPO_FUNDING`         | Academic / NBER / FRB             | literature_support | repo_collateral_haircut; rollover_stress         | CW1, CW3, CW4           | USABLE_NOW                          | Brunnermeier 2009 + Gorton-Metrick 2012 + KNO 2014 anchors                  | Methodology, not data                                                                | D-002J-W4 (literature) |

---

## Inclusion logic per source class

### banking (4)
`BIS_CBS` and `ECB_CBD` cover cross-border / euro-area
consolidated banking; `FDIC_CALL_REPORTS` and `FED_Y9C` cover the
US per-bank micro layer. Together they cover the four largest
public banking-data perimeters with documented overlap discipline.
No single source covers all four perimeters; bias correction is
explicit (Mistrulli 2011 bias on `BIS_CBS` reconstruction).

### repo (4)
`NYFED_SOFR` (post-2018 daily), `OFR_REPO_DATA` (post-2014 daily
volumes + haircuts), `FED_H15` (long-history daily interest
rates), `ECB_MMSR` (post-2016 euro-area aggregates). The four
together cover both the US tri-party perimeter and the euro-area
money-market layer, with `LIT_REPO_FUNDING` providing the
methodology anchor.

### macro_financial (6 — P1B)
`FRED` + `ALFRED` + `PHILLY_FED_RTDSM` cover the de facto public
backbone with vintage discipline (`PHILLY_FED_RTDSM` added in
D-002J-P1B 2026-05-14 to satisfy the `information_constraint`
mechanism-family floor of ≥ 2 verified/partial sources, complementing
ALFRED with non-FRED-native macro variables); `OFR_FSI` + `STLFSI`
+ `KCFSI` provide three independent stress-composite constructions
for cross-check.

### market_structure (4)
`CBOE_VIX` (equity implied vol), `ICAP_MOVE` (Treasury implied
vol, candidate due to vendor licence), `BIS_QR_NETWORK` (global
banking-network narrative), `OFR_WP_NETWORK` (methodology
working papers).

### crisis_window (5)
`NBER_RECESSION` (US ex-post label), `FED_TIMELINE` (US central
bank chronology), `ECB_FSR` (euro-area narrative), `BOE_LDI_REVIEW`
(UK 2022), `FDIC_SVB_POSTMORTEM` (US 2023). Five public regulator
or research chronologies together anchor all six crisis windows.

### literature_support (3)
`LIT_INTERBANK_CONTAGION` (Eisenberg-Noe / DebtRank / Glasserman-
Young / Anand / Aldasoro-Alves / Brunnermeier),
`LIT_NETWORK_RECON` (Upper-Worms / Mistrulli / Anand-Craig-vonPeter
/ Battiston complex-systems), `LIT_REPO_FUNDING` (Brunnermeier
2009 / Gorton-Metrick 2012 / KNO 2014 / Copeland-Martin-Walker).

---

## Boundary clauses

Every row in the §9 matrix above carries a boundary clause:

- `why_include` — explicit reason the source is in the registry.
- `why_not_enough_alone` — explicit reason the source CANNOT
  stand up the mechanism / window on its own.

The boundary clauses are the audit surface. A future PR that
removes a `why_not_enough_alone` clause without replacing it with
a stronger boundary constitutes a fresh D-002K pre-registration.

## Forbidden interpretations of this rationale

This document does NOT constitute:

- a claim that the registry is complete,
- a claim that ingestion has occurred,
- a claim of real-bank validation,
- a claim that the listed sources rescue D-002H,
- a claim that the listed sources invalidate D-002H REFUSED.

See `docs/governance/D002J_PREREGISTRATION.yaml` `forbidden_claims`
and `docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md` for the
binding boundary.
