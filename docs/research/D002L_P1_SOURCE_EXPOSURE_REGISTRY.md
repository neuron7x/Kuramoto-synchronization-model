# D-002L-P1 — Treasury source and exposure-event registry

## Purpose

P1 implements the P0-locked exposure side only. It compiles an official
TreasuryDirect **Calculated New Cash/Pay Down Amounts** snapshot into one
content-addressed event per unique coupon settlement date. It does **not**
observe TGCR, IOER, IORB, `y_t`, `beta_coupon`, a p-value, or any confirmatory
outcome.

## Fail-closed source boundary

Only the exact P0-locked TreasuryDirect URL is accepted. The raw bytes are
SHA-256 addressed. Provenance must declare a full historical table snapshot,
retrieval time, coverage range, publisher, dataset, and revision/vintage
status. A mirror, partial pagination, digest mismatch, incomplete date range,
or an outcome-like column is a hard refusal.

P1 does not claim that structural guards alone prove source completeness. The
required `full_historical_table_snapshot` provenance flag is combined with
coverage and year-continuity guards. A release-grade execution still requires
the official source bytes to be retrieved and retained.

## Event construction

- Unit: unique coupon settlement date.
- Coupon universe: Notes, Bonds, FRNs, TIPS; a direct `Coupons` row is accepted.
- All coupon cash-flow rows on the same date are aggregated deterministically.
- A direct `Coupons` row and constituent coupon rows on the same date are
  mutually exclusive; coexistence is refused as a double-count risk.
- Zero net-new-cash exposure is ineligible, never silently coerced.
- Input amounts are interpreted in TreasuryDirect's table units of millions of
  U.S. dollars; `x_t` is scaled by $100bn as locked at P0.
- 2014-09-02..2018-12-31 = calibration-power exposure partition.
- 2019-01-01..2026-08-20 = retrospective confirmatory **exposure-only** partition.
- 2026-08-21..2026-08-27 = preregistration gap, excluded.
- >=2026-08-28 = future accumulation only.

## Current execution state

The implementation and synthetic contract tests can PASS without official
network access. Synthetic fixtures are **not scientific evidence**. That is **not** a scientific P1 PASS. P1 advances to P2 only
when the official Treasury snapshot is source-complete, retained with digest,
and the registry compiles without refusal. If official retrieval is blocked,
status remains `NOT_EXECUTED / BLOCKED_SOURCE_ACCESS`, the D-002L lineage is
not advanced, and the P0 stop condition remains active.


## 10. P1 hardening after adversarial false-PASS test

A deliberate adversarial fixture containing only one synthetic coupon row per
year was able to satisfy the original year-presence/variance checks when its
JSON provenance falsely declared a full historical snapshot. That was a real
false-PASS path and is now a regression target.

The hardened P1 compiler therefore additionally requires:

1. row-level Treasury cash identity: `net = offering - publicly held maturing`;
2. the minimum and maximum settlement dates physically present in the raw bytes
   to equal the declared provenance coverage dates;
3. at least one coupon settlement event in every calendar month from September
   2014 through August 2026;
4. the previous year-presence and confirmatory exposure-variance checks;
5. direct locked-URL acquisition for any `TERMINAL_PASS`.

`--raw` + user-supplied provenance remains useful for deterministic offline
replay, but it returns `OFFLINE_REPLAY_ONLY`, exit code `20`, and
`lineage_advance_allowed=false`. A self-asserted provenance JSON is not treated
as source-authenticity evidence.

These checks deliberately make P1 harder to pass. They do not claim that
monthly recurrence proves byte-complete history; direct official acquisition
remains mandatory for lineage advancement.
