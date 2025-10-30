# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import functools
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

CONFIG_PATH = Path("configs/kuramoto_ricci_composite.yaml")


@functools.lru_cache(maxsize=1)
def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    return dict(loaded) if isinstance(loaded, dict) else {}


def test_kuramoto_timeframes_are_increasing() -> None:
    config = load_config()
    frames = config["kuramoto"]["timeframes"]
    assert all(isinstance(v, int) and v > 0 for v in frames)
    assert frames == sorted(frames)


def test_adaptive_window_bounds() -> None:
    config = load_config()
    window = config["kuramoto"]["adaptive_window"]
    base = window.get("base_window", 0)
    assert isinstance(base, int) and base >= 32


def test_temporal_ricci_parameters_valid() -> None:
    config = load_config()
    temporal = config["ricci"]["temporal"]
    assert temporal["window_size"] > 0
    assert 2 <= temporal["n_snapshots"] <= 32


def test_composite_thresholds_are_ordered() -> None:
    config = load_config()
    thresholds = config["composite"]["thresholds"]
    assert 0.0 < thresholds["R_proto_emergent"] < thresholds["R_strong_emergent"] <= 1.0
    assert thresholds["coherence_min"] <= thresholds["R_strong_emergent"]
    assert (
        thresholds["ricci_negative"] < 0 < thresholds["topological_transition"] <= 1.0
    )
    assert thresholds["temporal_ricci"] < 0


def test_signal_confidence_is_probabilistic() -> None:
    config = load_config()
    min_confidence = config["composite"]["signals"]["min_confidence"]
    assert 0.0 <= min_confidence <= 1.0
