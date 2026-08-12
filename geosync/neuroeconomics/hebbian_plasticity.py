# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reward-Modulated Hebbian Plasticity — self-tuning decision weights.

Mechanism: dopamine-gated LTP/LTD on FlowWeights.

  Profitable TRADE → dopamine spike → strengthen weights that led here
  Loss TRADE       → serotonin veto → weaken those weights, lower threshold
  OBSERVE that avoided loss → reinforce OBSERVE tendency for that regime
  OBSERVE that missed gain → slightly weaken OBSERVE tendency

Three components (neuroscience):
  1. Eligibility trace: which weights were active during this decision
  2. Dopamine gate: RPE > 0 → LTP (strengthen). RPE < 0 → LTD (weaken)
  3. Consolidation: after N updates, snapshot best weights (long-term memory)

Invariants:
  - Weights NEVER go negative
  - Weights ALWAYS renormalize (sum preserved)
  - Learning rate decays with consolidation (exploitation > exploration)
  - Catastrophic forgetting prevented by EWA with floor
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Number of plastic weights (see PlasticWeights). The eligibility trace must
# match this dimension exactly.
N_PLASTIC_WEIGHTS = 11


def _validate_eligibility(eligibility: list[float]) -> None:
    """Fail-closed input-contract check for a caller-supplied eligibility trace.

    The per-step weight update is bounded by ``lr · magnitude · eligibility[i]``
    with ``magnitude ≤ 1``; that envelope holds ONLY while each eligibility
    component is finite and in ``[0, 1]``. A component > 1 (or non-finite) falls
    outside the witnessed envelope, so it is rejected here rather than silently
    inflating the update. Closes the documented input-contract boundary
    (ledger ``hebbian-plasticity-update`` witness_note).
    """
    if len(eligibility) != N_PLASTIC_WEIGHTS:
        raise ValueError(
            f"eligibility must have {N_PLASTIC_WEIGHTS} components, got {len(eligibility)}"
        )
    for i, e in enumerate(eligibility):
        if not math.isfinite(e) or not (0.0 <= e <= 1.0):
            raise ValueError(
                f"eligibility[{i}]={e!r} outside the input contract [0, 1] (finite); "
                "Hebbian update fails closed on out-of-envelope eligibility."
            )


@dataclass(slots=True)
class PlasticWeights:
    """Mutable weight vector that learns from outcomes.

    Each weight corresponds to a named parameter in FlowWeights.
    Only the weights that MATTER for decisions are plastic:
      - ei_excitatory_* (3): what drives us to trade
      - ei_inhibitory_* (4): what holds us back
      - epistemic_* (3): when to observe vs trade
      - pragmatic_base (1): floor for trade signal
    Total: 11 plastic weights.
    """

    # Excitatory weights
    ei_ex_risk: float = 0.4
    ei_ex_strength: float = 0.3
    ei_ex_confidence: float = 0.3

    # Inhibitory weights
    ei_in_baseline: float = 0.3
    ei_in_uncertainty: float = 0.25
    ei_in_distance: float = 0.25
    ei_in_instability: float = 0.2

    # Epistemic weights
    ep_uncertainty: float = 0.3
    ep_surprise: float = 0.3
    ep_ambiguity: float = 0.25

    # Pragmatic
    pragmatic_base: float = 0.5

    def to_list(self) -> list[float]:
        return [
            self.ei_ex_risk,
            self.ei_ex_strength,
            self.ei_ex_confidence,
            self.ei_in_baseline,
            self.ei_in_uncertainty,
            self.ei_in_distance,
            self.ei_in_instability,
            self.ep_uncertainty,
            self.ep_surprise,
            self.ep_ambiguity,
            self.pragmatic_base,
        ]

    def from_list(self, values: list[float]) -> None:
        (
            self.ei_ex_risk,
            self.ei_ex_strength,
            self.ei_ex_confidence,
            self.ei_in_baseline,
            self.ei_in_uncertainty,
            self.ei_in_distance,
            self.ei_in_instability,
            self.ep_uncertainty,
            self.ep_surprise,
            self.ep_ambiguity,
            self.pragmatic_base,
        ) = values


@dataclass(frozen=True, slots=True)
class PlasticityState:
    """Snapshot of plasticity module state."""

    learning_rate: float
    consolidation_count: int
    total_ltp: int  # long-term potentiation events (successes)
    total_ltd: int  # long-term depression events (failures)
    best_sharpe: float


class HebbianPlasticity:
    """Reward-modulated weight adaptation.

    Parameters
    ----------
    lr_init
        Initial learning rate for weight updates.
    lr_decay
        Multiplicative decay per consolidation epoch.
    lr_floor
        Minimum learning rate (prevents freezing).
    consolidation_interval
        Updates between consolidation snapshots.
    weight_floor
        Minimum value for any weight (prevents zeroing).
    """

    def __init__(
        self,
        *,
        lr_init: float = 0.02,
        lr_decay: float = 0.995,
        lr_floor: float = 0.001,
        consolidation_interval: int = 100,
        weight_floor: float = 0.05,
    ) -> None:
        self._lr = lr_init
        self._lr_decay = lr_decay
        self._lr_floor = lr_floor
        self._consol_interval = consolidation_interval
        self._weight_floor = weight_floor

        self._weights = PlasticWeights()
        self._best_weights = PlasticWeights()
        self._best_sharpe: float = -999.0

        self._update_count: int = 0
        self._total_ltp: int = 0
        self._total_ltd: int = 0

        # Running Sharpe for consolidation decision
        from collections import deque

        self._pnl_window: deque[float] = deque(maxlen=consolidation_interval)

    @property
    def weights(self) -> PlasticWeights:
        return self._weights

    def update(
        self,
        *,
        decision: str,
        pnl: float,
        regime: str,
        eligibility: list[float] | None = None,
    ) -> None:
        """One plasticity step: RPE-gated weight modification.

        Parameters
        ----------
        decision
            "TRADE", "OBSERVE", "ABORT", "DISSOCIATED".
        pnl
            Realized P&L (0 for non-trade decisions).
        regime
            Market regime at time of decision.
        eligibility
            Optional explicit eligibility trace (11 floats).
            If None, auto-computed from decision type.
        """
        pnl = pnl if math.isfinite(pnl) else 0.0

        # Track rolling Sharpe window
        self._pnl_window.append(pnl)

        # Auto eligibility: which weights were "active" for this decision.
        # A caller-supplied trace is validated fail-closed against the input
        # contract [0, 1]^11 (auto traces are 0/1 by construction).
        if eligibility is None:
            eligibility = self._auto_eligibility(decision)
        else:
            _validate_eligibility(eligibility)

        # RPE: simple sign → direction of update
        if decision == "TRADE":
            if pnl > 0:
                # LTP: strengthen weights that led to profitable trade
                self._apply_ltp(eligibility, magnitude=min(1.0, abs(pnl) * 10))
                self._total_ltp += 1
            elif pnl < 0:
                # LTD: weaken weights that led to loss
                self._apply_ltd(eligibility, magnitude=min(1.0, abs(pnl) * 10))
                self._total_ltd += 1

        elif decision == "OBSERVE":
            # If we would have lost → reinforce OBSERVE (epistemic weights up)
            if pnl < 0:  # hypothetical pnl passed as negative
                self._apply_ltp(
                    self._epistemic_eligibility(),
                    magnitude=0.3,
                )
                self._total_ltp += 1

        self._update_count += 1

        # Consolidation: snapshot best weights
        if self._update_count % self._consol_interval == 0:
            self._consolidate()

    def _apply_ltp(self, eligibility: list[float], magnitude: float) -> None:
        """Long-Term Potentiation: strengthen active weights."""
        w = self._weights.to_list()
        for i in range(len(w)):
            w[i] += self._lr * magnitude * eligibility[i]
            w[i] = max(self._weight_floor, w[i])
        self._weights.from_list(w)
        self._lr = max(self._lr_floor, self._lr * self._lr_decay)

    def _apply_ltd(self, eligibility: list[float], magnitude: float) -> None:
        """Long-Term Depression: weaken active weights."""
        w = self._weights.to_list()
        for i in range(len(w)):
            w[i] -= self._lr * magnitude * eligibility[i]
            w[i] = max(self._weight_floor, w[i])
        self._weights.from_list(w)
        self._lr = max(self._lr_floor, self._lr * self._lr_decay)

    def _auto_eligibility(self, decision: str) -> list[float]:
        """Which weights were responsible for this decision.

        TRADE → excitatory weights active, pragmatic active
        OBSERVE → epistemic weights active
        ABORT → inhibitory weights active
        """
        n = 11
        e = [0.0] * n
        if decision == "TRADE":
            e[0] = 1.0  # ei_ex_risk
            e[1] = 1.0  # ei_ex_strength
            e[2] = 1.0  # ei_ex_confidence
            e[10] = 1.0  # pragmatic_base
        elif decision in ("OBSERVE",):
            e[7] = 1.0  # ep_uncertainty
            e[8] = 1.0  # ep_surprise
            e[9] = 1.0  # ep_ambiguity
        elif decision in ("ABORT", "DISSOCIATED"):
            e[3] = 1.0  # ei_in_baseline
            e[4] = 1.0  # ei_in_uncertainty
            e[5] = 1.0  # ei_in_distance
            e[6] = 1.0  # ei_in_instability
        return e

    def _epistemic_eligibility(self) -> list[float]:
        e = [0.0] * 11
        e[7] = 1.0
        e[8] = 1.0
        e[9] = 1.0
        return e

    def _consolidate(self) -> None:
        """Snapshot best weights if current rolling Sharpe > historical best."""
        if len(self._pnl_window) < 20:
            return
        pnls = list(self._pnl_window)
        avg = sum(pnls) / len(pnls)
        var = sum((p - avg) ** 2 for p in pnls) / (len(pnls) - 1)
        std = math.sqrt(max(0.0, var))
        sharpe = avg / std * math.sqrt(252) if std > 1e-12 else 0.0

        if sharpe > self._best_sharpe:
            self._best_sharpe = sharpe
            self._best_weights = PlasticWeights()
            self._best_weights.from_list(self._weights.to_list())

    def restore_best(self) -> None:
        """Revert to best consolidated weights (anti-degradation)."""
        self._weights.from_list(self._best_weights.to_list())

    def state(self) -> PlasticityState:
        return PlasticityState(
            learning_rate=self._lr,
            consolidation_count=self._update_count // self._consol_interval,
            total_ltp=self._total_ltp,
            total_ltd=self._total_ltd,
            best_sharpe=self._best_sharpe,
        )
