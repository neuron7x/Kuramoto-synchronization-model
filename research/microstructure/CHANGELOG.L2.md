# CHANGELOG — L2 Ricci cross-sectional edge

Chronological record of every PR that shaped the 10-axis + 5-ablation
Ricci research stack on Binance USDT-M perp L2 substrate.

---

## 2026-06-20 · IAAFT gating audit — null certified ADVISORY (fail-closed)

- `feat(audit)` — added `research.microstructure.iaaft_audit`, the fail-closed
  positive-control audit that the advisory IAAFT null's docstring named as the
  precondition for ever gating: *"does it still recover a known edge?"*. It runs
  the **deployed** `killtest._iaaft_pvalue` (not a reimplementation) over many
  seeded synthetic replications and measures its operating characteristics:
  - **power** — positive control (signal predicts target through a temporal
    alignment IAAFT phase-randomisation destroys); fraction with `p < alpha`.
  - **fpr** — negative control (autocorrelated signal *independent* of target);
    fraction with `p < alpha`, i.e. the false-positive rate.
- **Canonical verdict** (`results/L2_IAAFT_GATING_AUDIT.json`, n=40 reps):
  **power = 1.0** but **fpr = 0.25** (95% CI ≈ [0.12, 0.38]) against an
  `fpr_ceiling = 0.10`. The null over-fires ~5× nominal α on the autocorrelated
  (random-walk) regime → **INELIGIBLE** → IAAFT stays **advisory**.
- `run_killtest` now resolves IAAFT gating from this committed artifact via
  `iaaft_is_gating_eligible` (fail-closed on missing / malformed / wrong-schema /
  ineligible) instead of a hand-set flag. Promotion is therefore **earned by a
  reproducible audit, never asserted**. Because the artifact is ineligible the
  binary PROCEED/KILL verdict is bit-identical to pre-PR behaviour.
- **Boundary recorded, not hidden:** the FPR inflation is a real anti-conservative
  failure of an IAAFT null on a *non-stationary* series — re-certification needs a
  stationarity-aware null (e.g. difference-then-surrogate), tracked as future work.

---

## 2026-06-20 · IAAFT linear-spectral null (advisory)

- `feat(killtest)` — wired the canonical IAAFT surrogate
  (`core.kuramoto.falsification.iaaft_surrogate`, Schreiber & Schmitz 1996)
  into `run_killtest` as a third, **advisory** null (`_iaaft_pvalue`). It
  surrogates the 1-D cross-sectional Ricci signal over its finite support,
  preserving the power spectrum **and** amplitude distribution exactly, then
  recomputes the pooled IC against the real forward-return target. A surviving
  IC therefore cannot be a linear-spectral artifact — a strictly stronger test
  than `circular_shift`, which loses power on the autocorrelated Ricci signal.
- Reported in `null_test_pvalues["iaaft"]`; **never gating**. The binary
  PROCEED/KILL verdict is unchanged: promotion to a gating null requires a
  separate fail-closed positive-control audit. Fails closed (p=1.0) on <50
  finite samples. No published verdict (FINDINGS.md) is altered.

---

## 2026-04-18 · Demo-readiness session

End-to-end integration from 8-axis narrative to canonical, self-verifying,
demo-shippable package.

### Validation layer — 10 orthogonal axes

- **PR #268** · `feat(robustness)` — Politis-Romano block bootstrap 95% CI +
  Lopez-de-Prado deflated Sharpe + Augmented Dickey-Fuller + mutual
  information (4 axes in one module: `research/microstructure/robustness.py`)
- **PR #270** · `feat(cv)` — purged & embargoed K-fold CV (AFML Ch. 7);
  5/5 folds positive, mean IC = 0.122
- **PR #271** · `feat(spectral)` — Welch PSD, redness slope β = 1.80
- **PR #272** · `feat(regime-markov)` — 6-state transition matrix,
  mean diagonal = 0.832
- **PR #273** · `feat(hurst)` — DFA-1 Hurst, H = 1.014, R² = 0.982
- **PR #274** · `feat(te)` — pairwise Transfer Entropy, 45/45 BIDIRECTIONAL
- **PR #276** · `feat(cte)` — Conditional Transfer Entropy (BTC-conditioned),
  33/36 PRIVATE_FLOW — rules out common-factor artifact
- **PR #280** · `feat(walk-forward)` — rolling temporal-stability summary,
  82.1% windows positive, STABLE_POSITIVE verdict

### Execution layer

- **PR #266** · `feat(diurnal-filter)` — sign-aware per-row direction filter
- **PR #269** · `feat(pnl)` — cost sweep + break-even for REGIME_Q75+DIURNAL,
  f* = 0.23167 (canonical gate fixture)

### Synthesis + demo artifacts

- **PR #275** · `docs(findings)` — 8-axis consolidated narrative
- **PR #278** · `feat(demo)` — three canonical figures + manifest + runner
- **PR #279** · `docs(readme)` — L2 microstructure section
- **PR #281** · `feat(visualize)` — fig4_stability walk-forward panel
- **PR #282** · `feat(visualize)` — fig0_cover single-page demo poster
- **PR #297** · `feat(demo)` — self-contained HTML dashboard (7.2 KB)
- **PR #300** · `feat(make)` — pro-max ergonomic Makefile targets

### Ablation / stress layer — 5 axes

- **PR #290** · `feat(ablation)` — hyperparameter (regime-q × window) sweep →
  **SENSITIVE** (f* drifts ±60%, but all 9 cells below production ceiling)
- **PR #293** · `feat(ablation)` — leave-one-symbol-out → **MIXED**
  (BTC removal drops IC 43%; all 10 cells still positive)
- **PR #295** · `feat(ablation)` — hold-time (60–600 s) → **ROBUST**
  (3/5 cells already profitable at f = 0)
- **PR #296** · `feat(stress)` — slippage stress (±bp/side) → **BOUND**
  (max viable +3 bp/side; typical prod +0.5–1.5 bp)
- **PR #298** · `feat(stress)` — fee-tier sensitivity → **RESILIENT**
  (all 4 VIP tiers bracket below 0.50)

### Coherence / integrity gates

- **PR #286** · `test(coherence)` — 7 independent gate suites
  (deterministic replay, doc-data, per-axis invariants, schema registry,
  CLI discoverability, performance budget, E2E demo smoke)
- **PR #288** · `test(property-based)` — Hypothesis coverage for
  DFA Hurst, TE, CTE, walk-forward

### Additional polish PRs

- **PR #297** · `feat(demo)` — HTML dashboard (7.5 KB self-contained)
- **PR #298** · `feat(stress)` — taker-fee tier sensitivity → RESILIENT
- **PR #300** · `feat(make)` — pro-max ergonomic Makefile targets
- **PR #301** · `docs(l2)` — CHANGELOG + Makefile integrity tests
- **PR #303** · `feat(dashboard)` — fee-tier row in ablations section
- **PR #304** · `feat(make)` — `l2-open` + frozen SESSION_STATE.md
- **PR #306** · `ci(l2-demo)` — dedicated GitHub Actions gate
- **PR #308** · `test(fail-closed)` — 17 adversarial input tests
- **PR #309** · `feat(regime-cond)` — VOL_DRIVEN (3.16× high/low ratio)
- **PR #312** · `feat(metrics)` — flat headline metrics JSON (44 keys)

### Final state

- **10 validation axes**, all green on Session 1
- **5 ablation / stress axes** with honest verdicts (SENSITIVE / MIXED /
  ROBUST / BOUND / RESILIENT)
- **1 regime-conditional decomposition** (VOL_DRIVEN, 3.16× high/low)
- **5 canonical figures** + self-contained HTML dashboard
- **1 one-command runner** + SHA-256 manifest (81 s end-to-end)
- **1 flat headline metrics JSON** for downstream ingestion (44 keys)
- **345+ L2 tests** passing (coherence + property-based + fail-closed)
- **Deterministic replay** confirmed bit-exact across two runs
- **CI gate workflow** protects canonical state under branch-protection

Canonical entry point: `make l2-demo`
Synthesis document: `research/microstructure/FINDINGS.md`
Demo landing page: `results/figures/index.html`
Headline metrics: `results/L2_HEADLINE_METRICS.json`
