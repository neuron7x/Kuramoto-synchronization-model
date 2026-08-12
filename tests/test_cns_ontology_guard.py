# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

from scripts.check_cns_ontology_usage import validate_cns_ontology

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "cns" / "control_ontology.schema.json"
ONTOLOGY_PATH = REPO_ROOT / "configs" / "cns" / "control_ontology.v1.json"
REGISTRY_PATH = REPO_ROOT / "configs" / "cns" / "stream_registry.v1.json"


def test_cns_ontology_guard_passes_for_repository_payload() -> None:
    assert validate_cns_ontology(SCHEMA_PATH, ONTOLOGY_PATH, REGISTRY_PATH) == []


def test_cns_ontology_guard_fails_when_axis_coverage_is_incomplete(tmp_path: Path) -> None:
    broken = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    broken["variables"] = [v for v in broken["variables"] if v.get("axis") != "Control"]

    broken_path = tmp_path / "control_ontology.broken.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")

    errors = validate_cns_ontology(SCHEMA_PATH, broken_path, REGISTRY_PATH)
    assert any("missing" in msg.lower() and "control" in msg.lower() for msg in errors)


def test_cns_ontology_guard_fails_on_invalid_contradiction_event(tmp_path: Path) -> None:
    broken = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    broken["variables"][0]["contradiction_event"] = "NotCanonical.Event"

    broken_path = tmp_path / "control_ontology.bad_event.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")

    errors = validate_cns_ontology(SCHEMA_PATH, broken_path, REGISTRY_PATH)
    assert any("contradiction_event has invalid format" in msg.lower() for msg in errors)


def test_cns_ontology_guard_fails_when_flow_contract_missing(tmp_path: Path) -> None:
    broken = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    del broken["variables"][0]["flow"]

    broken_path = tmp_path / "control_ontology.no_flow.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")

    errors = validate_cns_ontology(SCHEMA_PATH, broken_path, REGISTRY_PATH)
    assert any(
        "missing required keys" in msg.lower() or ".flow must be an object" in msg.lower()
        for msg in errors
    )


def test_cns_ontology_guard_fails_for_unregistered_stream(tmp_path: Path) -> None:
    broken = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    broken["variables"][0]["flow"]["source_stream"] = "runtime.policy.unknown_stream"

    broken_path = tmp_path / "control_ontology.unknown_stream.json"
    broken_path.write_text(json.dumps(broken), encoding="utf-8")

    errors = validate_cns_ontology(SCHEMA_PATH, broken_path, REGISTRY_PATH)
    assert any("not registered" in msg.lower() for msg in errors)
