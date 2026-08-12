# Calibration Guide

Hyperparameters that matter, why, and how to tune them.

## Phase extraction (:class:`PhaseExtractionConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``f_low``, ``f_high`` | ``(0.05, 0.2)`` cycles/day | Passband for the Butterworth filter | Set the band wide enough to include the oscillation you care about but narrow enough to reject trend (low) and microstructure noise (high). |
| ``filter_order`` | 4 | Butterworth steepness | 4 with ``filtfilt`` ≈ effective order 8, zero-phase. Raise carefully — ``filtfilt`` padlen grows with order. |
| ``detrend_window`` | 250 | Rolling-mean detrend window | Matches ≈ 1 trading year. Set to ``None`` on synthetic stationary signals. |
| ``min_amplitude_ratio`` | 0.1 | Q1 gate: ``A/median`` below which a sample is unreliable | Raise to 0.2 on low-S/N data to discard more samples. |

## Coupling estimator (:class:`CouplingEstimationConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``penalty`` | ``"mcp"`` | MCP is unbiased for large coefficients and zeros out noise more aggressively than Lasso | Use ``lasso`` only as a baseline reference. |
| ``lambda_reg`` | ``0.01`` (static) / ``0.1`` (production) | Shrinks β toward zero | **Critical.** Sweep via ``lambda_grid`` inside ``complementary_pairs_stability``. Production default lambda ≈ 0.1 with ``standardize=True`` gives TPR > 0.9 / FPR < 0.1 on synthetic recovery tests. |
| ``gamma`` | 3.0 | MCP concavity | Rarely changed; ``γ > 1/L`` required for the prox to be contractive (automatically satisfied in practice). |
| ``stability_selection`` | ``False`` | Toggle complementary-pairs selection | Enable for production fits. Set ``n_subsamples`` ≥ 40 and ``stability_threshold`` 0.6. |
| ``lambda_grid`` | ``None`` → ``logspace(-3,-1,10)`` | Grid for stability selection | Use 10 log-spaced points spanning 1–2 orders of magnitude around the static optimum. |

## Delay estimator (:class:`DelayEstimationConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``max_lag`` | 10 | Largest integer lag tested | Bound by the maximum physically plausible propagation delay. For daily data 3–5 days is typical. |
| ``method`` | ``"joint"`` | Joint per-row coordinate descent; switches to exhaustive enumeration for small rows | Keep default. ``"cross_correlation"`` is a cheap single-edge fallback. |
| ``n_passes`` | 3 | Coordinate descent cycles | 2 passes usually suffice; 3 is a safety margin. |

**Identifiability warning.** With strong coupling the network
synchronises, ``sin(θ_j − θ_i)`` collapses, and lag estimation
becomes ill-posed. If your estimates are noisy, check whether the
observed trajectory is phase-locked — if so, no amount of tuning
will help. Weak coupling + large ``Δω`` is the identifiable
regime.

## Frustration estimator (:class:`FrustrationEstimationConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``subtract_other_edges`` | ``True`` | Two-pass residual subtraction over the rest of the row | Keep on. Turning it off only makes sense for single-edge diagnostic tests. |

## Dynamic graph (:class:`DynamicGraphConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``window`` | 150 | Sliding window in timesteps | ≥ 60 required for the MCP solver; at 150 it resolves 2–3 complete cycles at the default passband. |
| ``step`` | 15 | Stride | Finer resolution = more fits. ``step = window // 10`` is a sensible default. |

## OOS validation (:class:`OOSConfig`)

| Parameter | Default | Effect | Tuning |
|---|---|---|---|
| ``train_frac``, ``val_frac`` | 0.6, 0.2 | 60/20/20 split | Do not change unless you are running walk-forward with fewer folds. |
| ``n_bootstrap`` | 500 | SPA replications | 500 is adequate; raise to 2000 for publication-quality reports. |
| ``block_length`` | 20 | Stationary-bootstrap block mean | Should match the autocorrelation horizon of the loss differential. 20 is appropriate for daily-bar residuals. |

## Checklist for a new instrument

1. Run :func:`extract_phases_hilbert` and inspect the Q1/Q2/Q3
   gates on :attr:`PhaseMatrix.quality_scores`. If any asset
   fails a gate, drop it or extend the buffer.
2. Fit a one-shot :class:`CouplingEstimator` and verify
   sparsity in the 70–95 % range.
3. If sparsity is out of range, sweep ``lambda_reg`` until it
   is.
4. Run :func:`complementary_pairs_stability` at the chosen
   ``lambda_grid``; retain edges with selection probability
   ≥ 0.6.
5. Feed the resulting :class:`NetworkState` to
   :func:`evaluate_oos` with default ``OOSConfig``.
6. If Hansen SPA rejects (p < 0.05) against all baselines,
   the model is release-ready.
