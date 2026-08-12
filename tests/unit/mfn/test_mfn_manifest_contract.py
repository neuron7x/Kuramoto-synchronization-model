# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MFN manifest contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from geosync.mfn.cli import main
from geosync.mfn.pipeline import read_json, validate_bundle, write_json


def _bundle(tmp_path: Path) -> Path:
    out = tmp_path / "bundle"
    assert main(["--out", str(out), "--seed", "7", "--points", "8", "run"]) == 0
    return out


def test_manifest_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    out = _bundle(tmp_path)
    manifest = read_json(out / "manifest.json")
    manifest["schema_version"] = "mfn.bundle.v0"
    write_json(out / "manifest.json", manifest)

    assert any("schema_version" in item for item in validate_bundle(out))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "invalid bytes"),
        (-1, "invalid bytes"),
        (0, "size mismatch"),
    ],
)
def test_manifest_rejects_bad_file_size_contract(
    tmp_path: Path, value: object, message: str
) -> None:
    out = _bundle(tmp_path)
    manifest = read_json(out / "manifest.json")
    manifest["files"][0]["bytes"] = value
    write_json(out / "manifest.json", manifest)

    assert any(message in item for item in validate_bundle(out))
