# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causal guardrails for risk gating."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

__all__ = [
    "CausalGuardConfig",
    "CausalGuardResult",
    "CausalGuard",
]


@dataclass(frozen=True)
class CausalGuardConfig:
    """Configuration for :class:`CausalGuard`."""

    kappa: float = 0.35
    te_threshold: float = 0.05
    max_gate: float = 1.0
    min_gate: float = 0.2


@dataclass(frozen=True)
class CausalGuardResult:
    """Output of :class:`CausalGuard.evaluate`."""

    gates: pd.Series
    causal_strength: pd.Series


class CausalGuard:
    """Route risk based on causal transport strength."""

    def __init__(self, config: CausalGuardConfig | None = None) -> None:
        self._config = config or CausalGuardConfig()

    @property
    def config(self) -> CausalGuardConfig:
        return self._config

    def evaluate(
        self,
        causal_matrix: Mapping[str, Mapping[str, float]] | pd.DataFrame,
        *,
        rolling_te: Mapping[tuple[str, str], float] | None = None,
        ftest_pass: Mapping[tuple[str, str], bool] | None = None,
    ) -> CausalGuardResult:
        matrix = _to_frame(causal_matrix)
        entities = matrix.index.tolist()

        te_lookup = rolling_te or {}
        ftest_lookup = ftest_pass or {}

        causal_strength = []
        gates = []
        for target in entities:
            drivers = matrix[target]
            influence = 0.0
            for driver, strength in drivers.items():
                if driver == target or strength <= 0:
                    continue
                key = (driver, target)
                rolling = te_lookup.get(key, strength)
                ftest_ok = ftest_lookup.get(key, True)
                if not ftest_ok or rolling < self._config.te_threshold:
                    continue
                influence += rolling
            causal_strength.append(influence)
            gate = max(
                self._config.min_gate,
                min(self._config.max_gate, 1.0 - self._config.kappa * influence),
            )
            gates.append(gate)

        return CausalGuardResult(
            gates=pd.Series(gates, index=entities, name="gate"),
            causal_strength=pd.Series(causal_strength, index=entities, name="causal_strength"),
        )


def _to_frame(data: Mapping[str, Mapping[str, float]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    frame = pd.DataFrame(data)
    if frame.shape[0] != frame.shape[1]:
        frame = frame.reindex(index=frame.columns, columns=frame.columns, fill_value=0.0)
    return frame.fillna(0.0)
