# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Public API for the DRO-ARA regime observer subsystem.

See :mod:`core.dro_ara.engine` for invariants and references.
"""

from __future__ import annotations

from .engine import (
    ADF_CV_5PCT,
    ADF_MAX_LAGS,
    EPSILON_H,
    FREE_ENERGY_CRITICAL,
    H_CRITICAL,
    H_DRIFT,
    MAX_DEPTH,
    MIN_WINDOW,
    R2_MIN,
    RS_LONG_THRESH,
    STABLE_RUNS,
    VARIATIONAL_ENERGY_CEILING,
    VARIATIONAL_ENERGY_FLOOR,
    Regime,
    Signal,
    State,
    classify,
    derive_gamma,
    geosync_observe,
    risk_scalar,
)

__all__ = [
    "ADF_CV_5PCT",
    "ADF_MAX_LAGS",
    "EPSILON_H",
    "FREE_ENERGY_CRITICAL",
    "VARIATIONAL_ENERGY_CEILING",
    "VARIATIONAL_ENERGY_FLOOR",
    "H_CRITICAL",
    "H_DRIFT",
    "MAX_DEPTH",
    "MIN_WINDOW",
    "R2_MIN",
    "RS_LONG_THRESH",
    "STABLE_RUNS",
    "Regime",
    "Signal",
    "State",
    "classify",
    "derive_gamma",
    "geosync_observe",
    "risk_scalar",
]
