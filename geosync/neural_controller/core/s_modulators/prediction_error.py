# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Dict


def modulator(model: object, obs: Dict[str, float]) -> float:
    params = getattr(model, "p", None)
    if params is None:
        return 0.0
    prediction_error = float(obs.get("prediction_error", 0.0))
    sensory_confidence = float(obs.get("sensory_confidence", 1.0))
    confidence_weight = max(
        0.0,
        (1.0 - params.sensory_confidence_gain)
        + params.sensory_confidence_gain * max(0.0, min(1.0, sensory_confidence)),
    )
    return params.prediction_gain * prediction_error * confidence_weight
