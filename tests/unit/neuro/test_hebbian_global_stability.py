# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization of the Hebbian GLOBAL (cumulative) stability LIMITATION.

This is an HONEST NEGATIVE witness, not a stability proof. The ledger entry
``hebbian-plasticity-update`` is kept PARTIAL precisely because the per-step
update is envelope-bounded but the *cumulative* weight is NOT globally bounded:
the learning-rate floor ``lr_floor > 0`` means that once the geometric lr decay
saturates, every subsequent LTP step adds a fixed ``lr_floor · magnitude ·
eligibility`` increment, so a continuously-reinforced weight grows LINEARLY
without an upper bound (the docstring's "renormalize / sum preserved" is not
implemented).

These tests pin that limitation as executable fact so it cannot silently
"become" global stability by wording. If a future change adds renormalization
or removes the lr floor, the monotone-unbounded assertion flips and forces a
ledger re-evaluation.
"""

from __future__ import annotations

from geosync.neuroeconomics.hebbian_plasticity import HebbianPlasticity

LR_FLOOR = 0.001


def _driven(n: int) -> float:
    """Weight[0] after n profitable TRADE updates (eligibility 1 every step)."""
    hp = HebbianPlasticity(
        lr_init=0.02,
        lr_decay=0.995,
        lr_floor=LR_FLOOR,
        consolidation_interval=10**9,  # isolate the update rule
        weight_floor=0.05,
    )
    for _ in range(n):
        hp.update(decision="TRADE", pnl=1.0, regime="bull")
    return hp.weights.to_list()[0]


def test_sustained_ltp_grows_without_global_upper_bound() -> None:
    """No global ceiling: doubling the horizon adds ~lr_floor per extra step.

    Past the lr-decay saturation point the increment per step is exactly
    lr_floor, so w(2N) − w(N) ≈ lr_floor · N. The weight therefore exceeds ANY
    fixed bound for large enough N — the defining property of NO global BIBO
    bound. (A renormalizing / floor-free scheme would saturate instead.)
    """
    w10k = _driven(10_000)
    w20k = _driven(20_000)
    # Continued near-linear growth of ~lr_floor per extra step (10k steps).
    assert w20k - w10k > 0.9 * LR_FLOOR * 10_000  # > 9.0
    # And it has blown well past any "renormalized" small-weight ceiling.
    assert w20k > 20.0


def test_growth_is_monotone_in_horizon() -> None:
    """The driven weight is strictly increasing in the number of updates —
    it never saturates onto a fixed attractor (the limitation, made explicit)."""
    ws = [_driven(n) for n in (2_000, 6_000, 12_000)]
    assert all(b > a for a, b in zip(ws, ws[1:], strict=False))
