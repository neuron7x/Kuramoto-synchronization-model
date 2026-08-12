# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from geosync.mfn.cli import main
from geosync.mfn.pipeline import validate_bundle, write_manifests


def test_runbook_must_include_reproduction_guidance(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    (bundle / "runbook.md").write_text("# MFN\n", encoding="utf-8")
    write_manifests(
        bundle,
        [path for path in bundle.iterdir() if path.name not in {"manifest.json", "SHA256SUMS"}],
    )

    errors = validate_bundle(bundle)
    assert any("first-file" in item for item in errors)
    assert any("validation command" in item for item in errors)
