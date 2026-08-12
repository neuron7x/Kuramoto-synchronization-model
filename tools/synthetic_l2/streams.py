# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Temporal sequences of synthetic ``L2DepthSnapshot``s.

Each snapshot in the stream is independently seeded from a base seed (using
``np.random.SeedSequence.spawn``) so the stream is deterministic *and*
trivially parallelisable. Timestamps advance by exactly ``dt_ns`` per step.

Optional regime drift: callers may provide ``end_regime`` to linearly
interpolate the per-step regime parameters between ``regime`` and
``end_regime``. This is intended for transition / regime-shift tests; if the
two regimes have different ``name`` fields, drift falls back to step-wise
selection with the second regime taking over at the midpoint (this keeps
parameters well-defined without inventing cross-regime conjugation).
"""

from __future__ import annotations

from typing import Final

import numpy as np

from core.kuramoto.capital_weighted import L2DepthSnapshot

from .book_factory import (
    MidPriceDistribution,
    RegimeName,
    RegimeSpec,
    synthesize_l2_snapshot,
)

__all__ = [
    "synthesize_l2_stream",
]

_DEFAULT_DT_NS: Final[int] = 1_000_000_000  # one second


def _coerce_spec(regime: RegimeName | RegimeSpec) -> RegimeSpec:
    if isinstance(regime, RegimeSpec):
        return regime
    return RegimeSpec(name=regime, params={})


def _interpolate_params(
    start: RegimeSpec,
    end: RegimeSpec,
    t: float,
) -> RegimeSpec:
    """Interpolate regime parameters when ``start.name == end.name``.

    Otherwise return ``start`` for ``t < 0.5`` and ``end`` for ``t >= 0.5``.
    """
    if start.name != end.name:
        return start if t < 0.5 else end
    keys = set(start.params) | set(end.params)
    blended: dict[str, float] = {}
    for key in keys:
        a = float(start.params.get(key, end.params.get(key, 0.0)))
        b = float(end.params.get(key, start.params.get(key, 0.0)))
        blended[key] = (1.0 - t) * a + t * b
    return RegimeSpec(name=start.name, params=blended)


def synthesize_l2_stream(
    *,
    n_nodes: int = 64,
    n_levels: int = 5,
    n_snapshots: int,
    regime: RegimeName | RegimeSpec = "pareto",
    end_regime: RegimeName | RegimeSpec | None = None,
    dt_ns: int = _DEFAULT_DT_NS,
    start_timestamp_ns: int = 0,
    seed: int = 20260425,
    mid_price_distribution: MidPriceDistribution = "lognormal",
    bid_share: float = 0.5,
) -> tuple[L2DepthSnapshot, ...]:
    """Generate a deterministic sequence of L2 snapshots.

    Parameters
    ----------
    n_nodes:
        Number of instruments per snapshot.
    n_levels:
        Number of price levels per side.
    n_snapshots:
        Length of the stream. Must be ``>= 1``.
    regime:
        Starting regime (or the only regime if ``end_regime is None``).
    end_regime:
        Optional terminal regime. When provided, parameters are linearly
        interpolated between ``regime`` and ``end_regime`` across the stream
        (see :func:`_interpolate_params`).
    dt_ns:
        Inter-snapshot interval in nanoseconds. Must be ``> 0``.
    start_timestamp_ns:
        Timestamp of the first snapshot in nanoseconds.
    seed:
        Base seed; per-snapshot seeds are spawned deterministically so two
        runs with the same ``seed`` produce identical streams.
    mid_price_distribution:
        Forwarded to :func:`synthesize_l2_snapshot`.
    bid_share:
        Forwarded to :func:`synthesize_l2_snapshot`.

    Returns
    -------
    tuple[L2DepthSnapshot, ...]
        Frozen tuple of snapshots with strictly monotone timestamps.
    """
    if not isinstance(n_snapshots, int):
        raise TypeError(f"n_snapshots must be int, got {type(n_snapshots).__name__}.")
    if n_snapshots <= 0:
        raise ValueError(f"n_snapshots must be > 0, got {n_snapshots}.")
    if not isinstance(dt_ns, int):
        raise TypeError(f"dt_ns must be int, got {type(dt_ns).__name__}.")
    if dt_ns <= 0:
        raise ValueError(f"dt_ns must be > 0, got {dt_ns}.")
    if not isinstance(start_timestamp_ns, int):
        raise TypeError(f"start_timestamp_ns must be int, got {type(start_timestamp_ns).__name__}.")
    if start_timestamp_ns < 0:
        raise ValueError(f"start_timestamp_ns must be >= 0, got {start_timestamp_ns}.")

    start_spec = _coerce_spec(regime)
    end_spec = _coerce_spec(end_regime) if end_regime is not None else start_spec

    seed_seq = np.random.SeedSequence(seed)
    child_seeds = seed_seq.spawn(n_snapshots)

    snapshots: list[L2DepthSnapshot] = []
    for i, child in enumerate(child_seeds):
        t = 0.0 if n_snapshots == 1 else i / float(n_snapshots - 1)
        spec_at_t = _interpolate_params(start_spec, end_spec, t)
        # Convert spawned SeedSequence to a deterministic int seed for
        # synthesize_l2_snapshot, which accepts int seeds.
        child_seed = int(child.generate_state(1, dtype=np.uint32)[0])
        snap = synthesize_l2_snapshot(
            n_nodes=n_nodes,
            n_levels=n_levels,
            regime=spec_at_t,
            mid_price_distribution=mid_price_distribution,
            timestamp_ns=start_timestamp_ns + i * dt_ns,
            seed=child_seed,
            bid_share=bid_share,
        )
        snapshots.append(snap)

    return tuple(snapshots)
