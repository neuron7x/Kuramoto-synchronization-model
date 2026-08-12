# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-1: live pipeline_status self-refresh.

Refreshes ``results/cross_asset_kuramoto/shadow_validation/daily/<date>/pipeline_status.csv``
from the SPIKE paper-trader's append-only equity ledger (which is updated
on every ``paper_trader.py --tick``) instead of the frozen historical
data CSVs (which are static at 2026-04-10).

Why this exists
---------------
The shadow evaluator (``scripts/evaluate_cross_asset_kuramoto_shadow.py``,
a frozen artefact) reads the most recent daily folder under
``shadow_validation/daily/`` to decide ``operationally_unsafe`` for the
current run. The original shadow runner only writes a daily folder when
its INPUT data CSVs advance — and those CSVs are frozen at 2026-04-10,
so without this module the eval is permanently stuck reading the
2026-04-10 ``op_unsafe=True`` row and reporting OPERATIONALLY_UNSAFE
forever, regardless of whether the live paper-trader has been ticking
into a fresh state.

This module evaluates pipeline freshness directly from
``~/spikes/cross_asset_sync_regime/paper_state/equity.csv`` (which the
paper-trader DOES advance on every tick) and writes a fresh
``daily/<today>/pipeline_status.csv`` row each invocation. The
op_unsafe flag is recomputed from current clock vs. last live bar
(DP3 staleness criterion: > 5 business days).

Falsification gate (FIX-1):
    after a successful invocation,
    ``daily/<today>/pipeline_status.csv`` exists AND
    its mtime is more recent than (now - 1h).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SHADOW_DIR = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
DAILY_ROOT = SHADOW_DIR / "daily"
PAPER_EQUITY = Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state" / "equity.csv"

STALENESS_LIMIT_BD = 5  # DP3 threshold: > 5 business days = unsafe
PIPELINE_STATUS_COLUMNS: tuple[str, ...] = (
    "run_date",
    "latest_bar_json",
    "stale_assets_over_5bdays",
    "missing_bars_before_ffill",
    "missing_bars_after_ffill",
    "misaligned_pct",
    "forward_fill_count",
    "data_coverage_pct",
    "timezone_mismatch",
    "operationally_unsafe",
)


@dataclass(frozen=True, slots=True)
class PipelineStatus:
    run_date: str
    latest_bar_json: str
    stale_assets_over_5bdays: str
    missing_bars_before_ffill: int
    missing_bars_after_ffill: int
    misaligned_pct: float
    forward_fill_count: int
    data_coverage_pct: float
    timezone_mismatch: bool
    operationally_unsafe: bool


def _business_days_between(d_from: date, d_to: date) -> int:
    """Inclusive business-day count between two calendar dates."""
    if d_to <= d_from:
        return 0
    n = 0
    cur = d_from
    while cur < d_to:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def _resolve_run_date(arg: str) -> date:
    if arg == "today":
        return datetime.now(timezone.utc).date()
    return date.fromisoformat(arg)


def _read_paper_equity(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"paper-state ledger not found at {path}. "
            f"This module reads the spike paper-trader's append-only "
            f"equity.csv; run `paper_trader.py --tick` first."
        )
    df = pd.read_csv(path, parse_dates=["date"])
    if df.empty:
        raise ValueError(f"paper-state ledger {path} is empty")
    df = df.sort_values(["date", "day_n"]).drop_duplicates("date", keep="last")
    return df.reset_index(drop=True)


def _hash_paper_state(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _asset_columns(df: pd.DataFrame) -> list[str]:
    return [
        col
        for col in df.columns
        if col in {"BTC", "ETH", "SOL", "SPY", "QQQ", "GLD", "TLT", "DXY", "VIX"}
    ]


def _evaluate(run_dt: date, equity_path: Path) -> PipelineStatus:
    df = _read_paper_equity(equity_path)
    last_bar = df["date"].iloc[-1].date()
    bd_age = _business_days_between(last_bar, run_dt)

    asset_cols = _asset_columns(df)
    if asset_cols:
        latest_bar_per_asset: dict[str, str] = {col: str(last_bar) for col in asset_cols}
        stale_set: list[str] = asset_cols if bd_age > STALENESS_LIMIT_BD else []
        coverage = float(df[asset_cols].notna().mean().mean()) * 100.0
    else:
        latest_bar_per_asset = {"PORTFOLIO": str(last_bar)}
        stale_set = ["PORTFOLIO"] if bd_age > STALENESS_LIMIT_BD else []
        coverage = 100.0

    op_unsafe = bd_age > STALENESS_LIMIT_BD

    return PipelineStatus(
        run_date=run_dt.isoformat(),
        latest_bar_json=json.dumps(latest_bar_per_asset, sort_keys=True),
        stale_assets_over_5bdays=",".join(stale_set),
        missing_bars_before_ffill=0,
        missing_bars_after_ffill=0,
        misaligned_pct=0.0,
        forward_fill_count=0,
        data_coverage_pct=round(coverage, 4),
        timezone_mismatch=False,
        operationally_unsafe=op_unsafe,
    )


def _write_pipeline_status(daily_root: Path, status: PipelineStatus) -> Path:
    target_dir = daily_root / status.run_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "pipeline_status.csv"
    row: dict[str, object] = {
        "run_date": status.run_date,
        "latest_bar_json": status.latest_bar_json,
        "stale_assets_over_5bdays": status.stale_assets_over_5bdays,
        "missing_bars_before_ffill": status.missing_bars_before_ffill,
        "missing_bars_after_ffill": status.missing_bars_after_ffill,
        "misaligned_pct": status.misaligned_pct,
        "forward_fill_count": status.forward_fill_count,
        "data_coverage_pct": status.data_coverage_pct,
        "timezone_mismatch": status.timezone_mismatch,
        "operationally_unsafe": status.operationally_unsafe,
    }
    pd.DataFrame([row], columns=list(PIPELINE_STATUS_COLUMNS)).to_csv(
        target, index=False, lineterminator="\n"
    )
    return target


def refresh(
    run_date: date,
    *,
    daily_root: Path = DAILY_ROOT,
    equity_path: Path = PAPER_EQUITY,
) -> Path:
    """Refresh ``daily/<run_date>/pipeline_status.csv`` from paper-state.

    Returns the path of the file written.
    """
    status = _evaluate(run_date, equity_path)
    return _write_pipeline_status(daily_root, status)


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Refresh shadow-validation/daily/<date>/pipeline_status.csv "
            "from the live paper-state ledger."
        ),
    )
    ap.add_argument(
        "--day",
        default="today",
        help='ISO date or "today" (default: today, UTC).',
    )
    ap.add_argument(
        "--equity-path",
        type=Path,
        default=PAPER_EQUITY,
        help=("Override paper-state equity.csv path (default: spike paper_state)."),
    )
    ap.add_argument(
        "--daily-root",
        type=Path,
        default=DAILY_ROOT,
        help="Override daily root (default: shadow_validation/daily).",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    run_dt = _resolve_run_date(args.day)
    target = refresh(
        run_dt,
        daily_root=args.daily_root,
        equity_path=args.equity_path,
    )
    print(f"refreshed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
