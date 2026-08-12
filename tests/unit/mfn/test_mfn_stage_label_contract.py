# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from geosync.mfn.cli import main
from geosync.mfn.pipeline import read_json, validate_bundle, write_json, write_manifests


def test_stage_label_must_match_artifact_name(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    doc = read_json(bundle / "detect.json")
    doc["stage"] = "forecast"
    write_json(bundle / "detect.json", doc)
    write_manifests(
        bundle,
        [path for path in bundle.iterdir() if path.name not in {"manifest.json", "SHA256SUMS"}],
    )

    errors = validate_bundle(bundle)
    assert any("detect.json" in item and "stage" in item for item in errors)
