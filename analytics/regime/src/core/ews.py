# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ensemble early warning signal aggregator."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Optional

from .causal_guard import CausalGuardResult
from .fk_detector import FKDetectorResult
from .ricci_flow import RicciFlowResult
from .topo_sentinel import TopoSentinelResult

__all__ = [
    "EWSConfig",
    "EWSResult",
    "KillSwitchPolicy",
    "EarlyWarningSignal",
]


@dataclass(frozen=True)
class EWSConfig:
    """Weights for the early warning ensemble."""

    weight_fk: float = 1.0
    weight_ricci: float = 1.0
    weight_topo: float = 1.0
    weight_causal: float = 1.0
    bias: float = 0.0


@dataclass(frozen=True)
class KillSwitchPolicy:
    """Policy thresholds for auto-engaging the kill-switch."""

    min_online_auc: float = 0.6
    max_false_positive_rate: float = 0.15


@dataclass(frozen=True)
class EWSResult:
    """Aggregate score and diagnostics returned by the ensemble."""

    ews_score: float
    fk_index: float
    ricci_mean: float
    topo_score: float
    causal_strength: float
    probability: float
    kill_switch_recommended: bool


class EarlyWarningSignal:
    """Combine orthogonal detectors into a calibrated signal."""

    def __init__(
        self,
        config: EWSConfig | None = None,
        *,
        policy: KillSwitchPolicy | None = None,
    ) -> None:
        self._config = config or EWSConfig()
        self._policy = policy or KillSwitchPolicy()

    @property
    def config(self) -> EWSConfig:
        return self._config

    @property
    def policy(self) -> KillSwitchPolicy:
        return self._policy

    def aggregate(
        self,
        fk: FKDetectorResult,
        ricci: RicciFlowResult,
        topo: TopoSentinelResult,
        causal: Optional[CausalGuardResult] = None,
        *,
        online_auc: float | None = None,
        false_positive_rate: float | None = None,
    ) -> EWSResult:
        causal_strength = float(causal.causal_strength.mean()) if causal else 0.0
        score = (
            self._config.weight_fk * fk.fk_index
            + self._config.weight_ricci * (1.0 - ricci.ricci_mean)
            + self._config.weight_topo * topo.topo_score
            + self._config.weight_causal * causal_strength
            + self._config.bias
        )
        probability = _sigmoid(score)

        kill_switch_recommended = False
        if online_auc is not None and false_positive_rate is not None:
            kill_switch_recommended = (
                online_auc < self._policy.min_online_auc
                or false_positive_rate > self._policy.max_false_positive_rate
            )

        return EWSResult(
            ews_score=float(score),
            fk_index=fk.fk_index,
            ricci_mean=ricci.ricci_mean,
            topo_score=topo.topo_score,
            causal_strength=causal_strength,
            probability=float(probability),
            kill_switch_recommended=bool(kill_switch_recommended),
        )


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))
