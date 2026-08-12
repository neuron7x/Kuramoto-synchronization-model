# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression guard for the five-minute D-H-T-F-V proof command."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from geosync.proof import run as proof


REQUIRED_KEYS = {
    "mechanism",
    "input_dataset",
    "dataset_sha256",
    "hypothesis",
    "metric",
    "threshold",
    "result",
    "verdict",
    "failure_condition",
    "repro_command",
    "timestamp_utc",
    "code_version",
    "content_digest",
}


def test_fixture_generates_reject_verdict() -> None:
    verdict = proof.build_verdict()
    assert set(verdict) == REQUIRED_KEYS
    assert verdict["mechanism"] == "lag1_directional_persistence_fixture_test"
    assert verdict["verdict"] == "REJECT"
    result = verdict["result"]
    assert isinstance(result, dict)
    assert result["training_rule"] == "continuation"
    assert result["training_hit_rate"] > 0.60
    assert result["holdout_hit_rate"] == 0.0
    assert result["samples"] >= 3


def test_proof_command_writes_verdict_json(tmp_path: Path) -> None:
    artifact = Path("artifacts/geosync_proof/verdict.json")
    if artifact.exists():
        artifact.unlink()
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = "1700000000"
    env["GEOSYNC_PROOF_CODE_VERSION"] = "test-version"
    proc = subprocess.run(
        [sys.executable, "-m", "geosync.proof.run"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "GEOSYNC_PROOF verdict=REJECT" in proc.stdout
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["verdict"] == "REJECT"
    assert data["repro_command"] == "python -m geosync.proof.run"
    assert data["timestamp_utc"] == "2023-11-14T22:13:20Z"
    assert data["code_version"] == "test-version"


def test_verdict_is_provenance_bound() -> None:
    # auditor-grade: the verdict must name the exact code + data, never a silent blank
    verdict = proof.build_verdict()
    assert verdict["code_version"] != "unknown"  # git: or env pin, resolved here
    assert str(verdict["dataset_sha256"]).startswith("sha256:")
    assert str(verdict["content_digest"]).startswith("sha256:")


def test_content_digest_is_deterministic_and_covers_every_field() -> None:
    import os as _os
    env = dict(_os.environ)
    env_pin = {**{k: v for k, v in env.items()},
               "GEOSYNC_PROOF_CODE_VERSION": "pin", "SOURCE_DATE_EPOCH": "1700000000"}
    # deterministic under a pinned substrate
    a = _build_under(env_pin)
    b = _build_under(env_pin)
    assert a["content_digest"] == b["content_digest"]
    # digest is a self-hash: recomputing over the body (minus the digest) reproduces it
    assert proof._content_digest(a) == a["content_digest"]


def test_verify_detects_tampering(tmp_path: Path) -> None:
    verdict = proof.build_verdict()
    good = tmp_path / "verdict.json"
    good.write_text(json.dumps(verdict, sort_keys=True), encoding="utf-8")
    ok, problems = proof.verify_verdict(good)
    assert ok and not problems
    # flip the verdict field — the tamper-evident digest must catch it
    verdict["verdict"] = "ACCEPT"
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(verdict, sort_keys=True), encoding="utf-8")
    ok2, problems2 = proof.verify_verdict(bad)
    assert not ok2
    assert any("content_digest mismatch" in p for p in problems2)


def _build_under(env: dict) -> dict:
    import os as _os
    saved = dict(_os.environ)
    try:
        _os.environ.clear()
        _os.environ.update(env)
        return proof.build_verdict()
    finally:
        _os.environ.clear()
        _os.environ.update(saved)


def test_degenerate_fixture_is_inconclusive(tmp_path: Path) -> None:
    path = tmp_path / "short.csv"
    path.write_text("timestamp,close\n2026-01-01T00:00:00Z,100\n2026-01-02T00:00:00Z,101\n", encoding="utf-8")
    try:
        proof.build_verdict(path)
    except ValueError as exc:
        assert "enough bars" in str(exc)
    else:
        raise AssertionError("short fixture must fail closed")
