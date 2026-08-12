# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from core.altdata import (
    AltDataComplianceChecker,
    AltDataFusionEngine,
    DistributionDriftMonitor,
    FusionConfig,
    NewsFeatureBuilder,
    NewsItem,
    NewsSentimentAnalyzer,
    OnChainFeatureBuilder,
    OnChainMetric,
    SentimentFeatureBuilder,
    SentimentSignal,
)


def _ts(offset: int) -> dt.datetime:
    return dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=offset)


def test_news_feature_builder_aggregates_sentiment():
    analyzer = NewsSentimentAnalyzer(positive_tokens=["growth"], negative_tokens=["fraud"])
    builder = NewsFeatureBuilder(analyzer)
    items = [
        NewsItem(timestamp=_ts(0), headline="Company reports growth"),
        NewsItem(timestamp=_ts(1), headline="Fraud investigation launched"),
    ]
    features = builder.aggregate(items, freq="1min")
    assert list(features.columns) == [
        "news_count",
        "sentiment_mean",
        "sentiment_std",
        "source_diversity",
    ]
    assert features.iloc[0]["news_count"] == 1
    snapshot = builder.latest_snapshot(items)
    assert snapshot["news_count"] == 2.0


def test_sentiment_feature_builder_weights_scores():
    builder = SentimentFeatureBuilder(clip=2.0)
    signals = [
        SentimentSignal(timestamp=_ts(0), source="twitter", score=3.0, volume=2.0),
        SentimentSignal(timestamp=_ts(0), source="reddit", score=-1.0, volume=1.0),
    ]
    aggregated = builder.aggregate(signals, freq="1min")
    assert "sentiment_vwap" in aggregated.columns
    latest = builder.latest(signals)
    assert latest["sources"] == 2.0


def test_onchain_feature_builder_creates_deltas():
    builder = OnChainFeatureBuilder()
    metrics = [
        OnChainMetric(timestamp=_ts(0), metric="active_addresses", value=100.0),
        OnChainMetric(timestamp=_ts(1), metric="active_addresses", value=105.0),
    ]
    features = builder.to_features(metrics, freq="1min")
    assert "active_addresses" in features.columns
    assert "active_addresses_delta" in features.columns
    vol = builder.rolling_volatility(metrics)
    assert not vol.empty


def test_altdata_fusion_engine_combines_frames():
    engine = AltDataFusionEngine(FusionConfig(join_horizon="1min"))
    market = pd.DataFrame({"close": [1.0, 1.1]}, index=pd.DatetimeIndex([_ts(0), _ts(1)]))
    news = pd.DataFrame({"news_count": [1, 2]}, index=pd.DatetimeIndex([_ts(0), _ts(1)]))
    sentiment = pd.DataFrame(
        {"sentiment_vwap": [0.1, 0.2]}, index=pd.DatetimeIndex([_ts(0), _ts(1)])
    )
    fused = engine.fuse(market, news_features=news, sentiment_features=sentiment)
    assert set(fused.columns) >= {
        "close",
        "news_news_count",
        "sentiment_sentiment_vwap",
    }
    assert engine.validate_alignment(fused)


def test_distribution_drift_monitor_reports():
    monitor = DistributionDriftMonitor(method="psi", threshold=0.1, bins=5)
    reference = np.random.normal(0, 1, size=1000)
    current = np.random.normal(0.5, 1, size=1000)
    assessment = monitor.assess(reference, current)
    assert assessment.metric == "psi"
    assert isinstance(assessment.value, float)


def test_distribution_drift_monitor_ks_numpy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.altdata.drift as drift_module

    monitor = DistributionDriftMonitor(method="ks", threshold=0.2, bins=8)
    reference = np.linspace(-1.0, 1.0, num=256)
    current = np.linspace(-0.5, 1.5, num=256)

    monkeypatch.setattr(drift_module, "_SCIPY_STATS", None, raising=False)

    assessment = monitor.assess(reference, current)
    assert assessment.metric == "ks"
    assert 0.0 <= assessment.value <= 1.0
    assert 0.0 <= assessment.details["pvalue"] <= 1.0


def test_distribution_drift_monitor_ks_runtime_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.altdata.drift as drift_module

    monitor = DistributionDriftMonitor(method="ks", threshold=0.2, bins=6)
    rng = np.random.default_rng(42)
    reference = rng.normal(0.0, 1.0, size=300)
    current = rng.normal(0.4, 1.1, size=300)

    class BrokenStats:
        @staticmethod
        def ks_2samp(*_args, **_kwargs):
            raise RuntimeError("simulated SciPy failure")

    monkeypatch.setattr(drift_module, "_SCIPY_STATS", BrokenStats(), raising=False)

    assessment = monitor.assess(reference, current)
    assert assessment.metric == "ks"
    assert 0.0 <= assessment.details["pvalue"] <= 1.0


def test_ks_fallback_small_sample_matches_scipy() -> None:
    reference = np.array([0.1257, -0.1321, 0.6404, 0.1049, -0.5357])
    current = np.array([0.5339, 1.6648, 1.2365, -0.7445, -1.4185])

    from core.altdata.drift import _ks_2samp_fallback

    statistic, fallback_pvalue = _ks_2samp_fallback(reference, current)

    try:
        from scipy import stats as scipy_stats  # type: ignore
    except Exception:  # pragma: no cover - SciPy optional
        pytest.skip("SciPy not available to validate fallback p-values")

    expected_statistic, scipy_pvalue = scipy_stats.ks_2samp(reference, current)
    assert statistic == pytest.approx(float(expected_statistic))
    assert fallback_pvalue == pytest.approx(float(scipy_pvalue), rel=1e-2, abs=1e-3)


def test_altdata_compliance_checker_flags_issues():
    checker = AltDataComplianceChecker(restricted_regions=["EU"])
    metadata = {
        "license": "MIT",
        "usage": "commercial",
        "region": "EU",
        "expires_at": (_ts(-10)).isoformat(),
    }
    report = checker.check(metadata)
    assert not report.compliant
    severities = {issue.severity for issue in report.issues}
    assert "error" in severities


def test_drift_psi_degenerate_reference_reports_no_drift() -> None:
    """`if len(edges) < 2` -- a constant reference has no bins, so PSI is 0.

    Under Lt->GtE the degenerate guard is skipped and the histogram is built on
    a single edge, corrupting the score. A constant reference must return a
    clean, non-drifted 0.0.
    """
    monitor = DistributionDriftMonitor(method="psi", threshold=0.2)
    assessment = monitor.assess([1.0] * 50, [1.0] * 50)
    assert assessment.value == 0.0
    assert assessment.drifted is False
    assert assessment.details["bins"] == 1


def test_drift_psi_flags_divergent_distributions() -> None:
    """`psi >= threshold` -- a large PSI is flagged as drift.

    Under GtE->Lt a high PSI reads as `< threshold` and drift is missed.
    """
    monitor = DistributionDriftMonitor(method="psi", threshold=0.2)
    rng = np.random.RandomState(1)
    drifted = monitor.assess(list(rng.normal(0, 1, 500)), list(rng.normal(5, 1, 500)))
    assert drifted.value >= 0.2
    assert drifted.drifted is True
    # Negative control: identical samples do not drift.
    same = monitor.assess([1.0, 2.0, 3.0, 4.0, 5.0] * 40, [1.0, 2.0, 3.0, 4.0, 5.0] * 40)
    assert same.drifted is False


def test_drift_ks_flags_divergent_distributions() -> None:
    """`pvalue < threshold` -- a small KS p-value is flagged as drift.

    Under Lt->GtE a divergent sample's small p-value reads as `>= threshold`
    and drift is missed.
    """
    monitor = DistributionDriftMonitor(method="ks", threshold=0.05)
    rng = np.random.RandomState(2)
    drifted = monitor.assess(list(rng.normal(0, 1, 300)), list(rng.normal(5, 1, 300)))
    assert bool(drifted.drifted)  # numpy bool from the scipy path -> truthy check
    # Negative control: identical samples do not drift.
    same = monitor.assess([1.0, 2.0, 3.0, 4.0, 5.0] * 60, [1.0, 2.0, 3.0, 4.0, 5.0] * 60)
    assert not bool(same.drifted)


def test_ks_fallback_rejects_an_empty_sample() -> None:
    """`n_ref == 0 or n_cur == 0` -- either empty sample fails closed.

    Under Or->And one empty and one populated sample slips past and the KS
    statistic is computed on an empty array.
    """
    from core.altdata.drift import _ks_2samp_fallback

    with pytest.raises(ValueError, match="observations"):
        _ks_2samp_fallback(np.array([], dtype=float), np.array([1.0, 2.0, 3.0]))


def test_ks_asymptotic_pvalue_boundaries() -> None:
    """`if adjusted <= 0.0: return 1.0` and the alternating `indices % 2 == 1`.

    A zero statistic yields p=1.0 (LtE->Gt would fall through to the series);
    a positive statistic yields a positive p-value whose sign series must
    alternate as +,-,+,... (Eq->NotEq flips every sign, negating the sum so it
    clips to 0.0).
    """
    from core.altdata.drift import _ks_pvalue_asymptotic

    assert _ks_pvalue_asymptotic(0.0, 100, 100) == 1.0
    assert _ks_pvalue_asymptotic(0.3, 100, 100) > 0.0
