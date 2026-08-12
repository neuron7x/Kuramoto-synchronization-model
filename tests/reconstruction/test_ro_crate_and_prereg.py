# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for RO-Crate 1.2 + Workflow Run RO-Crate + OSF/AsPredicted prereg.

Publication-readiness layer (epic #640). These tests pin the structural
validity of the emitted provenance and preregistration artifacts. They
do NOT assert any scientific validity claim — only that the crate /
prereg are spec-shaped and traceable to the capsule.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from research.reconstruction.prereg import (
    ASPREDICTED_PREREG_FILENAME,
    OSF_PREREG_FILENAME,
    build_aspredicted_prereg,
    build_osf_secondary_data_prereg,
    emit_prereg,
)
from research.reconstruction.reconstruction_capsule import (
    ReconstructionCapsule,
    ReconstructionStatus,
    build_reconstruction_capsule,
)
from research.reconstruction.ro_crate import (
    CAPSULE_FILENAME,
    METADATA_FILENAME,
    RO_CRATE_CONTEXT,
    RO_CRATE_PROFILE,
    WFRUN_PROCESS_PROFILE,
    WFRUN_WORKFLOW_PROFILE,
    build_ro_crate_metadata,
    emit_ro_crate,
)

_DRIVER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_x10r_d003_dov_dry_run.py"


def _capsule() -> ReconstructionCapsule:
    return build_reconstruction_capsule(
        payload_sha256=hashlib.sha256(b"payload").hexdigest(),
        scope_id="x10r/test/2026-06-17",
        inferred_density=0.05,
        spectral_radius=1.5e6,
        L1_error_row=1.0e-10,
        L1_error_col=1.0e-10,
        n_nodes=80,
        z_calibrated=12.34,
        prng_seed=42,
        ground_truth_recovery_cert_id=hashlib.sha256(b"gt").hexdigest(),
        kuramoto_recovery_cert_id=hashlib.sha256(b"kr").hexdigest(),
        reconstruction_status=ReconstructionStatus.GROUND_TRUTH_RECOVERED,
        code_sha=hashlib.sha256(b"code").hexdigest(),
        metrics_sha=hashlib.sha256(b"metrics").hexdigest(),
    )


def _graph_by_id(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entity["@id"]: entity for entity in metadata["@graph"]}


# ---------------------------------------------------------------------------
# RO-Crate 1.2 structural validity
# ---------------------------------------------------------------------------


def test_crate_has_ro_crate_1_2_context() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    assert metadata["@context"] == RO_CRATE_CONTEXT
    assert "@graph" in metadata
    assert isinstance(metadata["@graph"], list)


def test_crate_has_metadata_descriptor_and_root_dataset() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)

    descriptor = by_id[METADATA_FILENAME]
    assert descriptor["@type"] == "CreativeWork"
    assert descriptor["about"] == {"@id": "./"}

    root = by_id["./"]
    assert root["@type"] == "Dataset"


def test_root_dataset_conforms_to_ro_crate_1_2() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)
    conforms = {c["@id"] for c in by_id["./"]["conformsTo"]}
    assert RO_CRATE_PROFILE in conforms


def test_metadata_descriptor_declares_all_three_profiles() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)
    conforms = {c["@id"] for c in by_id[METADATA_FILENAME]["conformsTo"]}
    assert {RO_CRATE_PROFILE, WFRUN_PROCESS_PROFILE, WFRUN_WORKFLOW_PROFILE} <= conforms


def test_capsule_file_part_present_and_referenced() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)
    parts = {p["@id"] for p in by_id["./"]["hasPart"]}
    assert CAPSULE_FILENAME in parts
    assert by_id[CAPSULE_FILENAME]["@type"] == "File"


def test_every_graph_entity_has_id_and_type() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    for entity in metadata["@graph"]:
        assert "@id" in entity
        assert "@type" in entity


# ---------------------------------------------------------------------------
# Workflow Run RO-Crate entities
# ---------------------------------------------------------------------------


def test_workflow_run_entities_present() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)

    types_by_id = {eid: e["@type"] for eid, e in by_id.items()}
    create_actions = [eid for eid, t in types_by_id.items() if t == "CreateAction"]
    organize_actions = [eid for eid, t in types_by_id.items() if t == "OrganizeAction"]

    # reconstruction + Gate 5 + Gate 6 = three CreateActions, one OrganizeAction.
    assert len(create_actions) >= 3
    assert len(organize_actions) >= 1


def test_pipeline_organize_action_orders_the_three_gates() -> None:
    metadata = build_ro_crate_metadata(_capsule())
    by_id = _graph_by_id(metadata)
    organize = next(e for e in metadata["@graph"] if e["@type"] == "OrganizeAction")
    ordered = [o["@id"] for o in organize["object"]]
    assert len(ordered) == 3
    # The instrument is the computational workflow entity.
    workflow_id = organize["instrument"]["@id"]
    assert by_id[workflow_id]["@type"] == ["SoftwareSourceCode", "ComputationalWorkflow"]


def test_crate_is_deterministic_for_same_capsule() -> None:
    cap = _capsule()
    a = json.dumps(build_ro_crate_metadata(cap), sort_keys=True)
    b = json.dumps(build_ro_crate_metadata(cap), sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# emit_ro_crate writes valid JSON to disk
# ---------------------------------------------------------------------------


def test_emit_ro_crate_writes_metadata_and_capsule(tmp_path: Path) -> None:
    out = emit_ro_crate(_capsule(), tmp_path)
    assert out.name == METADATA_FILENAME
    assert out.exists()
    assert (tmp_path / CAPSULE_FILENAME).exists()
    parsed = json.loads(out.read_text())
    assert parsed["@context"] == RO_CRATE_CONTEXT


def test_emit_ro_crate_accepts_dry_run_dict(tmp_path: Path) -> None:
    capsule_dict = {
        "scoped_tier": "within_validated_domain",
        "input_label": "TEST",
        "payload_sha256": hashlib.sha256(b"x").hexdigest(),
        "d003_dry_run_capsule_version": 1,
    }
    out = emit_ro_crate(capsule_dict, tmp_path)
    parsed = json.loads(out.read_text())
    by_id = {e["@id"]: e for e in parsed["@graph"]}
    assert by_id["./"]["@type"] == "Dataset"


# ---------------------------------------------------------------------------
# OSF + AsPredicted prereg
# ---------------------------------------------------------------------------


def test_osf_prereg_has_required_sections() -> None:
    md = build_osf_secondary_data_prereg({"scoped_tier": "within_validated_domain"})
    for section in (
        "Study information",
        "Hypotheses",
        "Design plan",
        "Sampling plan",
        "Analysis plan",
        "Decision rules",
    ):
        assert section in md


def test_aspredicted_prereg_has_nine_questions() -> None:
    md = build_aspredicted_prereg({"scoped_tier": "out_of_validated_domain"})
    for n in range(1, 10):
        assert f"**{n}." in md


def test_emit_prereg_writes_both_templates(tmp_path: Path) -> None:
    paths = emit_prereg({"scoped_tier": "within_validated_domain"}, tmp_path)
    assert (tmp_path / OSF_PREREG_FILENAME).exists()
    assert (tmp_path / ASPREDICTED_PREREG_FILENAME).exists()
    assert paths["osf"].read_text().strip() != ""
    assert paths["aspredicted"].read_text().strip() != ""


# ---------------------------------------------------------------------------
# Dry-run integration: prereg + crate emitted next to the capsule
# ---------------------------------------------------------------------------


def _load_driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d003_driver_rocrate", _DRIVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver() -> ModuleType:
    return _load_driver()


def test_dry_run_emits_prereg_and_crate_next_to_capsule(
    driver: ModuleType, tmp_path: Path
) -> None:
    out = tmp_path / "capsule.json"
    capsule = driver.run_dry_run(marginals_path=None, certificate_path=None, out_path=out)

    crate = tmp_path / METADATA_FILENAME
    osf = tmp_path / OSF_PREREG_FILENAME
    asp = tmp_path / ASPREDICTED_PREREG_FILENAME
    assert crate.exists()
    assert osf.exists()
    assert asp.exists()

    assert capsule["ro_crate_metadata_path"] == str(crate)
    assert capsule["osf_prereg_path"] == str(osf)
    assert capsule["aspredicted_prereg_path"] == str(asp)

    parsed = json.loads(crate.read_text())
    assert parsed["@context"] == RO_CRATE_CONTEXT
