# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import builtins
import importlib
from typing import Sequence

import numpy as np
import pandas as pd
import pytest

import core.indicators.multiscale_kuramoto as kuramoto_mod
from core.indicators.multiscale_kuramoto import (
    FractalResampler,
    KuramotoResult,
    MultiScaleKuramoto,
    MultiScaleKuramotoFeature,
    MultiScaleResult,
    TimeFrame,
    WaveletWindowSelector,
)
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


def _synth_dataframe(periods: int = 4096) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=periods, freq="1min")
    t = np.arange(periods)
    price = (
        100
        + 5 * np.sin(2 * np.pi * t / 240)
        + 2 * np.sin(2 * np.pi * t / 1024)
        + 0.25 * np.random.default_rng(0).normal(size=periods)
    )
    return pd.DataFrame({"close": price}, index=idx)


@pytest.mark.skipif(kuramoto_mod._signal is None, reason="SciPy not installed")
def test_hilbert_phase_fallback_matches_scipy_on_sloped_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = np.linspace(0, 4 * np.pi, 1024)
    sloped_signal = np.sin(t) + 0.01 * np.arange(t.size)

    phases_scipy = kuramoto_mod._hilbert_phase(sloped_signal)

    monkeypatch.setattr(kuramoto_mod, "_signal", None)
    phases_fft = kuramoto_mod._hilbert_phase(sloped_signal)

    assert np.allclose(
        np.unwrap(phases_fft),
        np.unwrap(phases_scipy),
        rtol=1e-5,
        atol=1e-5,
    )

    order_fft, _ = kuramoto_mod._kuramoto(phases_fft)
    order_scipy, _ = kuramoto_mod._kuramoto(phases_scipy)
    assert order_fft == pytest.approx(order_scipy, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)


def test_hilbert_phase_accepts_readonly_buffer_without_mutating_caller() -> None:
    """Regression: a read-only / caller-owned series must not crash or be mutated.

    ``_hilbert_phase`` works in place (putmask on non-finite fill, in-place
    detrend + Hilbert multiplier). A read-only input previously raised
    "putmask: output array is read-only", which silently degraded
    GeoSyncCompositeEngine to its fallback feature set. A writable input was
    additionally mutated in place — an aliasing side effect. The function must
    instead own a private copy: no crash, caller bytes preserved, and the result
    identical to the writable-input path.
    """
    base = np.linspace(1.0, 10.0, 256)
    base[7] = np.nan  # force the putmask branch (non-finite fill)

    read_only = base.copy()
    read_only.setflags(write=False)
    snapshot = read_only.copy()

    phases_ro = kuramoto_mod._hilbert_phase(read_only)

    assert np.array_equal(read_only, snapshot, equal_nan=True), "caller buffer mutated"

    writable = base.copy()
    writable_snapshot = writable.copy()
    phases_w = kuramoto_mod._hilbert_phase(writable)
    assert np.array_equal(writable, writable_snapshot, equal_nan=True), "writable caller mutated"

    assert np.allclose(phases_ro, phases_w, rtol=1e-12, atol=1e-12, equal_nan=True)


def test_fractal_gcl_handles_torch_loader_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.indicators.fractal_gcl as fractal_gcl

    real_import = builtins.__import__

    def raising_import(name, *args, **kwargs):
        if name == "torch":
            raise OSError("libtorch missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", raising_import)
    reloaded = importlib.reload(fractal_gcl)
    assert reloaded._TORCH_AVAILABLE is False
    assert reloaded.torch is None
    assert reloaded.F is None


def test_timeframe_properties_expose_human_friendly_metadata() -> None:
    assert TimeFrame.M1.pandas_freq == "60s"
    assert TimeFrame.H1.seconds == 3600
    assert str(TimeFrame.M5) == "M5"


def test_wavelet_selector_validates_window_bounds() -> None:
    with pytest.raises(ValueError):
        WaveletWindowSelector(min_window=0, max_window=10)
    with pytest.raises(ValueError):
        WaveletWindowSelector(min_window=128, max_window=64)


def test_wavelet_selector_rejects_excessive_resource_requests() -> None:
    selector = WaveletWindowSelector(min_window=64, max_window=2_000_000)
    with pytest.raises(ValueError):
        selector.select_window([1.0, 2.0, 3.0])

    selector = WaveletWindowSelector(levels=10_000)
    with pytest.raises(ValueError):
        selector.select_window([1.0, 2.0, 3.0])


def test_wavelet_selector_limits_sample_count_for_energy_efficiency() -> None:
    selector = WaveletWindowSelector(min_window=16, max_window=64, max_samples=128)
    prices = np.linspace(0.0, 1.0, 1024)
    window = selector.select_window(prices)
    assert selector.max_samples == 128
    assert selector.min_window <= window <= selector.max_window


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


def test_fractal_resampler_reuses_parent_timeframes() -> None:
    df = _synth_dataframe()
    resampler = FractalResampler(df["close"])
    m1 = resampler.resample(TimeFrame.M1)
    assert not m1.empty
    m5 = resampler.resample(TimeFrame.M5)
    stats = resampler.stats()
    expected_m5 = df["close"].sort_index().resample(TimeFrame.M5.pandas_freq).last()
    expected_m5 = expected_m5.ffill().dropna()
    pd.testing.assert_series_equal(m5, expected_m5)
    assert stats["resample_requests"] == pytest.approx(2.0)
    assert stats["fractal_cache_hits"] == pytest.approx(1.0)
    assert 0.0 <= stats["fractal_reuse_ratio"] <= 1.0


def test_fractal_resampler_resample_many_honours_fractal_ordering() -> None:
    df = _synth_dataframe()
    resampler = FractalResampler(df["close"])
    requested = (TimeFrame.M15, TimeFrame.M1, TimeFrame.M5, TimeFrame.M5)
    results = resampler.resample_many(requested)

    assert list(results.keys()) == [TimeFrame.M15, TimeFrame.M1, TimeFrame.M5]
    assert all(isinstance(series, pd.Series) for series in results.values())

    stats = resampler.stats()
    assert stats["resample_requests"] == pytest.approx(3.0)
    assert stats["fractal_cache_hits"] >= 2.0
    assert stats["direct_resamples"] == pytest.approx(1.0)
    assert stats["cached_timeframes"] == pytest.approx(3.0)


def test_multiscale_analyzer_marks_skipped_timeframes_when_insufficient_samples() -> None:
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
    assert "resample_requests" in result.energy_profile
    assert result.energy_profile["resample_requests"] >= 1.0


def test_multiscale_feature_reports_metadata_and_custom_price_column() -> None:
    class StubAnalyzer:
        def __init__(self) -> None:
            self.price_cols: list[str] = []

        def analyze(self, _: pd.DataFrame, *, price_col: str = "close") -> MultiScaleResult:
            self.price_cols.append(price_col)
            return MultiScaleResult(
                consensus_R=0.55,
                cross_scale_coherence=0.82,
                dominant_scale=TimeFrame.M5,
                adaptive_window=144,
                timeframe_results={
                    TimeFrame.M1: KuramotoResult(order_parameter=0.42, mean_phase=0.1, window=128),
                    TimeFrame.M5: KuramotoResult(order_parameter=0.68, mean_phase=0.3, window=144),
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
    assert outcome.metadata["R_M1"] == pytest.approx(0.42, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
    assert outcome.metadata["window_M5"] == 144
    assert outcome.metadata["energy_profile"] == {}


def test_multiscale_analyzer_reports_energy_profile() -> None:
    df = _synth_dataframe(periods=1024)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M5, TimeFrame.M15),
        use_adaptive_window=False,
        base_window=64,
    )
    result = analyzer.analyze(df)
    energy = result.energy_profile
    assert energy["resample_requests"] >= 3.0
    assert energy["fractal_cache_hits"] >= 2.0
    assert 0.0 <= energy["fractal_reuse_ratio"] <= 1.0
    assert energy["samples_processed"] >= sum(
        res.window for res in result.timeframe_results.values()
    )


def test_multiscale_analyzer_exposes_resampled_series() -> None:
    df = _synth_dataframe(periods=512)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M5),
        use_adaptive_window=False,
        base_window=64,
    )
    result = analyzer.analyze(df)

    assert TimeFrame.M1 in result.timeframe_series
    assert TimeFrame.M5 in result.timeframe_series

    expected = df["close"].sort_index().resample(TimeFrame.M5.pandas_freq).last().ffill().dropna()
    pd.testing.assert_series_equal(result.timeframe_series[TimeFrame.M5], expected)


def test_timeframe_cache_reuses_resampled_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = _synth_dataframe(periods=512)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M5),
        use_adaptive_window=False,
        base_window=64,
    )
    result = analyzer.analyze(df)

    class RecordingCache:
        def __init__(self) -> None:
            self.store_calls: list[dict[str, object]] = []
            self.backfill_calls: list[dict[str, object]] = []

        def load(self, **_: object) -> None:
            return None

        def store(self, **kwargs: object) -> str:
            self.store_calls.append(dict(kwargs))
            return "fingerprint"

        def update_backfill_state(self, *args: object, **kwargs: object) -> None:
            self.backfill_calls.append({"args": args, "kwargs": dict(kwargs)})

    cache = RecordingCache()
    feature = MultiScaleKuramotoFeature(analyzer=analyzer, cache=cache)

    def fail_resample(*_: object, **__: object) -> pd.Series:
        raise AssertionError(
            "_resample_prices should not be used when timeframe_series is populated"
        )

    monkeypatch.setattr(feature.analyzer, "_resample_prices", fail_resample)

    params = feature._cache_params("close")
    feature._store_timeframe_cache(df, "close", params, result)

    assert cache.store_calls
    assert cache.backfill_calls


def test_multiscale_skipped_timeframes_emit_warning_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TD-002: dropped scales are observable, not silent — a warning is emitted
    naming the skipped timeframes so an opaque all-zero consensus is attributable."""
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    def _spy_warning(event: str, **fields: object) -> None:
        warnings_seen.append((event, fields))

    monkeypatch.setattr(kuramoto_mod._logger, "warning", _spy_warning)

    df = _synth_dataframe(periods=90)
    analyzer = MultiScaleKuramoto(
        timeframes=(TimeFrame.M1, TimeFrame.M15),
        use_adaptive_window=False,
        base_window=64,
        min_samples_per_scale=20,
    )
    result = analyzer.analyze(df)

    assert TimeFrame.M15 in result.skipped_timeframes
    skip_events = [e for e in warnings_seen if e[0] == "multiscale_timeframes_skipped"]
    assert skip_events, "expected a skipped-timeframes warning"
    assert "M15" in skip_events[0][1]["skipped"]


def test_wavelet_selector_constant_series_returns_stable_window() -> None:
    """TD-003: a flat / constant series carries no oscillatory energy; the selector
    must NOT collapse to the smallest, noisiest window — it returns the stable
    mid-range fallback instead of amplifying noise on degenerate input."""
    selector = WaveletWindowSelector(min_window=8, max_window=256)

    constant = selector.select_window(np.ones(2000, dtype=float))
    near_flat = selector.select_window(np.full(2000, 42.0, dtype=float))

    assert constant == selector._fallback_window
    assert constant > selector.min_window
    assert near_flat == selector._fallback_window
    # A genuinely oscillatory series is still free to pick any bounded scale.
    osc = selector.select_window(np.sin(np.linspace(0, 40 * np.pi, 2000)))
    assert selector.min_window <= osc <= selector.max_window


# ---------------------------------------------------------------------------
# Layer-B descriptor honesty (S5): the multiscale result must declare that it
# is a single-series cross-scale phase-coherence descriptor, NOT an inferred
# N×N asset-network Kuramoto model. The labels are declarative scope, not
# enforcement; these tests lock the declaration and confirm it does not alter
# the numeric output of a valid analysis.
# ---------------------------------------------------------------------------


def test_multiscale_result_declares_layer_b_descriptor_boundary() -> None:
    """MultiScaleResult carries machine-readable Layer-B provenance.

    Honest scope: layer == "market_descriptor",
    claim_boundary == "descriptor_only_not_predictor",
    single_series is True, is_network_model is False. This declares that the
    object is a single-series descriptor and NOT the asset-network model in
    core.kuramoto.network_engine.
    """
    df = _synth_dataframe(periods=4096)
    analyzer = MultiScaleKuramoto()
    result = analyzer.analyze(df)

    assert result.layer == "market_descriptor"
    assert result.claim_boundary == "descriptor_only_not_predictor"
    assert result.single_series is True
    assert result.is_network_model is False


def test_multiscale_feature_metadata_surfaces_descriptor_boundary() -> None:
    """The FeatureResult metadata propagates the Layer-B descriptor labels.

    Downstream consumers that read only the feature metadata must still see
    the descriptor-only / single-series / not-a-network-model boundary.
    """
    df = _synth_dataframe(periods=4096)
    feature = MultiScaleKuramotoFeature()
    out = feature.transform(df)

    assert out.metadata["layer"] == "market_descriptor"
    assert out.metadata["claim_boundary"] == "descriptor_only_not_predictor"
    assert out.metadata["single_series"] is True
    assert out.metadata["is_network_model"] is False


def test_descriptor_labels_do_not_change_numeric_output() -> None:
    """Regression: the honesty labels are additive; the numbers are unchanged.

    The descriptor's numeric summaries (consensus_R, cross_scale_coherence,
    per-horizon order parameters) for a valid series are exactly the values
    the analyzer computes from the phases, independent of the provenance
    fields. consensus_R is, by construction, the mean of the per-horizon
    order parameters; this reconstructs it from timeframe_results to confirm
    the label additions did not perturb the computation.
    """
    df = _synth_dataframe(periods=4096)
    analyzer = MultiScaleKuramoto()
    result = analyzer.analyze(df)

    # INV-K1: every per-horizon order parameter stays in [0, 1].
    r_values = [res.order_parameter for res in result.timeframe_results.values()]
    assert r_values, "expected at least one analyzed timeframe"
    for r in r_values:
        assert 0.0 <= r <= 1.0
    # consensus_R is the mean of the per-horizon order parameters — unchanged
    # by the additive provenance fields.
    assert result.consensus_R == pytest.approx(
        float(np.mean(r_values)), rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
    )
    assert 0.0 <= result.cross_scale_coherence <= 1.0


def test_multiscale_output_cannot_claim_network_or_market_consensus() -> None:
    """Issue #1107 — the single-series descriptor must not be read as the
    asset-network Kuramoto model nor as a 'market consensus' claim."""
    df = _synth_dataframe(periods=4096)
    result = MultiScaleKuramoto().analyze(df)

    assert result.is_network_model is False
    assert result.single_series is True
    assert result.claim_boundary == "descriptor_only_not_predictor"
    # Public-language guard: the declarative string fields must not advertise a
    # network model, market consensus, or predictive validity.
    blob = f"{result.layer} {result.claim_boundary}".lower()
    for forbidden in (
        "network model",
        "asset-network",
        "market consensus",
        "predictive validity",
        "alpha",
    ):
        assert forbidden not in blob, f"unsupported claim '{forbidden}' leaked"
