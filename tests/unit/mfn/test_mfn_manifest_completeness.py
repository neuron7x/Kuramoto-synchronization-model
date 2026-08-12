# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from geosync.mfn.cli import main
from geosync.mfn.pipeline import read_json, validate_bundle, write_json


def test_manifest_index_must_cover_report_artifact(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    doc = read_json(bundle / "manifest.json")
    doc["files"] = [entry for entry in doc["files"] if entry["path"] != "report.json"]
    write_json(bundle / "manifest.json", doc)

    lines = [
        line
        for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        if not line.endswith("  report.json")
    ]
    (bundle / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert any("missing required entry: report.json" in item for item in validate_bundle(bundle))
