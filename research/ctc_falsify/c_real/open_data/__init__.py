# SPDX-License-Identifier: MIT
"""C-real open-data acquisition + A-gate binding (Tier-0 metadata-only).

Autonomously discovers open electrophysiology datasets, scores them
against the FROZEN C-real preregistration (paired spikes+LFP, >=2 areas,
trial structure, INDEPENDENT routing label, session-disjoint capacity,
reproducible public access), and fails closed. Network discovery is
strictly separated from pure admissibility logic; the latter is offline-
deterministic. Nothing here is a CTC-theory claim and no real arrays are
downloaded — coarse metadata cannot confirm an independent routing label,
so the honest ceiling for a metadata-only candidate is
``UNKNOWN_NEEDS_MANUAL_REVIEW`` (never promoted to admissible).
"""

from research.ctc_falsify.c_real.open_data.candidate import (
    OpenDataCandidate,
    classify_candidate,
    explain_candidate_blockers,
    has_minimal_c_real_requirements,
    terminal_verdict,
)

__all__ = [
    "OpenDataCandidate",
    "classify_candidate",
    "explain_candidate_blockers",
    "has_minimal_c_real_requirements",
    "terminal_verdict",
]
