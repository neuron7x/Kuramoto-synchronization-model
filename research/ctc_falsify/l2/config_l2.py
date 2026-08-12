# SPDX-License-Identifier: MIT
"""L2 single source of truth. Constants live ONLY here (SSOT)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from research.ctc_falsify import config as l1

L2_ID: Final[str] = "CTC-FALSIFY-001-L2"

CLAIM: Final[str] = (
    "On real paired LFP+spike data, the CTC causal claim (the gamma phase "
    "relation carries inter-areal routing) survives subtraction of a "
    "jointly-matched confound surrogate."
)
BOUNDARY: Final[str] = (
    "Scoped to the pre-committed dataset and the rate/waveform/SNR/common-drive "
    "jointly-matched surrogate defined here. Pre-data: KILLED_SCOPED/"
    "SURVIVED_INITIAL are unreachable until a dataset is bound (C3)."
)

# --- Fix #1: standardized residual estimand + single primary endpoint -----
# residual_z = (SFC_obs - mean(SFC_surr)) / std(SFC_surr) per pair-direction.
# Primary endpoint = fraction of pair-directions with residual_z > Z_GATE.
Z_GATE: Final[float] = 1.96
PRIMARY_ENDPOINT_DELTA: Final[float] = 0.10  # min fraction over surrogate share
# --- Fix #2: joint surrogate matching tolerances --------------------------
RATE_MATCH_TOL: Final[float] = 0.05  # |Δ mean-rate proxy| relative
SNR_MATCH_TOL: Final[float] = 0.05  # |Δ power| relative
N_SURROGATE: Final[int] = 200
# --- Fix #3: positive control (known-routing) recovery --------------------
NPLUS_RESIDUAL_MIN_Z: Final[float] = 3.0  # estimator must see a true channel
CONFOUND_RESIDUAL_MAX_Z: Final[float] = 1.96  # must NOT flag confound-only
# --- Fix #6: multiplicity -------------------------------------------------
HOLM_ALPHA: Final[float] = 0.01
# --- Fix #7: power --------------------------------------------------------
MDE_RESIDUAL_Z: Final[float] = 0.5  # min detectable standardized residual
MIN_SESSIONS: Final[int] = 8
# --- Fix #8: symmetric terminal thresholds --------------------------------
# KILLED and SURVIVED use the SAME endpoint magnitude and the SAME alpha.
SYMMETRIC_ALPHA: Final[float] = HOLM_ALPHA
SYMMETRIC_DELTA: Final[float] = PRIMARY_ENDPOINT_DELTA

# In-silico self-validation reuses the L1 generative ground truth.
N_VALIDATION_SEEDS: Final[int] = l1.N_NULL_SEEDS

VERDICT_INADMISSIBLE_NO_PAIRED_DATA: Final[str] = "INADMISSIBLE_NO_PAIRED_DATA"
VERDICT_INADMISSIBLE_DATASET_UNSUITABLE: Final[str] = "INADMISSIBLE_DATASET_UNSUITABLE"
VERDICT_INADMISSIBLE_SURROGATE_MISMATCH: Final[str] = "INADMISSIBLE_SURROGATE_MISMATCH"
VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND: Final[str] = "INADMISSIBLE_NPLUS_INSITU_BLIND"
VERDICT_INADMISSIBLE_UNDERPOWERED: Final[str] = "INADMISSIBLE_UNDERPOWERED"
VERDICT_KILLED_SCOPED: Final[str] = "KILLED_SCOPED"
VERDICT_SURVIVED_INITIAL: Final[str] = "SURVIVED_INITIAL"

ALL_VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_INADMISSIBLE_NO_PAIRED_DATA,
    VERDICT_INADMISSIBLE_DATASET_UNSUITABLE,
    VERDICT_INADMISSIBLE_SURROGATE_MISMATCH,
    VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND,
    VERDICT_INADMISSIBLE_UNDERPOWERED,
    VERDICT_KILLED_SCOPED,
    VERDICT_SURVIVED_INITIAL,
)

# --- C3: v2 time-reversed-surrogate directed estimator -------------------
# v1 (phase-randomization) was blind by its own gate. v2 uses a directed
# Phase-Slope Index with a time-reversed surrogate. SAME admissibility bar
# (NPLUS_RESIDUAL_MIN_Z / CONFOUND_RESIDUAL_MAX_Z) — the gate is not relaxed
# for v2; only the estimator changes.
ESTIMATOR_VERSION: Final[str] = "v2_time_reversed_psi"
PSI_NPERSEG: Final[int] = 512
V2_SCHEMA_PATH: Final[Path] = (
    Path(__file__).resolve().parent / "schema" / "ctc_falsify_l2v2_result.schema.json"
)
V2_RESULT_PATH: Final[Path] = (
    Path(__file__).resolve().parent / "evidence" / "ctc_falsify_l2v2_result.json"
)

_PKG: Final[Path] = Path(__file__).resolve().parent
SCHEMA_PATH: Final[Path] = _PKG / "schema" / "ctc_falsify_l2_result.schema.json"
EVIDENCE_DIR: Final[Path] = _PKG / "evidence"
RESULT_PATH: Final[Path] = EVIDENCE_DIR / "ctc_falsify_l2_result.json"


def config_hash() -> str:
    """Hash of BOTH SSOT files — L2 inherits L1 constants, so both pin."""
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    h.update(Path(l1.__file__).read_bytes())
    return h.hexdigest()
