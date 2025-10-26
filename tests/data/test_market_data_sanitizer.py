from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from src.data.market_sanitizer import (
    MarketDataSanitizer,
    SanitizationIssueKind,
)

UTC = timezone.utc


def _frame_from_prices(prices: list[float], *, base: datetime, gap: int = 1) -> pd.DataFrame:
    timestamps = [base + timedelta(seconds=i * gap) for i in range(len(prices))]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "price": prices,
            "volume": [1.0] * len(prices),
            "symbol": ["btcusdt"] * len(prices),
            "venue": ["binance"] * len(prices),
            "supplier": ["alpha"] * len(prices),
        }
    )


def test_outliers_removed_and_lineage_matches_checksum() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    frame = _frame_from_prices([100.0, 101.0, 160.0, 102.0], base=base)

    sanitizer = MarketDataSanitizer(
        price_mad_threshold=3.0,
        max_staleness=timedelta(minutes=5),
    )
    result = sanitizer.sanitize(
        frame,
        ingestion_time=base + timedelta(seconds=10),
        parent_versions=("feed:v1",),
    )

    assert len(result.data) == 3
    assert any(issue.kind is SanitizationIssueKind.OUTLIER for issue in result.issues)
    assert result.lineage.data_fingerprint == result.checksum
    assert all(symbol == "BTC/USDT" for symbol in result.data["symbol"])
    assert all(venue == "BINANCE" for venue in result.data["venue"])
    assert result.data["timestamp"].dt.tz == UTC


def test_stale_ticks_are_removed() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    frame = _frame_from_prices([100.0, 100.5, 101.0], base=base)

    sanitizer = MarketDataSanitizer(
        price_mad_threshold=10.0,
        max_staleness=timedelta(seconds=1),
    )
    result = sanitizer.sanitize(frame, ingestion_time=base + timedelta(seconds=2))

    assert len(result.data) == 2
    assert any(issue.kind is SanitizationIssueKind.STALE_TICK for issue in result.issues)
    assert result.dropped.shape[0] == 1


def test_gap_detection_reports_issue_without_dropping_rows() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "timestamp": [
                base,
                base + timedelta(seconds=1),
                base + timedelta(seconds=5),
                base + timedelta(seconds=6),
            ],
            "price": [100.0, 100.1, 100.2, 100.3],
            "volume": [1.0, 1.0, 1.0, 1.0],
            "symbol": ["btcusdt"] * 4,
            "venue": ["binance"] * 4,
            "supplier": ["alpha"] * 4,
        }
    )

    sanitizer = MarketDataSanitizer(
        price_mad_threshold=10.0,
        max_staleness=timedelta(minutes=5),
        expected_frequency=pd.Timedelta(seconds=1),
        gap_tolerance=pd.Timedelta(milliseconds=500),
    )
    result = sanitizer.sanitize(frame, ingestion_time=base + timedelta(seconds=6))

    assert len(result.data) == len(frame)
    assert any(issue.kind is SanitizationIssueKind.GAP for issue in result.issues)


def test_quarantine_blocks_supplier_after_threshold() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    frame = _frame_from_prices([100.0, 101.0, 102.0, 1000.0, 1200.0], base=base)

    sanitizer = MarketDataSanitizer(
        price_mad_threshold=3.0,
        max_staleness=None,
        quarantine_threshold=2,
    )
    first_result = sanitizer.sanitize(frame, ingestion_time=base + timedelta(seconds=3))

    assert first_result.data.empty
    assert "alpha" in first_result.quarantined_suppliers
    assert any(
        issue.kind is SanitizationIssueKind.SUPPLIER_QUARANTINED for issue in first_result.issues
    )

    follow_up_frame = _frame_from_prices([101.0, 101.5], base=base + timedelta(seconds=10))
    follow_up = sanitizer.sanitize(
        follow_up_frame,
        ingestion_time=base + timedelta(seconds=12),
    )

    assert follow_up.data.empty
    assert any(
        issue.kind is SanitizationIssueKind.SUPPLIER_QUARANTINED for issue in follow_up.issues
    )
    assert follow_up.dropped.shape[0] == len(follow_up_frame)
