# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Callable

import numpy as np
import pytest

from core.indicators import kuramoto


@pytest.fixture()
def restore_hilbert(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    original = kuramoto.hilbert

    def restore() -> None:
        monkeypatch.setattr(kuramoto, "hilbert", original, raising=False)

    return restore


def test_compute_phase_fft_fallback(
    monkeypatch: pytest.MonkeyPatch, restore_hilbert: Callable[[], None]
) -> None:
    """The FFT-based fallback should be exercised when SciPy is unavailable."""

    original_fft = np.fft.fft
    original_ifft = np.fft.ifft
    fft_calls: list[int] = []
    ifft_calls: list[int] = []

    def tracking_fft(values: np.ndarray) -> np.ndarray:
        fft_calls.append(1)
        return original_fft(values)

    def tracking_ifft(values: np.ndarray) -> np.ndarray:
        ifft_calls.append(1)
        return original_ifft(values)

    monkeypatch.setattr(kuramoto, "hilbert", None, raising=False)
    monkeypatch.setattr(np.fft, "fft", tracking_fft)
    monkeypatch.setattr(np.fft, "ifft", tracking_ifft)

    samples = np.sin(np.linspace(0, 2 * np.pi, 32, endpoint=False))
    phases = kuramoto.compute_phase(samples)

    restore_hilbert()
    monkeypatch.setattr(np.fft, "fft", original_fft)
    monkeypatch.setattr(np.fft, "ifft", original_ifft)

    assert len(fft_calls) == 1
    assert len(ifft_calls) == 1
    assert phases.shape == samples.shape
    assert np.all(np.isfinite(phases))
    assert np.max(np.abs(phases)) <= math.pi


def test_compute_phase_normalises_non_finite_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-finite input should be sanitised before phase computation."""

    monkeypatch.setattr(kuramoto, "hilbert", None, raising=False)
    samples = np.array([0.0, np.nan, np.inf, -np.inf, 1.0])
    phases = kuramoto.compute_phase(samples)
    assert phases.shape == samples.shape
    assert np.all(np.isfinite(phases))


@pytest.mark.parametrize(
    "phases,expected",
    [
        (np.array([0.0, np.pi]), pytest.approx(0.0, abs=1e-12)),
        (
            np.array([[0.0, np.pi], [np.pi / 2, np.pi / 2]]),
            np.array([math.sqrt(2) / 2, math.sqrt(2) / 2]),
        ),
    ],
)
def test_kuramoto_order_handles_nan_and_multidimensional(phases: np.ndarray, expected) -> None:
    value = kuramoto.kuramoto_order(phases)
    if isinstance(expected, np.ndarray):
        np.testing.assert_allclose(value, expected)
    else:
        assert value == expected


def test_compute_phase_gpu_without_cupy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kuramoto, "cp", None, raising=False)
    series = np.linspace(-1, 1, 16)
    phases = kuramoto.compute_phase_gpu(series)
    assert isinstance(phases, np.ndarray)
    assert phases.shape == series.shape


def test_compute_phase_gpu_with_mocked_cupy(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyFFT:
        @staticmethod
        def fft(values: np.ndarray) -> np.ndarray:
            return np.fft.fft(values)

        @staticmethod
        def ifft(values: np.ndarray) -> np.ndarray:
            return np.fft.ifft(values)

    class DummyCp(SimpleNamespace):
        float32 = np.float32

        @staticmethod
        def asarray(values: np.ndarray, dtype: np.dtype | None = None) -> np.ndarray:
            return np.asarray(values, dtype=dtype)

        fft = DummyFFT()

        @staticmethod
        def zeros(length: int, dtype: np.dtype | None = None) -> np.ndarray:
            return np.zeros(length, dtype=dtype)

        @staticmethod
        def angle(values: np.ndarray) -> np.ndarray:
            return np.angle(values)

        @staticmethod
        def asnumpy(values: np.ndarray) -> np.ndarray:
            return np.asarray(values)

    monkeypatch.setattr(kuramoto, "cp", DummyCp, raising=False)
    samples = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    phases = kuramoto.compute_phase_gpu(samples)
    assert isinstance(phases, np.ndarray)
    assert phases.shape == samples.shape


def test_compute_phase_gpu_fallback_on_gpu_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenFFT:
        @staticmethod
        def fft(values: np.ndarray) -> np.ndarray:
            raise RuntimeError("GPU error")

        @staticmethod
        def ifft(values: np.ndarray) -> np.ndarray:
            return np.fft.ifft(values)

    class BrokenCp(SimpleNamespace):
        float32 = np.float32
        fft = BrokenFFT()

        @staticmethod
        def asarray(values: np.ndarray, dtype: np.dtype | None = None) -> np.ndarray:
            return np.asarray(values, dtype=dtype)

    monkeypatch.setattr(kuramoto, "cp", BrokenCp, raising=False)
    series = np.cos(np.linspace(0, 1, 16))
    phases = kuramoto.compute_phase_gpu(series)
    assert isinstance(phases, np.ndarray)
    assert phases.shape == series.shape


def test_multi_asset_kuramoto_feature_collects_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kuramoto, "hilbert", None, raising=False)
    feature = kuramoto.MultiAssetKuramotoFeature()
    base = np.sin(np.linspace(0, 2 * np.pi, 32, endpoint=False))
    value = feature.transform([base, base * 0.5, base * 0.25])
    assert value.name == "multi_asset_kuramoto"
    assert value.metadata == {"assets": 3}
    assert 0.0 <= value.value <= 1.0


def test_kuramoto_order_feature_float32_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kuramoto, "hilbert", None, raising=False)
    feature = kuramoto.KuramotoOrderFeature(use_float32=True)
    signal = np.sin(np.linspace(0, 2 * np.pi, 32, endpoint=False))
    result = feature.transform(signal)
    assert result.metadata == {"use_float32": True}
    assert 0.0 <= result.value <= 1.0


def test_compute_phase_emits_operation_logging_when_debug_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyContext:
        def __init__(self, logger: "DummyLogger") -> None:
            self.logger = logger

        def __enter__(self) -> None:
            self.logger.entered += 1

        def __exit__(self, exc_type, exc, tb) -> None:
            self.logger.exited += 1

    class DummyLogger:
        def __init__(self) -> None:
            self.logger = SimpleNamespace(isEnabledFor=lambda level: True)
            self.calls: list[tuple[str, dict]] = []
            self.entered = 0
            self.exited = 0

        def operation(self, name: str, **kwargs) -> DummyContext:
            self.calls.append((name, kwargs))
            return DummyContext(self)

    dummy = DummyLogger()
    monkeypatch.setattr(kuramoto, "_logger", dummy, raising=False)
    monkeypatch.setattr(kuramoto, "_scipy_fft", None, raising=False)
    monkeypatch.setattr(kuramoto, "hilbert", None, raising=False)

    samples = np.sin(np.linspace(0, 2 * np.pi, 16, endpoint=False))
    phases = kuramoto.compute_phase(samples)

    assert phases.shape == samples.shape
    assert dummy.calls and dummy.calls[0][0] == "compute_phase"
    assert dummy.entered == 1 and dummy.exited == 1
