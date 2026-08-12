# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based tests using Hypothesis."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from core.compat import utc_now
from cortex_service.app.config import SignalSettings
from cortex_service.app.core.signals import FeatureObservation, compute_signal
from cortex_service.app.modulation.regime import RegimeModulator, RegimeSettings


@given(
    value=st.floats(min_value=-1000, max_value=1000, allow_nan=False),
    mean=st.floats(min_value=-1000, max_value=1000, allow_nan=False),
    std=st.floats(min_value=0.001, max_value=100, allow_nan=False),
    weight=st.floats(min_value=0.01, max_value=10, allow_nan=False),
)
def test_signal_always_in_range(value, mean, std, weight):
    """Signal strength should always be in configured range."""
    settings = SignalSettings(rescale_min=-1.0, rescale_max=1.0)
    features = [
        FeatureObservation(
            instrument="TEST",
            name="feature",
            value=value,
            mean=mean,
            std=std,
            weight=weight,
        )
    ]
    signal = compute_signal(features, settings)
    assert settings.rescale_min <= signal.strength <= settings.rescale_max


@given(
    values=st.lists(
        st.floats(min_value=-100, max_value=100, allow_nan=False),
        min_size=1,
        max_size=10,
    ),
    mean=st.floats(min_value=-100, max_value=100, allow_nan=False),
    std=st.floats(min_value=0.01, max_value=50, allow_nan=False),
)
def test_signal_multiple_features_in_range(values, mean, std):
    """Multiple features should still produce bounded signal."""
    settings = SignalSettings(rescale_min=-2.0, rescale_max=2.0)
    features = [
        FeatureObservation(
            instrument="TEST",
            name=f"feature_{i}",
            value=v,
            mean=mean,
            std=std,
            weight=1.0,
        )
        for i, v in enumerate(values)
    ]
    signal = compute_signal(features, settings)
    assert settings.rescale_min <= signal.strength <= settings.rescale_max
    assert signal.instrument == "TEST"
    assert len(signal.contributors) == len(values)


@given(
    valence=st.floats(min_value=-10, max_value=10, allow_nan=False),
    min_valence=st.floats(min_value=-5, max_value=-0.1),
    max_valence=st.floats(min_value=0.1, max_value=5),
)
def test_regime_valence_always_clipped(valence, min_valence, max_valence):
    """Regime valence should always be clipped to configured bounds."""
    if min_valence >= max_valence:
        return  # Skip invalid configurations

    settings = RegimeSettings(
        decay=0.2,
        min_valence=min_valence,
        max_valence=max_valence,
        confidence_floor=0.1,
    )
    modulator = RegimeModulator(settings)

    state = modulator.update(None, valence, 0.1, utc_now())
    assert min_valence <= state.valence <= max_valence


@given(
    feedback=st.floats(min_value=-1, max_value=1, allow_nan=False),
    volatility=st.floats(min_value=0, max_value=0.99, allow_nan=False),
    decay=st.floats(min_value=0.01, max_value=0.99),
)
def test_regime_confidence_bounds(feedback, volatility, decay):
    """Regime confidence should respect floor and never exceed 1.0."""
    confidence_floor = 0.05
    settings = RegimeSettings(
        decay=decay,
        min_valence=-1.0,
        max_valence=1.0,
        confidence_floor=confidence_floor,
    )
    modulator = RegimeModulator(settings)

    state = modulator.update(None, feedback, volatility, utc_now())
    assert confidence_floor <= state.confidence <= 1.0


@given(
    exposures=st.lists(
        st.tuples(
            st.floats(min_value=0.01, max_value=100),  # exposure
            st.floats(min_value=0.01, max_value=10),  # limit
            st.floats(min_value=0.001, max_value=1),  # volatility
        ),
        min_size=1,
        max_size=20,
    )
)
def test_risk_score_non_negative(exposures):
    """Risk score should always be non-negative."""
    from cortex_service.app.config import RiskSettings
    from cortex_service.app.ethics.risk import Exposure, compute_risk

    settings = RiskSettings()
    exposure_list = [
        Exposure(instrument=f"TEST{i}", exposure=e, limit=lim, volatility=v)  # noqa: E741
        for i, (e, lim, v) in enumerate(exposures)
    ]
    assessment = compute_risk(exposure_list, settings)
    assert assessment.score >= 0.0
    assert assessment.value_at_risk >= 0.0


@given(st.floats(min_value=-100, max_value=100, allow_nan=False))
def test_zscore_zero_std_handles_gracefully(value):
    """Zero std should not crash zscore computation."""
    feature = FeatureObservation(
        instrument="TEST", name="f", value=value, mean=0.0, std=0.0, weight=1.0
    )
    zscore = feature.zscore()
    assert isinstance(zscore, float)
    assert not (zscore != zscore)  # Not NaN


@given(st.floats(min_value=-100, max_value=100, allow_nan=False))
def test_zscore_none_std_handles_gracefully(value):
    """None std should not crash zscore computation."""
    feature = FeatureObservation(
        instrument="TEST", name="f", value=value, mean=0.0, std=None, weight=1.0
    )
    zscore = feature.zscore()
    assert isinstance(zscore, float)
    assert not (zscore != zscore)  # Not NaN
