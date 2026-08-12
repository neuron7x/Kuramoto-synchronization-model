# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the L2 Ricci evidence-bearing session protocol.

Pins the promotion-path invariant the README asserts: no L2 (depth-5) Ricci
claim may move beyond HYPOTHESIS without a real data hash, replay, baseline,
null model, falsifier, and negative evidence. The schema MUST reject any
artifact missing a required field, and the semantic gate MUST reject a
schema-shaped fake that claims evidence on zero hashes.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "research" / "l2_ricci_session.schema.json"
TOOL_PATH = ROOT / "tools" / "research" / "run_l2_ricci_session.py"

REQUIRED_FIELDS = (
    "git_sha",
    "data_sha256",
    "config_sha256",
    "venue",
    "symbol",
    "depth_level",
    "session_start_utc",
    "session_end_utc",
    "baseline_id",
    "null_model_id",
    "falsifier_id",
    "replay_command",
    "negative_evidence",
    "semantic_validation_status",
)


def _load_tool() -> Any:
    spec = importlib.util.spec_from_file_location("_run_l2_ricci_session", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    artifact = tmp_path / "session.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    return artifact


def test_schema_required_fields_match_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["title"] == "L2 Ricci Evidence-Bearing Session Artifact"
    assert set(schema["required"]) == set(REQUIRED_FIELDS)
    assert schema["additionalProperties"] is False
    # depth_level is pinned to the depth-5 session named in the README.
    assert schema["properties"]["depth_level"]["const"] == 5


def test_dry_run_skeleton_is_schema_valid(tmp_path: Path) -> None:
    skeleton = tool.skeleton()
    assert set(REQUIRED_FIELDS) <= set(skeleton)
    artifact = _write(tmp_path, skeleton)
    assert tool.validate_artifact(artifact) == []


def test_dry_run_skeleton_is_a_placeholder_not_evidence() -> None:
    skeleton = tool.skeleton()
    # The skeleton must be honestly inert: zero hashes, PLACEHOLDER status.
    assert skeleton["data_sha256"] == "0" * 64
    assert skeleton["config_sha256"] == "0" * 64
    assert skeleton["git_sha"] == "0" * 40
    assert skeleton["semantic_validation_status"] == "PLACEHOLDER"


def test_dry_run_main_emits_valid_skeleton(tmp_path: Path) -> None:
    out = tmp_path / "skeleton.json"
    assert tool.main(["--dry-run", "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    artifact = _write(tmp_path, payload)
    assert tool.validate_artifact(artifact) == []


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_schema_rejects_artifact_missing_any_required_field(
    tmp_path: Path, missing: str
) -> None:
    payload = tool.skeleton()
    payload.pop("conforms_to", None)
    del payload[missing]
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert errors, f"removing required field {missing!r} must fail validation"
    assert any(missing in error for error in errors)


def test_schema_rejects_wrong_depth_level(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["depth_level"] = 4
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("depth_level" in error for error in errors)


def test_schema_rejects_unknown_field(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["promoted"] = True
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("promoted" in error for error in errors)


def test_semantic_gate_rejects_evidence_claim_on_zero_hashes(tmp_path: Path) -> None:
    # A schema-shaped fake: PASS status but the skeleton's zero hashes.
    payload = tool.skeleton()
    payload["semantic_validation_status"] = "PASS"
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("data_sha256" in error for error in errors)
    assert any("git_sha" in error for error in errors)
    assert any("config_sha256" in error for error in errors)


def test_semantic_gate_rejects_placeholder_with_real_data(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["data_sha256"] = "a" * 64
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("semantic_validation_status" in error for error in errors)


def test_semantic_gate_rejects_end_before_start(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["session_start_utc"] = "2026-06-16T10:00:00Z"
    payload["session_end_utc"] = "2026-06-16T09:00:00Z"
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("session_end_utc" in error for error in errors)


def _evidence_payload() -> dict[str, Any]:
    payload = tool.skeleton()
    payload["git_sha"] = "a" * 40
    payload["data_sha256"] = "b" * 64
    payload["config_sha256"] = "c" * 64
    payload["session_start_utc"] = "2026-06-16T09:00:00Z"
    payload["session_end_utc"] = "2026-06-16T10:00:00Z"
    payload["semantic_validation_status"] = "PASS"
    # Replay must be an executable recorder invocation and not blocked; the
    # ids must resolve to config/research/l2_ricci_registry.yaml.
    payload["replay_blocked"] = False
    payload["replay_command"] = (
        "python tools/research/run_l2_ricci_session.py --artifact session.json"
    )
    payload["baseline_id"] = "no_lookahead_persistence"
    payload["null_model_id"] = "permutation_null"
    payload["falsifier_id"] = "lookahead_leak_falsifier"
    payload["negative_evidence"] = [
        {
            "claim": "depth-5 Ricci IC survives a permutation null model",
            "outcome": "SURVIVED",
            "detail": "Permutation null model run; IC remained above the null band.",
        },
        {
            "claim": "depth-5 Ricci IC is not a lookahead artifact",
            "outcome": "SURVIVED",
            "detail": "Lag sweep with no future data; IC persisted at non-negative lags.",
        },
    ]
    return payload


def test_complete_evidence_session_passes(tmp_path: Path) -> None:
    artifact = _write(tmp_path, _evidence_payload())
    assert tool.validate_artifact(artifact) == []


def test_evidence_session_missing_falsification_axis_is_rejected(tmp_path: Path) -> None:
    payload = _evidence_payload()
    # Drop the lookahead axis: only the null-model attempt remains.
    payload["negative_evidence"] = [payload["negative_evidence"][0]]
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("negative_evidence" in error for error in errors)


def test_evidence_session_all_blocked_is_rejected(tmp_path: Path) -> None:
    payload = _evidence_payload()
    for entry in payload["negative_evidence"]:
        entry["outcome"] = "BLOCKED"
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("negative_evidence" in error for error in errors)


# --- P1-3 hardening: placeholder/replay/registry resolution ------------------


def test_skeleton_replay_is_blocked_not_silently_unrunnable() -> None:
    skeleton = tool.skeleton()
    # The skeleton has no real capture to recompute, so its replay must be
    # honestly flagged blocked rather than masquerading as runnable.
    assert skeleton["replay_blocked"] is True


def test_placeholder_with_real_config_hash_is_rejected(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["config_sha256"] = "c" * 64
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("config hash" in error for error in errors)


def test_placeholder_with_real_git_sha_is_rejected(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["git_sha"] = "a" * 40
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("git sha" in error for error in errors)


def test_non_evidence_silently_unrunnable_replay_is_rejected(tmp_path: Path) -> None:
    payload = tool.skeleton()
    payload["semantic_validation_status"] = "PENDING"
    payload["replay_command"] = "see internal notes"
    payload["replay_blocked"] = False
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("replay_command" in error for error in errors)


def test_evidence_session_with_blocked_replay_is_rejected(tmp_path: Path) -> None:
    payload = _evidence_payload()
    payload["replay_blocked"] = True
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("replay_blocked" in error for error in errors)


def test_evidence_session_with_non_executable_replay_is_rejected(tmp_path: Path) -> None:
    payload = _evidence_payload()
    payload["replay_command"] = "rerun the pipeline manually"
    payload["replay_blocked"] = False
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("replay_command" in error for error in errors)


def test_evidence_session_with_unresolved_ids_is_rejected(tmp_path: Path) -> None:
    payload = _evidence_payload()
    payload["baseline_id"] = "baseline_unset"
    payload["null_model_id"] = "null_model_unset"
    payload["falsifier_id"] = "falsifier_unset"
    artifact = _write(tmp_path, payload)
    errors = tool.validate_artifact(artifact)
    assert any("baseline_id" in error for error in errors)
    assert any("null_model_id" in error for error in errors)
    assert any("falsifier_id" in error for error in errors)
