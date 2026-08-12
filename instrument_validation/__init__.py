# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Instrument-validation gate for the Disha article artefact (PR #592).

Refuses to emit a verdict unless the scoring instrument has demonstrated:
  (i)   power ≥ 0.80 to detect the preregistered effect (positive control),
  (ii)  false-positive rate ≤ 0.05 across declared null families (negative control),
  (iii) separable resolution (observed inter-model delta > MDE) for any
        cross-model claim (discrimination).

If any of (i)+(ii)+(iii) is missing, the verdict is INVALID_INSTRUMENT,
not PASS/FAIL/NOT_DISTINGUISHED.
"""

from __future__ import annotations

from instrument_validation.capsule import Capsule, rerun_strict
from instrument_validation.claim_boundary import (
    FORBIDDEN_UNLESS_CERTIFIED,
    ClaimBoundaryViolation,
    claim_boundary_check,
    normalize_claim_text,
)
from instrument_validation.discrimination import (
    DiscriminationReport,
    DiscriminationVerdict,
    discriminate,
    mde_at_n31,
)
from instrument_validation.negative_control import (
    REQUIRED_NULLS,
    NegativeControlCertificate,
    run_negative_controls,
)
from instrument_validation.null_audit import REQUIRED_QUANTILES, NullAudit
from instrument_validation.positive_control import (
    PosControlCertificate,
    validate_instrument,
)
from instrument_validation.scope import InstrumentScope, scope_match
from instrument_validation.verdict import ClaimTier, ClaimType, Verdict, emit_verdict

__all__ = [
    "Capsule",
    "ClaimBoundaryViolation",
    "ClaimTier",
    "ClaimType",
    "DiscriminationReport",
    "DiscriminationVerdict",
    "FORBIDDEN_UNLESS_CERTIFIED",
    "InstrumentScope",
    "NegativeControlCertificate",
    "NullAudit",
    "PosControlCertificate",
    "REQUIRED_NULLS",
    "REQUIRED_QUANTILES",
    "Verdict",
    "claim_boundary_check",
    "discriminate",
    "emit_verdict",
    "mde_at_n31",
    "normalize_claim_text",
    "rerun_strict",
    "run_negative_controls",
    "scope_match",
    "validate_instrument",
]
