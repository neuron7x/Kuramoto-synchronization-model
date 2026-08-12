# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the strategy configuration DSL."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.strategies.dsl import StrategyDSLLoader, StrategyPresetRegistry
from tests.unit.strategies.sample_components import DummyStrategy


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _preset_payload() -> dict:
    return {
        "name": "base_momentum",
        "metadata": {"name": "base", "description": "Base preset"},
        "runtime": {"seed": 17, "environment": "preset", "deterministic": True},
        "pipeline": [
            {
                "id": "features",
                "kind": "feature",
                "entrypoint": "tests.unit.strategies.sample_components:build_feature_set",
                "parameters": {
                    "required": {
                        "scale": {
                            "value": 2.0,
                            "type": "float",
                            "description": "Feature scaling factor",
                        }
                    },
                },
            },
            {
                "id": "strategy",
                "kind": "strategy",
                "entrypoint": "tests.unit.strategies.sample_components:DummyStrategy",
                "parameters": {
                    "required": {
                        "symbol": {"value": "BTC-USD", "type": "str"},
                        "window": {"value": 55, "type": "int"},
                    },
                    "optional": {
                        "threshold": {
                            "default": 0.35,
                            "type": "float",
                            "description": "Z-score entry threshold",
                        }
                    },
                },
            },
        ],
    }


def test_preset_registry_loads_and_annotates(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    preset_path = preset_dir / "base.yaml"
    _write_yaml(preset_path, _preset_payload())

    registry = StrategyPresetRegistry([preset_dir])

    payload = registry.resolve("base_momentum")
    component = next(item for item in payload["pipeline"] if item["id"] == "strategy")
    threshold_meta = component["parameters"]["optional"]["threshold"]
    assert threshold_meta["origin"] == "preset:base_momentum"


def test_loader_merges_preset_and_inline_values(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    _write_yaml(preset_dir / "base.yaml", _preset_payload())

    overrides = {
        "version": "1.0",
        "extends": "base_momentum",
        "metadata": {"name": "derived"},
        "runtime": {"seed": 42, "environment": "test"},
        "pipeline": [
            {
                "id": "strategy",
                "parameters": {
                    "required": {
                        "symbol": {"value": "ETH-USD", "type": "str"},
                    },
                    "optional": {
                        "threshold": {"value": 0.5, "type": "float"},
                    },
                },
            }
        ],
    }

    loader = StrategyDSLLoader(preset_dirs=[preset_dir])
    definition = loader.load_from_dict(overrides)

    assert definition.metadata.preset == "base_momentum"
    assert definition.runtime.seed == 42

    strategy_component = next(item for item in definition.pipeline if item.id == "strategy")
    assert strategy_component.entrypoint.endswith("DummyStrategy")
    assert strategy_component.parameters.require()["symbol"] == "ETH-USD"
    assert strategy_component.parameters.require()["window"] == 55
    assert strategy_component.parameters.optional["threshold"].resolved() == pytest.approx(0.5)


def test_pipeline_materialise_resets_rng(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    _write_yaml(preset_dir / "base.yaml", _preset_payload())

    config = {
        "version": "1.0",
        "extends": "base_momentum",
        "metadata": {"name": "rng"},
        "runtime": {"seed": 11, "environment": "ci"},
    }

    loader = StrategyDSLLoader(preset_dirs=[preset_dir])
    definition = loader.load_from_dict(config)

    pipeline = definition.instantiate()
    first_components = pipeline.materialise()
    first_sample = np.random.random()
    second_components = pipeline.materialise()
    second_sample = np.random.random()

    assert isinstance(first_components["strategy"], DummyStrategy)
    assert first_components["strategy"].symbol == "BTC-USD"
    assert first_components["features"] == {"scale": 2.0}
    assert first_sample == pytest.approx(second_sample)
    assert first_components["strategy"].window == 55
    assert second_components["strategy"].threshold == pytest.approx(0.35)


def test_generate_documentation_contains_sections(tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    _write_yaml(preset_dir / "base.yaml", _preset_payload())

    config = {
        "version": "1.0",
        "extends": "base_momentum",
        "metadata": {"name": "doc", "owner": "research"},
        "runtime": {"seed": 19, "environment": "analysis"},
    }

    loader = StrategyDSLLoader(preset_dirs=[preset_dir])
    definition = loader.load_from_dict(config)
    doc = definition.generate_documentation()

    assert "# Strategy Pipeline: doc" in doc
    assert "## Components" in doc
    assert "DummyStrategy" in doc
    assert "threshold" in doc
    assert "preset:base_momentum" in doc


def test_loader_supports_inline_template(tmp_path: Path) -> None:
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    template_path = template_dir / "strategy.yaml.j2"
    template_path.write_text(
        """
version: "1.0"
metadata:
  name: "{{ name }}"
runtime:
  seed: {{ seed }}
  environment: "{{ environment }}"
pipeline:
  - id: strategy
    kind: strategy
    entrypoint: "tests.unit.strategies.sample_components:DummyStrategy"
    parameters:
      required:
        symbol:
          value: "{{ symbol }}"
          type: str
        window:
          value: {{ window }}
          type: int
""".strip(),
        encoding="utf-8",
    )

    loader = StrategyDSLLoader(template_dirs=[template_dir])
    definition = loader.load(
        template_path,
        context={
            "name": "templated",
            "seed": 101,
            "environment": "qa",
            "symbol": "ADA",
            "window": 25,
        },
    )

    assert definition.metadata.name == "templated"
    assert definition.runtime.seed == 101
    strategy_component = definition.pipeline[0]
    assert strategy_component.parameters.require()["symbol"] == "ADA"
