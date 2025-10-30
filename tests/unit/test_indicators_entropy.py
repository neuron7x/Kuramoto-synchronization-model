# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for entropy-based market uncertainty indicators.

This module tests the EntropyFeature and DeltaEntropyFeature classes,
including their metadata handling. These features now support optional
optimization parameters (use_float32, chunk_size) which are conditionally
included in metadata only when explicitly enabled.

Tests verify:
- Core entropy calculations are correct
- Metadata contains required keys (e.g., 'bins')
- Optional metadata fields appear only when parameters are enabled
- Edge cases like empty arrays and extreme values are handled properly
- Performance optimizations don't change core behavior significantly
"""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from core.indicators.entropy import (
    DeltaEntropyFeature,
    EntropyFeature,
    delta_entropy,
    entropy,
)


def test_entropy_uniform_distribution_matches_log_bins(
    uniform_series: np.ndarray,
) -> None:
    bins = 20
    result = entropy(uniform_series, bins=bins)
    expected = np.log(bins)
    assert (
        abs(result - expected) < 0.15
    ), f"Entropy {result} deviates from log(bins) {expected}"


def test_entropy_degenerate_distribution_near_zero() -> None:
    series = np.ones(128)
    result = entropy(series, bins=10)
    assert result < 1e-9


def test_entropy_handles_extreme_values_and_non_finite() -> None:
    series = np.array(
        [
            0.0,
            0.0,
            1.0,
            np.finfo(float).max,
            -np.finfo(float).max / 10,
            np.nan,
            np.inf,
            -np.inf,
        ]
    )
    result = entropy(series, bins=16)
    assert np.isfinite(result)
    assert result >= 0.0


def test_entropy_of_empty_series_is_zero() -> None:
    assert entropy(np.array([])) == 0.0


def test_delta_entropy_requires_two_windows(peaked_series: np.ndarray) -> None:
    short_series = peaked_series[:100]
    assert delta_entropy(short_series, window=80) == 0.0


def test_delta_entropy_detects_spread_change() -> None:
    first = np.zeros(80)
    second = np.linspace(-1.0, 1.0, 80)
    series = np.concatenate([first, second])
    result = delta_entropy(series, window=80)
    assert result > 0.0, "Delta entropy should increase when distribution widens"


def test_entropy_feature_wraps_indicator(uniform_series: np.ndarray) -> None:
    """Test EntropyFeature with default parameters produces minimal metadata."""
    feature = EntropyFeature(bins=15, name="custom_entropy")
    outcome = feature.transform(uniform_series)
    assert outcome.name == "custom_entropy"
    # With default parameters, only 'bins' should be in metadata
    assert outcome.metadata == {"bins": 15}
    expected = entropy(uniform_series, bins=15)
    assert outcome.value == pytest.approx(expected, rel=1e-12)


def test_delta_entropy_feature_metadata(peaked_series: np.ndarray) -> None:
    """Test DeltaEntropyFeature metadata structure."""
    feature = DeltaEntropyFeature(window=40, bins_range=(5, 25))
    outcome = feature.transform(peaked_series)
    assert outcome.name == "delta_entropy"
    assert outcome.metadata == {"window": 40, "bins_range": (5, 25)}
    expected = delta_entropy(peaked_series, window=40, bins_range=(5, 25))
    assert outcome.value == pytest.approx(expected, rel=1e-12)


def test_entropy_feature_metadata_contains_required_keys(
    uniform_series: np.ndarray,
) -> None:
    """Test that EntropyFeature metadata always contains required keys.

    This test verifies that the 'bins' key is always present in metadata,
    regardless of whether optional optimization parameters are used.
    """
    feature = EntropyFeature(bins=20)
    outcome = feature.transform(uniform_series)

    # Required key must always be present
    assert "bins" in outcome.metadata
    assert outcome.metadata["bins"] == 20

    # With default settings, only 'bins' should be present
    assert set(outcome.metadata.keys()) == {"bins"}


def test_entropy_feature_with_float32_adds_metadata(uniform_series: np.ndarray) -> None:
    """Test that use_float32 parameter adds metadata when enabled."""
    feature = EntropyFeature(bins=20, use_float32=True)
    outcome = feature.transform(uniform_series)

    # Required keys
    assert "bins" in outcome.metadata
    assert outcome.metadata["bins"] == 20

    # Optional optimization flag should be present when enabled
    assert "use_float32" in outcome.metadata
    assert outcome.metadata["use_float32"] is True

    # Verify computation still works correctly
    expected = entropy(uniform_series, bins=20, use_float32=True)
    assert outcome.value == pytest.approx(expected, rel=1e-6)


def test_entropy_feature_with_chunk_size_adds_metadata(
    uniform_series: np.ndarray,
) -> None:
    """Test that chunk_size parameter adds metadata when enabled."""
    feature = EntropyFeature(bins=20, chunk_size=50)
    outcome = feature.transform(uniform_series)

    # Required keys
    assert "bins" in outcome.metadata
    assert outcome.metadata["bins"] == 20

    # Optional optimization flag should be present when enabled
    assert "chunk_size" in outcome.metadata
    assert outcome.metadata["chunk_size"] == 50

    # Verify computation still works correctly
    expected = entropy(uniform_series, bins=20, chunk_size=50)
    # Chunked processing should now match non-chunked execution
    assert outcome.value == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_entropy_feature_with_combined_optimizations(
    uniform_series: np.ndarray,
) -> None:
    """Test EntropyFeature with both float32 and chunk_size enabled."""
    feature = EntropyFeature(bins=25, use_float32=True, chunk_size=40)
    outcome = feature.transform(uniform_series)

    # All keys should be present
    assert "bins" in outcome.metadata
    assert "use_float32" in outcome.metadata
    assert "chunk_size" in outcome.metadata

    assert outcome.metadata["bins"] == 25
    assert outcome.metadata["use_float32"] is True
    assert outcome.metadata["chunk_size"] == 40

    # Verify value is computed
    assert isinstance(outcome.value, float)
    assert np.isfinite(outcome.value)
    assert outcome.value >= 0.0


def test_entropy_feature_float32_preserves_accuracy(uniform_series: np.ndarray) -> None:
    """Test that float32 optimization doesn't significantly change results."""
    feature_64 = EntropyFeature(bins=30, use_float32=False)
    feature_32 = EntropyFeature(bins=30, use_float32=True)

    result_64 = feature_64.transform(uniform_series)
    result_32 = feature_32.transform(uniform_series)

    # Results should be very close (within float32 precision tolerance)
    assert (
        abs(result_64.value - result_32.value) < 0.1
    ), f"Float32 and float64 results differ too much: {result_64.value} vs {result_32.value}"


def test_entropy_feature_chunk_size_behavior() -> None:
    """Test that chunk_size affects processing of large arrays."""
    # Create a large array
    large_data = np.random.randn(10000)

    feature_unchunked = EntropyFeature(bins=50)
    feature_chunked = EntropyFeature(bins=50, chunk_size=1000)

    result_unchunked = feature_unchunked.transform(large_data)
    result_chunked = feature_chunked.transform(large_data)

    # Both should produce valid results
    assert np.isfinite(result_unchunked.value)
    assert np.isfinite(result_chunked.value)

    # Chunking aggregates histograms and should match the single-pass result
    assert result_unchunked.value == pytest.approx(
        result_chunked.value, rel=1e-9, abs=1e-12
    )

    # Metadata should reflect the difference
    assert "chunk_size" not in result_unchunked.metadata
    assert result_chunked.metadata["chunk_size"] == 1000


def test_entropy_chunked_matches_heterogeneous_series() -> None:
    """Chunked entropy should match non-chunked results on mixed scales."""
    rng = np.random.default_rng(1234)
    low_variance = rng.normal(loc=0.0, scale=0.1, size=256)
    high_variance = rng.normal(loc=0.0, scale=250.0, size=256)
    series = np.concatenate([low_variance, high_variance])

    baseline = entropy(series, bins=64)
    chunked = entropy(series, bins=64, chunk_size=128)

    assert np.isfinite(baseline)
    assert np.isfinite(chunked)
    assert chunked == pytest.approx(baseline, rel=1e-9, abs=1e-12)


def test_entropy_gpu_backend_falls_back_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.indicators.entropy as entropy_module

    class DummyLogger:
        def __init__(self) -> None:
            self.warnings: list[tuple[str, tuple]] = []

        def operation(self, *_args, **_kwargs):  # noqa: D401 - contextmanager interface
            class _Context:
                def __enter__(self_inner):
                    return {}

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Context()

        def warning(self, msg: str, *args: object) -> None:
            self.warnings.append((msg, args))

    dummy_logger = DummyLogger()
    monkeypatch.setattr(entropy_module, "_logger", dummy_logger)
    monkeypatch.setattr(
        entropy_module,
        "_resolve_backend",
        lambda backend, **_: "cupy",
    )

    def _failing_gpu_backend(x: np.ndarray, bins: int, backend: str) -> float:
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(entropy_module, "_entropy_gpu", _failing_gpu_backend)

    data = np.linspace(-1.0, 1.0, 64)
    result = entropy_module.entropy(data, bins=16)

    assert np.isfinite(result)
    assert dummy_logger.warnings, "Expected GPU fallback warning to be emitted"
    assert entropy_module._LAST_ENTROPY_BACKEND == "cpu"


def test_entropy_process_executor_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.indicators.entropy as entropy_module

    class DummyExecutor:
        def __init__(
            self, *args, **kwargs
        ) -> None:  # noqa: D401 - signature compatibility
            self.args = args
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def map(self, fn, tasks):
            return [fn(task) for task in tasks]

    monkeypatch.setattr(entropy_module, "ProcessPoolExecutor", DummyExecutor)

    rng = np.random.default_rng(0)
    series = rng.normal(size=512)
    value = entropy_module.entropy(series, bins=32, chunk_size=64, parallel="process")

    assert np.isfinite(value)


def test_entropy_resolve_backend_respects_data_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.indicators.entropy as entropy_module

    monkeypatch.setattr(entropy_module, "cp", object())
    monkeypatch.setattr(entropy_module, "_gpu_memory_info", lambda: (2**30, 2**30))
    monkeypatch.setattr(entropy_module, "_cuda_available", lambda: False)

    small_backend = entropy_module._resolve_backend("auto", data_bytes=1024)
    large_backend = entropy_module._resolve_backend(
        "auto", data_bytes=10 * entropy_module._GPU_MIN_SIZE_BYTES
    )

    assert small_backend == "cpu"
    assert large_backend == "cupy"


def test_entropy_resolve_backend_handles_low_gpu_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.indicators.entropy as entropy_module

    monkeypatch.setattr(entropy_module, "cp", object())
    monkeypatch.setattr(entropy_module, "_gpu_memory_info", lambda: (128 * 1024, 2**30))
    monkeypatch.setattr(entropy_module, "_cuda_available", lambda: False)

    backend = entropy_module._resolve_backend(
        "auto", data_bytes=entropy_module._GPU_MIN_SIZE_BYTES * 2
    )

    assert backend == "cpu"


def test_entropy_async_parallel_matches_serial() -> None:
    """Async chunk execution should produce the same entropy as serial mode."""
    rng = np.random.default_rng(2025)
    series = rng.normal(loc=0.0, scale=1.0, size=4096)

    baseline = entropy(series, bins=48, chunk_size=256)
    async_result = entropy(
        series,
        bins=48,
        chunk_size=256,
        parallel="async",
        max_workers=4,
    )

    assert async_result == pytest.approx(baseline, rel=1e-9, abs=1e-12)


def test_entropy_async_respects_running_event_loop() -> None:
    """The async executor should tolerate being invoked from a running loop."""

    async def _runner() -> float:
        series = np.linspace(-1.0, 1.0, 1024)
        return entropy(
            series,
            bins=32,
            chunk_size=128,
            parallel="async",
        )

    expected = entropy(np.linspace(-1.0, 1.0, 1024), bins=32, chunk_size=128)
    result = asyncio.run(_runner())

    assert result == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_entropy_rejects_unknown_backend() -> None:
    """Invalid backend names should raise an explicit error."""

    with pytest.raises(ValueError, match="Unsupported backend"):
        entropy(np.arange(8, dtype=float), backend="quantum")


def test_entropy_feature_backend_metadata_on_fallback(
    uniform_series: np.ndarray,
) -> None:
    """When GPU is requested but unavailable, metadata should note the fallback."""

    feature = EntropyFeature(bins=18, backend="gpu")
    outcome = feature.transform(uniform_series)

    assert outcome.metadata["bins"] == 18
    assert outcome.metadata["backend"] == "cpu"
    assert outcome.metadata["backend_requested"] == "gpu"
    assert outcome.value == pytest.approx(
        entropy(uniform_series, bins=18, backend="gpu"), rel=1e-9, abs=1e-12
    )
