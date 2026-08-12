#!/usr/bin/env python3
"""Diurnal profile CLI — folds multiple L2 sessions by UTC hour.

Usage:
    python scripts/run_l2_diurnal_profile.py \\
        --data-dir data/binance_l2_perp \\
        --data-dir data/binance_l2_perp_v2 \\
        --data-dir data/binance_l2_perp_v3 \\
        --output results/L2_DIURNAL_PROFILE.json

Emits SIGN_FLIP_CONFIRMED / SIGN_STABLE / UNDERPOWERED verdict +
per-hour IC / p-value table.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from research.microstructure.diurnal import (
    compute_diurnal_profile,
    profile_to_json_dict,
    session_start_ms_from_frames,
)
from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS

_log = logging.getLogger("l2_diurnal")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        action="append",
        type=Path,
        required=True,
        help="Session parquet-shard dir (pass multiple times for cross-session)",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/L2_DIURNAL_PROFILE.json"),
    )
    parser.add_argument("--horizon-sec", type=int, default=180)
    parser.add_argument("--min-rows-per-hour", type=int, default=300)
    parser.add_argument("--perm-trials", type=int, default=500)
    parser.add_argument("--pvalue-gate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    sessions = []
    for d in args.data_dir:
        d = Path(d)
        if not d.exists():
            _log.error("missing data dir: %s", d)
            return 2
        frames = load_parquets(d, symbols)
        if not frames:
            _log.warning("no shards in %s — skipping", d)
            continue
        try:
            features = build_feature_frame(frames, symbols)
        except ValueError as exc:
            _log.warning("insufficient overlap in %s: %s — skipping", d, exc)
            continue
        start_ms = session_start_ms_from_frames(frames)
        sessions.append((d.name, features, start_ms))
        _log.info(
            "loaded %s: %d rows × %d symbols, start_ms=%d",
            d.name,
            features.n_rows,
            features.n_symbols,
            start_ms,
        )

    if not sessions:
        _log.error("no valid sessions loaded")
        return 2

    profile = compute_diurnal_profile(
        sessions,
        horizon_sec=int(args.horizon_sec),
        min_rows_per_hour=int(args.min_rows_per_hour),
        perm_trials=int(args.perm_trials),
        pvalue_gate=float(args.pvalue_gate),
        seed=int(args.seed),
    )

    body = json.dumps(profile_to_json_dict(profile), indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)
    _log.info(
        "verdict: %s — %d positive hrs, %d negative hrs, %d sessions",
        profile.verdict,
        profile.n_significant_positive,
        profile.n_significant_negative,
        len(profile.sessions_used),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
