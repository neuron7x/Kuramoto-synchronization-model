# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the GABA position-gate laws in the physics catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``core.neuro.gaba_position_gate.GABAPositionGate``.
Two previously-unwitnessed laws gain witnesses:

* ``gaba.gate_bounds`` — the gate multiplier lies in [0, 1] (INV-GABA1).
* ``gaba.monotone_inhibition`` — the gate is monotonically non-increasing in
  inhibition: more inhibition ⇒ a smaller (or equal) position. The registry
  anchor is INV-GABA3 ("effective_position ≤ raw_position — inhibition only
  reduces"); this witness additionally certifies the catalog's monotonicity
  direction that @law binds.

Nothing here is a market claim. These are inhibitory-gate-contract facts.
"""

from __future__ import annotations

import numpy as np

from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law

# Strict definitional bound; only float round-off is allowed.
GATE_EPS = 1e-12


def _gate_at(inhibition: float) -> float:
    """The gate multiplier at a given inhibition level (base_size = 1)."""
    bus = NeuroSignalBus()
    bus.publish_gaba(float(inhibition))
    return GABAPositionGate(bus).gate_position_size(1.0)


@law("gaba.gate_bounds", n_levels=200)
def test_gate_multiplier_lies_in_unit_interval() -> None:
    """INV-GABA1: the gate multiplier stays in [0, 1] for every inhibition level.

    With base size 1 the gated position IS the multiplier; it must never leave
    [0, 1] for any inhibition in [0, 1] (or beyond), since a gate can neither
    short nor amplify. Swept across a fine inhibition grid.
    """
    n_levels = 200
    worst_low = np.inf
    worst_high = -np.inf
    for inhibition in np.linspace(0.0, 1.0, n_levels):
        gate = _gate_at(float(inhibition))
        worst_low = min(worst_low, gate)
        worst_high = max(worst_high, gate)
    assert worst_low >= 0.0 - GATE_EPS, (
        "INV-GABA1 violated: observed min gate = "
        f"{worst_low:.6f} must be ≥ 0 (tolerance {GATE_EPS:.0e}) with grid_levels={n_levels} "
        "inhibition swept on [0,1]; the gate cannot go negative"
    )
    assert worst_high <= 1.0 + GATE_EPS, (
        "INV-GABA1 violated: observed max gate = "
        f"{worst_high:.6f} must be ≤ 1 (tolerance {GATE_EPS:.0e}) with grid_levels={n_levels} "
        "inhibition swept on [0,1]; the gate cannot amplify above the raw size"
    )


@law("gaba.monotone_inhibition", n_levels=200)
def test_gate_is_monotone_non_increasing_in_inhibition() -> None:
    """INV-GABA3: more inhibition never increases the gate (inhibition only reduces).

    The catalog law gaba.monotone_inhibition requires gate(i₁) ≥ gate(i₂) for
    i₁ ≤ i₂. The witness sweeps a monotone-increasing inhibition grid and requires
    the gate sequence to be non-increasing, and confirms the gate genuinely moves
    (max minus min is positive) so the monotonicity is not asserted on a flat
    slice. INV-GABA3 ("inhibition only reduces") is the registry anchor.
    """
    n_levels = 200
    inhibitions = np.linspace(0.0, 1.0, n_levels)
    gate_values: list[float] = []
    for inhibition in inhibitions:
        gate_values.append(_gate_at(float(inhibition)))
    gates = np.array(gate_values)
    worst_increase = float(np.max(np.diff(gates)))
    spread = float(gates.max() - gates.min())
    assert worst_increase <= GATE_EPS, (
        "INV-GABA3 violated: observed worst gate increase = "
        f"{worst_increase:.3e} must be ≤ {GATE_EPS:.0e} with grid_levels={n_levels} "
        "inhibition increasing on [0,1]; the gate must be non-increasing in inhibition"
    )
    assert spread > GATE_EPS, (
        "INV-GABA3 vacuity guard: observed gate spread = "
        f"{spread:.3e} must be > {GATE_EPS:.0e} with grid_levels={n_levels} sweep; the gate "
        "must genuinely respond to inhibition, not be asserted monotone on a flat slice"
    )
