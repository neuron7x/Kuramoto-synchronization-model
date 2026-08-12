# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CALIB-GRID-002 — integral / weak-form swing identifier calibration.

A NEW pre-registered lineage (not a refinement of the frozen
CALIB-GRID-001 / R1 gates). It attacks the proven differential-class
boundary with the weak / integral form (Messenger & Bortz, *Weak
SINDy*, J. Comput. Phys. 443 (2021) 110525): the phase is never
double-differentiated; it enters only inside integrals against the
analytic derivatives of a compactly supported test function.

See ``PREREGISTRATION_002.yaml``, ``PROVENANCE_002.md``, ``RESULTS.md``.
"""

from __future__ import annotations

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

__all__ = [
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
