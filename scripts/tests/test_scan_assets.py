# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for scan_assets.py script."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
from pathlib import Path

from scripts import scan_assets


def test_is_training_script_detects_train_files() -> None:
    """Test that _is_training_script correctly identifies training scripts."""
    assert scan_assets._is_training_script(Path("train_model.py")) is True
    assert scan_assets._is_training_script(Path("trainer.py")) is True
    assert scan_assets._is_training_script(Path("fit_pipeline.py")) is True
    assert scan_assets._is_training_script(Path("pipeline.py")) is True


def test_is_training_script_rejects_non_training_files() -> None:
    """Test that _is_training_script rejects non-training files."""
    assert scan_assets._is_training_script(Path("utils.py")) is False
    assert scan_assets._is_training_script(Path("config.yaml")) is False
    assert scan_assets._is_training_script(Path("model.pkl")) is False


def test_is_training_script_checks_extension() -> None:
    """Test that _is_training_script checks file extension."""
    assert scan_assets._is_training_script(Path("train.py")) is True
    assert scan_assets._is_training_script(Path("train.ipynb")) is True
    assert scan_assets._is_training_script(Path("train.txt")) is False


def test_derive_description_model() -> None:
    """Test _derive_description for model assets."""
    asset = scan_assets.AssetRecord(name="model", path="models/model.pkl", kind="model")
    desc = scan_assets._derive_description(asset)
    assert "Trained model" in desc


def test_derive_description_training_script() -> None:
    """Test _derive_description for training script assets."""
    asset = scan_assets.AssetRecord(name="train", path="scripts/train.py", kind="training_script")
    desc = scan_assets._derive_description(asset)
    assert "training" in desc.lower() or "pipeline" in desc.lower()


def test_derive_description_dataset() -> None:
    """Test _derive_description for dataset assets."""
    asset = scan_assets.AssetRecord(name="data", path="data/sample.csv", kind="dataset")
    desc = scan_assets._derive_description(asset)
    assert "Dataset" in desc or "feature" in desc.lower()


def test_discover_assets_finds_models(tmp_path: Path) -> None:
    """Test that discover_assets finds model files."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "model.pkl").write_bytes(b"model data")
    (models_dir / "model.pt").write_bytes(b"torch model")
    (models_dir / "model.onnx").write_bytes(b"onnx model")

    assets = scan_assets.discover_assets([tmp_path])

    model_assets = [a for a in assets if a.kind == "model"]
    assert len(model_assets) == 3
    assert {a.name for a in model_assets} == {"model"}


def test_discover_assets_finds_datasets(tmp_path: Path) -> None:
    """Test that discover_assets finds dataset files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sample.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (data_dir / "features.parquet").write_bytes(b"parquet data")

    assets = scan_assets.discover_assets([tmp_path])

    dataset_assets = [a for a in assets if a.kind == "dataset"]
    assert len(dataset_assets) == 2


def test_discover_assets_finds_training_scripts(tmp_path: Path) -> None:
    """Test that discover_assets finds training scripts."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "train_model.py").write_text("# training\n", encoding="utf-8")
    (scripts_dir / "trainer.py").write_text("# trainer\n", encoding="utf-8")

    assets = scan_assets.discover_assets([tmp_path])

    training_assets = [a for a in assets if a.kind == "training_script"]
    assert len(training_assets) == 2


def test_discover_assets_skips_missing_roots() -> None:
    """Test that discover_assets skips non-existent roots."""
    assets = scan_assets.discover_assets([Path("/nonexistent/path")])
    assert assets == []


def test_discover_assets_adds_descriptions(tmp_path: Path) -> None:
    """Test that discover_assets adds descriptions to assets."""
    (tmp_path / "model.pkl").write_bytes(b"model")

    assets = scan_assets.discover_assets([tmp_path])

    assert len(assets) == 1
    assert assets[0].description is not None


def test_serialize_assets() -> None:
    """Test that serialize_assets converts to dictionaries."""
    assets = [
        scan_assets.AssetRecord(
            name="model",
            path="models/model.pkl",
            kind="model",
            description="A model",
        ),
        scan_assets.AssetRecord(
            name="data",
            path="data/sample.csv",
            kind="dataset",
            description="Sample data",
        ),
    ]

    result = scan_assets.serialize_assets(assets)

    assert len(result) == 2
    assert result[0]["name"] == "model"
    assert result[0]["path"] == "models/model.pkl"
    assert result[0]["kind"] == "model"
    assert result[1]["name"] == "data"


def test_save_registry(tmp_path: Path) -> None:
    """Test that save_registry creates JSON file."""
    assets = [
        scan_assets.AssetRecord(
            name="model",
            path="models/model.pkl",
            kind="model",
            description="A model",
        )
    ]
    output = tmp_path / "subdir" / "registry.json"

    scan_assets.save_registry(assets, output)

    assert output.exists()
    content = json.loads(output.read_text(encoding="utf-8"))
    assert len(content) == 1
    assert content[0]["name"] == "model"


def test_build_parser() -> None:
    """Test that _build_parser creates valid parser."""
    parser = scan_assets._build_parser()
    args = parser.parse_args([])

    assert args.roots is not None
    assert args.output is not None


def test_build_parser_custom_args() -> None:
    """Test that _build_parser handles custom arguments."""
    parser = scan_assets._build_parser()
    args = parser.parse_args(
        [
            "--roots",
            "dir1",
            "dir2",
            "--output",
            "custom/output.json",
        ]
    )

    assert args.roots == ["dir1", "dir2"]
    assert args.output == Path("custom/output.json")


def test_main_creates_registry(tmp_path: Path) -> None:
    """Test that main creates registry file."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "model.pkl").write_bytes(b"model")

    output = tmp_path / "registry.json"

    scan_assets.main(
        [
            "--roots",
            str(models_dir),
            "--output",
            str(output),
        ]
    )

    assert output.exists()
    content = json.loads(output.read_text(encoding="utf-8"))
    assert len(content) >= 1


def test_main_empty_roots(tmp_path: Path) -> None:
    """Test that main handles empty roots gracefully."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    output = tmp_path / "registry.json"

    scan_assets.main(
        [
            "--roots",
            str(empty_dir),
            "--output",
            str(output),
        ]
    )

    assert output.exists()
    content = json.loads(output.read_text(encoding="utf-8"))
    assert content == []


def test_asset_record_dataclass() -> None:
    """Test AssetRecord dataclass properties."""
    asset = scan_assets.AssetRecord(
        name="test",
        path="path/to/test.pkl",
        kind="model",
        description="Test asset",
    )

    assert asset.name == "test"
    assert asset.path == "path/to/test.pkl"
    assert asset.kind == "model"
    assert asset.description == "Test asset"


def test_model_extensions_constant() -> None:
    """Test that MODEL_EXTENSIONS contains expected extensions."""
    assert ".pkl" in scan_assets.MODEL_EXTENSIONS
    assert ".pt" in scan_assets.MODEL_EXTENSIONS
    assert ".onnx" in scan_assets.MODEL_EXTENSIONS


def test_dataset_extensions_constant() -> None:
    """Test that DATASET_EXTENSIONS contains expected extensions."""
    assert ".csv" in scan_assets.DATASET_EXTENSIONS
    assert ".parquet" in scan_assets.DATASET_EXTENSIONS
    assert ".json" in scan_assets.DATASET_EXTENSIONS
