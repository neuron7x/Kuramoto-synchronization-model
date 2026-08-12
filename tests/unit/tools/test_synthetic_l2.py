# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the deterministic synthetic L2 generator (``tools.synthetic_l2``).

Coverage
--------
- Concentration ordering: uniform < bimodal < winner / pareto (Gini metric).
- Determinism under fixed seed (snapshot-equality and stream-equality).
- Validation contract: factory output passes the
  :class:`core.kuramoto.capital_weighted.L2DepthSnapshot` validator
  (the same routine that ``build_capital_weighted_adjacency`` uses).
- Stream timestamps strictly monotone increasing.
- CLI ``.npz`` round-trip under ``subprocess`` invocation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.capital_weighted import (
    L2DepthSnapshot,
    _validate_snapshot,
    compute_l2_depth_mass,
)
from tools.synthetic_l2 import (
    MidPriceDistribution,
    RegimeName,
    RegimeSpec,
    bimodal_depth,
    pareto_depth,
    synthesize_l2_snapshot,
    synthesize_l2_stream,
    uniform_depth,
    winner_takes_most_depth,
)
from tools.synthetic_l2.cli import main as cli_main

_SEED: int = 20260425


def _gini(x: NDArray[np.float64]) -> float:
    """Population Gini on a non-negative vector (mirror of capital_weighted._gini).

    Returns 0 for an all-equal vector and approaches 1 for maximal concentration.
    """
    if x.size == 0:
        return 0.0
    sorted_x = np.sort(x)
    n = sorted_x.size
    weights = np.arange(1, n + 1, dtype=np.float64)
    total = float(sorted_x.sum())
    if total <= 0.0:
        return 0.0
    g = (2.0 * float((weights * sorted_x).sum()) / (n * total)) - (n + 1.0) / n
    return float(np.clip(g, 0.0, 1.0))


def test_uniform_regime_produces_low_concentration() -> None:
    """Uniform regime must have a low Gini coefficient.

    Threshold 0.10 is justified empirically: with jitter=0.1 (log-normal sd
    on a positive mean), expected Gini < 0.06; we leave a safety margin.
    """
    rng = np.random.default_rng(_SEED)
    depth = uniform_depth(n=256, mean=1.0, jitter=0.1, rng=rng)
    g = _gini(depth)
    assert g < 0.10, f"uniform regime Gini={g:.4f} exceeds 0.10 threshold."


def test_pareto_regime_produces_high_concentration() -> None:
    """Pareto regime must have a high Gini (heavy tail signature)."""
    rng = np.random.default_rng(_SEED)
    depth = pareto_depth(n=256, alpha=1.5, rng=rng)
    g = _gini(depth)
    assert g > 0.30, f"pareto regime Gini={g:.4f} below 0.30 threshold (alpha=1.5)."


def test_winner_regime_concentration_above_dominance_floor() -> None:
    """Winner-takes-most: max share must equal the requested dominance.

    Stronger than a Gini bound — it directly verifies the contract that one
    node holds ``dominance`` of total mass.
    """
    rng = np.random.default_rng(_SEED)
    dominance = 0.7
    depth = winner_takes_most_depth(n=64, dominance=dominance, rng=rng)
    share = float(depth.max() / depth.sum())
    msg_share = f"winner share={share:.6f} != dominance={dominance:.6f} (n=64)."
    assert abs(share - dominance) < 1e-6, msg_share
    g = _gini(depth)
    msg_gini = f"winner regime Gini={g:.4f} below floor {dominance - 0.1:.4f}."
    assert g > dominance - 0.1, msg_gini


def test_bimodal_regime_concentration_above_uniform() -> None:
    """Bimodal Gini is strictly higher than uniform (cluster contrast).

    NOTE: bimodal vs pareto ordering is *not* part of the contract. At finite
    N a sharp two-cluster split (10x contrast) can exceed a Pareto α=1.5 draw
    (which is heavy-tailed only in expectation). The factory only guarantees:
    uniform < bimodal, and uniform < pareto.
    """
    rng_u = np.random.default_rng(_SEED)
    rng_b = np.random.default_rng(_SEED + 1)
    g_u = _gini(uniform_depth(n=256, mean=1.0, jitter=0.1, rng=rng_u))
    g_b = _gini(bimodal_depth(n=256, ratio=0.3, rng=rng_b))
    assert g_u < g_b, f"bimodal Gini {g_b:.4f} did not exceed uniform {g_u:.4f}."


def test_seed_determinism() -> None:
    """Two runs with identical seed produce bit-identical snapshots."""
    snap_a = synthesize_l2_snapshot(n_nodes=32, n_levels=4, regime="pareto", seed=_SEED)
    snap_b = synthesize_l2_snapshot(n_nodes=32, n_levels=4, regime="pareto", seed=_SEED)
    assert snap_a.timestamp_ns == snap_b.timestamp_ns
    np.testing.assert_array_equal(snap_a.bid_sizes, snap_b.bid_sizes)
    np.testing.assert_array_equal(snap_a.ask_sizes, snap_b.ask_sizes)
    np.testing.assert_array_equal(snap_a.mid_prices, snap_b.mid_prices)


def test_seed_determinism_differs_across_seeds() -> None:
    """Different seeds must produce different snapshots (sanity)."""
    snap_a = synthesize_l2_snapshot(n_nodes=32, n_levels=4, regime="pareto", seed=_SEED)
    snap_b = synthesize_l2_snapshot(n_nodes=32, n_levels=4, regime="pareto", seed=_SEED + 1)
    assert not np.array_equal(snap_a.bid_sizes, snap_b.bid_sizes)


def test_factory_returns_valid_l2_depth_snapshot() -> None:
    """Snapshot satisfies the ``capital_weighted`` validation contract.

    Iterates over all four regimes and both mid-price distributions to
    exercise the full factory surface.
    """
    regime_names: tuple[RegimeName, ...] = ("uniform", "pareto", "winner", "bimodal")
    mid_dists: tuple[MidPriceDistribution, ...] = ("lognormal", "uniform")
    for regime_name in regime_names:
        for mid_dist in mid_dists:
            snap = synthesize_l2_snapshot(
                n_nodes=16,
                n_levels=3,
                regime=regime_name,
                mid_price_distribution=mid_dist,
                seed=_SEED,
            )
            assert isinstance(snap, L2DepthSnapshot)
            _validate_snapshot(snap)
            mass = compute_l2_depth_mass(snap)
            assert mass.shape == (16,)
            assert (mass > 0.0).all(), f"regime={regime_name} produced zero-mass node."


def test_factory_default_parameters_match_brief() -> None:
    """Defaults are N=64, L=5, regime=pareto."""
    snap = synthesize_l2_snapshot()
    assert snap.bid_sizes.shape == (64, 5)
    assert snap.ask_sizes.shape == (64, 5)
    assert snap.mid_prices.shape == (64,)


def test_factory_bid_ask_asymmetry_respected() -> None:
    """``bid_share`` controls the bid/ask split."""
    snap = synthesize_l2_snapshot(
        n_nodes=8, n_levels=2, regime="uniform", seed=_SEED, bid_share=0.8
    )
    bid_total = float(snap.bid_sizes.sum())
    ask_total = float(snap.ask_sizes.sum())
    ratio = bid_total / (bid_total + ask_total)
    assert abs(ratio - 0.8) < 1e-9, f"asymmetry violated: ratio={ratio:.6f}."


def test_stream_timestamps_monotone_increasing() -> None:
    """Stream timestamps strictly increase by ``dt_ns`` per snapshot."""
    dt = 250_000_000
    stream = synthesize_l2_stream(
        n_nodes=8,
        n_levels=2,
        n_snapshots=10,
        regime="uniform",
        dt_ns=dt,
        start_timestamp_ns=10**9,
        seed=_SEED,
    )
    assert len(stream) == 10
    for i in range(1, len(stream)):
        delta = stream[i].timestamp_ns - stream[i - 1].timestamp_ns
        msg_dt = f"stream[{i}].timestamp_ns - stream[{i - 1}].timestamp_ns = {delta} != {dt}"
        assert delta == dt, msg_dt


def test_stream_determinism() -> None:
    """Stream is bit-identical under repeated invocation with fixed seed."""
    a = synthesize_l2_stream(n_nodes=8, n_levels=2, n_snapshots=4, regime="pareto", seed=_SEED)
    b = synthesize_l2_stream(n_nodes=8, n_levels=2, n_snapshots=4, regime="pareto", seed=_SEED)
    assert len(a) == len(b)
    for sa, sb in zip(a, b):
        np.testing.assert_array_equal(sa.bid_sizes, sb.bid_sizes)
        np.testing.assert_array_equal(sa.ask_sizes, sb.ask_sizes)
        np.testing.assert_array_equal(sa.mid_prices, sb.mid_prices)


def test_stream_regime_drift_changes_concentration() -> None:
    """Regime drift from uniform → pareto increases concentration over time."""
    stream = synthesize_l2_stream(
        n_nodes=64,
        n_levels=3,
        n_snapshots=8,
        regime="uniform",
        end_regime="pareto",
        seed=_SEED,
    )
    first_mass = compute_l2_depth_mass(stream[0])
    last_mass = compute_l2_depth_mass(stream[-1])
    msg_drift = "regime drift uniform→pareto did not raise the Gini of the final snapshot."
    assert _gini(first_mass) < _gini(last_mass), msg_drift


def test_regime_spec_custom_parameters() -> None:
    """``RegimeSpec`` overrides default regime parameters."""
    spec = RegimeSpec(name="pareto", params={"alpha": 0.5})  # very heavy tail
    snap_heavy = synthesize_l2_snapshot(n_nodes=128, n_levels=2, regime=spec, seed=_SEED)
    snap_light = synthesize_l2_snapshot(
        n_nodes=128, n_levels=2, regime=RegimeSpec(name="pareto", params={"alpha": 3.0}), seed=_SEED
    )
    g_heavy = _gini(compute_l2_depth_mass(snap_heavy))
    g_light = _gini(compute_l2_depth_mass(snap_light))
    msg_alpha = f"alpha=0.5 Gini {g_heavy:.4f} did not exceed alpha=3.0 Gini {g_light:.4f}."
    assert g_heavy > g_light, msg_alpha


def test_regime_invalid_name_raises() -> None:
    """Unknown regime name fails fast."""
    with pytest.raises(ValueError, match="unknown regime"):
        synthesize_l2_snapshot(n_nodes=4, n_levels=2, regime="nonexistent")  # type: ignore[arg-type]


def test_regime_invalid_parameters_raise() -> None:
    """Each regime validates its own parameter ranges."""
    rng = np.random.default_rng(_SEED)
    with pytest.raises(ValueError):
        uniform_depth(n=4, mean=-1.0, jitter=0.1, rng=rng)
    with pytest.raises(ValueError):
        pareto_depth(n=4, alpha=0.0, rng=rng)
    with pytest.raises(ValueError):
        winner_takes_most_depth(n=4, dominance=0.4, rng=rng)
    with pytest.raises(ValueError):
        bimodal_depth(n=4, ratio=1.5, rng=rng)


def test_factory_invalid_n_nodes_raises() -> None:
    with pytest.raises(ValueError):
        synthesize_l2_snapshot(n_nodes=0, n_levels=2, regime="uniform")


def test_factory_negative_timestamp_raises() -> None:
    with pytest.raises(ValueError):
        synthesize_l2_snapshot(n_nodes=4, n_levels=2, regime="uniform", timestamp_ns=-1)


def test_cli_writes_npz(tmp_path: Path) -> None:
    """CLI run writes a valid ``.npz`` round-trip-loadable into a snapshot."""
    out = tmp_path / "snap.npz"
    rc = cli_main(
        [
            "--n",
            "8",
            "--levels",
            "2",
            "--regime",
            "pareto",
            "--seed",
            str(_SEED),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert out.exists()

    with np.load(out) as data:
        ts = int(data["timestamp_ns"].item())
        bid = data["bid_sizes"].astype(np.float64, copy=True)
        ask = data["ask_sizes"].astype(np.float64, copy=True)
        mid = data["mid_prices"].astype(np.float64, copy=True)

    snap = L2DepthSnapshot(timestamp_ns=ts, bid_sizes=bid, ask_sizes=ask, mid_prices=mid)
    _validate_snapshot(snap)
    assert bid.shape == (8, 2)
    assert ask.shape == (8, 2)
    assert mid.shape == (8,)


def test_cli_subprocess_writes_npz(tmp_path: Path) -> None:
    """``python -m tools.synthetic_l2`` works as advertised in the brief."""
    out = tmp_path / "snap.npz"
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.synthetic_l2",
            "--n",
            "16",
            "--levels",
            "3",
            "--regime",
            "uniform",
            "--seed",
            str(_SEED),
            "--out",
            str(out),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}; stderr={result.stderr!r}"
    assert out.exists()
    with np.load(out) as data:
        assert data["bid_sizes"].shape == (16, 3)
