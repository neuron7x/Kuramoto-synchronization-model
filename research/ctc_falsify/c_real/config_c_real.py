# SPDX-License-Identifier: MIT
"""C-real SSOT. Constants — including the FROZEN dataset selection rule —
live ONLY here. config_hash pins them; the prereg is sealed by this hash
*before* any dataset is downloaded or inspected.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from research.ctc_falsify import config as l1

C_REAL_ID: Final[str] = "CTC-FALSIFY-001-C-REAL"

CLAIM: Final[str] = (
    "On real paired LFP+spike data, the causal CTC claim (the gamma phase "
    "relation carries inter-areal routing) is supported iff the "
    "C5-validated full gamma cross-spectral discriminant separates an "
    "INDEPENDENTLY manipulated routing-ON vs routing-OFF condition out of "
    "sample, above a jointly-matched confound surrogate, while the standard "
    "scalar estimands do not."
)
BOUNDARY: Final[str] = (
    "Scoped to the pre-committed dataset + pipeline. NOT a universal "
    "CTC-theory verdict. There is NO toggleable ground truth in real data: "
    "the routing label MUST come from an independent experimental "
    "manipulation (attention in/out with behavioural readout, or "
    "opto/microstim perturbation). Absent that, the line is UNTESTABLE by "
    "this protocol — reported, not forced."
)

# --- FROZEN dataset selection rule (pre-committed; no data touched) -------
# Deterministic: the FIRST source satisfying ALL criteria, by this fixed
# alphabetical source order, is bound at the C-real-data A-gate. Recorded
# here so selection cannot be post-hoc (garden-of-forking-paths closed).
DATASET_INCLUSION: Final[tuple[str, ...]] = (
    "simultaneous LFP+spikes in >=2 areas",
    "an independent routing manipulation (attention cue / opto / microstim)",
    "open licence + versioned, content-addressable dump",
    "trial structure permitting a jointly-matched confound surrogate",
)
DATASET_SOURCE_ORDER: Final[tuple[str, ...]] = (
    "allen_visual_coding_neuropixels",
    "crcns_pfc_2",
    "crcns_v1_*",
    "published_ctc_fries_lab_if_open",
)

# --- Pre-registered thresholds (carried from L2/C4/C5; no post-hoc tune) --
ESTIMATOR: Final[str] = "c5_full_gamma_cross_spectral_discriminant"  # scalar estimands rejected
PRIMARY_ENDPOINT: Final[str] = "OOS ROC-AUC, routing-ON vs routing-OFF, train/test split-disjoint"
AUC_SUPPORT_MIN: Final[float] = 0.70  # support requires OOS AUC >= this on real data
AUC_CHANCE_HI: Final[float] = 0.60  # <= this with N+ control present => KILLED_SCOPED
HOLM_ALPHA: Final[float] = 0.01
MDE_AUC: Final[float] = 0.65  # min detectable; undershoot power => underpowered
MIN_SESSIONS: Final[int] = 8
N_SURROGATE: Final[int] = 200  # jointly rate∧power∧common-drive matched (L2 fix #2)

VERDICT_NO_PAIRED_DATA: Final[str] = "INADMISSIBLE_NO_PAIRED_DATA"
VERDICT_NO_INDEPENDENT_LABEL: Final[str] = "INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL"
VERDICT_DATASET_UNSUITABLE: Final[str] = "INADMISSIBLE_DATASET_UNSUITABLE"  # P-replication gate
VERDICT_UNDERPOWERED: Final[str] = "INADMISSIBLE_UNDERPOWERED"
VERDICT_KILLED_SCOPED: Final[str] = "KILLED_SCOPED"
VERDICT_SURVIVED_INITIAL: Final[str] = "SURVIVED_INITIAL"

ALL_VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_NO_PAIRED_DATA,
    VERDICT_NO_INDEPENDENT_LABEL,
    VERDICT_DATASET_UNSUITABLE,
    VERDICT_UNDERPOWERED,
    VERDICT_KILLED_SCOPED,
    VERDICT_SURVIVED_INITIAL,
)

_PKG: Final[Path] = Path(__file__).resolve().parent
SCHEMA_PATH: Final[Path] = _PKG / "schema" / "ctc_falsify_c_real_result.schema.json"
EVIDENCE_DIR: Final[Path] = _PKG / "evidence"
RESULT_PATH: Final[Path] = EVIDENCE_DIR / "ctc_falsify_c_real_result.json"


def config_hash() -> str:
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    h.update(Path(l1.__file__).read_bytes())
    return h.hexdigest()
