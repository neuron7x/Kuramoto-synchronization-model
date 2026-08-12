# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pytest

from core.indicators.hurst import hurst_exponent
from core.indicators.kuramoto import compute_phase, compute_phase_gpu, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci


@pytest.mark.arm
@pytest.mark.parametrize("window", [64, 128])
def test_kuramoto_consistency_across_backends(window: int) -> None:
    """Kuramoto phase computations align across CPU, GPU, and float32 paths."""

    rng = np.random.default_rng(1337)
    series = rng.standard_normal(window)

    cpu_phases = compute_phase(series)
    gpu_phases = compute_phase_gpu(series)
    arm_phases = compute_phase(series.astype(np.float32)).astype(np.float32)

    assert cpu_phases.shape == gpu_phases.shape == arm_phases.shape == (window,)
    assert np.allclose(cpu_phases, gpu_phases, atol=5e-3)
    assert np.allclose(cpu_phases.astype(np.float32), arm_phases, atol=5e-3)

    cpu_order = kuramoto_order(np.exp(1j * cpu_phases))
    gpu_order = kuramoto_order(np.exp(1j * gpu_phases))
    arm_order = kuramoto_order(np.exp(1j * arm_phases))

    assert pytest.approx(cpu_order, abs=5e-4) == gpu_order
    assert pytest.approx(cpu_order, abs=5e-4) == arm_order


@pytest.mark.arm
def test_hurst_exponent_float32_matches_float64() -> None:
    """Hurst exponent remains stable when executed with float32 precision."""

    rng = np.random.default_rng(2024)
    prices = np.cumsum(rng.normal(size=512))

    hurst64 = hurst_exponent(prices)
    hurst32 = hurst_exponent(prices.astype(np.float32))

    assert pytest.approx(hurst64, abs=2e-3) == hurst32


@pytest.mark.arm
def test_ricci_mean_curvature_is_portable() -> None:
    """Ricci mean curvature agrees across numeric backends within tolerance."""

    rng = np.random.default_rng(7)
    data = rng.standard_normal(512)
    graph = build_price_graph(data)

    ricci64 = mean_ricci(graph)
    ricci32 = mean_ricci(graph, use_float32=True)

    assert pytest.approx(ricci64, abs=5e-3) == ricci32
