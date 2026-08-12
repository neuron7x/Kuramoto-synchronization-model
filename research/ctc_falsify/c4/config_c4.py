# SPDX-License-Identifier: MIT
"""C4 single source of truth. Constants live ONLY here (SSOT)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from research.ctc_falsify import config as l1

C4_ID: Final[str] = "CTC-FALSIFY-001-C4"

CLAIM: Final[str] = (
    "The privileged mean-gamma-phase-offset estimator that underwrote C3's "
    "'channel recoverable in principle' is itself admissible: it separates "
    "N+ from confounds, rejects confound-only draws, is genuinely directed "
    "(sign-flips), and never invents a channel at channel_strength == 0 "
    "across a common-drive sweep."
)
BOUNDARY: Final[str] = (
    "Scoped, in-silico, hypothesis-level. Audits ONLY the C3 boundary-probe "
    "estimator on the existing generative ground truth. NOT a CTC-theory "
    "verdict, NOT real data. Pass => C3's in-silico negative hardens; any "
    "failure => the C3 'recoverable in principle' claim is scoped/retracted, "
    "not the standard-estimand blindness finding."
)

# Pre-registered gate thresholds (no post-hoc tuning).
D_MIN: Final[float] = 1.0  # Cohen's d, N+ vs pooled confounds
FP_MAX: Final[float] = 0.05  # confound false-positive rate at the boundary
SIGN_FRAC: Final[float] = 0.90  # fraction of N+ seeds with a real sign flip
SWEEP_COMMON_DRIVE: Final[tuple[float, ...]] = (0.05, l1.COMMON_DRIVE, 1.0, 1.5)
SWEEP_SEEDS: Final[int] = 8

VERDICT_CANT_SEPARATE: Final[str] = "C4_INADMISSIBLE_ESTIMATOR_CANT_SEPARATE"
VERDICT_SIGNFLIP_BROKEN: Final[str] = "C4_INADMISSIBLE_SIGNFLIP_BROKEN"
VERDICT_CONFOUND_FALSE_POSITIVE: Final[str] = "C4_INADMISSIBLE_CONFOUND_FALSE_POSITIVE"
VERDICT_BOUNDARY_HARDENED: Final[str] = "C4_BOUNDARY_HARDENED"

ALL_VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_CANT_SEPARATE,
    VERDICT_SIGNFLIP_BROKEN,
    VERDICT_CONFOUND_FALSE_POSITIVE,
    VERDICT_BOUNDARY_HARDENED,
)

_PKG: Final[Path] = Path(__file__).resolve().parent
SCHEMA_PATH: Final[Path] = _PKG / "schema" / "ctc_falsify_c4_result.schema.json"
EVIDENCE_DIR: Final[Path] = _PKG / "evidence"
RESULT_PATH: Final[Path] = EVIDENCE_DIR / "ctc_falsify_c4_result.json"


def config_hash() -> str:
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    h.update(Path(l1.__file__).read_bytes())
    return h.hexdigest()
