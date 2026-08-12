#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from tools.cns_program.verify_reports_contract import verify_reports

ROOT = Path(__file__).resolve().parents[2]


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_json_object(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise AssertionError("json payload is not an object")
    return cast(dict[str, Any], payload)


def assert_ok(args: list[str]) -> None:
    completed = run(args)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)


def verify_release_chain() -> None:
    for args in [
        ["-m", "tools.cns_program.deploy_release_gate"],
        ["-m", "tools.cns_program.build_release_manifest"],
        ["-m", "tools.cns_program.verify_release_manifest"],
        ["-m", "tools.cns_program.verify_reports_contract"],
        ["-m", "tools.cns_program.quality_gate"],
    ]:
        assert_ok(args)

    quality_path = ROOT / "results/cns_quality_gate.json"
    payload = load_json_object(quality_path.read_text(encoding="utf-8"))
    if payload.get("passed") is not True:
        raise AssertionError("quality gate not green")
    if payload.get("quality_score") != 1.0:
        raise AssertionError("quality score drift")


def verify_manifest_altered_case() -> None:
    assert_ok(["-m", "tools.cns_program.deploy_release_gate"])
    assert_ok(["-m", "tools.cns_program.build_release_manifest"])
    manifest_path = ROOT / "results/cns_release_manifest.json"
    data = load_json_object(manifest_path.read_text(encoding="utf-8"))
    sha_map = data.get("sha256")
    if not isinstance(sha_map, dict) or not sha_map:
        raise AssertionError("manifest sha map missing")
    first = next(iter(sha_map))
    sha_map[first] = "0" * 64

    with tempfile.TemporaryDirectory() as tmpdir:
        candidate = Path(tmpdir) / "candidate.json"
        candidate.write_text(json.dumps(data), encoding="utf-8")
        args = [
            "-m",
            "tools.cns_program.verify_release_manifest",
            "--manifest",
            str(candidate),
        ]
        completed = run(args)
    if completed.returncode == 0:
        raise AssertionError("altered manifest returned zero")
    payload = load_json_object(completed.stdout)
    if payload.get("valid") is not False:
        raise AssertionError("altered manifest marked valid")
    if not payload.get("errors"):
        raise AssertionError("altered manifest has no errors")


def verify_reports_missing_case() -> None:
    payload = verify_reports((Path("reports/__absent__.md"),))
    if payload.get("valid") is not False:
        raise AssertionError("missing report marked valid")
    if not payload.get("errors"):
        raise AssertionError("missing report has no errors")


def main() -> int:
    verify_release_chain()
    verify_manifest_altered_case()
    verify_reports_missing_case()
    print(json.dumps({"cns_regression_selftest": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
