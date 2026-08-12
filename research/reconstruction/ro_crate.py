# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""RO-Crate 1.2 + Workflow Run RO-Crate provenance for X-10R capsules.

PUBLICATION-READINESS LAYER — NOT METHOD-VALIDITY (epic #640).

This module wraps an existing :class:`ReconstructionCapsule` (or the
D-003 real-data dry-run capsule dict) in machine-readable provenance so
a reviewer / archive can ingest the whole pipeline without re-running
it. Nothing here makes or strengthens a scientific claim: it only
*describes* artifacts that the validity layer already produced.

Two specifications are emitted, both spec-valid and minimal:

  * **RO-Crate 1.2** (https://w3id.org/ro/crate/1.2/) — a JSON-LD
    ``ro-crate-metadata.json`` whose root is a ``Dataset`` that
    ``conformsTo`` the RO-Crate 1.2 profile and references the capsule
    inputs / outputs / workflow as first-class entities.

  * **Workflow Run RO-Crate** (https://w3id.org/ro/wfrun/process/0.5
    and .../workflow/0.5) — ``CreateAction`` / ``OrganizeAction``
    entities describing the reconstruction → Gate 5 / Gate 6 → capsule
    pipeline as an executed process run.

The emitted crate is deterministic for a given capsule (sorted keys,
stable @ids), so it can itself be hashed and replay-checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.reconstruction.reconstruction_capsule import (
    ReconstructionCapsule,
    serialise_reconstruction_capsule,
)

RO_CRATE_CONTEXT: str = "https://w3id.org/ro/crate/1.2/context"
RO_CRATE_PROFILE: str = "https://w3id.org/ro/crate/1.2"
WFRUN_PROCESS_PROFILE: str = "https://w3id.org/ro/wfrun/process/0.5"
WFRUN_WORKFLOW_PROFILE: str = "https://w3id.org/ro/wfrun/workflow/0.5"

METADATA_FILENAME: str = "ro-crate-metadata.json"
CAPSULE_FILENAME: str = "reconstruction_capsule.json"

# Stable @ids for the workflow-run entities. Kept as module constants so
# tests can assert their presence without string drift.
_ROOT_ID: str = "./"
_METADATA_ID: str = "ro-crate-metadata.json"
_RECONSTRUCTION_ACTION_ID: str = "#action-cimini-squartini-reconstruction"
_GATE5_ACTION_ID: str = "#action-gate5-domain-of-validity"
_GATE6_ACTION_ID: str = "#action-gate6-precursor-discriminative"
_PIPELINE_ORGANIZE_ID: str = "#organize-x10r-pipeline"
_WORKFLOW_ID: str = "#workflow-x10r-reconstruction-pipeline"


def _capsule_payload(capsule: ReconstructionCapsule | dict[str, Any]) -> dict[str, Any]:
    """Normalise either capsule form to a plain serialisable dict."""
    if isinstance(capsule, ReconstructionCapsule):
        return serialise_reconstruction_capsule(capsule)
    return dict(capsule)


def _capsule_identifier(payload: dict[str, Any]) -> str:
    """A stable human/machine identifier for the wrapped capsule."""
    for key in ("capsule_id", "cert_id", "d003_dry_run_capsule_version"):
        value = payload.get(key)
        if value:
            return str(value)
    return "unidentified-capsule"


def build_ro_crate_metadata(
    capsule: ReconstructionCapsule | dict[str, Any],
    *,
    capsule_filename: str = CAPSULE_FILENAME,
) -> dict[str, Any]:
    """Build the RO-Crate 1.2 + Workflow Run RO-Crate JSON-LD graph.

    The returned object is the full ``ro-crate-metadata.json`` content:
    a JSON-LD document with ``@context`` pinned to the RO-Crate 1.2
    context and a ``@graph`` whose root ``Dataset`` ``conformsTo`` the
    RO-Crate 1.2 profile and the Workflow Run RO-Crate process /
    workflow profiles.

    The crate is descriptive provenance only. It asserts no validity
    claim beyond what ``capsule.reconstruction_status`` already records.
    """
    payload = _capsule_payload(capsule)
    capsule_id = _capsule_identifier(payload)
    status = str(payload.get("reconstruction_status", payload.get("scoped_tier", "unknown")))

    # --- Metadata descriptor (mandatory RO-Crate entity) ----------------
    metadata_descriptor: dict[str, Any] = {
        "@id": _METADATA_ID,
        "@type": "CreativeWork",
        "conformsTo": [
            {"@id": RO_CRATE_PROFILE},
            {"@id": WFRUN_PROCESS_PROFILE},
            {"@id": WFRUN_WORKFLOW_PROFILE},
        ],
        "about": {"@id": _ROOT_ID},
    }

    # --- Root Dataset ---------------------------------------------------
    root_dataset: dict[str, Any] = {
        "@id": _ROOT_ID,
        "@type": "Dataset",
        "name": f"X-10R reconstruction capsule {capsule_id}",
        "description": (
            "Machine-readable provenance crate wrapping a Cimini-Squartini "
            "reconstruction capsule. Publication-readiness packaging; the "
            "scientific verdict is carried by the capsule's "
            "reconstruction_status field, not by this crate."
        ),
        "conformsTo": [
            {"@id": RO_CRATE_PROFILE},
            {"@id": WFRUN_PROCESS_PROFILE},
            {"@id": WFRUN_WORKFLOW_PROFILE},
        ],
        "datePublished": "2026-06-17",
        "license": {"@id": "https://spdx.org/licenses/MIT.html"},
        "hasPart": [
            {"@id": capsule_filename},
        ],
        "mentions": [
            {"@id": _RECONSTRUCTION_ACTION_ID},
            {"@id": _GATE5_ACTION_ID},
            {"@id": _GATE6_ACTION_ID},
            {"@id": _PIPELINE_ORGANIZE_ID},
            {"@id": _WORKFLOW_ID},
        ],
    }

    # --- Capsule output artifact ---------------------------------------
    capsule_file: dict[str, Any] = {
        "@id": capsule_filename,
        "@type": "File",
        "name": "ReconstructionCapsule (JSON)",
        "encodingFormat": "application/json",
        "description": (f"Bit-exact reproducibility capsule; reconstruction_status={status!r}."),
        "sha256": str(payload.get("payload_sha256", payload.get("cert_id", ""))),
    }

    # --- Workflow (the abstract reconstruction pipeline) ---------------
    workflow: dict[str, Any] = {
        "@id": _WORKFLOW_ID,
        "@type": ["SoftwareSourceCode", "ComputationalWorkflow"],
        "name": "X-10R reconstruction -> Gate5/Gate6 -> capsule pipeline",
        "programmingLanguage": "Python",
        "description": (
            "Cimini-Squartini fitness reconstruction, followed by the "
            "Gate 5 domain-of-validity check and the Gate 6 precursor "
            "discriminative test, sealed into a ReconstructionCapsule."
        ),
    }

    # --- Workflow Run entities (CreateAction / OrganizeAction) ---------
    reconstruction_action: dict[str, Any] = {
        "@id": _RECONSTRUCTION_ACTION_ID,
        "@type": "CreateAction",
        "name": "Cimini-Squartini reconstruction",
        "description": (
            "Maximum-entropy reconstruction of the weighted adjacency from "
            "node strengths (inference, not observation)."
        ),
        "result": {"@id": capsule_filename},
    }
    gate5_action: dict[str, Any] = {
        "@id": _GATE5_ACTION_ID,
        "@type": "CreateAction",
        "name": "Gate 5 domain-of-validity check",
        "description": (
            "Scoped-tier domain-of-validity gate (within / out-of / "
            "insufficient-certificate). No bank-level inference claim."
        ),
        "object": {"@id": _RECONSTRUCTION_ACTION_ID},
    }
    gate6_action: dict[str, Any] = {
        "@id": _GATE6_ACTION_ID,
        "@type": "CreateAction",
        "name": "Gate 6 precursor discriminative test",
        "description": (
            "Instrument-validated Kuramoto precursor test on the inferred "
            "network; verdict binds to the reconstruction class."
        ),
        "object": {"@id": _GATE5_ACTION_ID},
    }
    pipeline_organize: dict[str, Any] = {
        "@id": _PIPELINE_ORGANIZE_ID,
        "@type": "OrganizeAction",
        "name": "X-10R pipeline run",
        "description": (
            "Ordered orchestration: reconstruction -> Gate 5 -> Gate 6 -> capsule sealing."
        ),
        "instrument": {"@id": _WORKFLOW_ID},
        "object": [
            {"@id": _RECONSTRUCTION_ACTION_ID},
            {"@id": _GATE5_ACTION_ID},
            {"@id": _GATE6_ACTION_ID},
        ],
        "result": {"@id": capsule_filename},
    }

    graph: list[dict[str, Any]] = [
        metadata_descriptor,
        root_dataset,
        capsule_file,
        workflow,
        reconstruction_action,
        gate5_action,
        gate6_action,
        pipeline_organize,
    ]

    return {"@context": RO_CRATE_CONTEXT, "@graph": graph}


def emit_ro_crate(
    capsule: ReconstructionCapsule | dict[str, Any],
    out_dir: Path,
    *,
    write_capsule: bool = True,
) -> Path:
    """Write ``ro-crate-metadata.json`` (and the capsule) into ``out_dir``.

    Returns the path to the written ``ro-crate-metadata.json``. The
    capsule payload is co-located so the crate's ``hasPart`` reference
    resolves; pass ``write_capsule=False`` if the capsule file is
    already present alongside.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = _capsule_payload(capsule)

    if write_capsule:
        capsule_path = out_dir / CAPSULE_FILENAME
        capsule_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    metadata = build_ro_crate_metadata(capsule)
    metadata_path = out_dir / METADATA_FILENAME
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return metadata_path
