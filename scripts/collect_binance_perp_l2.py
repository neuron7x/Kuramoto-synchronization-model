#!/usr/bin/env python3
"""Minimal Binance USDT-M perpetual L2 depth collector.

Streams depth5@100ms for N symbols, parses each message into the canonical
L2 schema, flushes hourly parquet shards to `data/binance_l2_perp/`.
Designed for a 6-10h fail-fast collection, not a 7-day production run.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import time
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import websockets
from websockets.exceptions import ConnectionClosed

from research.microstructure.l2_schema import (
    DEFAULT_SYMBOLS,
    N_LEVELS,
    l2_schema,
    level_columns,
)

_log = logging.getLogger("binance_perp_l2")

_WS_BASE = "wss://fstream.binance.com/stream"
_FLUSH_EVERY_SEC = 60.0
_FLUSH_EVERY_ROWS = 5_000


def _build_url(symbols: tuple[str, ...]) -> str:
    streams = "/".join(f"{s.lower()}@depth{N_LEVELS}@100ms" for s in symbols)
    return f"{_WS_BASE}?streams={streams}"


def _parse_depth(msg: dict[str, Any], ts_ingest_ms: int) -> dict[str, Any] | None:
    data = msg.get("data")
    if not isinstance(data, dict):
        return None
    bids_raw = data.get("b")
    asks_raw = data.get("a")
    if not isinstance(bids_raw, list) or not isinstance(asks_raw, list):
        return None
    if len(bids_raw) < N_LEVELS or len(asks_raw) < N_LEVELS:
        return None
    symbol = str(data.get("s", ""))
    ts_event = int(data.get("E", 0))
    update_id = int(data.get("u", 0))
    if not symbol or ts_event == 0:
        return None
    row: dict[str, Any] = {
        "ts_event": ts_event,
        "ts_ingest": ts_ingest_ms,
        "symbol": symbol,
        "update_id": update_id,
    }
    for k in range(N_LEVELS):
        b_px, b_sz = bids_raw[k][0], bids_raw[k][1]
        a_px, a_sz = asks_raw[k][0], asks_raw[k][1]
        row[f"bid_px_{k + 1}"] = float(b_px)
        row[f"bid_sz_{k + 1}"] = float(b_sz)
        row[f"ask_px_{k + 1}"] = float(a_px)
        row[f"ask_sz_{k + 1}"] = float(a_sz)
    return row


class ShardWriter:
    """Accumulates rows and flushes to hourly parquet shards per symbol."""

    def __init__(self, out_dir: Path) -> None:
        self._out_dir = out_dir
        self._rows: list[dict[str, Any]] = []
        self._last_flush_ts = time.monotonic()
        self._schema = l2_schema()
        self._columns = ["ts_event", "ts_ingest", "symbol", "update_id", *level_columns()]
        self._out_dir.mkdir(parents=True, exist_ok=True)

    def append(self, row: dict[str, Any]) -> None:
        self._rows.append(row)

    def maybe_flush(self, *, force: bool = False) -> int:
        now = time.monotonic()
        elapsed = now - self._last_flush_ts
        if not force and len(self._rows) < _FLUSH_EVERY_ROWS and elapsed < _FLUSH_EVERY_SEC:
            return 0
        if not self._rows:
            self._last_flush_ts = now
            return 0
        written = self._flush_rows(self._rows)
        self._rows = []
        self._last_flush_ts = now
        return written

    def _flush_rows(self, rows: list[dict[str, Any]]) -> int:
        shards: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for r in rows:
            hour_bucket = r["ts_event"] // 3_600_000
            shards.setdefault((r["symbol"], hour_bucket), []).append(r)
        written = 0
        for (symbol, hour_bucket), shard_rows in shards.items():
            path = self._out_dir / f"{symbol}_hour_{hour_bucket}.parquet"
            columns = {c: [r[c] for r in shard_rows] for c in self._columns}
            table = pa.Table.from_pydict(columns, schema=self._schema)
            if path.exists():
                existing = pq.read_table(path, schema=self._schema)
                table = pa.concat_tables([existing, table])
            pq.write_table(table, path, compression="zstd")
            written += len(shard_rows)
        _log.info("flushed %d rows across %d shards", written, len(shards))
        return written


async def _run_collector(
    symbols: tuple[str, ...],
    out_dir: Path,
    duration_sec: float,
    stop_event: asyncio.Event,
) -> int:
    writer = ShardWriter(out_dir)
    url = _build_url(symbols)
    started = time.monotonic()
    total_rows = 0
    backoff = 1.0

    while not stop_event.is_set():
        if time.monotonic() - started >= duration_sec:
            _log.info("duration reached (%.0fs) — exiting", duration_sec)
            break
        try:
            _log.info("connecting: %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                backoff = 1.0
                while not stop_event.is_set():
                    if time.monotonic() - started >= duration_sec:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    except TimeoutError:
                        _log.warning("recv timeout — reconnecting")
                        break
                    ts_ingest_ms = int(time.time() * 1000)
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    row = _parse_depth(msg, ts_ingest_ms)
                    if row is None:
                        continue
                    writer.append(row)
                    total_rows += 1
                    writer.maybe_flush()
        except (ConnectionClosed, OSError) as exc:
            _log.warning("connection dropped: %r — sleeping %.1fs", exc, backoff)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2.0, 60.0)

    writer.maybe_flush(force=True)
    _log.info("collector exiting: total rows ingested = %d", total_rows)
    return total_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated list of perp symbols (e.g. BTCUSDT,ETHUSDT,...)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/binance_l2_perp"),
        help="Output directory for parquet shards",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=6 * 3600.0,
        help="Run duration in seconds (default 6h). Ignored if --unbounded.",
    )
    parser.add_argument(
        "--unbounded",
        action="store_true",
        help="Run indefinitely until SIGTERM/SIGINT (systemd-managed lifetime).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    if not symbols:
        _log.error("no symbols provided")
        return 2

    stop_event = asyncio.Event()
    loop = asyncio.new_event_loop()

    def _handle_sigterm() -> None:
        _log.info("SIGTERM received — shutting down")
        stop_event.set()

    with contextlib.suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, _handle_sigterm)

    effective_duration_sec = float("inf") if bool(args.unbounded) else float(args.duration_sec)
    if bool(args.unbounded):
        _log.info("unbounded mode — running until SIGTERM/SIGINT")

    try:
        total = loop.run_until_complete(
            _run_collector(
                symbols=symbols,
                out_dir=Path(args.out),
                duration_sec=effective_duration_sec,
                stop_event=stop_event,
            )
        )
    finally:
        loop.close()

    return 0 if total > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
