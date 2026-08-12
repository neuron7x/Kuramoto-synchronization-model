# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GABA Position Sizing Gate.

Integrates GABAergic inhibition into position sizing decisions.
High inhibition → smaller positions (risk-off).  The gate reads
current GABA inhibition from the NeuroSignalBus and applies a
multiplicative brake to the base position size.

Biological basis:
    Mink 1996 — basal ganglia GABAergic output tonically inhibits
    thalamocortical motor circuits; release of inhibition gates action.

STDP-like plasticity:
    Negative RPE (pain) → increase inhibition sensitivity weights,
    implementing Hebbian "learn from pain" adaptation.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.neuro.signal_bus import NeuroSignalBus


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


class GABAPositionGate:
    """GABA-based inhibitory gate on position sizing.

    Parameters
    ----------
    bus : NeuroSignalBus
        Signal bus for reading config and publishing GABA inhibition.
    w_vix : float
        Weight for VIX contribution to inhibition.
    w_vol : float
        Weight for realised volatility contribution.
    w_rpe : float
        Weight for negative RPE contribution.
    plasticity_rate : float
        STDP learning rate for pain-driven weight adaptation.
    """

    def __init__(
        self,
        bus: "NeuroSignalBus",
        w_vix: float = 1.0,
        w_vol: float = 1.0,
        w_rpe: float = 1.0,
        plasticity_rate: float = 0.05,
    ) -> None:
        self._bus = bus
        self.w_vix = w_vix
        self.w_vol = w_vol
        self.w_rpe = w_rpe
        self._plasticity_rate = plasticity_rate

    # ── Position gating ──────────────────────────────────────────────

    def gate_position_size(self, base_size: float) -> float:
        """Apply GABA inhibition gate to a base position size.

        effective = base_size * (1 - inhibition * scale)

        *scale* is read from the bus config
        (``BusConfig.inhibition_position_scale``).

        Returns
        -------
        float
            Gated position size, clamped to [0, base_size].
        """
        inhibition = self._bus.snapshot().gaba_inhibition
        scale = self._bus._config.inhibition_position_scale
        effective = base_size * (1.0 - inhibition * scale)
        return max(0.0, min(base_size, effective))  # INV-GABA3: effective ≤ raw and effective ≥ 0

    # ── Inhibition update from market state ──────────────────────────

    def update_inhibition(
        self,
        vix: float,
        volatility: float,
        rpe: float,
    ) -> float:
        """Compute and publish GABA inhibition from market state.

        z          = w_vix * vix/30 + w_vol * vol/0.2 + w_rpe * max(0, -rpe)
        inhibition = max(0, 2 * sigmoid(z) - 1)   # rectified: z=0 -> 0

        The rectified sigmoid sends a dead-calm market (z = 0) to inhibition 0
        rather than the 0.5 floor a plain sigmoid would impose (INV-GABA4).

        Also applies STDP-like plasticity: negative RPE increases
        the RPE weight (learn from pain).

        Returns
        -------
        float
            New inhibition value in [0, 1].
        """
        # STDP plasticity: negative RPE → increase w_rpe
        if rpe < 0:
            self.w_rpe += self._plasticity_rate * abs(rpe)

        # All stress drivers are non-negative (vix, volatility >= 0; the RPE
        # term is rectified), so z >= 0 always. A plain sigmoid(z) would floor
        # the gate at sigmoid(0) = 0.5 — a permanent 50% inhibition even in a
        # dead-calm market, which violates INV-GABA4 (vol -> 0 => inhibition
        # -> 0). The rectified form 2*sigmoid(z) - 1 maps z in [0, inf) onto
        # [0, 1) with f(0) = 0 (INV-GABA4) and f(inf) -> 1 (INV-GABA5), while
        # staying monotone in every driver (INV-GABA2).
        z = (
            self.w_vix * (vix / 30.0)
            + self.w_vol * (volatility / 0.2)
            + self.w_rpe * max(0.0, -rpe)
        )
        # INV-GABA1: clamp to [0, 1]; the max guards the pathological z < 0
        # case (negative inputs), inactive for the physical z >= 0 regime.
        inhibition = max(0.0, 2.0 * _sigmoid(z) - 1.0)

        self._bus.publish_gaba(inhibition)
        return inhibition
