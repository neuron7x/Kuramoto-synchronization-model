# SPDX-License-Identifier: MIT
"""Offline guards for the open-data manifest schema and the deterministic
CLI mock path. Network-free: the only discovery exercised here is the
fixed-timestamp offline fixture, so the artifacts are bit-stable in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from research.ctc_falsify.c_real.open_data import discovery
from research.ctc_falsify.c_real.open_data.discovery import (
    SCHEMA_PATH,
    build_manifest,
)


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
    return schema


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def test_offline_manifest_is_schema_valid_and_deterministic() -> None:
    m1 = build_manifest(discovery._offline_fixture())
    m2 = build_manifest(discovery._offline_fixture())
    _validator().validate(m1)
    # Verdict-bearing content is identical run-to-run (fixed-timestamp mock).
    assert m1["candidates"] == m2["candidates"]
    assert m1["terminal_verdict"] == m2["terminal_verdict"]
    assert m1["schema_version"] == 1


def test_offline_terminal_is_a_fail_closed_inadmissible() -> None:
    m = build_manifest(discovery._offline_fixture())
    # The mock set is intentionally >8 GiB with no independent label, so
    # it can only land on an INADMISSIBLE_* terminal — never bound.
    assert m["terminal_verdict"].startswith("INADMISSIBLE_")
    assert m["terminal_verdict"] != "DATASET_BOUND_READY_FOR_C_REAL"


def test_schema_rejects_missing_required_candidate_field() -> None:
    m = build_manifest(discovery._offline_fixture())
    del m["candidates"][0]["has_independent_routing_label"]
    with pytest.raises(Exception):
        _validator().validate(m)


def test_schema_rejects_inconsistent_admissible_bindable() -> None:
    # ADMISSIBLE_BINDABLE while a required flag is not const-true must be
    # rejected by the schema's conditional allOf branch.
    m = build_manifest(discovery._offline_fixture())
    row = m["candidates"][0]
    row["admissibility_verdict"] = "ADMISSIBLE_BINDABLE"
    row["has_independent_routing_label"] = None
    assert not _validator().is_valid(m)


def test_schema_requires_blocker_on_reject() -> None:
    m = build_manifest(discovery._offline_fixture())
    row = m["candidates"][0]
    row["admissibility_verdict"] = "REJECT_NO_LFP"
    row["blockers"] = []
    assert not _validator().is_valid(m)


def test_schema_rejects_non_https_source_url() -> None:
    m = build_manifest(discovery._offline_fixture())
    m["candidates"][0]["source_url"] = "http://insecure.example/x"
    assert not _validator().is_valid(m)


def test_cli_offline_writes_schema_valid_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_p = tmp_path / "open_data_candidates.yaml"
    agate_p = tmp_path / "evidence" / "a_gate_open_data_binding.json"
    report_p = tmp_path / "OPEN_DATA_REPORT.md"
    monkeypatch.setattr(discovery, "MANIFEST_PATH", manifest_p)
    monkeypatch.setattr(discovery, "AGATE_PATH", agate_p)
    monkeypatch.setattr(discovery, "REPORT_PATH", report_p)

    rc = discovery.main(["--offline"])
    assert rc == 0

    manifest = yaml.safe_load(manifest_p.read_text())
    _validator().validate(manifest)

    agate = json.loads(agate_p.read_text())
    assert agate["can_run_c_real"] is False
    assert agate["selected_dataset_id"] is None
    assert agate["verdict"] == manifest["terminal_verdict"]
    assert agate["verdict"].startswith("INADMISSIBLE_")
    # repro_hash + config_hash are present and stable across a re-run.
    assert len(agate["repro_hash"]) == 64
    assert len(agate["config_hash"]) == 64
    assert report_p.exists()

    discovery.main(["--offline"])
    agate2 = json.loads(agate_p.read_text())
    assert agate2["repro_hash"] == agate["repro_hash"]
