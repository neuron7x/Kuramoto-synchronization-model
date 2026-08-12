# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.scan_assets import AssetRecord, discover_assets, save_registry


def create_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_discover_assets_identifies_models_and_scripts(tmp_path: Path) -> None:
    model_file = tmp_path / "analytics" / "signals" / "alpha_model.pkl"
    training_file = tmp_path / "analytics" / "training" / "train_alpha.py"
    dataset_file = tmp_path / "data" / "datasets" / "history.parquet"

    for file in (model_file, training_file, dataset_file):
        create_file(file)

    assets = discover_assets([tmp_path / "analytics", tmp_path / "data"])
    asset_index = {asset.name: asset for asset in assets}

    assert "alpha_model" in asset_index
    assert asset_index["alpha_model"].kind == "model"

    assert "train_alpha" in asset_index
    assert asset_index["train_alpha"].kind == "training_script"

    assert "history" in asset_index
    assert asset_index["history"].kind == "dataset"


def test_save_registry_writes_json(tmp_path: Path) -> None:
    assets = [
        AssetRecord(name="alpha_model", path="analytics/alpha_model.pkl", kind="model"),
        AssetRecord(name="train_alpha", path="analytics/train_alpha.py", kind="training_script"),
    ]
    output = tmp_path / "registry" / "assets_registry.json"

    save_registry(assets, output)

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["name"] == "alpha_model"


def test_discover_assets_missing_root(tmp_path: Path) -> None:
    create_file(tmp_path / "analytics" / "models" / "beta_model.onnx")

    assets = discover_assets([tmp_path / "analytics", tmp_path / "non_existent"])
    assert len(assets) == 1
    assert assets[0].kind == "model"


@pytest.mark.parametrize("file_name", ["train.ipynb", "pipeline.py", "fit_model.py"])
def test_training_keyword_detection(tmp_path: Path, file_name: str) -> None:
    file_path = tmp_path / "application" / "ml" / file_name
    create_file(file_path)

    assets = discover_assets([tmp_path / "application"])
    assert any(asset.kind == "training_script" for asset in assets)
