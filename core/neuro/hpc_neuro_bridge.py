# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""HPC-Neuro Integration Bridge.

Connects the HPC Active Inference subsystem with core neuro controllers
via the NeuroSignalBus. Translates HPC outputs (PWPE, action, entropy)
into neuromodulator signals and produces integrated trading decisions.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from typing import List

import numpy as np

from core.neuro.signal_bus import NeuroSignalBus


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + np.exp(-x))
    ex = np.exp(x)
    return ex / (1.0 + ex)


class HPCNeuroBridge:
    """Bridge between HPC Active Inference and core neuro subsystems.

    Translates HPC outputs into neuromodulator bus signals and provides
    integrated trading decisions that combine all subsystem states.

    Parameters
    ----------
    bus : NeuroSignalBus
        Shared neuromodulator signal bus.
    pwpe_scale : float
        Scaling factor for PWPE → serotonin mapping (default 2.0).
    """

    def __init__(
        self,
        bus: NeuroSignalBus,
        pwpe_scale: float = 2.0,
    ) -> None:
        self._bus = bus
        self._pwpe_scale = pwpe_scale

    # ── Public API ────────────────────────────────────────────────────

    def process_hpc_output(self, pwpe: float, action: int, state_entropy: float) -> dict:
        """Process HPC Active Inference output into neuro bus signals.

        Parameters
        ----------
        pwpe : float
            Precision-weighted prediction error from HPC.
        action : int
            Selected action index.
        state_entropy : float
            Entropy of the belief state (higher = more uncertain).

        Returns
        -------
        dict
            Keys: pwpe, stress, confidence, action, serotonin_level
        """
        # Publish raw PWPE to bus
        self._bus.publish_hpc(abs(pwpe))

        # Map PWPE to serotonin stress signal via sigmoid
        stress = _sigmoid(self._pwpe_scale * abs(pwpe))
        self._bus.publish_serotonin(stress)

        # Map state entropy to confidence (dopamine-like)
        confidence = 1.0 / (1.0 + state_entropy)

        return {
            "pwpe": pwpe,
            "stress": stress,
            "confidence": confidence,
            "action": action,
            "serotonin_level": stress,
        }

    def get_integrated_decision(self, kelly_base: float = 1.0) -> dict:
        """Read all bus signals and produce an integrated trading decision.

        Parameters
        ----------
        kelly_base : float
            Base Kelly fraction before neuro adjustment.

        Returns
        -------
        dict
            should_hold, position_multiplier, learning_rate, regime,
            and all underlying signal values.
        """
        snapshot = self._bus.snapshot()
        should_hold = self._bus.should_hold()
        position_multiplier = self._bus.compute_position_multiplier(kelly_base)
        learning_rate = self._bus.compute_learning_rate(base_lr=1e-4)

        return {
            "should_hold": should_hold,
            "position_multiplier": position_multiplier,
            "learning_rate": learning_rate,
            "regime": snapshot.stress_regime.value,
            "kuramoto_R": snapshot.kuramoto_R,
            "hpc_pwpe": snapshot.hpc_pwpe,
            "ecs_free_energy": snapshot.ecs_free_energy,
            "serotonin_level": snapshot.serotonin_level,
            "dopamine_rpe": snapshot.dopamine_rpe,
            "gaba_inhibition": snapshot.gaba_inhibition,
        }

    def compute_adaptive_threshold(self, pwpe_history: List[float], quantile: float = 0.9) -> float:
        """Compute adaptive PWPE threshold for metastable transition detection.

        Parameters
        ----------
        pwpe_history : list[float]
            Recent PWPE values.
        quantile : float
            Quantile at which to set the threshold (default 0.9).

        Returns
        -------
        float
            Adaptive threshold. Returns 0.0 for empty history.
        """
        if not pwpe_history:
            return 0.0
        return float(np.quantile(pwpe_history, quantile))
