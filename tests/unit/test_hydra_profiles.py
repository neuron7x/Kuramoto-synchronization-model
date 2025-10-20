# SPDX-License-Identifier: MIT
"""Tests for Hydra experiment configuration and reproducibility helpers."""
from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hydra import compose
from hydra import initialize_config_dir as hydra_initialize_config_dir
from hydra.core.global_hydra import GlobalHydra

from analytics.runner import (
    apply_reproducibility_settings,
    collect_run_metadata,
    run_pipeline,
    set_random_seeds,
)
from core.config.hydra_profiles import (
    ExperimentProfileError,
    available_experiment_profiles,
    validate_experiment_profile,
)

omegaconf = pytest.importorskip("omegaconf")
OmegaConf = omegaconf.OmegaConf


def test_set_random_seeds_is_repeatable(monkeypatch) -> None:
    """Seeding should reset Python and NumPy RNGs deterministically."""

    set_random_seeds(123)
    python_sequence = [random.random() for _ in range(3)]
    numpy_sequence = np.random.rand(3)

    set_random_seeds(123)
    assert python_sequence == [random.random() for _ in range(3)]
    assert np.allclose(numpy_sequence, np.random.rand(3))
    assert os.environ["PYTHONHASHSEED"] == "123"


def test_collect_run_metadata_includes_context(tmp_path: Path) -> None:
    cfg = OmegaConf.create({"experiment": {"name": "local", "random_seed": 7}})
    metadata = collect_run_metadata(tmp_path, Path.cwd(), cfg)

    assert metadata.run_dir == tmp_path
    assert metadata.original_cwd == Path.cwd()
    assert metadata.environment == "local"
    assert metadata.random_seed == 7
    # ISO format should include explicit offset (e.g. +00:00) to avoid relying on Z suffix
    assert not metadata.timestamp_utc.endswith("Z")


def test_apply_reproducibility_settings_updates_numpy_precision() -> None:
    np.set_printoptions(precision=8)
    cfg = OmegaConf.create({"reproducibility": {"numpy_print_precision": 3}})

    apply_reproducibility_settings(cfg)

    assert np.get_printoptions()["precision"] == 3


def test_run_pipeline_generates_results(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    prices = np.linspace(100.0, 110.0, 300)
    df = pd.DataFrame({"price": prices})
    data_path = tmp_path / "prices.csv"
    df.to_csv(data_path, index=False)

    cfg = OmegaConf.create(
        {
            "experiment": {
                "data": {"price_csv": str(data_path), "price_column": "price"},
                "analytics": {"window": 64, "bins": 32, "delta": 0.01},
            }
        }
    )

    result = run_pipeline(cfg)

    assert result["status"] == "ok"
    assert "summary" in result and set(result["summary"]) >= {
        "order_parameter",
        "entropy",
        "delta_entropy",
        "mean_ricci",
    }
    assert Path("results.json").exists()


def test_validate_experiment_profile_rejects_invalid_values() -> None:
    cfg = OmegaConf.create(
        {
            "experiment": {
                "name": "local",
                "db_uri": "sqlite:///memory",
                "log_level": "INFO",
                "random_seed": 1,
                "data": {"price_csv": "sample.csv", "price_column": "price"},
                "analytics": {"window": 0, "bins": 32, "delta": 0.01},
                "tracking": {"enabled": True, "base_dir": "runs"},
            }
        }
    )

    with pytest.raises(ExperimentProfileError):
        validate_experiment_profile(cfg)


def test_available_experiment_profiles_excludes_base_profile() -> None:
    profiles = available_experiment_profiles()

    assert "base" not in profiles
    assert {"ci", "local", "prod", "stage"}.issubset(set(profiles))


def test_hydra_profiles_inherit_base_defaults() -> None:
    conf_root = Path(__file__).resolve().parents[2] / "conf"

    if GlobalHydra.instance().is_initialized():
        GlobalHydra.instance().clear()

    with hydra_initialize_config_dir(version_base="1.3", config_dir=str(conf_root)):
        cfg = compose(config_name="config", overrides=["experiment=stage"])

    stage_cfg = validate_experiment_profile(cfg)

    assert stage_cfg.analytics.window == 256
    assert stage_cfg.analytics.delta == pytest.approx(0.005)
