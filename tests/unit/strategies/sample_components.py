# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Support components for strategy DSL unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class DummyStrategy:
    """Minimal callable strategy used in DSL tests."""

    symbol: str
    window: int
    threshold: float = 0.0

    def __call__(self, data: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        return {
            "symbol": self.symbol,
            "window": self.window,
            "threshold": self.threshold,
            "data_keys": sorted(list(data.keys())) if data else [],
        }


def build_feature_set(scale: float = 1.0) -> dict[str, float]:
    """Return a predictable feature specification for doc generation tests."""

    return {"scale": float(scale)}
