# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

import scripts.validate_datasets as validate_datasets


def test_metadata_sidecars_present_and_valid() -> None:
    errors = validate_datasets.validate_all()
    assert errors == []


def test_missing_sidecar_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "unregistered.csv"
    csv_path.write_text("col\nvalue\n", encoding="utf-8")

    monkeypatch.setattr(validate_datasets, "iter_contracts", lambda: ())
    monkeypatch.setattr(validate_datasets, "_discover_csvs", lambda base: (csv_path,))

    errors = validate_datasets.validate_all()
    assert any("Unregistered dataset without metadata" in err for err in errors)
