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
    return dt.datetime(2024, 1, 1, 12, 0, tzinfo=dt.timezone.utc) + dt.timedelta(
        minutes=offset
    )


def test_news_feature_builder_aggregates_sentiment():
    analyzer = NewsSentimentAnalyzer(
        positive_tokens=["growth"], negative_tokens=["fraud"]
    )
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
    market = pd.DataFrame(
        {"close": [1.0, 1.1]}, index=pd.DatetimeIndex([_ts(0), _ts(1)])
    )
    news = pd.DataFrame(
        {"news_count": [1, 2]}, index=pd.DatetimeIndex([_ts(0), _ts(1)])
    )
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
        "license": "Proprietary",
        "usage": "commercial",
        "region": "EU",
        "expires_at": (_ts(-10)).isoformat(),
    }
    report = checker.check(metadata)
    assert not report.compliant
    severities = {issue.severity for issue in report.issues}
    assert "error" in severities
