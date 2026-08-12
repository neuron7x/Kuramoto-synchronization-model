# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the flagship population-frame gate (RES-006).

POSITIVE: the canonical, complete frame validates (exit 0).
NEGATIVE: a frame missing inclusion/exclusion -> RED; a frame asserting external
generalization beyond the snapshot -> FLAGGED/RED; a frame missing the digest ->
RED. Structural negatives run with digest verification off so they isolate the
field being tested.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.ci import check_population_frame as gate

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / "data" / "frames" / "flagship_population.json"


@pytest.fixture()
def base_doc() -> dict:
    return json.loads(CANONICAL.read_text(encoding="utf-8"))


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "frame.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# POSITIVE                                                                     #
# --------------------------------------------------------------------------- #

def test_canonical_frame_passes_with_digest_verification():
    """The real manifest is complete AND its digest reproduces from the tree."""
    assert gate.run(CANONICAL, REPO_ROOT, verify_digest=True) == 0


def test_canonical_frame_passes_structure_only(base_doc, tmp_path):
    p = _write(tmp_path, base_doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 0


def test_canonical_declares_infra_interpretation(base_doc):
    """Guard the honest interpretation choice: infra-modules, not markets."""
    assert base_doc["interpretation"] == "infrastructure-modules"
    assert base_doc["generalizes_beyond_snapshot"] is False


# --------------------------------------------------------------------------- #
# NEGATIVE — missing inclusion/exclusion -> RED                                #
# --------------------------------------------------------------------------- #

def test_missing_inclusion_rules_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    del doc["inclusion_rules"]
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_missing_exclusion_rules_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    del doc["exclusion_rules"]
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_empty_exclusion_rules_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["exclusion_rules"] = []
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE — external generalization beyond the snapshot -> FLAGGED/RED        #
# --------------------------------------------------------------------------- #

def test_boolean_external_generalization_is_flagged(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["generalizes_beyond_snapshot"] = True
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_external_validity_claim_field_is_flagged(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["external_validity_claim"] = "holds for other GeoSync-like repos"
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_free_text_generalization_claim_is_flagged(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["limitations"] = [
        "snapshot pinned",
        "This result generalizes to other repositories with similar layout.",
    ]
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE — missing / malformed digest -> RED                                #
# --------------------------------------------------------------------------- #

def test_missing_digest_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    del doc["population_digest"]
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_malformed_digest_value_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["population_digest"]["value"] = "not-a-sha256"
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_wrong_digest_does_not_reproduce_is_red(base_doc, tmp_path):
    """A digest that doesn't match the pinned tree fails closed under verification."""
    doc = copy.deepcopy(base_doc)
    doc["population_digest"]["value"] = "0" * 64
    p = _write(tmp_path, doc)
    # verify against the real repo root so the pinned commit resolves.
    assert gate.run(p, REPO_ROOT, verify_digest=True) == 1


# --------------------------------------------------------------------------- #
# NEGATIVE — snapshot boundary must be stated / manifest must exist            #
# --------------------------------------------------------------------------- #

def test_limitations_without_snapshot_boundary_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["limitations"] = ["synthetic-only boundary; NO_DEPLOY; census is complete"]
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_missing_pinned_commit_is_red(base_doc, tmp_path):
    doc = copy.deepcopy(base_doc)
    doc["pinned_snapshot"].pop("commit")
    p = _write(tmp_path, doc)
    assert gate.run(p, tmp_path, verify_digest=False) == 1


def test_missing_manifest_is_misconfig(tmp_path):
    assert gate.run(tmp_path / "nope.json", tmp_path, verify_digest=False) == 2
