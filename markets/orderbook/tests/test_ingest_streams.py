# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from markets.orderbook.src.ingest import (
    IngestConfig,
    InMemoryMetricsRecorder,
    OrderBookDiff,
    OrderBookIngestService,
    OrderBookSnapshot,
    OrderBookStateError,
    PriceLevel,
)
from markets.orderbook.src.ingest.exchanges import binance, okx


def _ts(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1_000, tz=timezone.utc)


def test_binance_ingest_flow() -> None:
    metrics = InMemoryMetricsRecorder()
    requests: list[tuple[str, str]] = []

    def record_request(instrument: str, reason: str) -> None:
        requests.append((instrument, reason))

    service = OrderBookIngestService(
        config=IngestConfig(snapshot_interval=timedelta(seconds=30), snapshot_depth=5),
        metrics=metrics,
        snapshot_requester=record_request,
    )

    snapshot_payload = {
        "lastUpdateId": 1027024,
        "bids": [["40000.00000000", "1.50000000"], ["39900.00000000", "2.00000000"]],
        "asks": [["40010.00000000", "1.20000000"], ["40020.00000000", "1.80000000"]],
        "E": 1_700_000_000_000,
    }
    arrival = _ts(1_700_000_000_500)
    snapshot = binance.parse_snapshot(
        snapshot_payload, instrument="BTCUSDT", ts_arrival=arrival
    )
    service.process_snapshot(snapshot)

    diff_payload = {
        "e": "depthUpdate",
        "E": 1_700_000_001_000,
        "s": "BTCUSDT",
        "U": 1_027_025,
        "u": 1_027_025,
        "b": [["40000.00000000", "0"]],
        "a": [["40010.00000000", "0"]],
    }
    diff = binance.parse_diff(diff_payload, ts_arrival=_ts(1_700_000_001_500))
    result = service.process_diff(diff)
    assert result is not None
    assert result.sequence == diff.sequence_end

    state = service.store.for_instrument("BTCUSDT")
    best_bid = state.best_bid()
    best_ask = state.best_ask()
    assert best_bid is not None
    assert best_bid.price == PriceLevel.from_raw("39900.0", "1").price
    assert best_bid.quantity == PriceLevel.from_raw("39900.0", "2.0").quantity
    assert best_ask is not None
    assert best_ask.price == PriceLevel.from_raw("40020.0", "0").price

    metrics_snapshot = metrics.snapshot()["BTCUSDT"]
    assert metrics_snapshot.latency_ms is not None and metrics_snapshot.latency_ms >= 0
    assert (
        metrics_snapshot.freshness_ms is not None and metrics_snapshot.freshness_ms >= 0
    )
    assert metrics_snapshot.gap_events == 0
    assert not requests  # no recovery requested

    # On demand snapshot should match current state
    snap = state.get_snapshot(depth=1)
    assert snap.bids[0].price == best_bid.price
    assert snap.asks[0].price == best_ask.price


def test_sequence_gap_triggers_recovery() -> None:
    metrics = InMemoryMetricsRecorder()
    requests: list[tuple[str, str]] = []

    def capture_request(instrument: str, reason: str) -> None:
        requests.append((instrument, reason))

    service = OrderBookIngestService(
        config=IngestConfig(snapshot_interval=timedelta(seconds=30), snapshot_depth=5),
        metrics=metrics,
        snapshot_requester=capture_request,
    )

    snapshot = binance.parse_snapshot(
        {"lastUpdateId": 200, "bids": [["10", "1"]], "asks": [["11", "1"]]},
        instrument="ETHUSDT",
        ts_arrival=_ts(1_700_010_000_000),
    )
    service.process_snapshot(snapshot)

    gap_payload = {
        "e": "depthUpdate",
        "E": 1_700_010_000_500,
        "s": "ETHUSDT",
        "U": 205,
        "u": 205,
        "b": [["10", "0.5"]],
        "a": [],
    }
    diff = binance.parse_diff(gap_payload, ts_arrival=_ts(1_700_010_001_000))

    with pytest.raises(OrderBookStateError):
        service.process_diff(diff)

    assert requests and requests[0][0] == "ETHUSDT"
    metrics_snapshot = metrics.snapshot()["ETHUSDT"]
    assert metrics_snapshot.gap_events == 1


def test_okx_snapshot_and_updates_indexed_by_time() -> None:
    metrics = InMemoryMetricsRecorder()
    requests: list[tuple[str, str]] = []

    def capture_request(instrument: str, reason: str) -> None:
        requests.append((instrument, reason))

    service = OrderBookIngestService(
        config=IngestConfig(
            snapshot_interval=timedelta(seconds=1), snapshot_depth=2, max_snapshots=8
        ),
        metrics=metrics,
        snapshot_requester=capture_request,
    )

    snapshot_payload = {
        "action": "snapshot",
        "arg": {"channel": "books-l2-tbt", "instId": "BTC-USDT"},
        "data": [
            {
                "instId": "BTC-USDT",
                "seqId": "3000",
                "ts": "1700002000000",
                "bids": [["30000", "1", "1700002000000"]],
                "asks": [["30010", "1.5", "1700002000000"]],
            }
        ],
    }
    snap_obj = okx.parse(snapshot_payload, ts_arrival=_ts(1_700_002_000_100))
    assert isinstance(snap_obj, OrderBookSnapshot)
    service.process_snapshot(snap_obj)

    update_payload = {
        "action": "update",
        "arg": {"channel": "books-l2-tbt", "instId": "BTC-USDT"},
        "data": [
            {
                "instId": "BTC-USDT",
                "seqId": "3002",
                "prevSeqId": "3000",
                "ts": "1700002005000",
                "bids": [["30005", "0.7", "1700002005000"]],
                "asks": [["30010", "0", "1700002005000"]],
            }
        ],
    }
    diff_obj = okx.parse(update_payload, ts_arrival=_ts(1_700_002_005_000))
    assert isinstance(diff_obj, OrderBookDiff)
    result = service.process_diff(diff_obj)
    assert result is not None

    store = service.store
    state = store.for_instrument("BTC-USDT")
    historic = state.snapshot_before(_ts(1_700_002_000_500))
    assert historic is not None
    assert historic.sequence == 3_000
    assert state.best_ask() is None

    assert metrics.snapshot()["BTC-USDT"].last_snapshot_ts is not None
    assert metrics.snapshot()["BTC-USDT"].gap_events == 0
