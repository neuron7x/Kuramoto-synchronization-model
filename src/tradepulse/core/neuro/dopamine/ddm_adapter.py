from __future__ import annotations

import math
from dataclasses import dataclass

@dataclass(frozen=True)
class DDMAdjustment:
    """Container describing drift and boundary adjustments."""

    drift: float
    boundary: float


def adapt_ddm_parameters(
    dopamine_level: float,
    base_drift: float,
    base_boundary: float,
    drift_gain: float = 0.5,
    boundary_gain: float = 0.3,
    min_boundary: float = 0.1,
    *,
    serotonin_hold: float = 0.0,
    hold_boundary_gain: float = 0.6,
    hold_drift_suppression: float = 0.5,
) -> DDMAdjustment:
    """Translate dopamine level into DDM drift/boundary adjustments.

    Dopamine increases drift (action confidence) while reducing the boundary to
    accelerate exploitative decisions. Gains are bounded to maintain numerical
    stability. When serotonin vetoes are active, the diffusion boundary can be
    widened and drift suppressed to mimic basal ganglia HOLD dynamics.
    """

    if not math.isfinite(dopamine_level):
        raise ValueError("dopamine_level must be finite")
    if not math.isfinite(base_drift) or base_drift <= 0.0:
        raise ValueError("base_drift must be positive and finite")
    if not math.isfinite(base_boundary) or base_boundary <= 0.0:
        raise ValueError("base_boundary must be positive and finite")
    dopamine_level = min(1.0, max(0.0, dopamine_level))
    serotonin_hold = min(1.0, max(0.0, float(serotonin_hold)))
    hold_boundary_gain = max(0.0, float(hold_boundary_gain))
    hold_drift_suppression = max(0.0, min(1.0, float(hold_drift_suppression)))

    centred = dopamine_level - 0.5
    drift = base_drift * (1.0 + drift_gain * centred * 2.0)
    boundary = max(min_boundary, base_boundary * (1.0 - boundary_gain * dopamine_level))
    if serotonin_hold > 0.0:
        boundary = max(
            min_boundary,
            boundary * (1.0 + hold_boundary_gain * serotonin_hold),
        )
        drift = max(1e-9, drift * (1.0 - hold_drift_suppression * serotonin_hold))
    return DDMAdjustment(drift=drift, boundary=boundary)
