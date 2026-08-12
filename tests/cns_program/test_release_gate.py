from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def load_json_object(text: str) -> dict[str, object]:
    payload: object = json.loads(text)
    if not isinstance(payload, dict):
        raise AssertionError("expected JSON object")
    return {str(key): value for key, value in payload.items()}


def test_release_gate_chain_passes() -> None:
    for args in [
        ["-m",
        "tools.cns_program.deploy_release_gate"],
        ["-m",
        "tools.cns_program.build_release_manifest"],
        ["-m",
        "tools.cns_program.verify_release_manifest"],
        ["-m",
        "tools.cns_program.verify_reports_contract"],
        ["-m",
        "tools.cns_program.quality_gate"],
    ]:
        completed = run(args)
        assert completed.returncode == 0, completed.stderr or completed.stdout

    payload = load_json_object((ROOT / "results/cns_quality_gate.json").read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["quality_score"] == 1.0


def test_manifest_verifier_fails_on_digest_mismatch(tmp_path: Path) -> None:
    assert run(["-m",
        "tools.cns_program.deploy_release_gate"]).returncode == 0
    assert run(["-m",
        "tools.cns_program.build_release_manifest"]).returncode == 0
    manifest_path = ROOT / "results/cns_release_manifest.json"
    data = load_json_object(manifest_path.read_text(encoding="utf-8"))
    raw_digest_map = data["sha256"]
    assert isinstance(raw_digest_map, dict)
    digest_map = {str(key): str(value) for key, value in raw_digest_map.items()}
    first = next(iter(digest_map))
    digest_map[first] = "0" * 64
    data["sha256"] = digest_map
    edited_file = tmp_path / "edited_release_manifest.json"
    edited_file.write_text(json.dumps(data), encoding="utf-8")
    completed = run(
        ["-m",
        "tools.cns_program.verify_release_manifest", "--manifest", str(edited_file)]
    )
    assert completed.returncode != 0
    payload = load_json_object(completed.stdout)
    assert payload["valid"] is False
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert any(
        isinstance(error, str) and error.startswith("artifact_hash_mismatch:") for error in errors
    )


def test_reports_contract_fails_on_missing_report() -> None:
    missing_report = Path("reports/__missing__.md")
    payload = verify_reports((missing_report,))
    assert payload["valid"] is False
    assert payload["errors"] == ["report_missing:reports/__missing__.md"]
