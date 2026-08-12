# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the OMS position-conservation law.

Binds a pytest function to the catalog law ``oms.position_conservation`` via
``@law`` and proves it holds in the fixed-point execution ledger that implements
it — ``geosync_hpc.ledger`` — without importing the forbidden ``execution/`` path.

* ``oms.position_conservation`` (INV-HPC3) — every fill conserves total book
  value: ``cash + position·mark`` is invariant modulo the trade fee, checked to
  the cent by ``conservation_holds()`` after each ``apply_fill``; and independent
  fills commute (order does not synthesize or destroy value).

Nothing here is a market claim. These are double-entry-conservation facts about
the deterministic int64 ledger.
"""

from __future__ import annotations

import numpy as np

from geosync_hpc.ledger import (
    apply_fill,
    conservation_holds,
    initial_state,
    scale_bps,
    scale_price,
    scale_qty,
)
from physics_contracts.law import law


def _random_fill(rng: np.random.Generator) -> dict[str, int]:
    return {
        "fill_price_scaled": scale_price(float(rng.uniform(50.0, 150.0))),
        "qty_delta_scaled": scale_qty(float(rng.uniform(-5.0, 5.0))),
        "fee_bps_scaled": scale_bps(float(rng.uniform(0.0, 10.0))),
    }


@law("oms.position_conservation", n_fills=200, seed=0)
def test_conservation_holds_on_every_fill() -> None:
    """INV-HPC3: cash + position·mark is conserved (modulo fee) by every fill.

    Starting from the empty ledger, each random fill must satisfy
    ``conservation_holds(before, after)`` to the cent — no synthesis or
    destruction of book value beyond the declared fee. The witness drives a long
    fill sequence and requires the identity to hold on every step.
    """
    n_fills = 200
    mark_price_scaled = scale_price(100.0)
    rng = np.random.default_rng(seed=0)
    state = initial_state()
    violations = 0
    for _ in range(n_fills):
        fill = _random_fill(rng)
        after = apply_fill(state, **fill)
        if not conservation_holds(state, after, mark_price_scaled=mark_price_scaled, **fill):
            violations += 1
        state = after
    assert violations == 0, (
        "INV-HPC3 violated: observed conservation violations = "
        f"{violations} of n_fills={n_fills} with seed=0 must be 0; cash + position·mark "
        "must be conserved modulo fee by every fill"
    )


@law("oms.position_conservation", n_pairs=100, seed=1)
def test_independent_fills_commute() -> None:
    """INV-HPC3: independent fills commute — order does not change the state.

    Applying two independent fills in either order must reach the byte-identical
    ledger state; otherwise the ledger would synthesize or destroy value through
    ordering, breaking conservation. The witness checks many random fill pairs.
    """
    n_pairs = 100
    rng = np.random.default_rng(seed=1)
    non_commuting = 0
    for _ in range(n_pairs):
        fill_a = _random_fill(rng)
        fill_b = _random_fill(rng)
        start = initial_state()
        ab = apply_fill(apply_fill(start, **fill_a), **fill_b)
        ba = apply_fill(apply_fill(start, **fill_b), **fill_a)
        if ab != ba:
            non_commuting += 1
    assert non_commuting == 0, (
        "INV-HPC3 violated: observed non-commuting pairs = "
        f"{non_commuting} of n_pairs={n_pairs} with seed=1 must be 0; independent fills "
        "must commute so ordering cannot synthesize or destroy book value"
    )
