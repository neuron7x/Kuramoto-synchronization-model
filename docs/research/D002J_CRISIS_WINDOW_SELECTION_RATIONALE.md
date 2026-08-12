# D-002J — Crisis Window Selection Rationale (P2 v1)

Anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
(sha256 `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0`).
Companion: `docs/research/D002J_CRISIS_WINDOW_REGISTRY.md`,
`artifacts/d002j/crisis_windows/crisis_window_registry_v1.json`.
Lineage: `D-002G -> D-002H REFUSED -> D-002I -> D-002J prereg #694 -> P1 #695 -> P1A #697 REJECTED -> P1B #698 PARTIALLY_VERIFIED -> P2 (this PR)`.

This document explains WHY these 6 windows (and only these 6), WHY the
specific day-level start / end dates, and WHY several plausible
alternative windows are EXCLUDED. It is the companion to the §0 table
in `D002J_CRISIS_WINDOW_REGISTRY.md`.

---

## §1 — Selection criteria (locked at pre-registration)

A window enters the D-002J v1 set only if it satisfies ALL of:

1. **Peer-reviewed and supervisory consensus** — at least one of:
   BIS Annual Economic Report / Quarterly Review, IMF Global Financial
   Stability Report, OFR Financial Stability Report, Federal Reserve
   FSR, ECB FSR, or NBER recession dating.
2. **Diverse mechanism coverage** — across the 6 windows, every
   `primary_mechanism_family` in
   `{balance_sheet, liquidity_funding, contagion, market_wide_stress,
   official_response}` is represented at least once as primary or
   secondary; `information_constraint` is covered indirectly via
   ALFRED / PHILLY_FED_RTDSM vintage anchors in 6/6 windows.
3. **Day-level bound identifiability** — the start and end events are
   public-record and unambiguous (regulator releases, central-bank
   announcements, official chronologies). NO subjective dating.
4. **P1B-surviving source binding ≥ 3** — at least three sources in
   the P1B audit-surviving (VERIFIED ∨ PARTIAL) set list this window
   in their `crisis_window_relevance`. (See §9 P1B source-binding
   matrix; the per-window minimum is 12, well above the floor of 3.)
5. **Forbidden-claim compatibility** — the window can be observed
   without inducing the forbidden classes of inference (bank-level
   validation, cross-asset/interbank causal, crisis prediction).
   Windows where the natural inference is forbidden are EXCLUDED.

The 6 windows pass all 5 criteria. The complete justification per
window appears in §2-§7 below.

---

## §2 — CW1 (2007-2009 GFC)

**Start `2007-08-09`**: BNP Paribas suspends three structured-asset
funds. This is the conventional academic / supervisory crisis-onset
anchor (FCIC Final Report 2011; BIS Quarterly Review 2007-Q4). The
Bear Stearns hedge-fund collapse (2007-06-22) is a *precursor* —
intentionally placed in the **pre-event buffer** (`2007-02-09`), not
the window proper, so that pre-event observability work has a
genuinely pre-onset period to characterise.

**End `2009-06-30`**: NBER trough. Rationale: financial-stress
indicators (STLFSI, OFR_FSI, TED spread) remain elevated through the
recession proper; closing on the NBER trough captures the full
stress signature without arbitrarily truncating at a single policy
event (e.g. 2008-10-03 TARP or 2008-12-16 ZLB).

**Why NOT 2008-09-15 single-day window**: Lehman Day is a
*within-window pulse* of CW1, not a separate window. Treating
2008-09-15 as a separate window would create a CW0.5/CW1.5
naming collision with the locked CW1..CW6 ids and would force the
substrate-detection task into a one-day spectacle rather than a
multi-month regime.

**Why NOT 2008-Q4 alone**: Same as above — 2008-Q4 is a sub-period
of CW1. The systemic-banking-crisis mechanism is multi-month.

---

## §3 — CW2 (2010-2012 Eurozone)

**Start `2010-05-02`**: First Greek bailout (Eurogroup / IMF €110bn
programme). This is the conventional academic anchor for the
Eurozone sovereign episode (ECB_FSR 2010 H2; BIS_QR_NETWORK 2010-Q3).

**End `2012-09-06`**: OMT announcement (ECB). The Draghi 2012-07-26
'whatever it takes' speech is an in-window official-response anchor;
OMT is the *operational* close of the acute episode (Krishnamurthy-
Nagel-Vissing-Jorgensen 2018; ECB_FSR 2012 H2).

**Why NOT 2009-Q4 Greek statistical revision**: Placed in pre-event
buffer (`2009-11-02`). It is a *precursor* event, not the start of
the systemic episode.

**Why NOT 2013 Cyprus banking crisis**: Distinct lineage (small-state
banking, deposit-bail-in mechanism) and post-OMT regime change.
Promoting Cyprus to a separate D-002J window would require Cyprus-
specific banking-data sources NOT in the P1B-surviving set; the
honest decision is exclusion, not pad.

**Why NOT 2014 ECB CSPP / AQR**: Post-acute-episode regime; treated
as official-response continuation, not a separate stress window.

---

## §4 — CW3 (2019 US Repo Spike)

**Start `2019-09-16`**: Intraday SOFR spike to ~5.25% (vs ~2.20%
prior day). This is the canonical anchor (NYFED_SOFR press release
2019-09-17; OFR Repo Markets Monitor 2019-Q4).

**End `2019-10-11`**: Fed Treasury-bill purchase announcement
($60bn/month) lifts reserves; the funding-stress signature
normalises within the following weeks.

**Why such a narrow window** (26 days vs. 700+ for CW1/CW2): the
mechanism (liquidity_funding) is *contained* and *short-lived*.
Substrate-detection on CW3 tests whether a substrate is well-
calibrated to NARROW funding-stress episodes WITHOUT broader equity
/ credit panic. This is the cleanest single-mechanism positive in
the set; a wider window would dilute the signal-to-noise ratio.

**Why NOT 2018-Q4 mild repo pressure**: Intentional pre-event buffer
(`2019-06-16`). The 2018-Q4 episode is a precursor of weaker
magnitude.

---

## §5 — CW4 (2020 COVID Dash-for-Cash)

**Start `2020-02-21`**: Italy COVID lockdowns trigger market
acknowledgment of systemic-scale shock (BIS Bulletin No. 2 'The
Covid-19 shock' April 2020; OFR FSR 2020 H1). Equity drawdown and
basis blowout from this date.

**End `2020-04-09`**: MSLP + Municipal Liquidity Facility
announcement. By this date the cross-asset stress signature has
stabilised (OFR FSR 2020-Q2 narrative). CPFF, PMCCF, MMLF anchors
all fall between start and end.

**Why NOT end at 2020-03-23 (PMCCF/SMCCF)**: 2020-03-23 is the
equity-market closing low and the largest single-day intervention,
but credit-spread normalisation requires until ~2020-04-09. Closing
on 2020-03-23 would truncate the credit-side dash-for-cash signature.

**Why NOT include late-2020 vaccine-rally regime change**: That is a
separate regime (recovery), not a stress episode. Placed in
post-event buffer (`2020-07-09`).

**Why NOT 2021-Q1 SLR-relief expiry stress**: A genuinely interesting
Treasury-market episode, but it is *not* a dash-for-cash event — the
mechanism is regulatory-capital-driven balance-sheet retreat, not
liquidity panic. Not promoted to a D-002J window.

---

## §6 — CW5 (2022 UK Gilt / LDI)

**Start `2022-09-23`**: UK 'mini-budget' (Kwarteng) announcement;
gilt yield breakout begins (BOE_LDI_REVIEW Financial Stability Report
December 2022).

**End `2022-10-14`**: BoE temporary purchase operations conclude;
mini-budget largely reversed by successor Chancellor. 2022-09-28 BoE
Financial Stability operation and 2022-10-10 extension to index-
linked gilts are in-window official-response anchors.

**Why such a narrow window** (22 days): the dysfunction is *acute*
and *UK-localised*. The dynamics of the LDI collateral-call spiral
play out on a 2-3 week timescale (BOE_LDI_REVIEW chronology).

**Why NOT pre-September 2022 Bank Rate hike cycle**: That is normal
monetary-policy transmission, not gilt-market dysfunction. Placed in
pre-event buffer (`2022-06-23`).

**Why CW5 is `data_availability_status: partial`**: Only 12 P1B-
surviving sources bind here (above the floor of 3 but lowest among
the 6). BOE_LDI_REVIEW is the authoritative anchor (VERIFIED post-
P1B repair); ECB_MMSR is PARTIAL (methodology-page license-bound).
NYFED_SOFR / OFR_REPO_DATA do NOT bind here — correctly, since the
dysfunction was contained to UK gilt collateral. The 'partial' rating
is honest, not theatrical.

---

## §7 — CW6 (2023 Regional Banking)

**Start `2023-03-08`**: Silvergate Capital voluntary liquidation
announcement + SVB Financial capital-raise announcement
(FDIC_SVB_POSTMORTEM April 2023; Federal Reserve Supervisory Review
of SVB April 2023). These are the public disclosures that initiated
the deposit-run dynamics.

**End `2023-05-01`**: First Republic Bank resolved by FDIC. By this
date the acute regional-bank-run episode has closed. SVB closure
2023-03-10, Signature 2023-03-12 + BTFP, Credit Suisse / UBS
2023-03-19 are all in-window official-response anchors.

**Why include Credit Suisse via official-response date but NOT as a
separate window**: CHF-USD funding-stress spillover was live in-window
and shaped market reaction; the Credit Suisse failure ITSELF is a
Swiss supervisory event without P1B-surviving Swiss banking data
sources. Promoting it to a separate window would require sources we
do not have; the honest decision is to keep it as an in-window
official-response anchor.

**Why NOT extend to PacWest / Western Alliance (May-June 2023)**:
Those events are residual aftershocks of CW6 in the post-event
buffer (`2023-08-01`), not separate windows.

**Why CW6 is `data_availability_status: partial`**: 16 sources bind
(above floor), but the most direct individual-bank data (FED_Y9C) is
PARTIAL in P1B audit, and KBW Regional Bank Index — the natural
secondary observable — is NOT in the P1B-surviving set. Use of
FED_Y9C and FDIC_CALL_REPORTS is restricted to AGGREGATES; per the
claim boundary, individual-bank modelling is explicitly forbidden.
The 'partial' rating is honest.

**Why `lookahead_risk: medium` (vs `low` for CW1..CW5)**: CW6 sources
include FDIC_SVB_POSTMORTEM published April 2023 — within the
window itself. Vintage-aware analyses MUST treat the postmortem as a
post-event narrative source, not a real-time observable. ALFRED and
PHILLY_FED_RTDSM remain available for vintage-aware variable use on
the macro-financial side.

---

## §8 — Explicit non-windows

These episodes are deliberately NOT D-002J windows, despite each
being a plausible candidate.

| candidate                                    | date range            | reason for exclusion                                                                                                                                |
|----------------------------------------------|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| LTCM 1998                                    | 1998-08 – 1998-10     | Pre-2000 era; data sources (LIBOR, repo) have inferior pre-2000 vintage availability. Reserved for D-002K extension.                                |
| 1987 Black Monday                            | 1987-10-19            | Single-day equity event; no banking-system data feasible at modern granularity. Not D-002J scope.                                                   |
| 1990-1991 US S&L crisis                      | 1990-Q3 – 1991-Q2     | Pre-modern supervisory data regime; FDIC_CALL_REPORTS reach back only to 1976 with limited variable continuity.                                     |
| 1997-1998 Asian crisis                       | 1997-07 – 1998-12     | Geographic scope mismatch: D-002J v1 anchors on US / Euro-area / UK supervisory data sources only. Reserved for D-002K (EM-extension).               |
| 2008-09-15 Lehman Day single-event window    | 2008-09-15            | A *within-window pulse* of CW1, not a separate window.                                                                                              |
| 2008-Q4 single-quarter window                | 2008-10-01 – 2008-12-31 | A sub-period of CW1.                                                                                                                                |
| 2014-15 oil-price collapse                   | 2014-06 – 2016-02     | Commodity-price shock, not a systemic financial-system event in P1B-surviving source coverage.                                                       |
| 2018-Q4 mild repo pressure                   | 2018-12               | Precursor of CW3, magnitude insufficient; placed in CW3 pre-event buffer.                                                                            |
| 2021-Q1 SLR-relief expiry                    | 2021-03               | Regulatory-capital-driven balance-sheet retreat, NOT liquidity panic. Out of CW4 scope.                                                              |
| 2013 Cyprus banking crisis                   | 2013-03 – 2013-04     | Distinct small-state-banking deposit-bail-in mechanism; post-OMT regime; no Cyprus-specific sources in P1B-surviving set.                            |
| 2016 Brexit                                  | 2016-06-23 onward     | Macro / political shock, not a systemic financial-system dysfunction event.                                                                          |
| 2023 Credit Suisse failure (as own window)   | 2023-03-19            | Swiss supervisory event; no P1B-surviving Swiss banking data. Captured as CW6 official-response anchor.                                              |
| 2023-Q2-Q3 PacWest / Western Alliance        | 2023-05 – 2023-06     | Residual aftershocks of CW6; placed in CW6 post-event buffer.                                                                                       |

**Why some plausible windows are deferred to D-002K rather than
rejected outright**: D-002J v1 is the LOCKED initial benchmark set
under the §7 pre-reg contract. Expansion (LTCM 1998, Asian 1997, EM
sovereign events) is a downstream PR with positive-control discipline,
not a freelance addition. The 6-window cap is intentional.

---

## §9 — P1B source-binding matrix (per-window count of P1B-surviving sources)

| window_id                          | n_VERIFIED | n_PARTIAL | total | floor (3) PASS |
|------------------------------------|-----------:|----------:|------:|:--------------:|
| `CW1_GFC_2007_2009`                |         14 |         7 |    21 | PASS           |
| `CW2_EUROZONE_2011_2012`           |         12 |         4 |    16 | PASS           |
| `CW3_US_REPO_SPIKE_2019`           |         12 |         5 |    17 | PASS           |
| `CW4_COVID_DASH_FOR_CASH_2020`     |         15 |         4 |    19 | PASS           |
| `CW5_UK_GILT_LDI_2022`             |          8 |         4 |    12 | PASS           |
| `CW6_REGIONAL_BANKING_2023`        |         11 |         5 |    16 | PASS           |

(Counts derived from `artifacts/d002j/data_registry/source_provenance_audit_v1.json`
and `artifacts/d002j/data_registry/source_registry_v1.json`. Every
source_id referenced is a P1B-surviving source.)

---

## §10 — Cross-asset vs. interbank scope reminder (Brunetti e-MID literature)

The mechanism-family taxonomy in this registry (`contagion`,
`liquidity_funding`, `balance_sheet`, `market_wide_stress`,
`official_response`, `information_constraint`) is DELIBERATELY
distinct from interbank-network contagion concepts in the
Brunetti / e-MID literature
(`LIT_INTERBANK_CONTAGION`, `LIT_NETWORK_RECON`).

The two scopes do NOT cleanly cross-validate:

- D-002J operates on **cross-asset / cross-instrument co-movement**
  using public aggregated sources.
- The Brunetti / Eisenberg-Noe / DebtRank literature operates on
  **interbank exposure networks** using supervisory micro-data
  (e-MID transaction-level data, BIS-supervisor-only data).

A signal detected on D-002J cross-asset data does NOT validate an
interbank-contagion mechanism. Conversely, an interbank-network
contagion result does NOT validate a D-002J cross-asset substrate.
The two literatures are complementary observation modalities of the
same financial system; substrate-detection claims in this registry
MUST stay strictly inside the cross-asset modality.

**This is the single hardest forbidden-claim drift to avoid** —
hence the explicit `test_no_cross_asset_interbank_overclaim` guard
in `tests/systemic_risk/test_d002j_crisis_window_registry.py`.

---

## §11 — Hard scope boundary (repeat for safety)

- P2 is **registry only**. P2 does **NOT** ingest any data; ingestion
  is the P3 boundary.
- P2 does **NOT** authorise any canonical run.
  `canonical_run_authorized: false`; `benchmark_only: true`.
- P2 does **NOT** claim crisis prediction at any window.
- P2 does **NOT** claim bank-level validation at any window.
- P2 does **NOT** claim cross-asset / interbank causal inference.
- P2 does **NOT** rescue D-002H. D-002H REFUSED remains the truthful
  canonical verdict.
- P2 does **NOT** pre-empt the D-002I investigation outcomes.
- P2 does **NOT** edit any locked governance file. The six locked
  sha256 pins (D-002C ledger, D-002G prereg, D-002G acceptance,
  D-002H prereg, D-002I prereg, D-002J prereg) all remain byte-exact.
- P2 does **NOT** edit any source code under
  `research/systemic_risk/*.py` or any `scripts/x10r_d002*.py`.
- P2 does **NOT** modify the P1B registry, audit, smoke, or evidence
  lock JSON artifacts.

Decision: `CRISIS_WINDOW_REGISTRY_READY`.
