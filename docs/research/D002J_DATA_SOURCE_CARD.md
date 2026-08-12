# D-002J — Data Source Cards (P1)

Pre-registration anchor: `docs/governance/D002J_PREREGISTRATION.yaml`
PR lineage: D-002J-P1 (`feat/x10r-d002j-p1-data-source-registry-v1`)
Date: 2026-05-14
Machine-readable registry: `artifacts/d002j/data_registry/source_registry_v1.json`

This document is a human-readable companion to the JSON registry.
Each card carries name, provider, official URL, license, what the
source gives us, what it does not, ingestion notes, and forbidden
interpretations. The cards below are the 8 most-critical sources
out of the 25 in the registry; the JSON registry remains the
canonical complete listing.

P1 scope discipline: cards describe public sources only; P1 does NOT
ingest any data and does NOT validate any source against real-bank
ground truth. See D-002J prereg `forbidden_claims` for the binding
boundary.

---

## Card template

```
- source_id: <stable identifier>
- name: <human-readable name>
- provider: <issuing body>
- official_url: <public landing page>
- license: <explicit boundary>
- what_it_gives_us: <bulleted observables>
- what_it_does_not: <bulleted gaps>
- ingestion_notes: <pipeline grade + format>
- forbidden_interpretations: <bulleted bounds>
```

A card missing any of the eight fields is incomplete.

---

## Card 1 — BIS Consolidated Banking Statistics

- **source_id**: `BIS_CBS`
- **name**: BIS Consolidated Banking Statistics
- **provider**: Bank for International Settlements (BIS)
- **official_url**: https://www.bis.org/statistics/consstats.htm
- **license**: public domain with attribution required
- **what_it_gives_us**:
  - Cross-border claims and local claims by jurisdiction, on both
    immediate-counterparty and ultimate-risk bases
  - Sectoral breakdown into banks / non-banks / official sector
  - 31-reporting-jurisdiction coverage with the deepest publicly
    available cross-border interbank time series (1983-Q4 onwards)
- **what_it_does_not**:
  - No counterparty-level resolution — only jurisdiction aggregates
  - No frequency finer than quarterly
  - Reporting-perimeter changes in 2014 and 2020 break some series
- **ingestion_notes**:
  - Public bulk download in CSV; fully documented schema in the
    BIS Statistical Bulletin
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - Intra-quarter contagion dynamics CANNOT be inferred from quarterly aggregates
  - Individual-bank attribution is OUT OF SCOPE — only jurisdiction-level aggregates are public

---

## Card 2 — FRED (Federal Reserve Economic Data)

- **source_id**: `FRED`
- **name**: Federal Reserve Economic Data
- **provider**: Federal Reserve Bank of St. Louis
- **official_url**: https://fred.stlouisfed.org/
- **license**: public redistribution permitted with attribution to FRED and underlying source
- **what_it_gives_us**:
  - De facto public macro-financial backbone — aggregates hundreds
    of thousands of upstream series
  - Canonical mirror of H.15 interest rates, VIX, FSI composites,
    yield curves, credit spreads
- **what_it_does_not**:
  - FRED is an aggregator, not a primary source — upstream revisions
    propagate without notice
  - Some series are subject to attribution-only redistribution rules
    of the upstream owner
  - Real-time (vintage) data requires `ALFRED`, not FRED
- **ingestion_notes**:
  - Public API with free key; well-documented endpoints; client
    libraries available in Python and R
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - Real-time decision-use must read ALFRED vintages, not FRED revised
  - FRED methodology cannot be claimed as owned by the user — it is
    St Louis Fed's

---

## Card 3 — OFR Short-Term Funding Monitor and Repo Data

- **source_id**: `OFR_REPO_DATA`
- **name**: OFR Short-Term Funding Monitor and Repo Data
- **provider**: Office of Financial Research (OFR), US Treasury
- **official_url**: https://www.financialresearch.gov/short-term-funding-monitor/
- **license**: public domain US government work
- **what_it_gives_us**:
  - Tri-party repo volumes broken out by collateral class
    (Treasuries, agency MBS, equities, corporate bonds, etc.)
  - Dealer-to-money-fund volumes
  - Haircut distributions at daily / monthly aggregate
- **what_it_does_not**:
  - Bilateral uncleared repo is partial — most segment lives outside
    the monitor
  - Haircut distributions are aggregated, not per-ISIN
  - No counterparty-level resolution
- **ingestion_notes**:
  - Public dashboard plus CSV export
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - Bilateral repo segments in detail are OUT OF SCOPE
  - European repo markets are NOT covered

---

## Card 4 — Secured Overnight Financing Rate (SOFR)

- **source_id**: `NYFED_SOFR`
- **name**: Secured Overnight Financing Rate (SOFR)
- **provider**: Federal Reserve Bank of New York
- **official_url**: https://www.newyorkfed.org/markets/reference-rates/sofr
- **license**: public domain with attribution required
- **what_it_gives_us**:
  - Daily SOFR rate plus 1st / 25th / 75th / 99th percentile of
    underlying transactions
  - Daily transaction volume
  - Canonical 2019-Q3 repo-spike signal at 99th percentile
- **what_it_does_not**:
  - Coverage starts 2018-04-02 — no GFC, no Eurozone 2011-2012 history
  - Aggregates three repo segments — segment-level signal blurred
- **ingestion_notes**:
  - Public daily publication; fully documented methodology
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - Pre-2018 repo history must use LIBOR-OIS / TED-spread proxies,
    not SOFR
  - Individual counterparty attribution is OUT OF SCOPE

---

## Card 5 — OFR Financial Stress Index

- **source_id**: `OFR_FSI`
- **name**: OFR Financial Stress Index
- **provider**: Office of Financial Research (OFR), US Treasury
- **official_url**: https://www.financialresearch.gov/financial-stress-index/
- **license**: public domain US government work
- **what_it_gives_us**:
  - Daily composite stress index plus five sub-indices (credit,
    equity-valuation, safe-asset, funding, volatility)
  - Five-region decomposition (US / other advanced / emerging /
    global / other)
- **what_it_does_not**:
  - Composite construction means decomposition is required for
    mechanism-level signal
  - Sub-component weights are periodically revised
- **ingestion_notes**:
  - Public CSV download; weighting methodology documented
    (Monin 2017, OFR Working Paper 17-04)
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - OFR_FSI cannot serve as the y-label when its constituent series
    are also in x — circularity
  - The composite is descriptive, not causal

---

## Card 6 — FDIC Quarterly Call Reports

- **source_id**: `FDIC_CALL_REPORTS`
- **name**: FDIC Quarterly Call Reports
- **provider**: Federal Deposit Insurance Corporation (FDIC)
- **official_url**: https://cdr.ffiec.gov/public/
- **license**: public domain US government work
- **what_it_gives_us**:
  - Per-bank balance-sheet attributes for ~4,000 US commercial banks
    quarterly back to 1976-Q1
  - Uninsured-deposit share, AFS / HTM securities, wholesale-funding
    share, loan-loss provisions
- **what_it_does_not**:
  - Quarterly frequency cannot capture intra-week dynamics like the
    SVB March-2023 run
  - US-only — no international coverage
  - Off-balance-sheet detail is only partially captured
- **ingestion_notes**:
  - Public per-bank download via FFIEC Central Data Repository (CDR)
  - Pipeline grade: READY for W1 downstream PR
- **forbidden_interpretations**:
  - Intra-day or intra-week run dynamics are OUT OF SCOPE
  - Non-US banks are OUT OF SCOPE

---

## Card 7 — Bank of England LDI Review

- **source_id**: `BOE_LDI_REVIEW`
- **name**: Bank of England Financial Policy Committee and Working
  Paper reports on the 2022 LDI episode
- **provider**: Bank of England (BoE)
- **official_url**: https://www.bankofengland.co.uk/financial-stability-report/2022/december-2022
- **license**: public domain with attribution required
- **what_it_gives_us**:
  - Canonical post-mortem chronology of the 2022-09 LDI fund
    collateral-call spiral
  - UK gilt-market dysfunction narrative
  - Temporary purchase facility dates and operational scope
- **what_it_does_not**:
  - Narrative PDF — no machine-readable underlying data
  - Post-mortem only — no real-time fund-level positions
- **ingestion_notes**:
  - Public PDF / HTML
  - Pipeline grade: narrative-extraction pipeline required for W1
    downstream PR
- **forbidden_interpretations**:
  - Individual pension-fund attribution is OUT OF SCOPE — only
    aggregate narrative is public
  - The post-mortem is post-hoc framing; real-time decision context
    is NOT reconstructable from this source alone

---

## Card 8 — Seminal Literature on Interbank Contagion Mechanisms

- **source_id**: `LIT_INTERBANK_CONTAGION`
- **name**: Seminal literature on interbank contagion mechanisms
- **provider**: Academic publishers / NBER / SSRN preprint mirrors
- **official_url**: https://www.nber.org/papers
- **license**: preprint redistribution OK; published version may be restricted
- **what_it_gives_us**:
  - Methodology anchors: Eisenberg-Noe 2001 clearing vectors;
    Battiston et al. 2012 DebtRank; Glasserman-Young 2015 contagion;
    Anand et al. 2018 max-entropy reconstruction; Aldasoro-Alves 2018
    multiplex networks; Brunnermeier 2009 repo funding fragility
- **what_it_does_not**:
  - These are methodology references, NOT real data streams
  - Published versions may be paywalled — preprints are the
    redistribution-safe source
- **ingestion_notes**:
  - Public preprint mirrors; bibliographic anchors only
  - Pipeline grade: literature reference; NO ingestion pipeline
- **forbidden_interpretations**:
  - Paper results CANNOT be treated as raw data series
  - Methodology references CANNOT substitute for an empirical
    null model in the D-002J pipeline

---

## Card 9 — Philadelphia Fed Real-Time Data Set for Macroeconomists (added in P1B)

- **source_id**: `PHILLY_FED_RTDSM`
- **name**: Philadelphia Fed Real-Time Data Set for Macroeconomists
- **provider**: Federal Reserve Bank of Philadelphia
- **official_url**: https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-for-macroeconomists
- **documentation_url**: https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/real-time-data-set-full-documentation
- **license**: public redistribution permitted with attribution to Federal Reserve Bank of Philadelphia
- **what_it_gives_us**:
  - Canonical vintage US macro time-series — every observation
    carries the date at which it was first released, allowing
    honest real-time replication free of revision lookahead
  - Coverage from 1965-Q4 onwards across real and nominal GNP/GDP,
    industrial production, civilian unemployment, CPI, PCE,
    payroll employment, fixed investment, and M1/M2 money stock
  - Non-FRED-native macro variables (GNP-era pre-1992 definitions,
    multiple GDP definitional regimes) that ALFRED does not vintage
- **what_it_does_not**:
  - US-only — no international macro real-time data
  - Macro-only — no financial micro data (no bank balance sheets,
    no repo, no derivatives)
  - Quarterly vintage release cadence — no daily granularity
  - Series not present in RTDSM are not vintaged
- **ingestion_notes**:
  - Public bulk download via XLSX / CSV
  - Pipeline grade: READY for W1 downstream PR
  - Anchor methodology: Croushore & Stark (1999, 2003)
- **forbidden_interpretations**:
  - Post-hoc revised data CANNOT be used for in-window prediction
  - Redistribution requires explicit Philadelphia Fed attribution
  - Methodology CANNOT be claimed as owned by the user — it is
    the Philadelphia Fed's
  - This card is for vintage US macro data only; do not extrapolate
    to financial micro-data or non-US series

This card was added in **D-002J-P1B** (2026-05-14) to satisfy the
`information_constraint` mechanism-family floor (≥ 2 verified/partial
sources). Together with `ALFRED`, this forms the canonical US
vintage-data pair.

---

## Lock anchors

This card document inherits the D-002J `locked_anchors` block. The
machine-readable registry sha256 is computed at PR merge and
recorded in the `source_registry_summary_v1.json` decision footer.
Card edits in a downstream PR are append-only by source-card id.
