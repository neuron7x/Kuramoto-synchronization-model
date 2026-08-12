"""Math + invariant tests for the L2 fail-fast gate.

Covers:
    * OFI + QI algebra on deterministic fixtures.
    * cross_sectional_ricci_signal returns finite κ_min on non-degenerate input.
    * run_killtest emits KILL on pure-noise substrate (null).
    * run_killtest emits PROCEED on substrate with injected cross-sectional edge.
    * Determinism: identical input + seed → identical verdict.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.microstructure.killtest import (
    FeatureFrame,
    _compute_ofi,
    _compute_queue_imbalance,
    _iaaft_pvalue,
    _pooled_ic,
    _to_grid,
    cross_sectional_ricci_signal,
    run_killtest,
    run_killtest_split,
    slice_features,
    split_verdict_to_json,
    verdict_to_json,
)


def test_to_grid_aligns_offset_timestamps() -> None:
    """Regression for the _to_grid millisecond-offset alignment bug.

    `resample("1s").last()` buckets events into round-second bins; the target
    grid must share that offset (floor-to-second), otherwise reindex yields
    all-NaN and ffill cannot recover.
    """
    start_ms = 1_700_000_000_197  # .197s offset — classic mid-second event time
    ts = np.arange(start_ms, start_ms + 30_000, 500, dtype=np.int64)
    df = pd.DataFrame(
        {
            "ts_event": ts,
            "bid_px_1": np.full(len(ts), 100.0),
            "ask_px_1": np.full(len(ts), 100.01),
            "bid_sz_1": np.full(len(ts), 1.0),
            "ask_sz_1": np.full(len(ts), 1.0),
        }
    )
    grid = _to_grid(df, int(ts[0]), int(ts[-1]))
    assert (
        int(np.isfinite(grid["bid_px_1"]).sum()) > 0
    ), "regression: _to_grid must produce finite rows when ts_event has sub-second offset"


def _deterministic_features(n_rows: int, n_sym: int, seed: int) -> FeatureFrame:
    rng = np.random.default_rng(seed)
    timestamps_ms = np.arange(n_rows, dtype=np.int64) * 1000
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    ofi = rng.normal(0.0, 1.0, size=(n_rows, n_sym))
    qi = rng.uniform(-1.0, 1.0, size=(n_rows, n_sym))
    for k in range(n_sym):
        mid[:, k] = 100.0 + (k + 1) + rng.normal(0.0, 0.03, size=n_rows).cumsum()
    return FeatureFrame(
        timestamps_ms=timestamps_ms,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=ofi,
        queue_imbalance=qi,
    )


def test_slice_features_boundary_invariants() -> None:
    features = _deterministic_features(1500, 5, seed=42)
    left = slice_features(features, 0, 750)
    right = slice_features(features, 750, 1500)
    assert left.n_rows == 750
    assert right.n_rows == 750
    assert left.n_symbols == right.n_symbols == 5
    assert left.symbols == right.symbols == features.symbols
    assert np.array_equal(left.mid[0], features.mid[0])
    assert np.array_equal(right.mid[-1], features.mid[-1])


def test_slice_features_rejects_invalid_bounds() -> None:
    features = _deterministic_features(100, 5, seed=42)
    for start, end in [(-1, 10), (0, 101), (50, 50), (80, 40)]:
        try:
            slice_features(features, start, end)
        except ValueError:
            continue
        raise AssertionError(f"slice_features must reject ({start}, {end})")


def test_run_killtest_split_emits_both_verdicts() -> None:
    features = _deterministic_features(1500, 6, seed=42)
    split = run_killtest_split(features, split_at_fraction=0.5)
    assert split.train.n_samples > 0
    assert split.test.n_samples > 0
    assert split.train.n_samples + split.test.n_samples == features.n_rows
    assert split.verdict in {"PROCEED", "KILL"}
    assert split.split_at_fraction == 0.5


def test_run_killtest_split_json_deterministic() -> None:
    features = _deterministic_features(1500, 6, seed=42)
    a = run_killtest_split(features, split_at_fraction=0.5)
    b = run_killtest_split(features, split_at_fraction=0.5)
    assert split_verdict_to_json(a) == split_verdict_to_json(b)


def test_run_killtest_split_rejects_bad_fraction() -> None:
    features = _deterministic_features(1500, 6, seed=42)
    for bad in [0.0, 0.05, 0.95, 1.0, -0.1, 1.5]:
        try:
            run_killtest_split(features, split_at_fraction=bad)
        except ValueError:
            continue
        raise AssertionError(f"run_killtest_split must reject fraction={bad}")


_SEED = 42


def _make_panel(n: int, mid_base: float, noise: float, rng: np.random.Generator) -> pd.DataFrame:
    steps = rng.normal(0.0, noise, size=n).cumsum()
    mid = mid_base + steps
    spread = 0.01
    bid = mid - spread / 2
    ask = mid + spread / 2
    df = pd.DataFrame(
        {
            "bid_px_1": bid,
            "ask_px_1": ask,
            "bid_sz_1": rng.uniform(1.0, 5.0, size=n),
            "ask_sz_1": rng.uniform(1.0, 5.0, size=n),
        }
    )
    return df


def test_queue_imbalance_bounds() -> None:
    rng = np.random.default_rng(_SEED)
    df = _make_panel(200, mid_base=100.0, noise=0.05, rng=rng)
    qi = _compute_queue_imbalance(df)
    assert qi.between(-1.0, 1.0).all()


def test_queue_imbalance_zero_sizes_safe() -> None:
    df = pd.DataFrame({"bid_px_1": [1.0], "ask_px_1": [1.0], "bid_sz_1": [0.0], "ask_sz_1": [0.0]})
    qi = _compute_queue_imbalance(df)
    assert qi.iloc[0] == 0.0


def test_ofi_zero_on_constant_book() -> None:
    df = pd.DataFrame(
        {
            "bid_px_1": [100.0] * 10,
            "ask_px_1": [100.01] * 10,
            "bid_sz_1": [2.0] * 10,
            "ask_sz_1": [3.0] * 10,
        }
    )
    ofi = _compute_ofi(df)
    assert np.allclose(ofi.to_numpy(), 0.0)


def test_cross_sectional_ricci_finite() -> None:
    rng = np.random.default_rng(_SEED)
    n, m = 1200, 5
    ofi_panel = rng.normal(0.0, 1.0, size=(n, m))
    kappa = cross_sectional_ricci_signal(ofi_panel, window=300, step=30, threshold=0.5)
    assert kappa.shape == (n,)
    assert np.isfinite(kappa[300:]).any()


def _build_features(
    n_rows: int, n_sym: int, noise_seed: int, mid_noise: float = 0.03
) -> FeatureFrame:
    rng = np.random.default_rng(noise_seed)
    timestamps_ms = np.arange(n_rows, dtype=np.int64) * 1000
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    ofi = rng.normal(0.0, 1.0, size=(n_rows, n_sym))
    qi = rng.uniform(-1.0, 1.0, size=(n_rows, n_sym))
    for k in range(n_sym):
        mid[:, k] = 100.0 + (k + 1) + rng.normal(0.0, mid_noise, size=n_rows).cumsum()
    return FeatureFrame(
        timestamps_ms=timestamps_ms,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=ofi,
        queue_imbalance=qi,
    )


def test_run_killtest_kills_noise_substrate() -> None:
    features = _build_features(n_rows=1500, n_sym=6, noise_seed=_SEED)
    verdict = run_killtest(features)
    assert verdict.verdict == "KILL"
    assert verdict.reasons, "KILL must carry at least one reason"
    assert verdict.n_samples == 1500
    assert verdict.n_symbols == 6


def test_run_killtest_verdict_deterministic() -> None:
    features = _build_features(n_rows=1500, n_sym=6, noise_seed=_SEED)
    v1 = run_killtest(features, seed=_SEED)
    v2 = run_killtest(features, seed=_SEED)
    assert verdict_to_json(v1) == verdict_to_json(v2)


def test_run_killtest_verdict_json_round_trip() -> None:
    features = _build_features(n_rows=1500, n_sym=6, noise_seed=_SEED)
    verdict = run_killtest(features)
    body = verdict_to_json(verdict)
    parsed = json.loads(body)
    assert parsed["verdict"] in ("KILL", "PROCEED")
    assert parsed["seed"] == _SEED
    assert parsed["n_symbols"] == features.n_symbols


def test_run_killtest_survives_injected_edge() -> None:
    """Substrate where OFI directly causes next-period mid moves.

    This is NOT a claim that Ricci actually captures the edge — it's a smoke
    test that the gate machinery produces a VERDICT object (not crashes) on
    substrate where genuine predictive structure exists. Pass criterion: the
    function returns a non-empty verdict with finite IC values.
    """
    rng = np.random.default_rng(_SEED + 7)
    n_rows, n_sym = 2000, 6
    ofi = rng.normal(0.0, 1.0, size=(n_rows, n_sym))
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    base = 100.0
    for k in range(n_sym):
        drift = 0.002 * ofi[:, k]
        mid[:, k] = base + (k + 1) + drift.cumsum()
    qi = rng.uniform(-1.0, 1.0, size=(n_rows, n_sym))
    timestamps_ms = np.arange(n_rows, dtype=np.int64) * 1000
    features = FeatureFrame(
        timestamps_ms=timestamps_ms,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=ofi,
        queue_imbalance=qi,
    )
    verdict = run_killtest(features)
    assert verdict.verdict in {"PROCEED", "KILL"}
    assert np.isfinite(verdict.ic_baselines["plain_ofi"])
    for h in (60, 120, 180, 240, 300):
        assert h in verdict.horizon_ic


# ---------------------------------------------------------------------------
# IAAFT linear-spectral null (advisory) — strengthens Day-4 falsification.
# ---------------------------------------------------------------------------


def _autocorrelated_signal(n: int, seed: int) -> np.ndarray:
    """A strongly autocorrelated 1-D series (random walk) — the regime an
    IAAFT null must preserve while destroying genuine target alignment."""
    rng = np.random.default_rng(seed)
    return np.asarray(rng.normal(0.0, 1.0, size=n).cumsum(), dtype=np.float64)


def test_iaaft_pvalue_bounded_probability() -> None:
    """p-value is always a valid probability, never degenerate to 0."""
    n, n_sym = 800, 4
    sig = _autocorrelated_signal(n, seed=1)
    target = np.repeat(sig[:, None], n_sym, axis=1)
    obs = _pooled_ic(np.repeat(sig[:, None], n_sym, axis=1), target)
    p = _iaaft_pvalue(sig, target, obs, n_sym, trials=60, iters=40, seed=7)
    assert 0.0 < p <= 1.0


def test_iaaft_null_has_power_on_real_edge() -> None:
    """Positive control: when the target IS the (autocorrelated) signal, the
    observed IC must survive the IAAFT null (small p). This proves the null
    does not trivially destroy a genuine edge — the precondition for ever
    promoting it to a gating null."""
    n, n_sym = 1000, 5
    sig = _autocorrelated_signal(n, seed=11)
    rng = np.random.default_rng(11)
    target = np.repeat(sig[:, None], n_sym, axis=1) + rng.normal(0.0, 0.01, size=(n, n_sym))
    obs = _pooled_ic(np.repeat(sig[:, None], n_sym, axis=1), target)
    p = _iaaft_pvalue(sig, target, obs, n_sym, trials=100, iters=60, seed=3)
    assert abs(obs) > 0.5, f"positive control IC too weak: {obs:.3f}"
    assert p < 0.05, f"IAAFT null blind to a real edge: p={p:.4f}"


def test_iaaft_null_not_significant_when_independent() -> None:
    """Negative control: an autocorrelated signal that is INDEPENDENT of the
    target must NOT survive the null more than a genuine edge does. Compared
    relatively (robust to single-draw stochasticity): independent-p strictly
    exceeds the positive-control-p from the matched-edge case."""
    n, n_sym = 1000, 5
    sig = _autocorrelated_signal(n, seed=21)
    indep_target = np.repeat(_autocorrelated_signal(n, seed=99)[:, None], n_sym, axis=1)
    obs_indep = _pooled_ic(np.repeat(sig[:, None], n_sym, axis=1), indep_target)
    p_indep = _iaaft_pvalue(sig, indep_target, obs_indep, n_sym, trials=100, iters=60, seed=5)

    matched_target = np.repeat(sig[:, None], n_sym, axis=1)
    obs_matched = _pooled_ic(matched_target, matched_target)
    p_matched = _iaaft_pvalue(sig, matched_target, obs_matched, n_sym, trials=100, iters=60, seed=5)
    assert p_indep > p_matched


def test_iaaft_pvalue_deterministic() -> None:
    """Same seed → identical p-value (INV-HPC1 reproducibility)."""
    n, n_sym = 600, 4
    sig = _autocorrelated_signal(n, seed=2)
    target = np.repeat(sig[:, None], n_sym, axis=1)
    obs = _pooled_ic(target, target)
    p1 = _iaaft_pvalue(sig, target, obs, n_sym, trials=50, iters=40, seed=13)
    p2 = _iaaft_pvalue(sig, target, obs, n_sym, trials=50, iters=40, seed=13)
    assert p1 == p2


def test_iaaft_pvalue_short_support_fails_closed() -> None:
    """Fewer than 50 finite samples → conservative p=1.0 (no false signal)."""
    sig = np.full(40, np.nan, dtype=np.float64)
    sig[:10] = np.arange(10, dtype=np.float64)
    target = np.repeat(sig[:, None], 3, axis=1)
    p = _iaaft_pvalue(sig, target, 0.5, 3, trials=20, iters=20, seed=0)
    assert p == 1.0


def test_run_killtest_reports_iaaft_null_without_changing_gate() -> None:
    """`iaaft` is reported in null_test_pvalues but is advisory: the binary
    verdict on a noise substrate stays KILL (driven by permutation_shuffle)."""
    features = _build_features(n_rows=1500, n_sym=6, noise_seed=_SEED)
    verdict = run_killtest(features)
    assert "iaaft" in verdict.null_test_pvalues
    assert 0.0 < verdict.null_test_pvalues["iaaft"] <= 1.0
    assert verdict.verdict == "KILL"
    # The advisory null is never one of the gate reasons.
    assert not any("iaaft" in r for r in verdict.reasons)


# ---------------------------------------------------------------------------
# CLI helpers (introduced in C1 of PR #238)
# ---------------------------------------------------------------------------

import importlib.util as _iu  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

import pytest as _pytest  # noqa: E402


def _load_cli_module() -> object:
    """Dynamic-import `scripts/run_l2_killtest.py` as a module object.

    The script lives at repo root / scripts / and uses a hyphenated filename
    that argparse hosts CLI-side; direct `from scripts.run_l2_killtest` works
    only because scripts/ is on sys.path in some configs. Importing by file
    path is robust.
    """
    repo_root = _Path(__file__).resolve().parents[1]
    path = repo_root / "scripts" / "run_l2_killtest.py"
    spec = _iu.spec_from_file_location("run_l2_killtest_cli", path)
    assert spec is not None and spec.loader is not None
    module = _iu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_cli_features(n_rows: int, n_sym: int, seed: int) -> FeatureFrame:
    rng = np.random.default_rng(seed)
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    for k in range(n_sym):
        mid[:, k] = 100.0 + (k + 1) + rng.normal(0.0, 0.03, size=n_rows).cumsum()
    return FeatureFrame(
        timestamps_ms=np.arange(n_rows, dtype=np.int64) * 1000,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=rng.normal(0.0, 1.0, size=(n_rows, n_sym)),
        queue_imbalance=rng.uniform(-1.0, 1.0, size=(n_rows, n_sym)),
    )


def test_cli_regime_score_dispatch_rv() -> None:
    """_regime_score('rv', ...) must equal rolling_rv_regime directly."""
    from research.microstructure.regime import rolling_rv_regime

    cli = _load_cli_module()
    features = _synthetic_cli_features(800, 5, seed=42)
    via_cli = cli._regime_score("rv", features, window_rows=200)  # type: ignore[attr-defined]
    via_fn = rolling_rv_regime(features, window_rows=200)
    # Element-wise equal where both finite, both NaN where neither finite
    mask = np.isfinite(via_cli) & np.isfinite(via_fn)
    assert mask.sum() > 0
    assert np.allclose(via_cli[mask], via_fn[mask])


def test_cli_regime_score_dispatch_corr() -> None:
    """_regime_score('corr', ...) must equal rolling_corr_regime directly."""
    from research.microstructure.regime import rolling_corr_regime

    cli = _load_cli_module()
    features = _synthetic_cli_features(800, 5, seed=42)
    via_cli = cli._regime_score("corr", features, window_rows=200)  # type: ignore[attr-defined]
    via_fn = rolling_corr_regime(features, window_rows=200)
    mask = np.isfinite(via_cli) & np.isfinite(via_fn)
    assert mask.sum() > 0
    assert np.allclose(via_cli[mask], via_fn[mask])


def test_cli_regime_score_rejects_unknown_name() -> None:
    cli = _load_cli_module()
    features = _synthetic_cli_features(400, 4, seed=0)
    with _pytest.raises(ValueError):
        cli._regime_score("bogus", features, window_rows=200)  # type: ignore[attr-defined]


def test_cli_train_threshold_mask_shape_and_dtype() -> None:
    """Mask must be bool dtype and match test.n_rows in length."""
    cli = _load_cli_module()
    features = _synthetic_cli_features(1600, 5, seed=42)
    mid = features.n_rows // 2
    train = slice_features(features, 0, mid)
    test = slice_features(features, mid, features.n_rows)
    mask = cli._train_threshold_mask(  # type: ignore[attr-defined]
        train, test, regime_name="rv", quantile=0.5, window_rows=200
    )
    assert mask.dtype == bool
    assert mask.shape == (test.n_rows,)


def test_cli_train_threshold_mask_monotone_in_quantile() -> None:
    """Higher quantile threshold keeps no more True cells than lower quantile."""
    cli = _load_cli_module()
    features = _synthetic_cli_features(1600, 5, seed=42)
    mid = features.n_rows // 2
    train = slice_features(features, 0, mid)
    test = slice_features(features, mid, features.n_rows)
    mask_q25 = cli._train_threshold_mask(  # type: ignore[attr-defined]
        train, test, regime_name="rv", quantile=0.25, window_rows=200
    )
    mask_q75 = cli._train_threshold_mask(  # type: ignore[attr-defined]
        train, test, regime_name="rv", quantile=0.75, window_rows=200
    )
    assert int(mask_q75.sum()) <= int(mask_q25.sum())


def test_cli_train_threshold_mask_rejects_all_nan_train() -> None:
    """If train regime score is all-NaN, CLI raises ValueError explicitly."""
    cli = _load_cli_module()
    n_rows, n_sym = 100, 4  # below rolling_rv_regime._MIN_WINDOW_ROWS=60... so use window > n_rows
    features = _synthetic_cli_features(n_rows, n_sym, seed=0)
    train = slice_features(features, 0, 50)
    test = slice_features(features, 50, 100)
    # window_rows exceeds train.n_rows → rolling_rv_regime yields all-NaN → CLI rejects
    with _pytest.raises(ValueError):
        cli._train_threshold_mask(  # type: ignore[attr-defined]
            train, test, regime_name="rv", quantile=0.5, window_rows=60
        )
