# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CALIB-GRID-001 — external ground-truth calibration of the Kuramoto stack.

Pre-registered, fail-closed calibration of GeoSync's Sakaguchi–Kuramoto
inverse-problem stack against the power-grid Kuramoto reduction
(Dörfler & Bullo, PNAS 2013) on canonical IEEE test systems. This is a
calibration instrument, **not** a scientific hypothesis: the ground
truth is already known exactly from published admittance / injection
data and a closed-form synchronisation condition.

See ``README.md``, ``PREREGISTRATION.md``, and ``PROVENANCE.md``.
"""

from __future__ import annotations

from .calibration import (
    CalibrationMetrics,
    SimConfig,
    ground_truth,
    recover_coupling,
    run_calibration,
    score_recovery,
    simulate_phases,
)
from .cg002 import (
    CG002_NOISELESS_GATES,
    CG002_NOISY_GATES,
    CG002_THEOREM_GATE,
    CG002Metrics,
    build_cg002_ledger,
    dcb_phase_cohesiveness_rel_error,
    null_battery_fpr,
    recover_coupling_integral,
    run_cg002_calibration,
)
from .gates import (
    NOISELESS_GATES,
    NOISY_GATES,
    GateResult,
    GateVerdict,
    evaluate_gates,
    overall_verdict,
)
from .grid_data import (
    GridSystem,
    coupling_from_susceptance,
    dorfler_bullo_critical_coupling,
    ieee_39_new_england,
    natural_frequency_from_injection,
    wscc_9_bus,
)

__all__ = [
    "CalibrationMetrics",
    "SimConfig",
    "ground_truth",
    "recover_coupling",
    "run_calibration",
    "score_recovery",
    "simulate_phases",
    "NOISELESS_GATES",
    "NOISY_GATES",
    "GateResult",
    "GateVerdict",
    "evaluate_gates",
    "overall_verdict",
    "GridSystem",
    "coupling_from_susceptance",
    "dorfler_bullo_critical_coupling",
    "ieee_39_new_england",
    "natural_frequency_from_injection",
    "wscc_9_bus",
    "CG002_NOISELESS_GATES",
    "CG002_NOISY_GATES",
    "CG002_THEOREM_GATE",
    "CG002Metrics",
    "build_cg002_ledger",
    "dcb_phase_cohesiveness_rel_error",
    "null_battery_fpr",
    "recover_coupling_integral",
    "run_cg002_calibration",
]
