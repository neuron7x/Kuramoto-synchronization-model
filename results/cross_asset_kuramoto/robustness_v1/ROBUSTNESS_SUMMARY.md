# Cross-asset Kuramoto · Robustness v1 summary

Canonical one-page digest of the v1 robustness battery. Entry point
for any future audit; all numeric claims reference specific artefacts
under `results/cross_asset_kuramoto/robustness_v1/`.

## What was tested

Three read-only suites over the frozen bundle (28 hash-verified
artefacts + inline-hash-verified LOO grid): CPCV+PBO+PSR, two-family
demeaned null on daily log returns, parameter-jitter stability.
Decision layer → `PASS` / `FAIL` / `INSUFFICIENT_EVIDENCE`.

## What passed

| Gate | Value | Threshold | Status |
|---|---:|---:|:-:|
| LOO-grid PBO (admissible, n = 13) | 0.2000 | < 0.50 | ✓ |
| Fold-mirror PBO (tautological, n = 2) | 0.0000 | < 0.50 | ✓ |
| PSR (daily, *no HAC*) | 1.0000 | ≥ 0.95 | ✓ (inflated) |

## What failed

| Gate | Value | Threshold | Status |
|---|---:|---:|:-:|
| iid_bootstrap null p-value | 0.0829 | ≤ 0.05 | ✗ |
| stationary_bootstrap null p-value | 0.1029 | ≤ 0.05 | ✗ |

Both nulls are *demeaned* bootstrap resamples — the canonical test of
H₀ that the true mean is zero. Observed Sharpe (0.483) sits at the
8–10 % upper-tail of the null distribution: suggestive but below the
strict α = 0.05 bar. Consistent with `SEPARATION_FINDING.md`: most
realised alpha lives in the narrow HIGH_SYNC regime.

Null suite evolved through three implementation states during review;
final demeaned bootstrap is the only honest one (PR #356:
`iid_permutation` → `iid_bootstrap` → demeaned).

## What is placeholder

Jitter evaluator is `PLACEHOLDER_APPROXIMATION`: a quadratic penalty
in fractional parameter-space distance, not a live rebuild. The
Jitter row shows `N/A`; decision layer abstains from live ✓/✗.

## Known statistical limitations

PSR is not HAC-adjusted; serial correlation inflates `psr_daily`.
LOO-grid PBO has 5 CPCV paths so 0.20 is a point estimate with wide
CI. Full catalogue in `ROBUSTNESS_LIMITATIONS.md`.

## Verdict

**`FAIL_ON_DAILY_RETURNS`** — the null suite rejects the hypothesis
that the realised daily log-return stream carries Sharpe-distinguishing
information beyond bootstrap resampling. Terminal label `FAIL` in
`verdict.json`; decision-stable across n_bootstrap ∈ {500, 1000,
2000, 5000} per `null_convergence.csv`.

## Forward path

The verdict flips when any of three blockers is removed: raw
`net_ret` ships with the frozen bundle (tightens the null),
HAC-adjusted PSR is wired (deflates PSR to its true value), or a
live jitter evaluator replaces the placeholder.

## Cross-references

- `SEPARATION_FINDING.md` — offline-robustness conclusion
- `shadow_validation/ACCEPTANCE_GATES.md` — 90-bar truth gate
- `ROBUSTNESS_PROTOCOL.md` — derivation + thresholds
- `ROBUSTNESS_LIMITATIONS.md` — forward-improvement catalogue
