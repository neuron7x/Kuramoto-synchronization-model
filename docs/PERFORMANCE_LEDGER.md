# Performance Ledger — Canonical Claims

**This file is the single source of truth for every performance number
GeoSync makes.** If a Sharpe ratio, hit rate, or P&L number appears in
README, in a marketing deck, or in conversation, it must cite a row of
this ledger. A number that is not in this ledger is not a claim — it is
either exploratory research (clearly labelled) or a typo.

> **Discipline rule.** Adding a row to this ledger requires the backing
> artefact to land in the repository first (under `results/`,
> `benchmarks/`, or linked from a merged ADR). Removing a row requires
> a reason recorded in the git commit message of the removal.

## Ledger

| # | Date | Metric | Value | Subsystem | Artefact | Caveat |
|---|------|--------|-------|-----------|----------|--------|
| 1 | 2026-04-18 | Deflated Sharpe | **15.1** | L2 robustness demo | `L2_ROBUSTNESS.json` (produced by the L2 demo gate workflow) | This is the Deflated Sharpe Ratio (DSR) under the `L2_ROBUSTNESS` scenario suite, **not** an annualised trading Sharpe on live capital. Interpret as robustness under the specific sweep defined by the demo gate. |
| 2 | 2026-04-18 | Pr(strategy is real) | **1.0** | L2 robustness demo | `L2_ROBUSTNESS.json` | Posterior that the DSR-15.1 result is not a false discovery under the demo's multiple-testing correction. Not a live-performance probability. |

## What this ledger is **not**

* It is **not** a live-capital track record. GeoSync does not ship a
  live-trading history; see [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md#l-1--execution-surface-is-paper-trading-only).
* It is **not** a marketing surface. If a figure appears here, it has a
  machine-readable artefact attached and that artefact is reproducible
  on CI.

## Scattered numbers that are **not** canonical

The following Sharpe-like numbers exist in the documentation set but are
**illustrative, subsystem-local outputs** and do not belong in this
ledger:

| Location | Number | Context |
|----------|--------|---------|
| `docs/HPC_AI_V4.md` | Sharpe Proxy 1.25 / Sharpe Ratio 1.32 | HPC-accelerated Q-learning baseline comparison |
| `docs/automated_risk_testing.md` | Sharpe 1.45 | Single `normal_market` risk-test scenario output |
| `docs/operations/PRODUCT_PAIN_SOLUTION.md` | Sharpe 1.12 | Illustrative product-narrative figure |

If any of those ever becomes a platform-level claim, it must graduate
into the ledger above with a real artefact.

## Changelog

* **2026-04-18** — Ledger established. Migrated the one DSR claim that
  the README carries; flagged three stray Sharpe numbers as illustrative.
