#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Ingest real Binance USD-M futures top-of-book data into the kernel bar schema.

Why this exists
---------------
Every empirical claim in this repository was capped at synthetic evidence. The
release gate's ``G.real_data`` probe was RED, and correctly so: the only market
data on disk (``data/askar_full/``) carries **no licence and no provenance
marker**, so it cannot lift a claim past rung 2 of the 14-rung maturity ladder
(``docs/EVIDENCE_ONTOLOGY.md``). The blocker was never "no data" — it was "no
data whose origin can be proved".

Binance publishes its historical market data openly at ``data.binance.vision``
**together with a SHA-256 CHECKSUM for every archive**. That is a provenance
chain the exchange itself signs, not an assertion by whoever ran the download.
This tool refuses to emit a bar file unless the published checksum matches the
bytes it received.

Data contract
-------------
Source: ``futures/um/daily/bookTicker/<SYMBOL>/<SYMBOL>-bookTicker-<DATE>.zip``
Columns: ``update_id, best_bid_price, best_bid_qty, best_ask_price,
best_ask_qty, transaction_time, event_time`` — one row per top-of-book change.

**The rows are not time-ordered.** Binance's dumps interleave streams: row 2 of
the 2024-02-05 BTCUSDT file is 15 hours after row 1. Reading them in file order
produces a garbage time series. This tool bins by ``transaction_time`` and keeps
the last quote per bin by that timestamp, which is order-independent and needs no
global sort (86 400 bins/day at 1 s, so memory is O(bins), not O(rows)).

Output (the schema `research/kernels/*` expect, index = timestamp):

    ts, bid_close, ask_close, bid_volume, ask_volume, updates

`mid`, `spread` and `mid_returns` are derived downstream by the kernels, never
stored — a derived column in a data file is a place for drift to hide.

Emits a sidecar ``<out>.provenance.json`` recording the source URL, the
exchange-published SHA-256, the locally computed SHA-256, and the row counts.

Usage::

    python tools/market_data/binance_book_ingest.py --symbol BTCUSDT --date 2024-02-05
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/daily/bookTicker"
LICENSE_PROVENANCE = (
    "Binance Public Market Data (data.binance.vision) — historical market data "
    "published openly by the venue for free download and analysis. Integrity is "
    "not asserted by this repository: each archive ships a SHA-256 CHECKSUM "
    "published by Binance alongside it, and this ingest fails closed unless the "
    "bytes received hash to that published value."
)


def _fetch(url: str, timeout: int = 600) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def ingest(symbol: str, date: str, bar_ms: int, out_dir: Path) -> dict:
    zip_url = f"{BASE}/{symbol}/{symbol}-bookTicker-{date}.zip"
    sum_url = f"{zip_url}.CHECKSUM"

    print(f"  fetching {symbol} {date} …", flush=True)
    blob = _fetch(zip_url)
    published = _fetch(sum_url).decode().split()[0].strip().lower()
    computed = hashlib.sha256(blob).hexdigest()

    if published != computed:
        raise SystemExit(
            f"CHECKSUM MISMATCH for {symbol} {date}\n"
            f"  published by venue: {published}\n"
            f"  computed locally  : {computed}\n"
            "Refusing to emit data whose provenance cannot be proved."
        )
    print(f"  checksum verified  {computed[:16]}…  ({len(blob) / 1048576:.0f} MB)", flush=True)

    # bin -> [last_tx_ms, bid, bid_qty, ask, ask_qty, updates]
    bins: dict[int, list] = {}
    rows_in = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        member = z.namelist()[0]
        with z.open(member) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
            header = next(reader)
            ix = {name: i for i, name in enumerate(header)}
            for row in reader:
                rows_in += 1
                try:
                    tx = int(row[ix["transaction_time"]])
                    bid = float(row[ix["best_bid_price"]])
                    bidq = float(row[ix["best_bid_qty"]])
                    ask = float(row[ix["best_ask_price"]])
                    askq = float(row[ix["best_ask_qty"]])
                except (ValueError, IndexError, KeyError):
                    continue  # a malformed row is dropped, never repaired
                # Fail-closed on a crossed or degenerate book: it is a data defect,
                # not a market state, and silently keeping it would poison the spread.
                if not (ask > bid > 0.0) or bidq <= 0.0 or askq <= 0.0:
                    continue
                b = tx // bar_ms
                cur = bins.get(b)
                if cur is None:
                    bins[b] = [tx, bid, bidq, ask, askq, 1]
                else:
                    cur[5] += 1
                    if tx >= cur[0]:
                        cur[0], cur[1], cur[2], cur[3], cur[4] = tx, bid, bidq, ask, askq

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{symbol}-{date}-bookticker-{bar_ms}ms.csv"

    import datetime as dt

    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "bid_close", "ask_close", "bid_volume", "ask_volume", "updates"])
        for b in sorted(bins):
            _, bid, bidq, ask, askq, n = bins[b]
            ts = dt.datetime.fromtimestamp(b * bar_ms / 1000, tz=dt.timezone.utc)
            w.writerow(
                [ts.strftime("%Y-%m-%dT%H:%M:%S%z"), f"{bid:.8f}", f"{ask:.8f}",
                 f"{bidq:.8f}", f"{askq:.8f}", n]
            )

    data_sha = hashlib.sha256(out_csv.read_bytes()).hexdigest()
    prov = {
        "schema_version": "1.0.0",
        "venue": "binance-usdm-futures",
        "symbol": symbol,
        "date_utc": date,
        "product": "bookTicker (top-of-book, per-update)",
        "source_url": zip_url,
        "checksum_url": sum_url,
        "venue_published_sha256": published,
        "downloaded_sha256": computed,
        "checksum_verified": True,
        "license_provenance": LICENSE_PROVENANCE,
        "bar_ms": bar_ms,
        "rows_in": rows_in,
        "rows_out": len(bins),
        "out_csv": out_csv.as_posix(),
        "out_csv_sha256": data_sha,
        "out_csv_bytes": out_csv.stat().st_size,
        "replay_command": (
            f"python tools/market_data/binance_book_ingest.py --symbol {symbol} "
            f"--date {date} --bar-ms {bar_ms}"
        ),
        "notes": (
            "Rows in the venue dump are NOT time-ordered; this ingest bins by "
            "transaction_time and keeps the last quote per bin. Crossed or "
            "non-positive books are dropped, never repaired."
        ),
    }
    (out_csv.with_suffix(".provenance.json")).write_text(
        json.dumps(prov, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"  {rows_in:,} quotes -> {len(bins):,} bars  "
        f"({out_csv.stat().st_size / 1048576:.1f} MB)  sha {data_sha[:16]}…",
        flush=True,
    )
    return prov


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--bar-ms", type=int, default=1000)
    ap.add_argument("--out-dir", default="data/real/binance_bookticker")
    args = ap.parse_args()
    ingest(args.symbol, args.date, args.bar_ms, Path(args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
