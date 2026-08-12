# Systemic Risk as Phase Transition — Kuramoto on Interbank Networks (v2)

> **Tier (per `CLAIMS.md`):** `HYPOTHESIS` until the v2 falsification
> battery returns `HARD_PASS` on ≥ 2 independent crises with real
> interbank exposure data and the bootstrap-CI lower bound clears 0.70.
>
> **Scope of the current executable falsification — score-level only.**
>
> The instrument tests:
>
> ```
> score(t)  →  crisis-window statistical evaluation
> ```
>
> It does **not** yet validate the full end-to-end pipeline:
>
> ```
> temporal exposure panel  →  topology  →  coupling  →  Kuramoto dynamics
>                          →  r(t)  →  early-warning score  →  crisis verdict
> ```
>
> End-to-end validation requires empirical temporal exposure ingest,
> locked score construction, executable null-audit orchestration,
> reproducibility manifest, and real-data runs. None of those have
> happened yet — see `LIMITATIONS.md` § "Domain limitations" and
> `governance.run_premerge_science_gate` for the machine-checked
> readiness profile.

## What this does

A pre-registered, fail-closed test of one falsifiable claim: the
early-warning score derived from rolling Kuramoto order-parameter
features (level + slope + variance) is *elevated* in pre-event
windows preceding banking-crisis dates relative to safely-distant
null windows. The verdict is encoded once and never edited after
seeing data — the AUC thresholds (`fail_auc=0.55`, `pass_auc_ci_low=0.70`),
permutation p (`pass_alpha=0.01`), and Bonferroni FWER discipline are
all defined in `falsification.FalsificationConfig`.

## What data it needs

A directed exposure matrix (asymmetric). The module ships **no** real
interbank exposure data; the loader expects user-supplied parquet/CSV
in shape `(N, N)` where `exposures[i, j]` is *i*'s exposure to *j*.

| Source | Status | Notes |
|--------|--------|-------|
| Laeven & Valencia 2018 (IMF WP/18/206) | inline | systemic banking crisis dates |
| post-LV2020 designations (USA-2023, CHE-2023) | inline | flagged `source="post_LV2020"` |
| e-MID Italian interbank (2009-2015) | external | feed `from_exposure_matrix` |
| BIS Locational Banking Statistics | external | quarterly, sensitivity-only |
| ECB MMSR | external | granular intraday |

## What it claims

`C-SYSRISK-PHASE` (`HYPOTHESIS` tier). Promotion to `MEASURED`
requires:

1. ≥ 2 valid crisis windows from available real exposure datasets
   (e-MID 2009-2015 ⇒ Eurozone 2011 + SVB-tail proxy; BIS LBS
   aggregated quarterly; ECB MMSR granular but access-constrained).
   The exact crisis labels admissible per dataset are documented in
   `LIMITATIONS.md`; e-MID does not cover Lehman 2008 (out-of-window).
2. The bootstrap CI lower bound clears 0.70 with Bonferroni-adjusted
   p ≤ 0.01 on each surviving crisis.
3. No crisis returns `HARD_FAIL` (CI crossing 0.5 or AUC ≤ 0.55).
4. Each surviving crisis additionally clears all six null baselines
   in `null_models.py` (per `PROTOCOL.md` § 4).

## Minimal example

```python
from datetime import date
import numpy as np

from research.systemic_risk import (
    DEFAULT_LEDGER,
    FalsificationConfig,
    coupling_from_exposures,
    fit_barabasi_albert_from_topology,
    from_exposure_matrix,
    run_falsification,
)

# 1. Build a directed topology from a real exposure matrix.
exposures: np.ndarray = ...  # (N, N) directed, non-negative
labels = tuple(f"bank_{i}" for i in range(exposures.shape[0]))
topo = from_exposure_matrix(exposures, labels, snapshot_date=date(2011, 6, 30))

# 2. Calibrate the BA null to the empirical degree distribution.
#    Use `_from_topology` — passing `topo.degree` directly (in + out)
#    doubles the recovered m on symmetric graphs.
m_hat, fit = fit_barabasi_albert_from_topology(topo, n_bootstrap=1000)
print(f"BA m={m_hat}, α={fit.alpha:.3f} ± {fit.alpha_se:.3f}, KS p={fit.ks_p_value:.3f}")

# 3. Build the asymmetric coupling matrix K_ij.
K = coupling_from_exposures(exposures, normalisation="row_stochastic")

# 4. Run the pre-registered falsification battery.
score: np.ndarray = ...           # (T,) early-warning score over time
dates: tuple[date, ...] = ...     # length T, monotonically increasing
report = run_falsification(score, dates, DEFAULT_LEDGER, country_filter="USA")

print(f"verdict: {report.verdict}")
for o in report.outcomes:
    print(f"{o.label}: AUC={o.auc:.3f} [{o.auc_ci_low:.3f}, {o.auc_ci_high:.3f}], p_BONF={o.p_bonferroni:.4f}")
```

## What changed in v2

- **Asymmetric directed coupling.** v1 auto-symmetrised; real interbank
  exposures are not symmetric (Bardoscia et al. 2021, *Nat. Rev. Phys.*
  3: 490). `from_exposure_matrix(..., directed=True)` is now the
  default; `directed=False` reserved for null baselines.
- **MLE-fitted BA null.** v1 hard-coded `m=3`; v2 fits the power-law
  exponent and BA `m` from the empirical degree sequence with a KS
  goodness-of-fit p-value and AIC vs an exponential alternative
  (Clauset, Shalizi, Newman 2009, *SIAM Rev.* 51: 661).
- **Bootstrap CI on AUC.** v1 reported only the point estimate; v2
  adds a stratified percentile-bootstrap CI (n=10000) and uses
  `auc_ci_low` for the pass/fail thresholds — the whole CI must
  clear the bar.
- **Bonferroni FWER, not BH FDR.** v2 uses strict family-wise control
  given the small crisis count and the cost of a false MEASURED
  promotion.
- **Optional snapshot date** for temporal pipelines (e-MID quarterly,
  BIS LBS).
- **ω from balance-sheet vol** via `omega_from_volatility` (first-order;
  full inverse problem in `core.kuramoto.natural_frequency`).

## Maintenance-hierarchy role

Sustainer (Layer 2). Emits a diagnostic score; never takes execution
action. A future `HARD_PASS` would only motivate promotion to a
Protector role downstream.

## References

- Bardoscia, M. et al. (2021). *Physics of Financial Networks*.
  *Nature Reviews Physics* **3**: 490 — canonical survey.
- Acemoglu, D., Ozdaglar, A., Tahbaz-Salehi, A. (2015). *Systemic
  Risk and Stability in Financial Networks*. *Am. Econ. Rev.*
  **105**: 564 — phase-transition argument for interbank networks.
- Arenas, A. et al. (2008). *Synchronization in Complex Networks*.
  *Physics Reports* **469**: 93 — Kuramoto on graphs.
- Boss, M. et al. (2004). *Network topology of the interbank market*.
  *Quantitative Finance* **4**: 677.
- Clauset, A., Shalizi, C. R., Newman, M. E. J. (2009).
  *Power-law distributions in empirical data*. *SIAM Review* **51**: 661.
- Laeven, L., Valencia, F. (2018). *Systemic Banking Crises Revisited*.
  IMF Working Paper WP/18/206.
- Scheffer, M. et al. (2009). *Early-warning signals for critical
  transitions*. *Nature* **461**: 53.
- Soramäki, K. et al. (2007). *The topology of interbank payment flows*.
  *Physica A* **379**: 317.
