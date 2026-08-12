"""Build aligned Askar L2 panels from the raw OTS Capital archive.

This is the reproducibility entry point for
:mod:`research.askar.full_validation`. It scans an external directory
of per-asset parquet files (as delivered by Askar), applies the
data-quality filters described in ``CLAUDE_CODE_TASK_askar_full.md``,
aligns the surviving series on common hourly timestamps, and writes
three panels into ``data/askar_full/``:

 * ``panel_hourly.parquet`` — multi-asset equity+FX+commodity panel
   with SPY as the anchor (rows where SPY is liquid and ≥90 % of
   columns have a valid close).
 * ``panel_daily.parquet``  — same universe resampled to daily last-close.
 * ``panel_fx_hourly.parquet`` — the 14 FX pairs required for the
   FX-only subtest in Step 6 of the validation task.

Filters (from task spec):
 * Start ≥ 2017-01-01
 * ``max_gap`` between consecutive bars ≤ 7 calendar days
   (covers long FX weekends; intraday gaps are much tighter)
 * No ``|log-return|`` > 15 % spikes
 * Anchor (SPY) must be present on every retained row
 * Multi-asset panel keeps only assets whose series start ≤ 2017-02-20
   (ensures apples-to-apples coverage with the GeoSync baseline)

Usage::

    python research/askar/panel_builder.py /path/to/askar/archive

or run with the default ``ASKAR_ARCHIVE`` environment variable. The
committed panels in ``data/askar_full/`` were produced by this script
and are sufficient for the validation pipeline & CI tests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "askar_full"

START_DATE = pd.Timestamp("2017-01-01")
EARLY_CUTOFF = pd.Timestamp("2017-02-20")
MAX_GAP_HOURS = 24 * 7  # generous: FX long weekends reach ~73 h
SPIKE_THRESHOLD = 0.15
COVERAGE_RATIO = 0.90
ANCHOR_NAME = "SPDR_S_P_500_ETF"

FX_UNIVERSE = (
    "AUDCAD",
    "AUDCHF",
    "AUDNZD",
    "AUDUSD",
    "CADCHF",
    "EURGBP",
    "EURJPY",
    "EURNZD",
    "EURUSD",
    "GBPAUD",
    "GBPCAD",
    "NZDCAD",
    "NZDUSD",
    "USDCAD",
)


def _normalise_name(filename: str) -> str:
    stem = filename.replace("_GMT+0_NO-DST.parquet", "")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return stem


def _load_asset(path: Path) -> pd.Series | None:
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df = df.sort_values("ts").drop_duplicates(subset="ts").set_index("ts")
    df = df[df.index >= START_DATE]
    if len(df) == 0:
        return None
    close = df["close"].astype(float)
    log_close: pd.Series = pd.Series(np.log(close.to_numpy()), index=close.index, dtype=float)
    log_ret = log_close.diff()
    if bool((log_ret.abs() > SPIKE_THRESHOLD).any()):
        return None
    gaps = pd.Series(close.index).diff().dt.total_seconds().div(3600.0)
    if float(gaps.max()) > MAX_GAP_HOURS:
        return None
    return close.rename(_normalise_name(path.name))


def discover(archive: Path) -> list[dict[str, Any]]:
    """Scan *archive* and return a JSON-serialisable report for every file."""
    reports: list[dict[str, Any]] = []
    for f in sorted(archive.glob("*.parquet")):
        try:
            df = pd.read_parquet(f)
        except Exception as exc:  # pragma: no cover - file-level fallback
            reports.append({"file": f.name, "ok": False, "reason": f"read:{exc}"})
            continue
        df = df.sort_values("ts").drop_duplicates(subset="ts").set_index("ts")
        df = df[df.index >= START_DATE]
        if len(df) == 0:
            reports.append({"file": f.name, "ok": False, "reason": "empty_post_2017"})
            continue
        close = df["close"].astype(float)
        log_close: pd.Series = pd.Series(np.log(close.to_numpy()), index=close.index, dtype=float)
        log_ret = log_close.diff()
        max_spike = float(log_ret.abs().max())
        gaps = pd.Series(close.index).diff().dt.total_seconds().div(3600.0)
        max_gap = float(gaps.max())
        ok = (
            max_spike <= SPIKE_THRESHOLD
            and max_gap <= MAX_GAP_HOURS
            and int((log_ret.abs() > SPIKE_THRESHOLD).sum()) == 0
        )
        reports.append(
            {
                "file": f.name,
                "name": _normalise_name(f.name),
                "ok": bool(ok),
                "n_bars": int(len(df)),
                "start": str(df.index.min()),
                "end": str(df.index.max()),
                "max_gap_h": round(max_gap, 2),
                "max_spike_abs_logret": round(max_spike, 6),
            }
        )
    return reports


def _align_multiasset(series: dict[str, pd.Series]) -> pd.DataFrame:
    panel = pd.DataFrame(series).sort_index()
    panel_ff = panel.ffill(limit=8)
    anchor_mask = panel_ff[ANCHOR_NAME].notna()
    coverage = panel_ff.notna().sum(axis=1) / panel_ff.shape[1]
    keep = anchor_mask & (coverage >= COVERAGE_RATIO)
    return panel_ff.loc[keep].dropna()


def build(archive: Path, out_dir: Path = DATA_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = discover(archive)
    (out_dir / "discovery_report.json").write_text(json.dumps(reports, indent=2))

    eligible = [r for r in reports if r.get("ok") and pd.Timestamp(r["start"]) <= EARLY_CUTOFF]
    print(f"Eligible early-start clean assets: {len(eligible)}")

    series: dict[str, pd.Series] = {}
    for r in eligible:
        s = _load_asset(archive / r["file"])
        if s is not None:
            series[r["name"]] = s
    if ANCHOR_NAME not in series:
        raise RuntimeError(f"anchor {ANCHOR_NAME!r} not available in archive")

    panel_hourly = _align_multiasset(series)
    panel_hourly.to_parquet(out_dir / "panel_hourly.parquet", compression="zstd")
    panel_daily = panel_hourly.resample("1D").last().dropna()
    panel_daily.to_parquet(out_dir / "panel_daily.parquet", compression="zstd")

    fx_series: dict[str, pd.Series] = {}
    for f in sorted(archive.glob("*.parquet")):
        name = _normalise_name(f.name)
        if name in FX_UNIVERSE:
            s = _load_asset(f)
            if s is not None:
                fx_series[name] = s
    fx_panel = pd.DataFrame(fx_series).sort_index().ffill(limit=8).dropna()
    fx_panel.to_parquet(out_dir / "panel_fx_hourly.parquet", compression="zstd")

    manifest = {
        "panel_hourly": {
            "assets": list(panel_hourly.columns),
            "n_assets": int(panel_hourly.shape[1]),
            "n_bars": int(panel_hourly.shape[0]),
            "start": str(panel_hourly.index.min()),
            "end": str(panel_hourly.index.max()),
            "anchor": ANCHOR_NAME,
            "early_cutoff": str(EARLY_CUTOFF),
        },
        "panel_daily": {
            "assets": list(panel_daily.columns),
            "n_assets": int(panel_daily.shape[1]),
            "n_bars": int(panel_daily.shape[0]),
            "start": str(panel_daily.index.min()),
            "end": str(panel_daily.index.max()),
        },
        "panel_fx_hourly": {
            "assets": list(fx_panel.columns),
            "n_assets": int(fx_panel.shape[1]),
            "n_bars": int(fx_panel.shape[0]),
            "start": str(fx_panel.index.min()),
            "end": str(fx_panel.index.max()),
        },
    }
    (out_dir / "panel_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Panels + manifest written to", out_dir)
    return manifest


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archive",
        nargs="?",
        default=os.environ.get("ASKAR_ARCHIVE"),
        help="Path to raw Askar parquet archive",
    )
    parser.add_argument(
        "--out",
        default=str(DATA_DIR),
        help="Output directory for aligned panels",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    if not args.archive:
        print(
            "error: no archive path supplied. Pass as argument or set ASKAR_ARCHIVE.",
            file=sys.stderr,
        )
        return 2
    archive = Path(args.archive)
    if not archive.is_dir():
        print(f"error: archive {archive} is not a directory", file=sys.stderr)
        return 2
    build(archive, out_dir=Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
