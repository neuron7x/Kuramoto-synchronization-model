# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from types import SimpleNamespace
from typing import Sequence

import numpy as np
import pandas as pd
import pytest

from core.indicators.kuramoto import (
    KuramotoOrderFeature,
    MultiAssetKuramotoFeature,
    compute_phase,
    compute_phase_gpu,
    kuramoto_order,
    multi_asset_kuramoto,
)
from core.indicators.multiscale_kuramoto import (
    KuramotoResult,
    MultiScaleKuramoto,
    MultiScaleKuramotoFeature,
    MultiScaleResult,
    TimeFrame,
    WaveletWindowSelector,
)
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


def test_compute_phase_matches_expected_linear_phase(sin_wave: np.ndarray) -> None:
    phase = compute_phase(sin_wave)
    t = np.linspace(0, 4 * np.pi, sin_wave.size, endpoint=False)
    expected = np.unwrap(t - np.pi / 2)
    np.testing.assert_allclose(
        np.unwrap(phase),
        expected,
        atol=5e-2,
        err_msg="Instantaneous phase should follow analytical sine phase profile",
    )


def test_compute_phase_requires_one_dimensional_input() -> None:
    with pytest.raises(ValueError):
        compute_phase(np.ones((4, 4)))


def test_kuramoto_order_is_one_for_aligned_phases() -> None:
    phases = np.zeros(128)
    result = kuramoto_order(phases)
    assert pytest.approx(1.0, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL) == result


def test_kuramoto_order_clips_roundoff_to_unit_circle() -> None:
    phases = np.zeros(64)
    # Introduce imperceptible jitter so floating-point reductions may drift
    phases[:8] = 1e-12
    result = kuramoto_order(phases)
    assert 0.0 <= result <= 1.0


def test_kuramoto_order_handles_matrix_input() -> None:
    phases = np.vstack([np.zeros(16), np.pi * np.ones(16)])
    result = kuramoto_order(phases)
    assert result.shape == (16,)
    assert np.all((0.0 <= result) & (result <= 1.0))


def test_kuramoto_order_supports_weights() -> None:
    phases = np.linspace(0.0, np.pi / 2, 12)
    weights = np.linspace(1.0, 2.0, phases.size)
    result = kuramoto_order(phases, weights=weights)
    manual = np.abs(np.sum(np.exp(1j * phases) * weights)) / np.sum(weights)
    assert pytest.approx(manual, rel=1e-6, abs=1e-6) == result


def test_multi_asset_kuramoto_uses_last_phase_alignment() -> None:
    base = np.linspace(0, 6 * np.pi, 256, endpoint=False)
    series_a = np.sin(base)
    series_b = np.sin(base + 0.2)
    result = multi_asset_kuramoto([series_a, series_b])
    phase_a = compute_phase(series_a)[-1]
    phase_b = compute_phase(series_b)[-1]
    reference = kuramoto_order(np.array([phase_a, phase_b]))
    assert pytest.approx(reference, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL) == result


def test_multi_asset_kuramoto_accepts_weights() -> None:
    base = np.linspace(0, 4 * np.pi, 128, endpoint=False)
    series = [np.sin(base), np.sin(base + 0.1), np.sin(base + 0.3)]
    weights = [1.0, 2.0, 0.5]
    result = multi_asset_kuramoto(series, weights=weights)
    phases = [compute_phase(s)[-1] for s in series]
    manual = kuramoto_order(np.array(phases), weights=np.array(weights))
    assert pytest.approx(manual, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL) == result


def test_compute_phase_gpu_fallback_matches_cpu() -> None:
    data = np.sin(np.linspace(0, 2 * np.pi, 64, endpoint=False))
    cpu = compute_phase(data)
    gpu = compute_phase_gpu(data)
    np.testing.assert_allclose(cpu, gpu, atol=1e-6)


def test_compute_phase_handles_odd_length_series() -> None:
    data = np.sin(np.linspace(0, 2 * np.pi, 129, endpoint=False))
    phase = compute_phase(data)
    assert phase.shape == data.shape
    assert np.isfinite(phase).all()


def test_compute_phase_uses_custom_hilbert(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.indicators.kuramoto as module

    data = np.linspace(-np.pi, np.pi, 16, endpoint=False)

    def fake_hilbert(values: np.ndarray) -> np.ndarray:
        return np.exp(1j * values)

    monkeypatch.setattr(module, "hilbert", fake_hilbert)
    phase = module.compute_phase(data)
    np.testing.assert_allclose(np.unwrap(phase), np.unwrap(data), atol=1e-9)


def test_compute_phase_gpu_uses_gpu_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.indicators.kuramoto as module

    def _asarray(values, dtype=None):
        if dtype is None:
            return np.asarray(values)
        return np.asarray(values, dtype=dtype)

    fake_cp = SimpleNamespace(
        asarray=_asarray,
        float32=np.float32,
        zeros=lambda n, dtype=None: np.zeros(
            n, dtype=dtype if dtype is not None else np.float32
        ),
        fft=SimpleNamespace(
            fft=lambda x: np.fft.fft(_asarray(x)),
            ifft=lambda x: np.fft.ifft(_asarray(x)),
        ),
        angle=np.angle,
        asnumpy=lambda x: np.asarray(x),
    )

    monkeypatch.setattr(module, "cp", fake_cp)

    even = np.sin(np.linspace(0, 2 * np.pi, 128, endpoint=False))
    even_gpu = module.compute_phase_gpu(even)
    even_cpu = module.compute_phase(even)
    np.testing.assert_allclose(np.unwrap(even_gpu), np.unwrap(even_cpu), atol=1e-6)

    odd = np.sin(np.linspace(0, 2 * np.pi, 129, endpoint=False))
    odd_gpu = module.compute_phase_gpu(odd)
    odd_cpu = module.compute_phase(odd)
    np.testing.assert_allclose(np.unwrap(odd_gpu), np.unwrap(odd_cpu), atol=1e-6)


def test_kuramoto_order_feature_returns_expected_metadata() -> None:
    feature = KuramotoOrderFeature()
    result = feature.transform(np.zeros(32))
    assert result.name == "kuramoto_order"
    assert result.metadata == {}
    assert result.value == pytest.approx(1.0, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)


def test_kuramoto_order_feature_accepts_weights() -> None:
    feature = KuramotoOrderFeature()
    phases = np.linspace(0.0, np.pi / 4, 16)
    weights = np.linspace(1.0, 2.0, phases.size)
    result = feature.transform(phases, weights=weights)
    manual = kuramoto_order(phases, weights=weights)
    assert result.metadata["weights"] == "provided"
    assert result.value == pytest.approx(manual, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)


def test_multi_asset_kuramoto_feature_reports_asset_count(sin_wave: np.ndarray) -> None:
    feature = MultiAssetKuramotoFeature(name="multi")
    data = [sin_wave, np.roll(sin_wave, 3)]
    outcome = feature.transform(data)
    assert outcome.name == "multi"
    assert outcome.metadata == {"assets": 2}
    expected = multi_asset_kuramoto(data)
    assert outcome.value == pytest.approx(
        expected, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
    )


def _synth_dataframe(periods: int = 4096, seed: int = 0) -> pd.DataFrame:
    """Generate deterministic synthetic data for Kuramoto tests.

    Args:
        periods: Number of data points to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with 'close' column and DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=periods, freq="1min")
    t = np.arange(periods)
    price = (
        100
        + 5 * np.sin(2 * np.pi * t / 240)
        + 2 * np.sin(2 * np.pi * t / 1024)
        + 0.25 * rng.normal(size=periods)
    )
    return pd.DataFrame({"close": price}, index=idx)


def test_multiscale_kuramoto_matches_realistic_sample() -> None:
    """Test multiscale Kuramoto analysis on synthetic data."""
    df = _synth_dataframe(periods=512, seed=42)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M5),
        use_adaptive_window=False,
        base_window=64,
    )
    result = analyzer.analyze(df)

    # Verify structure and bounds rather than exact values
    assert result.skipped_timeframes == ()
    assert 0.0 <= result.consensus_R <= 1.0
    assert 0.0 <= result.cross_scale_coherence <= 1.0

    R_values = [res.order_parameter for res in result.timeframe_results.values()]
    assert all(0.0 <= value <= 1.0 for value in R_values)
    assert TimeFrame.M1 in result.timeframe_results
    assert TimeFrame.M5 in result.timeframe_results


def test_kuramoto_order_remains_stable_with_nan_and_clamp() -> None:
    """Test that Kuramoto order is stable with NaN and Inf values."""
    df = _synth_dataframe(periods=512, seed=42)
    prices = df["close"].to_numpy(copy=True)
    prices[5] = np.nan
    prices[6] = np.inf
    prices[7] = -np.inf

    clean_phases = compute_phase(df["close"].to_numpy())
    noisy_phases = compute_phase(prices)

    clean_R = kuramoto_order(clean_phases[-256:])
    noisy_R = kuramoto_order(noisy_phases[-256:])

    assert 0.0 <= noisy_R <= 1.0
    assert noisy_R == pytest.approx(clean_R, rel=5e-3, abs=5e-3)


def test_multiscale_kuramoto_analyzer_reports_consensus_metrics() -> None:
    df = _synth_dataframe()
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M5, TimeFrame.M15),
        use_adaptive_window=False,
        base_window=128,
    )
    result = analyzer.analyze(df)
    assert 0.0 <= result.consensus_R <= 1.0
    assert (
        result.dominant_scale in result.timeframe_results
        or result.dominant_scale is None
    )
    assert result.adaptive_window == 128
    assert set(result.timeframe_results.keys()) == {
        TimeFrame.M1,
        TimeFrame.M5,
        TimeFrame.M15,
    }
    assert 0.0 <= result.cross_scale_coherence <= 1.0
    assert "resample_requests" in result.energy_profile


def test_multiscale_feature_metadata_contains_timeframe_scores() -> None:
    df = _synth_dataframe()
    feature = MultiScaleKuramotoFeature(
        analyzer=MultiScaleKuramoto(
            timeframes=(TimeFrame.M1, TimeFrame.M5),
            use_adaptive_window=False,
            base_window=96,
        ),
        name="kuramoto_multi",
    )
    outcome = feature.transform(df)
    assert outcome.name == "kuramoto_multi"
    assert 0.0 <= outcome.value <= 1.0
    assert outcome.metadata["adaptive_window"] == 96
    assert outcome.metadata["timeframes"] == ["M1", "M5"]
    assert "R_M1" in outcome.metadata and "R_M5" in outcome.metadata
    assert "energy_profile" in outcome.metadata


def test_wavelet_selector_falls_back_without_scipy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selector = WaveletWindowSelector(min_window=32, max_window=256)
    prices = np.sin(np.linspace(0, 6 * np.pi, 300))

    import core.indicators.multiscale_kuramoto as module

    monkeypatch.setattr(module, "_signal", None)
    fallback = selector.select_window(prices)
    assert fallback == int(np.sqrt(32 * 256))


def test_timeframe_properties_expose_human_friendly_metadata() -> None:
    assert TimeFrame.M1.pandas_freq == "60s"
    assert TimeFrame.H1.seconds == 3600
    assert str(TimeFrame.M5) == "M5"


def test_wavelet_selector_validates_window_bounds() -> None:
    with pytest.raises(ValueError):
        WaveletWindowSelector(min_window=0, max_window=10)
    with pytest.raises(ValueError):
        WaveletWindowSelector(min_window=128, max_window=64)


def test_multiscale_analyzer_requires_price_column() -> None:
    df = _synth_dataframe().rename(columns={"close": "price"})
    analyzer = MultiScaleKuramoto(use_adaptive_window=False)
    with pytest.raises(KeyError):
        analyzer.analyze(df)


def test_multiscale_analyzer_requires_datetime_index() -> None:
    df = _synth_dataframe().reset_index(drop=True)
    analyzer = MultiScaleKuramoto(use_adaptive_window=False)
    with pytest.raises(TypeError):
        analyzer.analyze(df)


def test_multiscale_analyzer_marks_skipped_timeframes_when_insufficient_samples() -> (
    None
):
    df = _synth_dataframe(periods=90)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M15),
        use_adaptive_window=False,
        base_window=64,
        min_samples_per_scale=20,
    )
    result = analyzer.analyze(df)
    assert TimeFrame.M1 in result.timeframe_results
    assert TimeFrame.M15 in result.skipped_timeframes
    assert TimeFrame.M15 not in result.timeframe_results


def test_multiscale_analyzer_uses_selector_for_adaptive_window() -> None:
    class TrackingSelector:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def select_window(self, prices: Sequence[float]) -> int:
            self.calls.append(len(prices))
            return 200

    selector = TrackingSelector()
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1,),
        use_adaptive_window=True,
        base_window=64,
        selector=selector,
        min_samples_per_scale=50,
    )
    df = _synth_dataframe(periods=512)
    result = analyzer.analyze(df)
    assert selector.calls  # ensure selector was invoked
    assert result.adaptive_window == 200


def test_multiscale_feature_respects_custom_price_column_and_metadata() -> None:
    class StubAnalyzer:
        def __init__(self) -> None:
            self.price_cols: list[str] = []

        def analyze(
            self, _: pd.DataFrame, *, price_col: str = "close"
        ) -> MultiScaleResult:
            self.price_cols.append(price_col)
            return MultiScaleResult(
                consensus_R=0.55,
                cross_scale_coherence=0.82,
                dominant_scale=TimeFrame.M5,
                adaptive_window=144,
                timeframe_results={
                    TimeFrame.M1: KuramotoResult(
                        order_parameter=0.42, mean_phase=0.1, window=128
                    ),
                    TimeFrame.M5: KuramotoResult(
                        order_parameter=0.68, mean_phase=0.3, window=144
                    ),
                },
                skipped_timeframes=(TimeFrame.M15,),
            )

    analyzer = StubAnalyzer()
    feature = MultiScaleKuramotoFeature(analyzer=analyzer, name="calibrated")
    df = _synth_dataframe()
    outcome = feature.transform(df, price_col="custom_price")

    assert analyzer.price_cols == ["custom_price"]
    assert outcome.name == "calibrated"
    assert outcome.value == pytest.approx(0.55, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert outcome.metadata["dominant_timeframe"] == "M5"
    assert outcome.metadata["skipped_timeframes"] == ["M15"]
    assert outcome.metadata["cross_scale_coherence"] == pytest.approx(
        0.82, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
    )
    assert outcome.metadata["R_M1"] == pytest.approx(
        0.42, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
    )
    assert outcome.metadata["window_M5"] == 144
