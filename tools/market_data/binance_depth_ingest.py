#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Ingest Binance USD-M futures `bookDepth` — multi-level order-book depth.

Closes the "you only looked at top-of-book" escape in RD-GRID-002.

`bookTicker` gives the best bid/ask only (L1). `bookDepth` gives **cumulative depth in
five price bands on each side** (±1 %, ±2 %, ±3 %, ±4 %, ±5 % from mid), sampled roughly
every 30 s. That is genuine multi-level book information, and it is what the OFI-unity
kernel (`research/kernels/ofi_unity_live.py`) actually needs: it looks for `bid*`/`ask*`
column pairs and computes the leading eigenvalue of their order-flow correlation matrix.
On L1 data there is exactly one pair, the matrix is 1x1, and the kernel degenerates to
the constant 1.0 — which is why it could never have been tested on `bookTicker`.

Source columns: ``timestamp, percentage, depth, notional``. Emitted wide:

    ts, bid_1..bid_5, ask_1..ask_5   (depth, in base units)

Provenance is identical to the bookTicker ingest: the venue publishes a SHA-256 for each
archive and this tool fails closed unless the bytes hash to it.

Usage::

    python tools/market_data/binance_depth_ingest.py --symbol BTCUSDT --date 2024-02-05
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
from collections import defaultdict
from pathlib import Path

BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"
LICENSE_PROVENANCE = (
    "Binance Public Market Data (data.binance.vision) — historical market data published "
    "openly by the venue. Each archive ships a SHA-256 CHECKSUM published by Binance; this "
    "ingest fails closed unless the bytes received hash to that published value."
)
LEVELS = (1, 2, 3, 4, 5)


def _fetch(url: str, timeout: int = 600) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def ingest(symbol: str, date: str, out_dir: Path) -> dict:
    zip_url = f"{BASE}/{symbol}/{symbol}-bookDepth-{date}.zip"
    blob = _fetch(zip_url)
    published = _fetch(f"{zip_url}.CHECKSUM").decode().split()[0].strip().lower()
    computed = hashlib.sha256(blob).hexdigest()
    if published != computed:
        raise SystemExit(f"CHECKSUM MISMATCH {symbol} {date}: {published} != {computed}")

    snaps: dict[str, dict[int, float]] = defaultdict(dict)
    rows_in = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as fh:
            rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
            hdr = next(rd)
            ix = {n: i for i, n in enumerate(hdr)}
            for row in rd:
                rows_in += 1
                try:
                    ts = row[ix["timestamp"]]
                    pct = int(float(row[ix["percentage"]]))
                    depth = float(row[ix["depth"]])
                except (ValueError, IndexError, KeyError):
                    continue
                snaps[ts][pct] = depth

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{symbol}-{date}-bookdepth.csv"
    cols = [f"bid_{i}" for i in LEVELS] + [f"ask_{i}" for i in LEVELS]
    n_out = 0
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", *cols])
        for ts in sorted(snaps):
            s = snaps[ts]
            # A snapshot missing any band is dropped, never back-filled: an imputed
            # depth is a fabricated observation.
            if not all(-i in s and i in s for i in LEVELS):
                continue
            w.writerow([ts, *[f"{s[-i]:.8f}" for i in LEVELS], *[f"{s[i]:.8f}" for i in LEVELS]])
            n_out += 1

    prov = {
        "schema_version": "1.0.0",
        "venue": "binance-usdm-futures",
        "symbol": symbol,
        "date_utc": date,
        "product": "bookDepth (cumulative depth at +/-1..5% bands)",
        "source_url": zip_url,
        "venue_published_sha256": published,
        "downloaded_sha256": computed,
        "checksum_verified": True,
        "license_provenance": LICENSE_PROVENANCE,
        "rows_in": rows_in,
        "rows_out": n_out,
        "out_csv": out_csv.as_posix(),
        "out_csv_sha256": hashlib.sha256(out_csv.read_bytes()).hexdigest(),
        "out_csv_bytes": out_csv.stat().st_size,
        "replay_command": (
            f"python tools/market_data/binance_depth_ingest.py --symbol {symbol} --date {date}"
        ),
    }
    out_csv.with_suffix(".provenance.json").write_text(
        json.dumps(prov, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  {symbol} {date}  sha ok  {rows_in:,} rows -> {n_out:,} snapshots", flush=True)
    return prov


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out-dir", default="data/real/binance_bookdepth")
    a = ap.parse_args()
    ingest(a.symbol, a.date, Path(a.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
