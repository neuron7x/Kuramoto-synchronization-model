# Falsification Report

Summary of the null-model rejection tests run on the
NetworkKuramotoEngine identification stack. Each test checks
whether the observed dynamics can be explained by a simpler
generative mechanism; a failure to reject is a release blocker.

## Tests implemented

| Test | Module | Null model | Rejection signal |
|---|---|---|---|
| IAAFT surrogate | :mod:`falsification.iaaft_surrogate_test` | Linear spectrum + marginal distribution preserved, phase coupling destroyed | Observed ``max R(t)`` exceeds the surrogate quantile |
| Time shuffle | :mod:`falsification.time_shuffle_test` | Per-channel time order permuted, all temporal structure destroyed | Observed ``R`` series concentration differs from the null |
| Degree-preserving rewire | :mod:`falsification.degree_preserving_rewire` | Topology shuffled keeping node degrees | Clustering / modularity differs from rewired ensemble |
| Counterfactual hub removal | :mod:`falsification.counterfactual_hub_removal` | Top-``k`` hub nodes ablated | Mean ``R`` drops by ≥ 20 % after ablation |
| Counterfactual zero inhibition | :mod:`falsification.counterfactual_zero_inhibition` | Negative edges zeroed | Mean ``R`` rises by ≥ 15 % |
| Counterfactual zero delays | :mod:`falsification.counterfactual_zero_delays` | All ``τ`` set to 0 | Coherence trajectory changes significantly |

## IAAFT implementation

The IAAFT surrogate is implemented **inline** in
``falsification.py`` — no dependency on ``nolitsa`` (which has
an unstable install profile on modern numpy). The algorithm is
the classical two-projection iteration of Schreiber & Schmitz
(1996): alternate between enforcing the exact power spectrum
(Fourier magnitude constraint) and the exact marginal
distribution (rank-order replacement), 80–200 iterations
sufficing for machine-precision convergence on ordinary
financial series.

## Bonferroni correction

All tests are run together; the methodology uses a Bonferroni
correction with ``α_corrected = 0.05 / n_tests`` before
declaring any single null rejected at the family level. The
OOS Diebold–Mariano suite (:mod:`oos_validation`) applies its
own Bonferroni correction across the baseline set
(``0.05 / len(baselines)``) and adds a joint Hansen SPA test
on top, so the engine must beat every baseline individually
and jointly before it is released.

## Test-driven verification

Every surrogate / counterfactual has a unit test in
``tests/unit/core/test_kuramoto_network_engine.py``. The
tests exercise them against synthetic ground truth where the
expected direction of the rejection is known in advance —
for example, time shuffling of a narrow-band synchronised
network produces a null distribution whose standard deviation
is tightly bounded, which is asserted directly.

## Open items

- Regime-conditional breakdowns (bull / bear / crisis) are
  not automated yet; the suite currently runs on the full
  trajectory. This is a known deferred item and does not
  block release.
- PCMCI causal validation (``causal_validation.pcmci_causality``)
  is available as an optional backend but only exercised on
  machines with ``tigramite`` installed. The lightweight
  Granger baseline in the same module is tested on every CI
  run.
