# D-002L-P1 Treasury Offering-Announcement Reconstruction Oracle

**Role:** secondary corroboration only. **It cannot authorize D002L-P1.**

## Why this exists

The P0-locked primary exposure source remains TreasuryDirect **Calculated New
Cash/Pay Down Amounts**. That table reports, by date and security class, total
offering, publicly held maturing amount, and net new cash/pay-down.

Treasury also publishes individual historical offering-announcement PDFs. A
coupon announcement carries the issue date, CUSIP, offering amount, and the
estimated amount of maturing coupon securities held by the public. Those
announcements form a second Treasury publication surface from which coupon
cash arithmetic can be reconstructed.

D-002L therefore uses the announcement layer as an error-detection oracle, not
as a replacement source and not as an independent-institution replication.

## Reconstruction

For each issue date:

1. retain each official announcement URL and raw PDF SHA-256;
2. accept coupon securities only: Notes, Bonds, FRNs and TIPS;
3. deduplicate by `(issue_date, CUSIP)`;
4. sum offering amounts once across all coupon announcements settling on that
   issue date;
5. require the stated public-maturing coupon amount to be identical across
   same-date announcements and subtract it exactly once;
6. require exact reconciliation to millions of dollars;
7. compare offering, maturing and net-cash values against the primary P1
   registry on overlapping dates.

A reopening is legal when the same CUSIP appears on a different issue date.
A duplicate on the same issue date is a refusal.

## Fail-closed conditions

The oracle refuses non-Treasury URLs, unexpected announcement paths, missing or
malformed SHA-256 values, bills in the coupon bundle, unknown security classes,
non-integer dollar values, duplicate raw documents, inconsistent same-date
maturing amounts, non-exact million-dollar reconciliation, false declared
coverage, zero overlap with the primary registry, or any primary/oracle value
mismatch.

`FULL_REQUIRED_WINDOW` additionally requires monthly recurrence from September
2014 through August 2026 and exact event-set identity with the primary registry
inside the required window.

## Authority boundary

The oracle has these invariants:

- `official_primary_source_replaced = false`
- `p1_terminal_pass_authorized_by_oracle = false`
- `lineage_advance_allowed_by_oracle = false`
- `confirmatory_outcomes_ingested = false`
- `canonical_run_authorized = false`

A forged or synthetic oracle can therefore never convert a blocked primary
source into P1 PASS. Synthetic bundles exist only for implementation tests.

## Current status

Implementation and adversarial tests can run offline. Scientific corroboration
remains unexecuted until retained official announcement PDF bytes are available.
The primary TreasuryDirect raw-snapshot blocker is unchanged.
