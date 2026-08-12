#!/usr/bin/env python3
"""Collect a real, hash-pinnable L2 order-book session from Binance USD-M futures.

Public REST depth endpoint — no API key, no auth. Each poll is one real
order-book snapshot (top-`depth` levels per side). The raw CSV this writes is the
*immutable* substrate: once collected it is frozen and SHA-256-pinned by the
ingest step (`research_lines.ricci_microstructure_v1.ingest`), satisfying the
lane's `immutability_required` / `required_hash: sha256` contract.

This is the lane's declared substrate (`crypto_perps depth5@100ms`); LOBSTER's
free equity samples moved behind a keyed API, so Binance futures depth is the
faithful, key-free real source. Collection itself is *not* reproducible (live
market) — reproducibility is anchored on the frozen file hash, not the fetch.

CSV columns (matches the Pandera L2 contract):
    timestamp, price, bid_px_i, bid_sz_i, ask_px_i, ask_sz_i   for i = 1..depth
where `price` is the mid (= (best_bid + best_ask) / 2).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

_ENDPOINT = "https://fapi.binance.com/fapi/v1/depth"


def _fetch_snapshot(symbol: str, depth: int, timeout_sec: float) -> dict[str, object]:
    url = f"{_ENDPOINT}?symbol={symbol}&limit={depth}"
    if not url.startswith("https://"):  # only ever the pinned Binance https endpoint
        raise ValueError(f"refusing non-https url: {url}")
    with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _header(depth: int) -> list[str]:
    cols = ["timestamp", "price"]
    for i in range(1, depth + 1):
        cols += [f"bid_px_{i}", f"bid_sz_{i}", f"ask_px_{i}", f"ask_sz_{i}"]
    return cols


def _row(snapshot: dict[str, object], depth: int, recv_ns: int) -> list[str] | None:
    bids = snapshot.get("bids")
    asks = snapshot.get("asks")
    if not isinstance(bids, list) or not isinstance(asks, list):
        return None
    if len(bids) < depth or len(asks) < depth:
        return None
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid = (best_bid + best_ask) / 2.0
    # local receive time (ns) → strictly monotonic, unique per poll (the book may
    # be unchanged between polls; that is a valid repeated time sample)
    row = [str(recv_ns), f"{mid:.8f}"]
    for i in range(depth):
        bpx, bsz = bids[i][0], bids[i][1]
        apx, asz = asks[i][0], asks[i][1]
        row += [str(bpx), str(bsz), str(apx), str(asz)]
    return row


def collect(
    symbol: str,
    depth: int,
    duration_sec: float,
    interval_sec: float,
    out_path: Path,
    timeout_sec: float = 5.0,
) -> int:
    """Poll the depth endpoint and stream rows to `out_path`. Returns row count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    deadline = time.monotonic() + duration_sec
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")  # LF, not csv default CRLF
        writer.writerow(_header(depth))
        last_ns = 0
        while time.monotonic() < deadline:
            tick = time.monotonic()
            try:
                snap = _fetch_snapshot(symbol, depth, timeout_sec)
                recv_ns = max(time.time_ns(), last_ns + 1)  # guarantee strict monotonic
                row = _row(snap, depth, recv_ns)
                if row is not None:
                    writer.writerow(row)
                    last_ns = recv_ns
                    written += 1
                    if written % 200 == 0:
                        fh.flush()
                        print(f"  collected {written} snapshots", file=sys.stderr)
            except Exception as exc:  # best-effort live collection: never abort the session
                print(f"  poll error (continuing): {exc}", file=sys.stderr)
            sleep_for = interval_sec - (time.monotonic() - tick)
            if sleep_for > 0:
                time.sleep(sleep_for)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect real Binance L2 depth session")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--duration-sec", type=float, default=240.0)
    parser.add_argument("--interval-sec", type=float, default=0.25)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    n = collect(args.symbol, args.depth, args.duration_sec, args.interval_sec, args.out)
    print(json.dumps({"out": args.out.as_posix(), "rows": n, "symbol": args.symbol}))
    return 0 if n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
