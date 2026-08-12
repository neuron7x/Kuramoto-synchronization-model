# Claim Boundary Contract — Disha BA + Correlation Article Artefact

This document is **load-bearing**. Every sentence in `DISHA_ARTICLE_SUMMARY.md`,
`DISHA_BA_CORRELATION_FINAL_REPORT.md`, figure captions, and the PR body must map
to one of the four categories below. Anything outside `CLAIM_ALLOWED` /
`CLAIM_WEAK` is gate-failed.

---

## CLAIM_ALLOWED — safe to publish without qualification

- BIS LBS supports country-level banking-system exposure network analysis.
- The thresholded network shows concentration: a small number of high-mass nodes
  carry most of the cross-border claims.
- Some stress-window exposure-change correlations identify plausible macro
  corridors (DE-FR, DE-LU, GB-US, CH-GB, BE-NL).
- The result is descriptive and reproducible.
- Some countries appear as target-only or constant-source under this filter
  (ES, IT, HK, PH, ZA) — a BIS reporting/filter constraint, not economic absence.
- The empirical degree distribution has a non-trivial zero-degree tail that the
  matched Barabási-Albert null cannot reproduce.

## CLAIM_WEAK — admissible only with explicit qualifier

- The network is loosely comparable to BA-style concentration.
  *(Required qualifier: "but not distinguishable from matched random-graph baseline.")*
- Correlation changes may indicate stress-period co-movement.
  *(Required qualifier: "descriptive, short window, fragile statistic.")*
- Some countries act as high-mass nodes in the aggregate exposure network.
  *(Required qualifier: "country-level aggregate, not bank-level.")*

## CLAIM_FORBIDDEN — gate-failed if present anywhere

- The network is bank-level interbank.
- The data validate repo liquidity contagion.
- BA is confirmed.
- Preferential attachment is proven.
- Pearson correlations prove causal contagion.
- Kuramoto or phase-transition dynamics are supported here.
- Production-grade scientific validation.
- Bank-to-bank exposures.

## CLAIM_REQUIRES_NEW_DATA — out of scope; would need supervisory access

- Bank-to-bank interbank topology.
- Repo collateral-chain dynamics.
- Haircut-driven fire-sale contagion.
- Funding maturity rollover risk.
- DebtRank on collateral rehypothecation network.
- Causal contagion identification.

---

## Gate

```
PASS = every published sentence maps to ALLOWED or WEAK (with qualifier)
FAIL = any FORBIDDEN claim appears in summary, report, captions, or PR body
```

The gate is enforced by `find_forbidden_phrases()` in
`tools/build_disha_ba_correlation_figures.py` (whitespace-normalised) and by
the `test_*` suite in `tests/research/systemic_risk/test_disha_ba_correlation_figures.py`.
