# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from application import (
    GeoSyncOrchestrator,
    LiveLoopSettings,
    build_geosync_system,
)
from core.neuro.fractal_regulator import RegulatorMetrics


def _sample_csv() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sample.csv"


def _build_system(tmp_path: Path):
    return build_geosync_system(
        allowed_data_roots=[_sample_csv().parent],
        live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
    )


def test_orchestrator_health_monitor_without_regulator(tmp_path):
    system = _build_system(tmp_path)
    orchestrator = GeoSyncOrchestrator(system)

    assert orchestrator.fractal_regulator is None

    for signal in (0.0, 0.75, np.nan):
        assert orchestrator.update_system_health(signal) is None

    assert orchestrator.is_system_in_crisis() is False
    assert orchestrator.get_system_health_metrics() is None


def test_orchestrator_fractal_regulator_callback(tmp_path, monkeypatch):
    system = _build_system(tmp_path)

    metrics = RegulatorMetrics(
        state=0.42,
        hurst=0.66,
        ple=1.4,
        csi=0.2,
        energy_cost=0.33,
        efficiency_delta=0.05,
    )

    class DummyRegulator:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.signals: list[float] = []

        def update_state(self, signal: float) -> RegulatorMetrics:
            if not np.isfinite(signal):
                raise ValueError("signal must be finite")
            self.signals.append(signal)
            return metrics

        def is_in_crisis(self) -> bool:
            return True

        def get_metrics(self) -> RegulatorMetrics:
            return metrics

    monkeypatch.setattr(
        "application.system_orchestrator.EEPFractalRegulator",
        DummyRegulator,
    )

    orchestrator = GeoSyncOrchestrator(
        system,
        enable_fractal_regulator=True,
        regulator_config={
            "window_size": 16,
            "embodied_baseline": 1.8,
            "crisis_threshold": 0.25,
            "energy_damping": 0.6,
            "seed": 123,
        },
    )

    assert isinstance(orchestrator.fractal_regulator, DummyRegulator)
    assert orchestrator.fractal_regulator.init_kwargs == {
        "window_size": 16,
        "embodied_baseline": 1.8,
        "crisis_threshold": 0.25,
        "energy_damping": 0.6,
        "seed": 123,
    }

    observed: list[RegulatorMetrics] = []
    orchestrator.set_crisis_callback(observed.append)

    result = orchestrator.update_system_health(0.9)

    assert result is metrics
    assert orchestrator.fractal_regulator.signals == [0.9]
    assert observed == [metrics]
    assert orchestrator.is_system_in_crisis() is True
    assert orchestrator.get_system_health_metrics() is metrics

    with pytest.raises(ValueError):
        orchestrator.update_system_health(np.nan)
