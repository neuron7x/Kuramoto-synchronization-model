# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""FIX-4: Sharpe-CI–aware verdict for the shadow trajectory.

The user-spec verdict thresholds {RECOVERING, STAGNANT, DECOMPOSING}
are well defined nominally:

    Sharpe >  0.0    → RECOVERING
    Sharpe ∈ [-3, 0] → STAGNANT-low
    Sharpe ∈ [-5,-3] → STAGNANT
    Sharpe < -5.0    → DECOMPOSING

But at low live-bar counts (n=15), the 95 % CI on annualised Sharpe is
~±2.0 — i.e. wider than the gap between adjacent thresholds. A point
estimate that lands at, say, Sharpe = −4.0 has CI roughly
[−6.0, −2.0], which spans both STAGNANT and DECOMPOSING. Reporting a
single label is then false-confidence.

This module computes a block-bootstrap CI on the live Sharpe and emits
``AMBIGUOUS`` if the CI overlaps a threshold boundary (i.e. the verdict
is not statistically distinguishable from its neighbour at the
configured confidence level).

Falsification gate (FIX-4):
    given a known true_sharpe and n bars, the CI must (i) be wider
    than the threshold gap when n is small (n=15), AND (ii) contract
    monotonically as n grows.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

REPO = Path(__file__).resolve().parents[1]
SHADOW_LIVE_JSON = REPO / "results" / "shadow_live.json"
PAPER_EQUITY = Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state" / "equity.csv"

BARS_PER_YEAR: float = 252.0
DEFAULT_BLOCK_LEN: int = 5
DEFAULT_N_PATHS: int = 999
DEFAULT_CI_LEVEL: float = 0.95
DEFAULT_SEED: int = 20260506

# Verdict thresholds — nominal Sharpe boundaries.
# Order matters: descending so the boundary search is monotonic.
THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("RECOVERING", 0.0),
    ("STAGNANT", -3.0),
    ("DECOMPOSING", -5.0),
)


@dataclass(frozen=True, slots=True)
class Verdict:
    bar: int
    sharpe_point: float
    ci_low: float
    ci_high: float
    label: str
    crosses_threshold: bool
    n_returns_used: int


def _load_returns_up_to_bar(bar: int, equity_path: Path = PAPER_EQUITY) -> NDArray[np.float64]:
    """Pull live log-returns derived from the equity curve up to (and including) ``bar``.

    Returns are computed as ``diff(log(equity))`` so the function is robust to
    paper-trader schema variations (older snapshots had ``log_ret``, newer
    snapshots ship ``net_ret`` + ``equity``). The equity column is canonical.
    """
    if not equity_path.is_file():
        raise FileNotFoundError(
            f"paper-state ledger not found at {equity_path}. "
            f"Run paper_trader.py --tick to populate."
        )
    df = pd.read_csv(equity_path, parse_dates=["date"])
    for col in ("equity", "day_n", "date"):
        if col not in df.columns:
            raise ValueError(
                f"paper-state {equity_path} missing required {col!r} column. "
                f"Got columns: {list(df.columns)}."
            )
    df = df.sort_values(["date", "day_n"]).drop_duplicates("date", keep="last")
    df = df.reset_index(drop=True)
    if bar < 1:
        raise ValueError(f"bar must be >= 1, got {bar}")
    if bar > len(df):
        raise ValueError(f"bar {bar} exceeds available live bars ({len(df)} unique dates)")
    equity = df["equity"].to_numpy(dtype=np.float64)[:bar]
    if equity.size < 2:
        return np.empty(0, dtype=np.float64)
    log_rets = np.diff(np.log(np.maximum(equity, 1e-12)))
    return log_rets[np.isfinite(log_rets)]


def _sharpe_annualised(returns: NDArray[np.float64]) -> float:
    if returns.size < 2:
        return float("nan")
    mu = float(returns.mean()) * BARS_PER_YEAR
    sd = float(returns.std(ddof=1)) * float(np.sqrt(BARS_PER_YEAR))
    if sd <= 0.0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd


def _block_bootstrap_ci(
    returns: NDArray[np.float64],
    *,
    block_len: int,
    n_paths: int,
    ci_level: float,
    seed: int,
) -> tuple[float, float]:
    """Block-bootstrap CI on annualised Sharpe.

    Returns (low, high) at the requested confidence level.
    Falls back to (nan, nan) when the input is too short to bootstrap.
    """
    n = returns.size
    if n < max(block_len, 2):
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    actual_block = min(block_len, n)
    n_blocks = int(np.ceil(n / actual_block))
    sims = np.zeros(n_paths, dtype=np.float64)
    for i in range(n_paths):
        pieces: list[NDArray[np.float64]] = []
        for _ in range(n_blocks):
            start = int(rng.integers(0, n - actual_block + 1))
            pieces.append(returns[start : start + actual_block])
        path: NDArray[np.float64] = np.concatenate(pieces)[:n]
        sims[i] = _sharpe_annualised(path)
    finite = sims[np.isfinite(sims)]
    if finite.size == 0:
        return (float("nan"), float("nan"))
    alpha = (1.0 - ci_level) / 2.0
    return (
        float(np.quantile(finite, alpha)),
        float(np.quantile(finite, 1.0 - alpha)),
    )


def _label_from_point(sharpe: float) -> str:
    if not np.isfinite(sharpe):
        return "INSUFFICIENT_DATA"
    for label, lower in THRESHOLDS:
        if sharpe > lower:
            return label
    return "DECOMPOSING"


def _crosses_threshold(low: float, high: float) -> bool:
    if not (np.isfinite(low) and np.isfinite(high)):
        return False
    boundaries = [t for _, t in THRESHOLDS]
    return any(low < b < high for b in boundaries)


def evaluate(
    bar: int,
    *,
    equity_path: Path = PAPER_EQUITY,
    block_len: int = DEFAULT_BLOCK_LEN,
    n_paths: int = DEFAULT_N_PATHS,
    ci_level: float = DEFAULT_CI_LEVEL,
    seed: int = DEFAULT_SEED,
) -> Verdict:
    returns = _load_returns_up_to_bar(bar, equity_path=equity_path)
    point = _sharpe_annualised(returns)
    low, high = _block_bootstrap_ci(
        returns,
        block_len=block_len,
        n_paths=n_paths,
        ci_level=ci_level,
        seed=seed,
    )
    crosses = _crosses_threshold(low, high)
    label = "AMBIGUOUS" if crosses else _label_from_point(point)
    return Verdict(
        bar=bar,
        sharpe_point=point,
        ci_low=low,
        ci_high=high,
        label=label,
        crosses_threshold=crosses,
        n_returns_used=int(returns.size),
    )


def _format(v: Verdict) -> str:
    return (
        f"BAR {v.bar} | SHARPE {v.sharpe_point:+.4f} | "
        f"CI95 [{v.ci_low:+.2f}, {v.ci_high:+.2f}] | "
        f"VERDICT {v.label} | "
        f"crosses_threshold={v.crosses_threshold} | "
        f"n_returns={v.n_returns_used}"
    )


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="CI-aware verdict on the live Sharpe trajectory.",
    )
    ap.add_argument("--bar", type=int, required=True, help="Live bar number (1-based).")
    ap.add_argument(
        "--equity-path",
        type=Path,
        default=PAPER_EQUITY,
        help="Override paper-state equity.csv path.",
    )
    ap.add_argument(
        "--block-len",
        type=int,
        default=DEFAULT_BLOCK_LEN,
        help=f"Block length for bootstrap (default {DEFAULT_BLOCK_LEN}).",
    )
    ap.add_argument(
        "--n-paths",
        type=int,
        default=DEFAULT_N_PATHS,
        help=f"Number of bootstrap paths (default {DEFAULT_N_PATHS}).",
    )
    ap.add_argument(
        "--ci-level",
        type=float,
        default=DEFAULT_CI_LEVEL,
        help=f"Confidence level (default {DEFAULT_CI_LEVEL}).",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed (default {DEFAULT_SEED}).",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable line.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    v = evaluate(
        args.bar,
        equity_path=args.equity_path,
        block_len=args.block_len,
        n_paths=args.n_paths,
        ci_level=args.ci_level,
        seed=args.seed,
    )
    if args.json:
        payload = {
            "bar": v.bar,
            "sharpe_point": v.sharpe_point,
            "ci_low": v.ci_low,
            "ci_high": v.ci_high,
            "label": v.label,
            "crosses_threshold": v.crosses_threshold,
            "n_returns_used": v.n_returns_used,
        }
        print(json.dumps(payload, sort_keys=True))
    else:
        print(_format(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
