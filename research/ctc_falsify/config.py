# SPDX-License-Identifier: MIT
"""CTC-FALSIFY-001 — single source of truth for every constant.

Duplicating any constant outside this module is a construct-validity break
(config/code SSOT drift) and is asserted against by the test-suite.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

EXPERIMENT_ID: Final[str] = "CTC-FALSIFY-001"

CLAIM: Final[str] = (
    "The standard CTC analysis pipeline (gamma-band PLV + coherence) "
    "distinguishes a true phase-gated inter-population communication channel "
    "from confound-only signals (common drive / rate / SNR) at the canonical "
    "effect size."
)

BOUNDARY: Final[str] = (
    "Scoped strictly to: a two-population Sakaguchi-Kuramoto generative ground "
    "truth and the naive PLV+coherence pipeline emulated here. NOT a claim "
    "about the CTC theory; NOT a claim on real neural data. KILLED_SCOPED / "
    "SURVIVED_INITIAL require a bound real electrophysiology dataset (L2)."
)

# --- Generative model (Sakaguchi-Kuramoto two-population) -----------------
SEED: Final[int] = 20260516
N_OSC: Final[int] = 64  # oscillators per population
T_STEPS: Final[int] = 4096
DT: Final[float] = 1.0e-3  # s
F0: Final[float] = 60.0  # gamma carrier (Hz)
FREQ_SIGMA: Final[float] = 2.0  # natural-frequency spread (Hz)
K_INTRA: Final[float] = 6.0  # within-population coupling
SAKAGUCHI_LAG: Final[float] = 0.20  # phase frustration (rad)

# Confound / channel knobs (dimensionless)
CHANNEL_STRENGTH_TRUE: Final[float] = 0.45  # directed A->B phase coupling for N+
COMMON_DRIVE: Final[float] = 0.55  # shared stochastic input (N1)
RATE_MOD_DEPTH: Final[float] = 0.70  # correlated amplitude/rate envelope (N2)
SNR_LOW: Final[float] = 0.8  # additive-noise SNR for the N3 confound

# --- Standard-pipeline canonical thresholds (pre-registered) -------------
# The literature treats inter-areal gamma PLV/coherence above these as
# evidence of CTC routing. We do NOT tune these to the result.
CANON_PLV: Final[float] = 0.30
CANON_COH: Final[float] = 0.20
GAMMA_BAND_HALFWIDTH: Final[float] = 8.0  # Hz around F0 for band measures

# --- Admissibility (fail-closed) -----------------------------------------
N_NULL_SEEDS: Final[int] = 24  # independent draws per null family / N+
NPLUS_MIN_RECOVERY: Final[float] = 0.90  # N+ must be detected on >=90% seeds
MIN_SEEDS_FOR_POWER: Final[int] = 12

# --- Verdict vocabulary (mirrors the schema enum; single source) ---------
VERDICT_INADMISSIBLE_NO_GROUNDTRUTH: Final[str] = "INADMISSIBLE_NO_GENERATIVE_GROUNDTRUTH"
VERDICT_INADMISSIBLE_ESTIMATOR_BLIND: Final[str] = "INADMISSIBLE_ESTIMATOR_BLIND"
VERDICT_INADMISSIBLE_CIRCULAR: Final[str] = "INADMISSIBLE_CIRCULAR_PIPELINE"
VERDICT_INADMISSIBLE_UNDERPOWERED: Final[str] = "INADMISSIBLE_UNDERPOWERED"
VERDICT_INADMISSIBLE_NO_REAL_DATA: Final[str] = "INADMISSIBLE_NO_REAL_DATA"
VERDICT_KILLED_SCOPED: Final[str] = "KILLED_SCOPED"
VERDICT_SURVIVED_INITIAL: Final[str] = "SURVIVED_INITIAL"

ALL_VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_INADMISSIBLE_NO_GROUNDTRUTH,
    VERDICT_INADMISSIBLE_ESTIMATOR_BLIND,
    VERDICT_INADMISSIBLE_CIRCULAR,
    VERDICT_INADMISSIBLE_UNDERPOWERED,
    VERDICT_INADMISSIBLE_NO_REAL_DATA,
    VERDICT_KILLED_SCOPED,
    VERDICT_SURVIVED_INITIAL,
)

NULL_FAMILIES: Final[tuple[str, ...]] = ("N1_COMMON_DRIVE", "N2_RATE", "N3_SNR")

# --- Paths ----------------------------------------------------------------
_PKG_ROOT: Final[Path] = Path(__file__).resolve().parent
SCHEMA_PATH: Final[Path] = _PKG_ROOT / "schema" / "ctc_falsify_001_result.schema.json"
EVIDENCE_DIR: Final[Path] = _PKG_ROOT / "evidence"
RESULT_PATH: Final[Path] = EVIDENCE_DIR / "ctc_falsify_001_result.json"


def config_hash() -> str:
    """Deterministic hash of this SSOT file's bytes — pins every constant."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
