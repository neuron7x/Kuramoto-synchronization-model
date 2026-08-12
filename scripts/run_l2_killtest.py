#!/usr/bin/env python3
"""Run the fail-fast L2 kill test against collected Binance-perp shards.

Composable CLI over `research.microstructure.killtest` + `.regime`.

Modes (composable via flags):
    - vanilla full-window gate  (no flags)
    - train/test split OOS retention   (--split FRAC)
    - regime-filtered single window    (--regime {rv,corr})
    - split + regime (test-half IC)    (--split + --regime)   ← GATE 1 path
    - cross-session (train/test dirs)  (--test-dir PATH [+ --regime])
    - N-bucket bisection (flat)        (--recursive --depth N [--cyclic])

Exit codes:
    0 — verdict produced (PROCEED / KILL / recursive body); check JSON
    2 — insufficient data / bad arguments
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.microstructure.killtest import (
    FeatureFrame,
    build_feature_frame,
    run_killtest,
    run_killtest_split,
    slice_features,
    split_verdict_to_json,
)
from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS
from research.microstructure.regime import (
    regime_mask_from_quantile,
    regime_mask_from_score,
    rolling_corr_regime,
    rolling_rv_regime,
)

_log = logging.getLogger("l2_killtest")


def _regime_score(
    name: str,
    features: FeatureFrame,
    window_rows: int,
) -> NDArray[np.float64]:
    if name == "rv":
        return rolling_rv_regime(features, window_rows=window_rows)
    if name == "corr":
        return rolling_corr_regime(features, window_rows=window_rows)
    raise ValueError(f"unknown regime: {name!r}")


def _train_threshold_mask(
    train: FeatureFrame,
    test: FeatureFrame,
    regime_name: str,
    quantile: float,
    window_rows: int,
) -> NDArray[np.bool_]:
    """Calibrate threshold on train regime score, apply to test regime score."""
    train_score = _regime_score(regime_name, train, window_rows)
    finite = train_score[np.isfinite(train_score)]
    if finite.size == 0:
        raise ValueError("train regime score has no finite values")
    threshold = float(np.quantile(finite, quantile))
    test_score = _regime_score(regime_name, test, window_rows)
    return regime_mask_from_score(test_score, threshold=threshold)


def _write_and_print(payload: dict[str, Any], path: Path) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    print(body)


def _emit_gate_value(name: str, value: float, tolerance: float = 1.0e-3) -> None:
    print(
        json.dumps(
            {"gate": name, "value": float(value), "tolerance": tolerance},
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/binance_l2_perp"),
        help="Train (or sole) parquet-shard dir",
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=None,
        help="If set, cross-session mode: --data-dir = train, --test-dir = test",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbol list",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/L2_KILLTEST_VERDICT.json"),
        help="Verdict JSON path",
    )
    parser.add_argument(
        "--split",
        type=float,
        default=None,
        help="Train/test split fraction (e.g. 0.5)",
    )
    parser.add_argument(
        "--retention-gate",
        type=float,
        default=0.5,
        help="Min IC(test)/IC(train) for split PROCEED (default 0.5)",
    )
    parser.add_argument(
        "--regime",
        choices=["rv", "corr"],
        default=None,
        help="Apply regime filter derived from rolling volatility or correlation",
    )
    parser.add_argument(
        "--regime-quantile",
        type=float,
        default=0.75,
        help="Quantile threshold for regime score (default 0.75)",
    )
    parser.add_argument(
        "--regime-window-sec",
        type=int,
        default=300,
        help="Rolling window (rows, seconds) for regime score (default 300)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Flat N-bucket bisection gate over --data-dir; requires --depth",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=8,
        help="Bucket count for --recursive (default 8)",
    )
    parser.add_argument(
        "--cyclic",
        action="store_true",
        help="Tag recursive output with cyclic_blocks metadata (= depth)",
    )
    parser.add_argument(
        "--emit-gate-value",
        choices=["ic_test_q75"],
        default=None,
        help="Print minimal {gate,value,tolerance} JSON instead of full verdict",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    symbols = tuple(s.strip().upper() for s in str(args.symbols).split(",") if s.strip())
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        _log.error("data dir does not exist: %s", data_dir)
        return 2

    train_frames = load_parquets(data_dir, symbols)
    if not train_frames:
        _log.error("no parquet shards found in %s", data_dir)
        return 2

    try:
        features = build_feature_frame(train_frames, symbols)
    except ValueError as exc:
        _log.error("insufficient overlap: %s", exc)
        return 2

    _log.info("train features: %d rows × %d symbols", features.n_rows, features.n_symbols)

    # --- Mode: recursive (flat N-bucket bisection) ---
    if args.recursive:
        if args.depth < 2:
            _log.error("--depth must be >= 2, got %d", args.depth)
            return 2
        n = features.n_rows
        bucket = n // args.depth
        leaves: list[dict[str, Any]] = []
        for i in range(args.depth):
            start = i * bucket
            end = (i + 1) * bucket if i < args.depth - 1 else n
            sub = slice_features(features, start, end)
            leaves.append(
                {
                    "index": i,
                    "start": start,
                    "end": end,
                    "verdict": asdict(run_killtest(sub)),
                }
            )
        payload: dict[str, Any] = {
            "mode": "recursive",
            "bisection_depth": args.depth,
            "cyclic_blocks": args.depth if args.cyclic else None,
            "n_rows_total": n,
            "leaves": leaves,
        }
        _write_and_print(payload, Path(args.output))
        return 0

    # --- Mode: cross-session (--test-dir) ---
    if args.test_dir is not None:
        test_dir = Path(args.test_dir)
        if not test_dir.exists():
            _log.error("test dir does not exist: %s", test_dir)
            return 2
        test_frames = load_parquets(test_dir, symbols)
        if not test_frames:
            _log.error("no parquet shards found in %s", test_dir)
            return 2
        try:
            test_features = build_feature_frame(test_frames, symbols)
        except ValueError as exc:
            _log.error("insufficient overlap in test: %s", exc)
            return 2
        _log.info(
            "test features: %d rows × %d symbols", test_features.n_rows, test_features.n_symbols
        )
        if args.regime is not None:
            mask = _train_threshold_mask(
                features,
                test_features,
                args.regime,
                args.regime_quantile,
                args.regime_window_sec,
            )
            verdict = run_killtest(test_features, regime_mask=mask)
        else:
            verdict = run_killtest(test_features)
        if args.emit_gate_value == "ic_test_q75":
            _emit_gate_value("ic_test_q75", verdict.ic_signal)
            return 0
        _write_and_print(asdict(verdict), Path(args.output))
        return 0

    # --- Mode: --split with or without --regime ---
    if args.split is not None:
        if not 0.1 <= args.split <= 0.9:
            _log.error("--split must be in [0.1, 0.9], got %s", args.split)
            return 2
        if args.regime is not None:
            mid = int(features.n_rows * float(args.split))
            train = slice_features(features, 0, mid)
            test = slice_features(features, mid, features.n_rows)
            mask = _train_threshold_mask(
                train, test, args.regime, args.regime_quantile, args.regime_window_sec
            )
            train_verdict = run_killtest(train)
            test_verdict = run_killtest(test, regime_mask=mask)
            if args.emit_gate_value == "ic_test_q75":
                _emit_gate_value("ic_test_q75", test_verdict.ic_signal)
                return 0
            payload_split: dict[str, Any] = {
                "mode": "split_with_regime",
                "split_at_fraction": float(args.split),
                "regime": args.regime,
                "regime_quantile": args.regime_quantile,
                "regime_window_sec": args.regime_window_sec,
                "train": asdict(train_verdict),
                "test": asdict(test_verdict),
                "test_ic_signal": float(test_verdict.ic_signal),
            }
            _write_and_print(payload_split, Path(args.output))
            return 0
        # --split only: existing retention-gate behavior
        split_verdict = run_killtest_split(
            features,
            split_at_fraction=float(args.split),
            retention_gate=float(args.retention_gate),
        )
        json_body = split_verdict_to_json(split_verdict)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json_body, encoding="utf-8")
        print(json_body)
        return 0

    # --- Mode: single window with or without --regime ---
    if args.regime is not None:
        score = _regime_score(args.regime, features, args.regime_window_sec)
        mask = regime_mask_from_quantile(score, quantile=args.regime_quantile)
        verdict = run_killtest(features, regime_mask=mask)
    else:
        verdict = run_killtest(features)

    if args.emit_gate_value == "ic_test_q75":
        _log.error("--emit-gate-value ic_test_q75 requires --split and --regime")
        return 2

    _write_and_print(asdict(verdict), Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
