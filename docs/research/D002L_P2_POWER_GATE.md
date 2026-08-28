# D-002L-P2 — Pre-outcome power gate

## Status

**Implementation:** complete and testable.  
**Scientific execution:** `NOT_EXECUTED`.  
**Reason:** D002L-P1 has not reached direct-source `TERMINAL_PASS`.

P2 is an inactive gate until the P1 Treasury exposure registry is authenticated,
source-complete and explicitly authorizes `D002L-P2`. The implementation checks
P1 status before reading any downstream registry/noise/prior artifacts.

## What P2 is allowed to know

P2 may consume the Treasury exposure registry produced by P1, calibration-period
noise information ending no later than 2018-12-31, and the preregistered external
effect prior. It may not load confirmatory TGCR/IOER/IORB observations, fit
`beta_coupon`, or score the empirical D-002L claim.

## Power model

The pre-outcome design has nine columns: intercept, coupon exposure `x_t`,
same-day Bill exposure `b_t`, Tuesday-Friday indicators with Monday as reference,
month-end, and quarter-end. Weekend settlement dates are invalid.

Coupon exposure is residualized against the nuisance columns. Coefficient power
is computed with a two-sided alpha of 0.05 and a conservative calibration noise
scale. Because the confirmatory inference contract uses week-clustered standard
errors, P2 requires a calibration `week_cluster_design_effect >= 1` and uses:

`effective_sigma = sigma_residual * sqrt(week_cluster_design_effect)`

Thus the power calculation cannot become more optimistic than the iid noise
estimate merely because clustering exists. Non-finite power, rank deficiency,
nonpositive residualized exposure variation, insufficient effective week
clusters, or power below 0.80 are fail-closed conditions.

## Important scope limit

The locked confirmatory model also contains lagged repo spread. That variable is
an outcome-derived control and is intentionally unavailable at P2. P2 therefore
checks only the pre-outcome/exogenous design. The **full** design matrix and
week-clustered confirmatory inference must be revalidated at D002L-P4 after the
legally gated P3 outcome ingestion.

The external 2026 FEDS design anchor overlaps the historical D-002L period.
Consequently a future positive D-002L result remains retrospective and cannot be
called an independent replication of that paper. P2 power adequacy does not
establish empirical association, causality, prediction, trading alpha or a
GeoSync-specific mechanism.
