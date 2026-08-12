# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the dependency-light MFN integration CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from geosync.mfn.cli import api_main, main, validate_main
from geosync.mfn.contract import MFN_COMMANDS, MFNContract
from geosync.mfn.pipeline import extract, read_json, validate_bundle, write_json


def test_mfn_run_creates_bundle_contract(tmp_path: Path, capsys) -> None:
    bundle = tmp_path / "bundle"

    exit_code = main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"first_file_to_open={bundle / 'manifest.json'}" in captured.out
    assert (bundle / "manifest.json").exists()
    assert (bundle / "SHA256SUMS").exists()
    assert (bundle / "runbook.md").exists()
    assert validate_bundle(bundle) == []

    manifest = read_json(bundle / "manifest.json")
    files = {entry["path"] for entry in manifest["files"]}
    assert {
        "simulate.json",
        "extract.json",
        "detect.json",
        "forecast.json",
        "compare.json",
        "report.json",
        "runbook.md",
    } <= files


def test_mfn_rejects_too_few_points(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--points", "3", "run"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "points must be >= 4" in captured.err


def test_mfn_validate_rejects_missing_bundle(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"

    exit_code = validate_main(["--bundle", str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required artifact" in captured.err


def test_mfn_bundle_is_byte_reproducible(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert main(["--out", str(first), "--seed", "7", "--points", "8", "run"]) == 0
    assert main(["--out", str(second), "--seed", "7", "--points", "8", "run"]) == 0

    for name in ("SHA256SUMS", "manifest.json", "runbook.md"):
        assert (first / name).read_text(encoding="utf-8") == (second / name).read_text(
            encoding="utf-8"
        )


def test_mfn_runbook_has_stable_final_newline(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"

    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    assert (bundle / "runbook.md").read_bytes().endswith(b"\n\n")


def test_mfn_manifest_rejects_invalid_path_entry(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    manifest = read_json(bundle / "manifest.json")
    manifest["files"][0]["path"] = "/not-relative.json"
    write_json(bundle / "manifest.json", manifest)

    assert any("invalid path" in item for item in validate_bundle(bundle))


def test_mfn_manifest_rejects_invalid_digest_entry(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    assert main(["--out", str(bundle), "--seed", "7", "--points", "8", "run"]) == 0

    manifest = read_json(bundle / "manifest.json")
    manifest["files"][0]["sha256"] = "0" * 63
    write_json(bundle / "manifest.json", manifest)

    assert any("invalid digest" in item for item in validate_bundle(bundle))


@pytest.mark.parametrize(
    ("price", "message"),
    [
        (None, "numeric"),
        ("nan", "finite"),
        ("inf", "finite"),
    ],
)
def test_mfn_extract_rejects_bad_price_values(tmp_path: Path, price: object, message: str) -> None:
    bundle = tmp_path / "bundle"
    write_json(
        bundle / "simulate.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "simulate",
            "observations": [{"price": 100.0}, {"price": price}],
        },
    )

    with pytest.raises(ValueError, match=message):
        extract(bundle, contract=MFNContract())


def test_mfn_extract_requires_price_key(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    write_json(
        bundle / "simulate.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "simulate",
            "observations": [{"price": 100.0}, {"volume": 1.0}],
        },
    )

    with pytest.raises(ValueError, match="price is required"):
        extract(bundle, contract=MFNContract())


def test_mfn_api_text_lists_contract_fields(capsys) -> None:
    exit_code = api_main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "schema_version=mfn.api.v1" in captured.out
    assert "status=INSTRUMENTED" in captured.out
    assert "default_bundle=" in captured.out
    assert "min_points=4" in captured.out
    assert "commands=" in captured.out


def test_mfn_api_json_lists_required_commands(capsys) -> None:
    exit_code = api_main(["--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["schema_version"] == "mfn.api.v1"
    assert payload["status"] == "INSTRUMENTED"
    assert payload["min_points"] == 4
    assert set(MFN_COMMANDS) <= set(payload["commands"])
