"""Unit tests for the Binance-perp L2 collector parser + sharding logic."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from research.microstructure.l2_schema import N_LEVELS, l2_schema
from scripts.collect_binance_perp_l2 import ShardWriter, _parse_depth


def _make_msg(symbol: str, ts: int, update_id: int) -> dict[str, Any]:
    bids = [[str(100 - 0.01 * k), str(1.0 + k)] for k in range(N_LEVELS + 2)]
    asks = [[str(100 + 0.01 * (k + 1)), str(1.0 + k)] for k in range(N_LEVELS + 2)]
    return {
        "stream": f"{symbol.lower()}@depth{N_LEVELS}@100ms",
        "data": {
            "e": "depthUpdate",
            "E": ts,
            "s": symbol,
            "u": update_id,
            "b": bids,
            "a": asks,
        },
    }


def test_parse_depth_ok() -> None:
    msg = _make_msg("BTCUSDT", 1_700_000_000_000, 42)
    row = _parse_depth(msg, ts_ingest_ms=1_700_000_000_010)
    assert row is not None
    assert row["symbol"] == "BTCUSDT"
    assert row["ts_event"] == 1_700_000_000_000
    assert row["update_id"] == 42
    assert row["bid_px_1"] == 100.0
    assert row["ask_px_1"] == 100.01
    for k in range(1, N_LEVELS + 1):
        assert f"bid_px_{k}" in row and f"ask_sz_{k}" in row


def test_parse_depth_rejects_short_book() -> None:
    msg = _make_msg("BTCUSDT", 1_700_000_000_000, 1)
    msg["data"]["b"] = msg["data"]["b"][:2]
    assert _parse_depth(msg, ts_ingest_ms=0) is None


def test_parse_depth_rejects_malformed() -> None:
    assert _parse_depth({"data": None}, ts_ingest_ms=0) is None
    assert _parse_depth({"data": {"b": [], "a": []}}, ts_ingest_ms=0) is None


def test_shard_writer_flushes_hourly_shards() -> None:
    with tempfile.TemporaryDirectory() as td:
        writer = ShardWriter(Path(td))
        hour_0_ms = 1_700_000_000_000
        hour_1_ms = hour_0_ms + 3_600_000
        for k, ts in enumerate([hour_0_ms, hour_0_ms + 500, hour_1_ms, hour_1_ms + 1000]):
            msg = _make_msg("BTCUSDT", ts, k)
            row = _parse_depth(msg, ts_ingest_ms=ts + 5)
            assert row is not None
            writer.append(row)
        written = writer.maybe_flush(force=True)
        assert written == 4
        shards = sorted(Path(td).glob("BTCUSDT_hour_*.parquet"))
        assert len(shards) == 2
        total_rows = 0
        schema = l2_schema()
        for p in shards:
            tbl = pq.read_table(p, schema=schema)
            total_rows += tbl.num_rows
        assert total_rows == 4


def test_shard_writer_appends_on_existing_shard() -> None:
    with tempfile.TemporaryDirectory() as td:
        writer = ShardWriter(Path(td))
        hour_ms = 1_700_000_000_000
        for k in range(3):
            msg = _make_msg("ETHUSDT", hour_ms + 100 * k, k)
            row = _parse_depth(msg, ts_ingest_ms=0)
            assert row is not None
            writer.append(row)
        writer.maybe_flush(force=True)
        for k in range(3, 7):
            msg = _make_msg("ETHUSDT", hour_ms + 100 * k, k)
            row = _parse_depth(msg, ts_ingest_ms=0)
            assert row is not None
            writer.append(row)
        writer.maybe_flush(force=True)
        shards = list(Path(td).glob("ETHUSDT_hour_*.parquet"))
        assert len(shards) == 1
        tbl = pq.read_table(shards[0], schema=l2_schema())
        assert tbl.num_rows == 7
