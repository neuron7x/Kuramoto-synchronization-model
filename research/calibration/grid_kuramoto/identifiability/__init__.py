# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CALIB-GRID-001 upgrade lineage #2 — graded identifiability front-gate.

Reliability / instrument-honesty infrastructure on the *already
calibrated* swing estimator (parents: PR #749 CALIB-GRID-001, PR #751
R1). **Not** a scientific claim and **not** a closure of the frozen
``noisy.frobenius`` gate: it makes the instrument *declare* that it
fails there instead of silently emitting a misleading ``K̂``.

The theory, the exact score formula and the pre-committed REFUSE
threshold are in ``THRESHOLD_PROVENANCE.md`` (committed before any
validation, no-peek-bound by a drift test). This package only re-runs
the FROZEN calibration cases through the new front-gate and serialises
the self-report; it does not touch ``PREREGISTRATION.md``,
``gates.py``, the seeds, σ, θ₀ or the decision rule.
"""

from __future__ import annotations

from .validate import build_identifiability_ledger

__all__ = ["build_identifiability_ledger"]
