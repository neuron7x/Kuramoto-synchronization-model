# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Out-of-sample validation for the NetworkKuramotoEngine (protocol M3.3).

Implements the methodology's level-D acceptance tests:

- **Temporal split.** 60/20/20 train/validation/test without shuffling
  (we are working with time series and any in-sample leakage would
  inflate the numbers).
- **Forward simulation on held-out windows.** Given an identified
  :class:`NetworkState` from the training window we forward-simulate
  the Sakaguchi–Kuramoto model on the val/test windows using the
  observed initial phase as the initial condition, and compare the
  predicted trajectory to the observed one at both the phase level
  (circular MAE) and the coherence level (correlation of ``R(t)``).
- **Strict model superiority via Diebold–Mariano and Hansen SPA.**
  The engine is compared against a suite of baselines — random walk,
  historical mean, AR(1) — and must beat each one individually
  (Diebold–Mariano with Bonferroni correction) and jointly
  (stationary-bootstrap SPA). Passing **both** tests is a hard
  release gate in the methodology.
- **Walk-forward evaluation.** Roll the split forward several times
  so the reported errors are not conditioned on a single train/test
  split.

All statistics are implemented in pure numpy/scipy. The SPA test
uses a simple circular-block bootstrap which preserves short-range
autocorrelation without requiring :mod:`arch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

from .contracts import NetworkState, PhaseMatrix
from .metrics import order_parameter
from .network_engine import NetworkKuramotoEngine

__all__ = [
    "OOSConfig",
    "OOSResult",
    "temporal_split",
    "simulate_forward",
    "circular_mae",
    "diebold_mariano_test",
    "spa_test",
    "evaluate_oos",
    "walk_forward_evaluate",
]


# ---------------------------------------------------------------------------
# Configuration / result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OOSConfig:
    """Hyperparameters for out-of-sample evaluation.

    Attributes
    ----------
    train_frac, val_frac : float
        Fractions of the trajectory assigned to the training and
        validation windows. The test window takes the remainder.
    horizon : int
        One-step prediction horizon used by :func:`simulate_forward`.
        A horizon of ``1`` is the standard Diebold–Mariano setup.
    n_bootstrap : int
        Bootstrap iterations for the SPA test.
    block_length : int
        Circular-block length for the stationary bootstrap.
    random_state : int
        Seed for deterministic bootstrap sampling.
    """

    train_frac: float = 0.6
    val_frac: float = 0.2
    horizon: int = 1
    n_bootstrap: int = 500
    block_length: int = 20
    random_state: int = 0
    embargo: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.train_frac < 1:
            raise ValueError("train_frac must lie in (0, 1)")
        if not 0 < self.val_frac < 1:
            raise ValueError("val_frac must lie in (0, 1)")
        if self.train_frac + self.val_frac >= 1.0:
            raise ValueError("train_frac + val_frac must be < 1.0")
        if self.horizon < 1:
            raise ValueError("horizon must be ≥ 1")
        if self.n_bootstrap < 1:
            raise ValueError("n_bootstrap must be ≥ 1")
        if self.block_length < 1:
            raise ValueError("block_length must be ≥ 1")
        if self.embargo < 0:
            raise ValueError("embargo must be ≥ 0")
        # Leakage gate: a multi-step (overlapping-label) horizon must purge at
        # least ``horizon - 1`` boundary observations between train and test, or
        # the last training label overlaps the first test label and the OOS
        # error is optimistically biased. At horizon == 1 the default embargo of
        # 0 is admissible. This turns a silently-leaky multi-step OOS into an
        # un-runnable one.
        if self.embargo < self.horizon - 1:
            raise ValueError(
                f"embargo ({self.embargo}) must be ≥ horizon - 1 ({self.horizon - 1}) "
                "to purge overlapping-label train/test leakage"
            )


@dataclass(frozen=True, slots=True)
class SplitProvenance:
    """How the train/val/test split was formed — serialized with every result.

    Makes an OOS result self-auditable for leakage protection: a reader can see
    the horizon, the embargo purge, the exact spans, the split method and the
    total length without re-running. ``train_span`` etc. are ``[start, stop)``.
    """

    split_method: str
    horizon: int
    embargo: int
    n_total: int
    train_span: tuple[int, int]
    val_span: tuple[int, int]
    test_span: tuple[int, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_method": self.split_method,
            "horizon": self.horizon,
            "embargo": self.embargo,
            "n_total": self.n_total,
            "train_span": list(self.train_span),
            "val_span": list(self.val_span),
            "test_span": list(self.test_span),
        }


@dataclass(frozen=True, slots=True)
class OOSResult:
    """Aggregate OOS statistics for one train/val/test split."""

    phase_mae_val: float
    phase_mae_test: float
    R_correlation_val: float
    R_correlation_test: float
    dm_p_values: dict[str, float]
    spa_p_value: float
    passed_level_D: bool
    split_provenance: SplitProvenance


# ---------------------------------------------------------------------------
# Temporal split & forward simulation
# ---------------------------------------------------------------------------


def temporal_split(
    phases: PhaseMatrix, *, train_frac: float, val_frac: float, embargo: int = 0
) -> tuple[slice, slice, slice]:
    """Return non-shuffling ``slice`` objects for train / val / test.

    ``embargo`` purged observations are dropped at each boundary (after train,
    after val) so an overlapping-label or autocorrelated trajectory cannot leak
    the last training point into the first test point. ``embargo == 0`` (the
    default, admissible only at horizon 1) reproduces the contiguous split.
    """
    T = phases.theta.shape[0]
    t_train = int(train_frac * T)
    t_val = int((train_frac + val_frac) * T)
    return (
        slice(0, t_train),
        slice(min(t_train + embargo, t_val), t_val),
        slice(min(t_val + embargo, T), T),
    )


def simulate_forward(
    state: NetworkState,
    initial_phase: np.ndarray,
    n_steps: int,
    dt: float,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Forward-simulate the identified SDDE for ``n_steps``.

    The simulator is the same Euler–Maruyama scheme used by the
    synthetic generator (:mod:`core.kuramoto.synthetic`). It is
    deterministic once ``rng`` is fixed. For purely drift-based
    point forecasts set ``state.noise_std = 0`` in the caller; we
    honour whatever value the state carries.
    """
    rng = rng or np.random.default_rng(0)
    K = np.asarray(state.coupling.K, dtype=np.float64)
    tau = np.asarray(state.delays.tau, dtype=np.int64)
    alpha = np.asarray(state.frustration.alpha, dtype=np.float64)
    omega = np.asarray(state.natural_frequencies, dtype=np.float64)
    sigma = float(state.noise_std)
    N = K.shape[0]
    max_tau = int(tau.max()) if tau.size else 0
    # History buffer: pad with initial_phase for t < 0
    history = np.broadcast_to(initial_phase, (max_tau + 1, N)).copy()
    theta = np.zeros((n_steps, N), dtype=np.float64)
    theta[0] = initial_phase
    active = K != 0.0
    sqrt_dt = float(np.sqrt(dt))
    col_idx = np.broadcast_to(np.arange(N)[np.newaxis, :], (N, N))
    for t in range(1, n_steps):
        # Delayed lookup: for the current step we need θ_j(t-1-τ_ij).
        # Build a joint buffer of history (pre-0) + simulated phases.
        combined = np.concatenate([history, theta[:t]], axis=0)
        t_idx = combined.shape[0] - 1  # index of theta[t-1]
        t_del = np.clip(
            t_idx - tau, 0, t_idx
        )  # bounds: delay index clamped to valid combined-buffer range
        theta_d = combined[t_del, col_idx]
        phase_diff = theta_d - theta[t - 1][:, np.newaxis] - alpha
        coupling = np.sum(np.where(active, K * np.sin(phase_diff), 0.0), axis=1)
        noise = sigma * rng.standard_normal(N) * sqrt_dt
        theta[t] = theta[t - 1] + dt * (omega + coupling) + noise
    return np.mod(theta, 2 * np.pi)


# ---------------------------------------------------------------------------
# Error metrics
# ---------------------------------------------------------------------------


def circular_mae(theta_pred: np.ndarray, theta_obs: np.ndarray) -> float:
    """Mean absolute circular distance between two phase matrices."""
    diff = np.angle(np.exp(1j * (theta_pred - theta_obs)))
    return float(np.mean(np.abs(diff)))


# ---------------------------------------------------------------------------
# Diebold–Mariano test
# ---------------------------------------------------------------------------


def diebold_mariano_test(
    errors_model: np.ndarray,
    errors_baseline: np.ndarray,
    h: int = 1,
) -> tuple[float, float]:
    """Diebold–Mariano test for equal predictive accuracy.

    ``H0``: model and baseline have identical squared-error loss.
    ``H1``: model has strictly lower loss. The test is one-sided:
    a small returned p-value indicates the model is superior.

    The variance of the loss differential is estimated with a
    Newey-West HAC kernel with bandwidth ``h - 1``, which removes
    the bias introduced by overlapping multi-step forecasts. For
    the one-step case the kernel reduces to the plain sample
    variance.
    """
    if errors_model.shape != errors_baseline.shape:
        raise ValueError("error series must have identical shape")
    d = errors_baseline**2 - errors_model**2
    n = d.shape[0]
    if n < 2:
        return 0.0, 1.0
    d_bar = float(np.mean(d))
    gamma_0 = float(np.var(d, ddof=0))
    gamma_sum = 0.0
    for k in range(1, min(h, n)):
        cov = float(np.cov(d[k:], d[:-k], ddof=0)[0, 1])
        gamma_sum += 2.0 * cov
    var_d = (gamma_0 + gamma_sum) / n
    if var_d <= 0:
        return 0.0, 1.0
    dm = d_bar / float(np.sqrt(var_d))
    # One-sided test: model superior ⇔ d_bar > 0 ⇔ DM > 0
    p_value = float(1.0 - stats.norm.cdf(dm))
    return float(dm), p_value


# ---------------------------------------------------------------------------
# Hansen SPA test via stationary bootstrap
# ---------------------------------------------------------------------------


def _stationary_bootstrap_indices(
    n: int, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    """Draw ``n`` indices from a stationary (random-length) block bootstrap.

    Each new index is with probability ``1 / block_length`` a fresh
    uniform draw and otherwise the predecessor plus one (mod ``n``).
    This preserves short-range autocorrelation without needing a
    fixed block boundary, and is the standard non-parametric
    resampler used by the arch package's SPA implementation.
    """
    p = 1.0 / block_length
    idx = np.empty(n, dtype=np.int64)
    idx[0] = int(rng.integers(0, n))
    for t in range(1, n):
        if rng.random() < p:
            idx[t] = int(rng.integers(0, n))
        else:
            idx[t] = (idx[t - 1] + 1) % n
    return idx


def spa_test(
    errors_model: np.ndarray,
    errors_baselines: dict[str, np.ndarray],
    *,
    n_bootstrap: int = 500,
    block_length: int = 20,
    random_state: int = 0,
) -> float:
    """Hansen (2005) Superior Predictive Ability test.

    Tests ``H0``: the model is no better than the best of the
    baseline set (there exists a benchmark whose expected loss is
    less than or equal to the model's). The returned p-value is the
    fraction of bootstrap replications in which the maximum
    standardised loss differential exceeds the observed statistic.
    A small p-value rejects ``H0``, i.e. the model *is* the best.

    ``errors_model`` and every entry of ``errors_baselines`` must
    have the same length. The stationary bootstrap preserves
    short-range autocorrelation in the loss differential.
    """
    names = list(errors_baselines.keys())
    n = errors_model.shape[0]
    if not names:
        raise ValueError("at least one baseline is required")
    L_model = errors_model**2
    L_bases = np.stack([errors_baselines[k] ** 2 for k in names], axis=0)  # (K, n)
    D = L_bases - L_model[np.newaxis, :]  # (K, n), positive = model better
    d_bar = D.mean(axis=1)  # (K,)

    rng = np.random.default_rng(random_state)
    sigmas = np.std(D, axis=1, ddof=0)
    sigmas = np.where(sigmas > 1e-12, sigmas, 1.0)
    studentised = np.sqrt(n) * d_bar / sigmas
    observed = float(np.max(studentised))

    null_stat = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        idx = _stationary_bootstrap_indices(n, block_length, rng)
        D_star = D[:, idx] - d_bar[:, np.newaxis]  # recentre
        d_star = D_star.mean(axis=1)
        sigma_star = np.std(D_star, axis=1, ddof=0)
        sigma_star = np.where(sigma_star > 1e-12, sigma_star, 1.0)
        null_stat[b] = float(np.max(np.sqrt(n) * d_star / sigma_star))
    p_value = float(np.mean(null_stat >= observed))
    return p_value


# ---------------------------------------------------------------------------
# End-to-end OOS evaluation
# ---------------------------------------------------------------------------


def evaluate_oos(
    phases: PhaseMatrix,
    engine: NetworkKuramotoEngine,
    *,
    config: OOSConfig | None = None,
) -> OOSResult:
    """Run the full level-D acceptance pipeline on a single split."""
    cfg = config or OOSConfig()
    theta = np.asarray(phases.theta, dtype=np.float64)
    ts = np.asarray(phases.timestamps, dtype=np.float64)
    dt = float(ts[1] - ts[0])

    train_s, val_s, test_s = temporal_split(
        phases, train_frac=cfg.train_frac, val_frac=cfg.val_frac, embargo=cfg.embargo
    )

    # Fail closed: an embargo (or fraction) that empties any split would otherwise
    # crash on ``theta[test_s][0]`` or yield a meaningless 0/1-row OOS metric. A
    # claim must not be produced from a degenerate split.
    n_total = theta.shape[0]
    spans = {"train": train_s, "val": val_s, "test": test_s}
    too_small = {name: s.stop - s.start for name, s in spans.items() if s.stop - s.start < 2}
    if too_small:
        raise ValueError(
            f"degenerate split: {too_small} has < 2 rows after embargo={cfg.embargo} "
            f"on n_total={n_total}; widen the series or reduce embargo/horizon"
        )

    provenance = SplitProvenance(
        split_method="temporal_embargo",
        horizon=cfg.horizon,
        embargo=cfg.embargo,
        n_total=n_total,
        train_span=(train_s.start, train_s.stop),
        val_span=(val_s.start, val_s.stop),
        test_span=(test_s.start, test_s.stop),
    )

    phases_train = PhaseMatrix(
        theta=theta[train_s],
        timestamps=ts[train_s],
        asset_ids=phases.asset_ids,
        extraction_method=phases.extraction_method,
        frequency_band=phases.frequency_band,
    )
    report = engine.identify(phases_train)
    state = report.state

    # Forward simulation on val/test
    rng = np.random.default_rng(cfg.random_state)
    val_theta_obs = theta[val_s]
    test_theta_obs = theta[test_s]
    val_theta_pred = simulate_forward(
        state, val_theta_obs[0], n_steps=val_theta_obs.shape[0], dt=dt, rng=rng
    )
    test_theta_pred = simulate_forward(
        state, test_theta_obs[0], n_steps=test_theta_obs.shape[0], dt=dt, rng=rng
    )

    phase_mae_val = circular_mae(val_theta_pred, val_theta_obs)
    phase_mae_test = circular_mae(test_theta_pred, test_theta_obs)

    R_val_obs = order_parameter(val_theta_obs)
    R_val_pred = order_parameter(val_theta_pred)
    R_test_obs = order_parameter(test_theta_obs)
    R_test_pred = order_parameter(test_theta_pred)
    R_corr_val = float(np.corrcoef(R_val_pred, R_val_obs)[0, 1] if R_val_obs.size > 1 else 0.0)
    R_corr_test = float(np.corrcoef(R_test_pred, R_test_obs)[0, 1] if R_test_obs.size > 1 else 0.0)

    # Baselines against which DM/SPA are computed on R(t) residuals
    model_errs = R_test_pred - R_test_obs

    rw = np.concatenate([[R_test_obs[0]], R_test_obs[:-1]])
    hist_mean = np.full_like(R_test_obs, float(R_val_obs.mean()))
    ar1_errs = _ar1_forecast_errors(R_val_obs, R_test_obs)
    baselines: dict[str, np.ndarray] = {
        "random_walk": rw - R_test_obs,
        "historical_mean": hist_mean - R_test_obs,
        "ar1": ar1_errs,
    }

    dm_p: dict[str, float] = {}
    for name, base_err in baselines.items():
        _, p = diebold_mariano_test(model_errs, base_err, h=cfg.horizon)
        dm_p[name] = p
    bonferroni = 0.05 / len(baselines)

    spa_p = spa_test(
        model_errs,
        baselines,
        n_bootstrap=cfg.n_bootstrap,
        block_length=cfg.block_length,
        random_state=cfg.random_state,
    )

    passed = (
        R_corr_test > 0.0
        and phase_mae_test < np.pi / 2
        and all(p < bonferroni for p in dm_p.values())
        and spa_p < 0.05
    )

    return OOSResult(
        phase_mae_val=phase_mae_val,
        phase_mae_test=phase_mae_test,
        R_correlation_val=R_corr_val,
        R_correlation_test=R_corr_test,
        dm_p_values=dm_p,
        spa_p_value=spa_p,
        passed_level_D=bool(passed),
        split_provenance=provenance,
    )


def _ar1_forecast_errors(train_series: np.ndarray, test_series: np.ndarray) -> np.ndarray:
    """Fit AR(1) on ``train_series`` and forecast errors on ``test_series``."""
    if train_series.size < 2:
        return np.zeros_like(test_series)
    y = train_series[1:]
    x = train_series[:-1]
    denom = float(np.dot(x - x.mean(), x - x.mean()))
    if denom < 1e-12:
        phi = 0.0
        c = float(train_series.mean())
    else:
        phi = float(np.dot(x - x.mean(), y - y.mean()) / denom)
        c = float(y.mean() - phi * x.mean())
    preds = np.empty_like(test_series)
    prev = float(train_series[-1])
    for i in range(test_series.shape[0]):
        preds[i] = c + phi * prev
        prev = float(test_series[i])
    return np.asarray(preds - test_series, dtype=np.float64)


# ---------------------------------------------------------------------------
# Walk-forward wrapper
# ---------------------------------------------------------------------------


def walk_forward_evaluate(
    phases: PhaseMatrix,
    engine: NetworkKuramotoEngine,
    *,
    n_folds: int = 3,
    config: OOSConfig | None = None,
) -> list[OOSResult]:
    """Evaluate the engine on ``n_folds`` non-overlapping train/test splits.

    The trajectory is chopped into ``n_folds`` equal-length segments
    and :func:`evaluate_oos` is called on each one. Returning a list
    (rather than a single averaged result) lets the caller inspect
    per-fold variance — the methodology requires passing on at least
    3 non-overlapping periods.
    """
    cfg = config or OOSConfig()
    T = phases.theta.shape[0]
    fold_size = T // n_folds
    results: list[OOSResult] = []
    theta = np.asarray(phases.theta, dtype=np.float64)
    ts = np.asarray(phases.timestamps, dtype=np.float64)
    for k in range(n_folds):
        start = k * fold_size
        stop = (k + 1) * fold_size
        sub = PhaseMatrix(
            theta=theta[start:stop],
            timestamps=ts[start:stop],
            asset_ids=phases.asset_ids,
            extraction_method=phases.extraction_method,
            frequency_band=phases.frequency_band,
        )
        results.append(evaluate_oos(sub, engine, config=cfg))
    return results
