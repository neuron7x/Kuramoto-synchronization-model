# D-002L Design Rationale — Repeated Ex-Ante Treasury Settlement Pressure

**Status:** P0 pre-registration only. **Zero confirmatory outcome scoring.**
**Date:** 2026-08-28.

## 0. Parent failure is retained, not repaired by rhetoric

D-002K-P4 is terminally `POWER_GATE_REFUSED_UNDERPOWERED`. Its feasible
crisis-side sample was one realization per crisis window. Under the locked
D-002K design (`alpha=0.016667`, conservative `d=0.80`, reference `n=5`),
power was `0.0481`, while the design needed roughly 20 crisis-side replicates.
That is a structural replication problem, not a compute-budget problem.

D-002L therefore does **not** increase seeds, relax alpha, inflate an effect
prior, reinterpret one crisis as many observations, or reopen D-002K. It
changes the scientific unit of replication.

## 1. Structural repair: repeated scheduled exposure

The new unit is a unique U.S. Treasury **coupon settlement date**. Treasury
publishes calculated new-cash/pay-down amounts by date and security type.
Coupon settlements recur throughout the sample and represent repeated funding
demands that are known from the Treasury issuance process independently of the
subsequent repo-rate response.

Same-date coupon cash flows are aggregated into one event. The event exposure
is net new cash (or pay-down), scaled per $100bn. Events are selected by a
deterministic source rule; there is no hand-maintained “interesting dates”
list.

This changes the physical information content of the experiment. It does not
manufacture repeated observations from a single historical crisis.

## 2. Why TGCR minus the reserve-remuneration anchor

The primary outcome is the daily change in the Tri-Party General Collateral
Rate relative to the Federal Reserve remuneration rate actually in force on
that date. Define:

`RRA_t = IOER_t` for observations through `2021-07-28`;

`RRA_t = IORB_t` for observations from `2021-07-29`.

Then:

`spread_t = 100 * (TGCR_t - RRA_t)` basis points

`y_t = spread_t - spread_{t-1}`

This splice is explicit because raw IORB does not exist for the 2014–2021
portion of the study. IOER and IORR were replaced by the single IORB rate on
July 29, 2021. D-002L therefore forbids silently backfilling IORB into the
IOER era or relabeling historical IOER observations as raw IORB.

TGCR is a direct overnight Treasury-repo reference rate administered by the
New York Fed. The reserve-remuneration anchor removes the contemporaneous
policy-rate level more directly than broad equity/volatility proxies.

The August 26, 2026 Federal Reserve FEDS Note “Repo Markets and the Fed’s
Balance Sheet: Implications for Monetary Policy Implementation” is used as a
**design and conservative power-prior anchor only**. It reports a positive
association between net Treasury coupon issuance and a TGCR-relative-to-policy
rate spread over September 2014–March 2026 and stronger coupon sensitivity
when aggregate liquidity is low. Because that literature overlaps the
historical sample, D-002L explicitly forbids an “independent replication”
claim.

## 3. Exactly one primary estimand

The confirmatory parameter is only `beta_coupon` in the locked public-data
model:

`Δspread_t = beta_0 + beta_coupon*x_t + beta_bill*b_t`
`            + beta_lag*spread_{t-1} + calendar_controls + epsilon_t`

where `x_t` is coupon net-new-cash settlement pressure per $100bn.

The test is two-sided at alpha 0.05; a confirmatory success additionally
requires `beta_coupon > 0`. Week-clustered standard errors are primary.
A deficient cluster count, rank-deficient design, zero exposure variance, or
missing required source field is a refusal, not an invitation to change the
model.

## 4. Temporal firewall

The sample is split **before outcome ingestion**:

- `2014-09-02 .. 2018-12-31`: calibration/power-only. Outcome values may be
  used to estimate noise scale and validate mechanics, never to choose the
  confirmatory model.
- `2019-01-01 .. 2026-08-20`: retrospective confirmatory partition. Its
  outcomes remain forbidden until P2 power passes.
- `>= 2026-08-28`: prospective accumulation only. A prospective performance
  claim requires a fresh successor contract and a minimum-event-count rule.

This does not turn the historical confirmatory period into prospective data.
The study class remains `retrospective_preregistered_falsification_benchmark`.

## 5. Power comes before confirmatory outcomes

P1 may ingest Treasury exposure/calendar data and construct the eligible-event
registry. It may not ingest confirmatory TGCR outcomes.

P2 uses:
1. the Treasury-only confirmatory event count and exposure variance;
2. calibration-period outcome noise;
3. a conservative external effect prior defined by a fixed shrinkage/bound
   rule.

P2 must reach power >=0.80 before P3 is legal. Otherwise D-002L terminates
truthfully. Confirmatory outcomes are never used to enlarge the prior.

## 6. Point-in-time and provenance contract

Every confirmatory observation must retain retrieval time, source URL,
content digest, observation date, publication/release boundary, and any
revision/vintage status. Forward fill is forbidden for the primary outcome.
Missing required data invalidate the event rather than being silently
imputed.

Primary sources:
- U.S. Treasury / TreasuryDirect — calculated new cash/pay-down amounts.
- Federal Reserve Bank of New York — TGCR.
- Board of Governors — IOER through 2021-07-28 and IORB from 2021-07-29.
- OFR U.S. Repo Markets Data Release — secondary validation only.

## 7. GeoSync-specific features are deliberately not primary

Kuramoto order parameters, phase coherence, cross-market synchronization and
other GeoSync-native features are `exploratory_only` in D-002L. This is a
deliberate anti-rescue constraint.

If the repeated public funding-pressure benchmark itself cannot survive a
single locked estimand, adding a complex GeoSync feature would only add
researcher degrees of freedom. If D-002L closes successfully, a fresh D-002M
may preregister **incremental** GeoSync information on a declared holdout.

## 8. Claims that D-002L cannot make

D-002L cannot claim crisis prediction, market prediction, trading alpha,
causality from significance alone, bank-level validation, interbank
contagion, independent replication of the 2026 FEDS Note, or rescue of any
D-002J/K terminal refusal.

## 9. Legal next node

`D002L-P1`: source + exposure-event registry, with **no confirmatory outcome
ingestion**. If provenance or event construction is incomplete, P1 stops.
