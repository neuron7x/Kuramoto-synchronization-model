# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from geosync.mfn.cli import main
from geosync.mfn.pipeline import read_json, sha256_file, validate_bundle, write_json


def test_manifest_index_rejects_extra_artifact(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    extra = bundle / "extra.txt"
    extra.write_text("extra\n", encoding="utf-8")
    digest = sha256_file(extra)

    doc = read_json(bundle / "manifest.json")
    doc["files"].append({"path": "extra.txt", "sha256": digest, "bytes": extra.stat().st_size})
    write_json(bundle / "manifest.json", doc)

    current = (bundle / "SHA256SUMS").read_text(encoding="utf-8")
    (bundle / "SHA256SUMS").write_text(current + f"{digest}  extra.txt\n", encoding="utf-8")

    assert any("unexpected entry: extra.txt" in item for item in validate_bundle(bundle))
