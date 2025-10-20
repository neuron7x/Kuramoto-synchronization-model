from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.pricing import (
    MarkPriceCalibrator,
    MarkPriceContributor,
    MarkPriceRejection,
    MarkPriceResult,
    MarkPriceSample,
    compute_mark_price,
)


def _ts(minutes: float) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def test_mark_price_weighted_average() -> None:
    samples = (
        MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(0), source="index"),
        MarkPriceSample(price=101.0, weight=2.0, timestamp=_ts(0.5), source="spot"),
        MarkPriceSample(price=100.5, weight=1.5, timestamp=_ts(0.75), source="perp"),
    )

    result = compute_mark_price(samples, now=_ts(1), max_staleness=None)

    expected = (100.0 * 1.0 + 101.0 * 2.0 + 100.5 * 1.5) / (1.0 + 2.0 + 1.5)
    assert isinstance(result, MarkPriceResult)
    assert pytest.approx(result.mark_price) == expected
    assert result.contributor_count == 3
    assert all(isinstance(contributor, MarkPriceContributor) for contributor in result.contributors)
    assert not result.fallback_used


def test_mark_price_rejects_outliers() -> None:
    samples = (
        MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(0), source="index"),
        MarkPriceSample(price=300.0, weight=1.0, timestamp=_ts(0.1), source="manipulated"),
        MarkPriceSample(price=101.0, weight=1.0, timestamp=_ts(0.2), source="spot"),
    )

    result = compute_mark_price(samples, now=_ts(0.3), max_deviation_bps=150.0)

    assert pytest.approx(result.mark_price) == 100.5
    assert result.contributor_count == 2
    reasons = {rejection.reason for rejection in result.rejections}
    assert "outlier" in reasons
    assert not result.fallback_used


def test_mark_price_handles_staleness_and_fallback() -> None:
    samples = (
        MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(-10), source="stale"),
    )

    result = compute_mark_price(
        samples,
        now=_ts(0),
        max_staleness=timedelta(minutes=1),
        fallback_price=99.0,
    )

    assert result.fallback_used
    assert result.mark_price == pytest.approx(99.0)
    assert not result.contributors
    assert {rejection.reason for rejection in result.rejections} == {"stale"}


def test_mark_price_requires_fallback_when_no_samples() -> None:
    with pytest.raises(ValueError):
        compute_mark_price((), now=_ts(0))


def test_mark_price_requires_min_samples_without_fallback() -> None:
    samples = (
        MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(0), source="spot"),
    )

    with pytest.raises(ValueError):
        compute_mark_price(samples, min_samples=2, now=_ts(0.1))


def test_time_decay_biases_towards_recent_prices() -> None:
    samples = (
        MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(0), source="old"),
        MarkPriceSample(price=102.0, weight=1.0, timestamp=_ts(4), source="recent"),
    )

    result = compute_mark_price(
        samples,
        now=_ts(4),
        max_staleness=None,
        time_decay_half_life=timedelta(minutes=2),
    )

    assert result.mark_price > 101.0
    assert result.mark_price < 102.0


def test_mark_price_calibrator_window_and_reset() -> None:
    calibrator = MarkPriceCalibrator(
        max_samples=2,
        max_staleness=timedelta(minutes=5),
        time_decay_half_life=timedelta(minutes=5),
    )
    calibrator.add_sample(MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(0), source="index"))
    calibrator.add_sample(MarkPriceSample(price=101.0, weight=1.0, timestamp=_ts(1), source="spot"))
    calibrator.add_sample(MarkPriceSample(price=102.0, weight=1.0, timestamp=_ts(2), source="perp"))

    result = calibrator.compute(now=_ts(2))
    assert result.contributor_count == 2
    decay = 0.5 ** (
        (_ts(2) - _ts(1)).total_seconds()
        / timedelta(minutes=5).total_seconds()
    )
    expected = (101.0 * decay + 102.0) / (decay + 1.0)
    assert pytest.approx(result.mark_price) == expected

    calibrator.reset()
    with pytest.raises(ValueError):
        calibrator.compute(now=_ts(3))


def test_mark_price_calibrator_prunes_stale_samples() -> None:
    calibrator = MarkPriceCalibrator(
        max_samples=10,
        max_staleness=timedelta(minutes=1),
        fallback_price=100.0,
    )
    calibrator.add_sample(MarkPriceSample(price=100.0, weight=1.0, timestamp=_ts(-5), source="stale"))
    calibrator.add_sample(MarkPriceSample(price=101.0, weight=1.0, timestamp=_ts(0), source="fresh"))

    result = calibrator.compute(now=_ts(0))
    assert result.contributor_count == 1
    assert result.mark_price == pytest.approx(101.0)
    assert result.contributors[0].sample.source == "fresh"
