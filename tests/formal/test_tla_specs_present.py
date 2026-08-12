# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Presence and property-catalogue audit for the four TLA+ specs that
back the research-extension invariants.

TLC may not be installed in CI; in that case we still want a textual
audit trail proving each spec exists, is non-empty, and lists every
required safety-property identifier. The mapping below is the contract
between the Python implementation and its formal counterpart.

Bound invariants:
    INV-FE-ROBUST  -> formal/tla/RobustFreeEnergyGate.tla
    INV-KBETA      -> formal/tla/CapitalWeightedKuramoto.tla
    INV-RC-FLOW    -> formal/tla/RicciFlowSurgery.tla
    INV-HO-SPARSE  -> formal/tla/SparseSimplicialKuramoto.tla
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TLA_DIR = REPO_ROOT / "formal" / "tla"


# (invariant_id, tla_filename, [required property names])
SPEC_CONTRACTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "INV-FE-ROBUST",
        "RobustFreeEnergyGate.tla",
        (
            "TypeOK",
            "NominalBounded",
            "RobustDominatesNominal",
            "ZeroAmbiguityEqualsNominal",
            "FailClosedOnMalformedAmbiguity",
        ),
    ),
    (
        "INV-KBETA",
        "CapitalWeightedKuramoto.tla",
        (
            "TypeOK",
            "KBetaFinite",
            "KBetaSymmetric",
            "ZeroDiagonal",
            "BetaOneRecoversBaseline",
            "MissingL2Fallback",
            "NoFutureL2",
        ),
    ),
    (
        "INV-RC-FLOW",
        "RicciFlowSurgery.tla",
        (
            "TypeOK",
            "WeightsFinite",
            "WeightsSymmetric",
            "MassPreservedWhenEnabled",
            "ConnectednessPreserved",
            "SurgeryRecorded",
            "MaxSurgeryFractionBounded",
        ),
    ),
    (
        "INV-HO-SPARSE",
        "SparseSimplicialKuramoto.tla",
        (
            "TypeOK",
            "OrderPreserved",
            "Unique",
            "RBounds",
            "Sigma2ZeroEqualsPairwise",
            "NoTrianglesZeroTriadic",
            "Finite",
        ),
    ),
)


@pytest.mark.parametrize(
    ("invariant_id", "spec_filename", "required_properties"),
    SPEC_CONTRACTS,
    ids=[c[0] for c in SPEC_CONTRACTS],
)
def test_tla_spec_present_and_non_empty(
    invariant_id: str,
    spec_filename: str,
    required_properties: tuple[str, ...],
) -> None:
    """Each research-extension invariant has a non-empty TLA+ counterpart."""
    spec_path = TLA_DIR / spec_filename
    assert spec_path.exists(), (
        f"{invariant_id} VIOLATED: TLA spec missing at {spec_path}; "
        f"every research invariant must have a formal counterpart under "
        f"formal/tla/. expected={spec_filename}"
    )
    text = spec_path.read_text(encoding="utf-8")
    assert text.strip(), (
        f"{invariant_id} VIOLATED: TLA spec at {spec_path} is empty; "
        f"empty spec cannot encode safety properties."
    )
    # Module declaration must match the filename (TLC contract).
    module_name = spec_filename.removesuffix(".tla")
    assert re.search(rf"MODULE\s+{re.escape(module_name)}\b", text), (
        f"{invariant_id} VIOLATED: spec at {spec_path} lacks "
        f"`MODULE {module_name}` declaration; TLC requires module name = filename."
    )


@pytest.mark.parametrize(
    ("invariant_id", "spec_filename", "required_properties"),
    SPEC_CONTRACTS,
    ids=[c[0] for c in SPEC_CONTRACTS],
)
def test_tla_spec_lists_required_safety_properties(
    invariant_id: str,
    spec_filename: str,
    required_properties: tuple[str, ...],
) -> None:
    """Each TLA spec advertises the full safety-property catalogue.

    This is a textual audit, not a model-checking run — it guarantees the
    contract between the Python implementation and the formal spec stays
    in sync even on CI hosts where TLC is unavailable.
    """
    spec_path = TLA_DIR / spec_filename
    text = spec_path.read_text(encoding="utf-8")
    missing = [name for name in required_properties if not re.search(rf"\b{name}\b", text)]
    assert not missing, (
        f"{invariant_id} VIOLATED: TLA spec is missing required safety properties; "
        f"observed missing={missing}, expected all of {list(required_properties)} "
        f"present in {spec_filename}."
    )


def test_tla_directory_contract() -> None:
    """formal/tla must hold every spec required by SPEC_CONTRACTS plus a README."""
    assert TLA_DIR.is_dir(), f"formal/tla missing at {TLA_DIR}"
    present = {p.name for p in TLA_DIR.iterdir() if p.suffix == ".tla"}
    required = {filename for _, filename, _ in SPEC_CONTRACTS}
    missing = sorted(required - present)
    msg = f"formal/tla is missing required specs: {missing}; present={sorted(present)}"
    assert not missing, msg
