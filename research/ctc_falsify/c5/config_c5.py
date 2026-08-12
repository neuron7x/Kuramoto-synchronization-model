# SPDX-License-Identifier: MIT
"""C5 single source of truth. Constants live ONLY here (SSOT)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from research.ctc_falsify import config as l1

C5_ID: Final[str] = "CTC-FALSIFY-001-C5"

CLAIM: Final[str] = (
    "Decide the C4 OPEN: is the standard-estimand blindness an "
    "identifiability limit of these observables at this regime, or an "
    "estimator-quality gap? Measured by the best out-of-sample linear "
    "discriminant over the full gamma cross-spectral representation "
    "(magnitude + phase), with train/test seed-disjoint (no leakage)."
)
BOUNDARY: Final[str] = (
    "Scoped, in-silico, hypothesis-level, on the existing generative GT. A "
    "near-oracle UPPER BOUND, not a real estimator and not a CTC-theory "
    "verdict. Decisive only for THIS regime/observables."
)

# Train/test seeds are disjoint bands (leakage = inadmissible).
N_TRAIN_SEEDS: Final[int] = 24
N_TEST_SEEDS: Final[int] = 24
TEST_SEED_OFFSET: Final[int] = 500_003
CSD_NPERSEG: Final[int] = 256

# Pre-registered decision bands on the out-of-sample ROC-AUC.
AUC_CHANCE_HI: Final[float] = 0.60  # <= this => identifiability limit
AUC_SEPARABLE: Final[float] = 0.90  # >= this => estimator-quality gap

VERDICT_IDENTIFIABILITY_LIMIT: Final[str] = "C5_IDENTIFIABILITY_LIMIT"
VERDICT_ESTIMATOR_QUALITY_GAP: Final[str] = "C5_ESTIMATOR_QUALITY_GAP"
VERDICT_AMBIGUOUS: Final[str] = "C5_INADMISSIBLE_AMBIGUOUS"
VERDICT_LEAKAGE: Final[str] = "C5_INADMISSIBLE_TRAIN_TEST_LEAKAGE"

ALL_VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_IDENTIFIABILITY_LIMIT,
    VERDICT_ESTIMATOR_QUALITY_GAP,
    VERDICT_AMBIGUOUS,
    VERDICT_LEAKAGE,
)

_PKG: Final[Path] = Path(__file__).resolve().parent
SCHEMA_PATH: Final[Path] = _PKG / "schema" / "ctc_falsify_c5_result.schema.json"
EVIDENCE_DIR: Final[Path] = _PKG / "evidence"
RESULT_PATH: Final[Path] = EVIDENCE_DIR / "ctc_falsify_c5_result.json"


def train_seeds() -> list[int]:
    return [l1.SEED + i for i in range(N_TRAIN_SEEDS)]


def test_seeds() -> list[int]:
    return [l1.SEED + TEST_SEED_OFFSET + i for i in range(N_TEST_SEEDS)]


def config_hash() -> str:
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    h.update(Path(l1.__file__).read_bytes())
    return h.hexdigest()
