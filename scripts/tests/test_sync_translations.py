# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import scripts.localization.sync_translations as sync


def _prepare_basic_layout(tmp_path: Path) -> dict[str, Path]:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}))

    locales_cfg = tmp_path / "locales.yaml"
    locales_cfg.write_text(
        "default_locale: en\n"
        "fallback_locale: en\n"
        "locales:\n"
        "  en:\n"
        "    tone:\n"
        "      voice: default\n"
        "      guidelines:\n"
        "        do: []\n"
        "        dont: []\n"
        "    formats: {}\n"
    )

    translations_dir = tmp_path / "locales"
    translations_dir.mkdir()
    (translations_dir / "en.json").write_text(
        json.dumps({"greeting": {"hello": "hi"}, "farewell": "bye"})
    )
    (translations_dir / "es.json").write_text(
        json.dumps({"greeting": {"hello": "hola"}, "extra": "remove me"})
    )

    metadata = tmp_path / "meta.json"
    coverage = tmp_path / "coverage.json"
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "es.json").write_text(json.dumps({"farewell": "adios"}))

    return {
        "schema": schema,
        "locales_cfg": locales_cfg,
        "translations_dir": translations_dir,
        "metadata": metadata,
        "coverage": coverage,
        "vendor": vendor_dir,
    }


def test_sync_writes_translations_and_metadata(tmp_path: Path) -> None:
    paths = _prepare_basic_layout(tmp_path)
    argv = [
        "--locales-config",
        str(paths["locales_cfg"]),
        "--translations-dir",
        str(paths["translations_dir"]),
        "--metadata-output",
        str(paths["metadata"]),
        "--schema",
        str(paths["schema"]),
        "--coverage-report",
        str(paths["coverage"]),
        "--vendor-dir",
        str(paths["vendor"]),
    ]

    assert sync.main(argv) == 0

    # Vendor key was merged and payloads written
    es_payload = json.loads((paths["translations_dir"] / "es.json").read_text())
    assert es_payload["farewell"] == "adios"
    assert "extra" in es_payload

    # Metadata and coverage artifacts exist
    assert paths["metadata"].exists()
    assert paths["coverage"].exists()

    first_output = paths["metadata"].read_text()
    second_output = paths["coverage"].read_text()

    # Idempotent on subsequent run
    assert sync.main(argv) == 0
    assert paths["metadata"].read_text() == first_output
    assert paths["coverage"].read_text() != ""
    assert paths["coverage"].read_text() == second_output


def test_check_mode_reports_missing_or_extra(tmp_path: Path) -> None:
    paths = _prepare_basic_layout(tmp_path)
    argv = [
        "--locales-config",
        str(paths["locales_cfg"]),
        "--translations-dir",
        str(paths["translations_dir"]),
        "--metadata-output",
        str(paths["metadata"]),
        "--schema",
        str(paths["schema"]),
        "--coverage-report",
        str(paths["coverage"]),
        "--vendor-dir",
        str(paths["vendor"]),
        "--check",
    ]

    assert sync.main(argv) == 1
