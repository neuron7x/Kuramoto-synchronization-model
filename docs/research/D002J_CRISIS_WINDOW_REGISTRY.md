# D-002J — Workstream 2: Crisis Window Registry (v1)

Pre-registration anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
(sha256 `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0`,
byte-exact UNCHANGED in this PR).
Parent registry: `artifacts/d002j/data_registry/source_registry_v1.json`
(sha256 `f1899b7a882b4b3efbebb54e3dc942c079839f77f981273e2dd09757973b14ec`,
P1B PARTIALLY_VERIFIED; 26 sources, all VERIFIED or PARTIAL, no DOWNGRADED, no REJECTED).
Machine-readable artifact: `artifacts/d002j/crisis_windows/crisis_window_registry_v1.json`
(schema `D002J-CRISIS-WINDOW-REGISTRY-v1`).
Summary artifact: `artifacts/d002j/crisis_windows/crisis_window_summary_v1.json`
(schema `D002J-CRISIS-WINDOW-SUMMARY-v1`).
Plan reference: §7.
PR lineage: `D-002G -> D-002H REFUSED -> D-002I -> D-002J prereg #694 -> P1 #695 -> P1A #697 REJECTED -> P1B #698 PARTIALLY_VERIFIED -> P2 (this PR)`.

> Each crisis window below is the external stress anchor against
> which D-002J substrates and null models are evaluated. The window
> id (`CW1`..`CW6`) is part of the D-002J pre-registration content
> address; ids are stable across the lineage and CANNOT be
> renumbered without a fresh D-002K pre-registration. Day-level
> start/end dates are now LOCKED in this v1 PR — any future revision
> requires a fresh pre-registered amendment.

---

## §0 — Top summary table

| id                              | label                                     | start_date | end_date   | event_type                    | primary_mechanism_family | secondary_mechanism_families                                | n_sources | data_availability_status |
|---------------------------------|-------------------------------------------|------------|------------|-------------------------------|--------------------------|-------------------------------------------------------------|-----------|--------------------------|
| `CW1_GFC_2007_2009`             | 2007-2009 Global Financial Crisis         | 2007-08-09 | 2009-06-30 | systemic_banking_crisis       | liquidity_funding        | contagion, balance_sheet, market_wide_stress, official_response | 21        | strong                   |
| `CW2_EUROZONE_2011_2012`        | 2010-2012 Eurozone Sovereign Debt Crisis  | 2010-05-02 | 2012-09-06 | sovereign_debt_crisis         | contagion                | official_response, liquidity_funding, market_wide_stress    | 16        | strong                   |
| `CW3_US_REPO_SPIKE_2019`        | 2019 US Repo Market Spike                 | 2019-09-16 | 2019-10-11 | repo_market_dysfunction       | liquidity_funding        | balance_sheet, official_response, market_wide_stress        | 17        | strong                   |
| `CW4_COVID_DASH_FOR_CASH_2020`  | 2020 COVID-19 Dash-for-Cash               | 2020-02-21 | 2020-04-09 | liquidity_crisis              | market_wide_stress       | liquidity_funding, official_response, contagion             | 19        | strong                   |
| `CW5_UK_GILT_LDI_2022`          | 2022 UK Gilt / LDI Crisis                 | 2022-09-23 | 2022-10-14 | gilt_dysfunction              | liquidity_funding        | contagion, balance_sheet, official_response                 | 12        | partial                  |
| `CW6_REGIONAL_BANKING_2023`     | 2023 US Regional Banking Stress           | 2023-03-08 | 2023-05-01 | regional_banking_crisis       | balance_sheet            | liquidity_funding, official_response, contagion             | 16        | partial                  |

Total distinct P1B-surviving sources referenced across all 6 windows: **26**
(every VERIFIED or PARTIAL source in the P1B audit is touched by at least
one window).

---

## §1 — CW1_GFC_2007_2009

- **window_id**: `CW1_GFC_2007_2009`
- **label**: 2007-2009 Global Financial Crisis
- **dates**: `2007-08-09` → `2009-06-30`
- **pre_event_buffer**: `2007-02-09`
- **post_event_buffer**: `2009-12-31`
- **event_type**: `systemic_banking_crisis`
- **primary_mechanism_family**: `liquidity_funding`
- **secondary_mechanism_families**: `contagion`, `balance_sheet`, `market_wide_stress`, `official_response`
- **lookahead_risk**: `low`
- **data_availability_status**: `strong`

### Justification

The conventional academic / supervisory crisis-onset anchor is BNP
Paribas' 2007-08-09 suspension of three funds citing complete
inability to value structured ABS holdings — see BIS Quarterly Review
December 2007 and FCIC Final Report (2011). The window closes at
the NBER trough on 2009-06-30 (NBER_RECESSION:`us_recession_start_end_dates`),
not on policy-event timing, because the financial-stress signature
persists through the recession proper.

### Source binding (21 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, CBOE_VIX, ECB_FSR, FDIC_CALL_REPORTS,
FDIC_SVB_POSTMORTEM, FED_H15, FED_TIMELINE, FED_Y9C, FRED, ICAP_MOVE,
KCFSI, LIT_INTERBANK_CONTAGION, LIT_NETWORK_RECON, LIT_REPO_FUNDING,
NBER_RECESSION, OFR_FSI, OFR_WP_NETWORK, PHILLY_FED_RTDSM, STLFSI`.

### Observable signature

TED spread and LIBOR-OIS basis sustained elevation 2007-08 through
2009-Q1; repo haircut step-up on agency MBS; financial-sector CDS
widening; STLFSI / OFR_FSI breach of crisis-regime thresholds; co-
movement spike on Lehman day (2008-09-15).

### Exclusion notes

Pre-2007-08-09 ABS market stress (Bear Stearns hedge funds collapse
2007-06) is intentionally excluded from the window proper — placed
in the pre-event buffer. Post-2009-06-30 stress (2010 sovereign
concerns) is intentionally excluded — owned by CW2. LTCM 1998 and
1987 Black Monday are not D-002J windows; reserved for D-002K
extension. PHILLY_FED_RTDSM and ALFRED listed among P1B-surviving
sources are vintage real-time anchors only — they are NOT crisis-
period observables in their own right and bind here only as anti-
leakage controls on dated variable releases.

### Claim boundary

This window is a registered observation interval, not a prediction
target. The substrate-detection task on CW1 is descriptive co-
movement characterisation under fail-closed null comparison; the
window does NOT authorise any claim of crisis prediction, bank-level
validation, or cross-asset/interbank causal inference. Co-movement
detection during the window does NOT imply substrate predictive power
outside the window. Vintage-aware analyses MUST use ALFRED or
PHILLY_FED_RTDSM for any variable used in supposedly pre-event
windows; revised-data use is permissible only with explicit
`look_ahead_audit: revised_data` labelling in the downstream analysis
manifest.

---

## §2 — CW2_EUROZONE_2011_2012

- **window_id**: `CW2_EUROZONE_2011_2012`
- **label**: 2010-2012 Eurozone Sovereign Debt Crisis
- **dates**: `2010-05-02` → `2012-09-06`
- **pre_event_buffer**: `2009-11-02`
- **post_event_buffer**: `2013-03-06`
- **event_type**: `sovereign_debt_crisis`
- **primary_mechanism_family**: `contagion`
- **secondary_mechanism_families**: `official_response`, `liquidity_funding`, `market_wide_stress`
- **lookahead_risk**: `low`
- **data_availability_status**: `strong`

### Justification

Start: 2010-05-02 first Greek bailout (€110bn EU/IMF programme).
End: 2012-09-06 OMT announcement (the conventional academic close on
the acute episode; see e.g. Krishnamurthy-Nagel-Vissing-Jorgensen
2018 on OMT-effect anchors and ECB_FSR 2012 H2). The Draghi
2012-07-26 'whatever it takes' speech is included as an official-
response anchor between start and end.

### Source binding (16 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, CBOE_VIX, ECB_CBD, ECB_FSR, FED_H15,
FRED, ICAP_MOVE, KCFSI, LIT_INTERBANK_CONTAGION, LIT_NETWORK_RECON,
OFR_FSI, OFR_WP_NETWORK, PHILLY_FED_RTDSM, STLFSI`.

### Observable signature

Peripheral-vs-Bund 10Y sovereign yield spread breakout (GR/IT/ES/PT);
intra-euro funding fragmentation via TARGET2; ECB FSR vulnerability
narrative escalation; sustained STLFSI / OFR_FSI elevation; co-
movement spike on OMT announcement 2012-09-06.

### Exclusion notes

Pre-window Greek statistical revision (2009-Q4) intentionally placed
in pre-event buffer, not window proper. Cyprus 2013 banking crisis
intentionally excluded — distinct lineage (small-state banking) and
post-OMT regime change. Brexit-related sovereign stress 2016 is NOT
a D-002J window. Window scope is sovereign-bank-doom-loop; pure
interbank phenomena are partially captured but cross-asset/interbank
causal interpretations are scope-prohibited per claim boundary.

### Claim boundary

Sovereign-bank doom-loop observation window. Substrate-detection
claims on CW2 are scoped to descriptive co-movement and elevated-
stress regime characterisation; NOT crisis prediction; NOT real-bank
validation; NOT cross-asset/interbank causal claims; NOT a basis for
policy attribution (OMT-effect estimation is event-study territory
and requires explicit pre-registered design).

---

## §3 — CW3_US_REPO_SPIKE_2019

- **window_id**: `CW3_US_REPO_SPIKE_2019`
- **label**: 2019 US Repo Market Spike
- **dates**: `2019-09-16` → `2019-10-11`
- **pre_event_buffer**: `2019-06-16`
- **post_event_buffer**: `2020-01-11`
- **event_type**: `repo_market_dysfunction`
- **primary_mechanism_family**: `liquidity_funding`
- **secondary_mechanism_families**: `balance_sheet`, `official_response`, `market_wide_stress`
- **lookahead_risk**: `low`
- **data_availability_status**: `strong`

### Justification

Start: 2019-09-16 SOFR intraday spike to ~5.25% (vs ~2.20% prior
day). End: 2019-10-11 Fed announces Treasury-bill purchases
($60bn/month) to lift reserves. The 2019-09-17 first post-2008 NY
Fed open-market repo operation is included as an official-response
anchor between start and end. Anchors: NYFED_SOFR press releases
2019-09 and OFR Repo Markets Monitor 2019-Q4.

### Source binding (17 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, CBOE_VIX, FED_H15, FED_TIMELINE,
FED_Y9C, FRED, ICAP_MOVE, LIT_INTERBANK_CONTAGION, LIT_REPO_FUNDING,
NYFED_SOFR, OFR_FSI, OFR_REPO_DATA, OFR_WP_NETWORK, PHILLY_FED_RTDSM,
STLFSI`.

### Observable signature

SOFR-vs-IORB spread spike (~300bps intraday on 2019-09-17); 99th
percentile of overnight repo distribution breaking IORB ceiling;
OFR_REPO_DATA haircut distributions shift on agency MBS / Treasuries;
FED_H15:EFFR_OBFR_TGCR_BGCR_SOFR_post_2014 reveals breakout; CRITICAL:
narrow funding-stress signature WITHOUT broader equity / credit market
panic (CBOE_VIX low through window).

### Exclusion notes

Pre-2014 GCF Repo Index period intentionally excluded (data product
regime change at SOFR transition). Q4 2018 mild repo pressure NOT
included — falls in pre-event buffer. CBOE_VIX bound to this window
but classified as a survival-of-null observable: VIX did NOT spike,
and that absence is part of the expected signature. CW3 is the
cleanest single-mechanism (liquidity_funding) window in the D-002J
set, intentionally chosen for substrate-isolation properties.

### Claim boundary

Narrow funding-market dysfunction window. Substrate detection MUST
respect the 'no equity/credit panic' constraint — a substrate that
fires on broader market stress is FAILING on CW3, not succeeding.
Substrate-detection claims on CW3 are scoped to repo-market liquidity-
rollover stress; NOT systemic-banking-crisis claims; NOT bank-level
validation; NOT cross-asset/interbank causal claims; NOT a basis for
Fed-intervention attribution.

---

## §4 — CW4_COVID_DASH_FOR_CASH_2020

- **window_id**: `CW4_COVID_DASH_FOR_CASH_2020`
- **label**: 2020 COVID-19 Dash-for-Cash
- **dates**: `2020-02-21` → `2020-04-09`
- **pre_event_buffer**: `2019-11-21`
- **post_event_buffer**: `2020-07-09`
- **event_type**: `liquidity_crisis`
- **primary_mechanism_family**: `market_wide_stress`
- **secondary_mechanism_families**: `liquidity_funding`, `official_response`, `contagion`
- **lookahead_risk**: `low`
- **data_availability_status**: `strong`

### Justification

Start: 2020-02-21 — Italy COVID lockdowns announced, market
acknowledgment of systemic-scale shock begins (equity drawdown and
basis blowout from this date forward; see BIS Bulletin No. 2 'The
Covid-19 shock' April 2020). End: 2020-04-09 announcement of MSLP +
Municipal Liquidity Facility; the broad cross-asset stress signature
has stabilised by this date per OFR FSR 2020-Q2 narrative. CPFF,
PMCCF, MMLF anchors all fall between start and end and are recorded
as official-response dates.

### Source binding (19 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, CBOE_VIX, ECB_CBD, ECB_FSR, FED_H15,
FED_TIMELINE, FRED, ICAP_MOVE, LIT_INTERBANK_CONTAGION, LIT_REPO_FUNDING,
NBER_RECESSION, NYFED_SOFR, OFR_FSI, OFR_REPO_DATA, OFR_WP_NETWORK,
PHILLY_FED_RTDSM, STLFSI`.

### Observable signature

Simultaneous breakdown of Treasury-market liquidity, basis-swap
blowout, MMF redemption spike, credit-spread widening, and equity
drawdown — broadest-front cross-sector stress in the window set.
ICAP_MOVE spikes alongside CBOE_VIX (rare joint blowout). OFR_FSI
registers maximum since 2008. SOFR briefly negative on 2020-03-26
(reserve glut following Fed Repo + bills); haircut distributions
spike. Co-movement spike at 2020-03-23 PMCCF announcement.

### Exclusion notes

Late-2020 vaccine-rally regime change intentionally excluded —
captured as post-event buffer only. SLR-relief expiry stress 2021-Q1
is NOT a D-002J window. Cross-asset co-movement during CW4 is genuine
but its causal interpretation as 'unified deleveraging mechanism' is
explicitly outside scope. Note: CBOE_VIX and ICAP_MOVE both PARTIAL
in P1B audit (license-bound methodology PDFs) — observable lists
remain admissible because the time-series themselves are public via
FRED:VIXCLS for CBOE_VIX.

### Claim boundary

Broad-front market-wide-stress window; uniquely characterised by
simultaneous breakdown of Treasury, funding, credit, and equity
markets. Substrate-detection claims MUST acknowledge that CW4 is
an easy positive — a substrate failing to detect anything in CW4 is
demonstrably under-powered. NOT a basis for crisis prediction (CW4
was an exogenous public-health shock; the financial channel was
rapid). NOT bank-level validation; NOT cross-asset/interbank causal
claims; NOT Fed-intervention attribution.

---

## §5 — CW5_UK_GILT_LDI_2022

- **window_id**: `CW5_UK_GILT_LDI_2022`
- **label**: 2022 UK Gilt / LDI Crisis
- **dates**: `2022-09-23` → `2022-10-14`
- **pre_event_buffer**: `2022-06-23`
- **post_event_buffer**: `2023-01-14`
- **event_type**: `gilt_dysfunction`
- **primary_mechanism_family**: `liquidity_funding`
- **secondary_mechanism_families**: `contagion`, `balance_sheet`, `official_response`
- **lookahead_risk**: `low`
- **data_availability_status**: `partial`

### Justification

Start: 2022-09-23 UK 'mini-budget' announced (Kwarteng); gilt yield
breakout begins. End: 2022-10-14 BoE temporary purchase operations
conclude; mini-budget largely reversed by successor Chancellor. The
2022-09-28 BoE Financial Stability operation and 2022-10-10 expansion
to index-linked gilts fall between start and end and are recorded as
official-response dates. Anchors: BOE_LDI_REVIEW (Financial Stability
Report December 2022).

### Source binding (12 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, BOE_LDI_REVIEW, CBOE_VIX, ECB_FSR,
ECB_MMSR, FED_H15, FRED, ICAP_MOVE, OFR_FSI, PHILLY_FED_RTDSM`.

### Observable signature

30Y gilt yield > 5% breakout (vs ~3.5% pre-window); LDI fund collateral-
call spiral chronicled in BOE_LDI_REVIEW; sterling depreciation episode
(GBPUSD intraday lows 2022-09-26); ICAP_MOVE-like UK rate volatility
spike (proxied via FED_H15 yield curves and BOE LDI narrative for
UK-specific dynamic); narrow UK-centred stress signature WITHOUT broad
global equity panic (CBOE_VIX modest); STLFSI marginally elevated only.

### Exclusion notes

Pre-September 2022 UK rate moves (Bank Rate hike cycle since 2021-12)
are intentional pre-event buffer. UK November 2022 budget (Hunt)
corrective measures are post-event buffer. Mini-budget fiscal-policy
attribution is outside D-002J scope. CW5 has the fewest P1B-surviving
sources (12) but ABOVE the floor of 3; the binding is intentional and
reflects the UK-specific narrative — BOE_LDI_REVIEW is the
authoritative anchor and is VERIFIED post-P1B repair. No US repo-
specific sources bind here (NYFED_SOFR / OFR_REPO_DATA absent)
because the dysfunction was contained to UK gilt collateral; this
scoping is deliberate, not a gap.

### Claim boundary

UK-specific gilt-LDI dysfunction window. Substrate-detection claims
on CW5 are scoped to LDI-collateral-call-spiral characterisation;
NOT generalised margin-call-cascade claims (without independent
positive-control survival on additional venues); NOT crisis
prediction; NOT bank-level validation; NOT cross-asset/interbank
causal claims. ECB_MMSR PARTIAL in P1B audit — its variables are
admissible only as Euro-area liquidity context, NOT as primary UK
indicators.

---

## §6 — CW6_REGIONAL_BANKING_2023

- **window_id**: `CW6_REGIONAL_BANKING_2023`
- **label**: 2023 US Regional Banking Stress
- **dates**: `2023-03-08` → `2023-05-01`
- **pre_event_buffer**: `2022-12-08`
- **post_event_buffer**: `2023-08-01`
- **event_type**: `regional_banking_crisis`
- **primary_mechanism_family**: `balance_sheet`
- **secondary_mechanism_families**: `liquidity_funding`, `official_response`, `contagion`
- **lookahead_risk**: `medium`
- **data_availability_status**: `partial`

### Justification

Start: 2023-03-08 Silvergate Capital announces voluntary liquidation;
SVB Financial announces capital raise — the public-disclosure events
that initiated the regional-bank run dynamics (see FDIC_SVB_POSTMORTEM,
April 2023). End: 2023-05-01 First Republic Bank resolved by FDIC.
SVB closure 2023-03-10, Signature 2023-03-12 + BTFP, and Credit
Suisse / UBS 2023-03-19 all fall between start and end and are
recorded as official-response dates.

### Source binding (16 P1B-surviving sources)

`ALFRED, BIS_CBS, BIS_QR_NETWORK, CBOE_VIX, FDIC_CALL_REPORTS,
FDIC_SVB_POSTMORTEM, FED_H15, FED_TIMELINE, FED_Y9C, FRED, ICAP_MOVE,
NYFED_SOFR, OFR_FSI, OFR_REPO_DATA, PHILLY_FED_RTDSM, STLFSI`.

### Observable signature

Uninsured-deposit run dynamics on a small set of regional banks;
AFS/HTM unrealised-loss-overhang materialisation
(FDIC_CALL_REPORTS:available_for_sale_securities,
held_to_maturity_securities, uninsured_deposits); KBW Regional Bank
Index drawdown > 25% intra-window (NOT directly available — proxied
via FDIC_CALL_REPORTS and FED_Y9C balance-sheet aggregates and
FDIC_SVB_POSTMORTEM narrative); Fed Discount-Window + BTFP utilisation
spike on FED_H15:discount_window_rate context; NYFED_SOFR /
OFR_REPO_DATA remain well-behaved (deposit-run channel, NOT repo-
market channel).

### Exclusion notes

Credit Suisse 2023-03-19 emergency takeover INCLUDED via UBS/SNB
official-response date because CHF-USD funding-stress spillover was
live in-window; the Credit Suisse failure ITSELF is a Swiss
supervisory event and is NOT promoted to a separate D-002J window
(no Swiss banking data sources in P1B-surviving set). PacWest and
Western Alliance stress May-June 2023 placed in post-event buffer.
Yellen 'systemic-risk exception' policy interpretation is outside
scope. FED_Y9C PARTIAL in P1B audit — variable usage restricted to
balance-sheet aggregates, not individual-bank validation.

### Claim boundary

Regional-banking uninsured-deposit-run window. CW6 is scoped
deliberately NARROW: substrate-detection claims MUST respect the
deposit-run channel and the absence of repo-market dysfunction.
Substrate-detection claims on CW6 are NOT bank-level validation
(FED_Y9C and FDIC_CALL_REPORTS aggregates only; individual-bank
modelling is explicitly forbidden); NOT cross-asset/interbank causal
claims; NOT crisis prediction; NOT a basis for supervisory-failure
attribution (despite FDIC_SVB_POSTMORTEM availability — the
postmortem is descriptive).

---

## §7 — Global forbidden interpretations of this registry

The registry, in its present v1 form, does **NOT** constitute:

- a claim of crisis prediction at any window (D-002J runs against
  historical windows, not live precursors);
- a claim of bank-level validation (D-002J pre-registration
  explicitly forbids real-bank validation claims);
- a claim of cross-asset / interbank causal inference (Brunetti
  e-MID / BIS literature reminds us that interbank contagion
  mechanisms are NOT directly identifiable from cross-asset co-
  movement; see `LIT_INTERBANK_CONTAGION` and `LIT_NETWORK_RECON`
  in P1B audit);
- a claim that data have been ingested or downloaded raw
  (P2 is registry-only; ingestion is the P3 boundary);
- authorisation of any canonical run
  (`canonical_run_authorized: false`; `benchmark_only: true`);
- an exhaustive list of all possible systemic-stress windows
  (the 6 windows are the locked initial set; expansion is a fresh
  pre-registered D-002K, not a freelance addition).

Any prose elsewhere in this PR that *appears* to violate a forbidden
interpretation is bounded inside an explicit `forbidden_use` or
`claim_boundary` block and is provided as a negative declaration,
not an affirmative claim.

---

## §8 — Lock anchors

This registry inherits the locked-governance anchors recorded in
`docs/governance/D002J_PREREGISTRATION.yaml` `locked_anchors`. Any
edit to the registry `CW1`..`CW6` ids, window count, date bounds,
mechanism-family mapping, or per-window claim boundary constitutes a
fresh D-002K pre-registration, not a patch.

Locked sha256 pins verified byte-exact at this PR open:

| anchor                       | path                                            | sha256                                                             |
|------------------------------|-------------------------------------------------|--------------------------------------------------------------------|
| D-002C claim ledger          | `docs/governance/D002C_CLAIM_LEDGER.yaml`       | `eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387` |
| D-002G pre-registration      | `docs/governance/D002G_PREREGISTRATION.yaml`    | `1ab91f09370e4705a8b0849467bc1f56df2e58d58d5623d3b6d905cbd110bb04` |
| D-002G acceptance rules      | `docs/governance/D002G_ACCEPTANCE_RULES.md`     | `875b1e3eb031b8e5333dc8b455454f0a30419ead1ebe787aa01d5882e7d6ad31` |
| D-002H pre-registration      | `docs/governance/D002H_PREREGISTRATION.yaml`    | `44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec` |
| D-002I pre-registration      | `docs/governance/D002I_PREREGISTRATION.yaml`    | `b646989c032dc0e29f9b791e0b68209ff22b40f4757737712badc8656cf2db5f` |
| D-002J pre-registration      | `docs/governance/D002J_PREREGISTRATION.yaml`    | `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0` |
| P1B source registry (parent) | `artifacts/d002j/data_registry/source_registry_v1.json` | `f1899b7a882b4b3efbebb54e3dc942c079839f77f981273e2dd09757973b14ec` |

---

## §9 — Decision

`CRISIS_WINDOW_REGISTRY_READY`.

Rationale: all 6 windows assembled with byte-exact date bounds and the
18 schema fields each. Every source_id referenced across the 6 windows
is a P1B-surviving source (audit_status `VERIFIED` or `PARTIAL`); no
`DOWNGRADED` or `REJECTED` source promoted. Minimum 3 P1B-surviving
sources per window enforced (actual: 12 to 21). Registry is registry-
only; no ingestion, no modeling, no null execution, no canonical run,
no prediction claim, no bank-level validation, no cross-asset /
interbank overclaim. Parent registry sha256 pinned. Six locked
governance shas verified byte-exact.

Next legal PR: `feat(x10r,D-002J-P3): implement ingestion manifest and
point-in-time adapter boundary` — opens W3/W4 scope (ingestion
manifest, vintage-aware adapters) on top of this v1 registry. P3 may
only open after this P2 PR is merged with decision
`CRISIS_WINDOW_REGISTRY_READY`.
