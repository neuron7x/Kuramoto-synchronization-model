# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contracts for the final inference-integrity verdict aggregator.

No single green workflow may imply system truth. The aggregator is PASS only when
every consumed artifact is present, schema-valid, passing, and not report-only.
These tests pin that: a missing artifact, a wrong schema, a FAIL sub-verdict, or a
report-only sub-artifact each force a FAIL, and a FAIL exits non-zero.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "audit_final_inference_verdict.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("afiv", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


afiv = _load_tool()

_SUBSTRATE = [s for s in afiv.INPUTS if s["tier"] == "substrate"]


def _populate(root: Path, *, verdict: str = "PASS") -> None:
    """Write a valid, passing artifact for every substrate input."""

    for spec in _SUBSTRATE:
        path = root / spec["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": afiv._SCHEMA_IDS[spec["name"]], "verdict": verdict}
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_all_present_and_passing_is_pass(tmp_path) -> None:
    _populate(tmp_path)
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "PASS"
    assert all(e["passed"] for e in report["inputs"])


def test_missing_artifact_fails(tmp_path) -> None:
    _populate(tmp_path)
    (tmp_path / _SUBSTRATE[0]["path"]).unlink()
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"
    missing = next(e for e in report["inputs"] if e["name"] == _SUBSTRATE[0]["name"])
    assert missing["present"] is False and missing["passed"] is False


def test_fail_sub_verdict_fails_final(tmp_path) -> None:
    _populate(tmp_path)
    bad = tmp_path / _SUBSTRATE[1]["path"]
    payload = json.loads(bad.read_text())
    payload["verdict"] = "FAIL"
    bad.write_text(json.dumps(payload))
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"


def test_unknown_schema_fails(tmp_path) -> None:
    _populate(tmp_path)
    bad = tmp_path / _SUBSTRATE[2]["path"]
    payload = json.loads(bad.read_text())
    payload["schema"] = "geosync.some_other_thing.v1"
    bad.write_text(json.dumps(payload))
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"
    entry = next(e for e in report["inputs"] if e["name"] == _SUBSTRATE[2]["name"])
    assert entry["passed"] is False and "schema" in entry["reason"]


def test_report_only_sub_artifact_cannot_satisfy_gate(tmp_path) -> None:
    _populate(tmp_path)
    bad = tmp_path / _SUBSTRATE[3]["path"]
    payload = json.loads(bad.read_text())
    payload["report_only"] = True
    bad.write_text(json.dumps(payload))
    report = afiv.build_verdict(tmp_path, release=False)
    assert report["verdict"] == "FAIL"
    entry = next(e for e in report["inputs"] if e["name"] == _SUBSTRATE[3]["name"])
    assert entry["passed"] is False and "report_only" in entry["reason"]


def test_release_requires_release_tier_artifacts(tmp_path) -> None:
    # Only substrate present: a --release aggregation must FAIL on the missing
    # release-tier artifacts (component strength, RVG).
    _populate(tmp_path)
    report = afiv.build_verdict(tmp_path, release=True)
    assert report["verdict"] == "FAIL"
    release_inputs = [e for e in report["inputs"] if e["tier"] == "release"]
    assert release_inputs and all(not e["present"] for e in release_inputs)


def test_exit_code_enforces_fail(tmp_path) -> None:
    assert afiv.exit_code({"verdict": "PASS"}, report_only=False) == 0
    assert afiv.exit_code({"verdict": "FAIL"}, report_only=False) == 1
    assert afiv.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def test_main_writes_schema_valid_artifact(tmp_path) -> None:
    _populate(tmp_path)
    out = tmp_path / "final.json"
    rc = afiv.main(["--root", str(tmp_path), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS"
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads(
        (ROOT / "audit" / "schema" / "final_inference_verdict.schema.json").read_text()
    )
    jsonschema.validate(report, schema)


def test_committed_artifact_is_present_and_pass() -> None:
    committed = ROOT / "artifacts" / "inference" / "final_inference_verdict.json"
    assert committed.is_file()
    report = json.loads(committed.read_text(encoding="utf-8"))
    assert report["schema"] == afiv.SCHEMA_ID
    assert report["verdict"] == "PASS"
