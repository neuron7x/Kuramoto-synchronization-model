#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Purged walk-forward backtest for a DRO-ARA-gated momentum strategy.

Primary alpha  : 24-bar log-return momentum (simple baseline, known weak)
Regime filter  : DRO-ARA v7 multiplier on the trailing ``window + step`` slice
                 (CRITICAL/CONVERGING→1.0, TRANSITION→0.5, DRIFT/INVALID→0.0)
Position       : sign(raw · multiplier) ∈ {−1, 0, +1}
Hold horizon   : 1 bar (close-to-close), re-checked at stride STEP bars
Cost model     : 1 bp per side on position changes

Folds come from ``research.microstructure.cv.purged_kfold_indices`` with
embargo = step and horizon = 1. Sharpe is computed per fold and pooled;
Lopez de Prado deflated Sharpe corrects for multiple-testing (n_trials=folds).

Contract:
    seed = 42, no-lookahead (signal at t uses only prices[:t]),
    NaN→ABORT, truncated replay_hash (16 hex), not committed to repo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from core.dro_ara import Regime, geosync_observe
from research.microstructure.cv import purged_kfold_indices
from research.microstructure.robustness import deflated_sharpe

SEED: int = 42
N_BOOT: int = 1000
WINDOW: int = 512
STEP: int = 64
MOMENTUM_LAG: int = 24
COST_BP: float = 1.0
DEFAULT_SYMBOLS: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY")


def _multiplier(regime: str, trend: str | None) -> float:
    if regime == Regime.INVALID.value:
        return 0.0
    if regime == Regime.DRIFT.value:
        return 0.0
    if regime == Regime.TRANSITION.value:
        return 0.5
    if regime == Regime.CRITICAL.value:
        if trend in ("CONVERGING", "STABLE"):
            return 1.0
        return 0.5
    return 0.0


def _observe(
    price: NDArray[np.float64], anchor: int, window: int, step: int
) -> dict[str, Any] | None:
    start = anchor - (window + step)
    if start < 0:
        return None
    try:
        return geosync_observe(price[start:anchor], window=window, step=step)
    except ValueError:
        return None


def build_positions(
    price: NDArray[np.float64],
    *,
    window: int,
    step: int,
    momentum_lag: int,
) -> NDArray[np.int8]:
    """Return +1/0/-1 position at every bar, strictly no-lookahead.

    Signal at bar ``t`` is computed from ``price[:t]``; it applies starting at
    ``t + 1`` (so the caller should pair position[i] with return[i+1..]).
    """
    n = len(price)
    positions = np.zeros(n, dtype=np.int8)
    log_p = np.log(np.abs(price) + 1e-12)

    current_pos: int = 0
    last_multiplier_anchor = -1
    log_p_lag = np.concatenate([np.zeros(momentum_lag), log_p[:-momentum_lag]])

    for t in range(window + step, n):
        if (t - (window + step)) % step == 0:
            obs = _observe(price, anchor=t, window=window, step=step)
            if obs is None:
                current_pos = 0
            else:
                mult = _multiplier(str(obs["regime"]), obs.get("trend"))  # type: ignore[arg-type]
                if mult <= 0.0:
                    current_pos = 0
                else:
                    mom = log_p[t - 1] - log_p_lag[t - 1]
                    sign = 1 if mom > 0 else (-1 if mom < 0 else 0)
                    current_pos = int(np.sign(sign * mult))
            last_multiplier_anchor = t
        positions[t] = current_pos

    if last_multiplier_anchor < 0:
        return positions
    return positions


def backtest_symbol(
    price: NDArray[np.float64],
    *,
    window: int,
    step: int,
    momentum_lag: int,
    cost_bp: float,
) -> dict[str, Any]:
    positions = build_positions(price, window=window, step=step, momentum_lag=momentum_lag)
    log_p = np.log(np.abs(price) + 1e-12)
    fwd_ret = np.zeros_like(log_p)
    fwd_ret[:-1] = log_p[1:] - log_p[:-1]
    pnl = positions.astype(np.float64) * fwd_ret
    turnover = np.abs(np.diff(positions, prepend=0).astype(np.float64))
    cost = turnover * (cost_bp / 1e4)
    net = pnl - cost
    return {
        "positions": positions,
        "pnl_gross": pnl,
        "pnl_net": net,
        "turnover": turnover,
    }


def _fold_sharpe(returns: NDArray[np.float64]) -> float:
    mask = np.isfinite(returns)
    r = returns[mask]
    if r.size < 30 or float(np.std(r, ddof=1)) < 1e-14:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * np.sqrt(252 * 24))


def walk_forward(
    panel: pd.DataFrame,
    symbols: tuple[str, ...],
    *,
    k: int,
    window: int,
    step: int,
    momentum_lag: int,
    cost_bp: float,
    max_bars: int | None,
) -> dict[str, Any]:
    per_symbol: dict[str, dict[str, Any]] = {}
    all_fold_sharpes: list[float] = []
    pooled_net: list[float] = []

    for sym in symbols:
        if sym not in panel.columns:
            per_symbol[sym] = {"error": "symbol missing"}
            continue
        series = panel[sym].dropna().to_numpy(dtype=np.float64)
        if max_bars is not None:
            series = series[-max_bars:]
        if len(series) < window + step + momentum_lag + k * 100:
            per_symbol[sym] = {"error": f"too short ({len(series)} bars)"}
            continue
        if np.all(series == series[0]):
            per_symbol[sym] = {"error": "constant series"}
            continue

        bt = backtest_symbol(
            series,
            window=window,
            step=step,
            momentum_lag=momentum_lag,
            cost_bp=cost_bp,
        )
        net = bt["pnl_net"]
        fold_sharpes: list[float] = []
        for _, test_idx in purged_kfold_indices(
            n_rows=len(net),
            k=k,
            horizon_rows=1,
            embargo_rows=step,
        ):
            fold_sharpes.append(_fold_sharpe(net[test_idx]))
        finite = [s for s in fold_sharpes if np.isfinite(s)]
        per_symbol[sym] = {
            "n_bars": int(len(series)),
            "fold_sharpes": fold_sharpes,
            "median_fold_sharpe": float(np.median(finite)) if finite else float("nan"),
            "mean_fold_sharpe": float(np.mean(finite)) if finite else float("nan"),
            "aggregate_sharpe": _fold_sharpe(net),
            "turnover_per_bar": float(np.mean(bt["turnover"])),
            "total_return_net": float(np.sum(net)),
            "hit_rate": float(np.mean(net[net != 0] > 0)) if np.any(net != 0) else float("nan"),
            "n_active_bars": int(np.sum(np.abs(bt["positions"]) > 0)),
        }
        all_fold_sharpes.extend(fold_sharpes)
        pooled_net.append(net)

    if not pooled_net:
        return {"per_symbol": per_symbol, "pooled": {"note": "no symbols evaluated"}}

    pooled = np.concatenate(pooled_net)
    agg_sharpe = _fold_sharpe(pooled)
    n_trials = max(1, len([s for s in all_fold_sharpes if np.isfinite(s)]))
    n_obs = int(np.sum(np.isfinite(pooled)))
    dsr_report: dict[str, Any]
    if np.isfinite(agg_sharpe) and n_obs >= 2:
        dsr = deflated_sharpe(
            sharpe_observed=agg_sharpe,
            n_trials=n_trials,
            n_observations=n_obs,
        )
        dsr_report = {
            "sharpe_observed": dsr.sharpe_observed,
            "sharpe_expected_max": dsr.sharpe_expected_max,
            "deflated_sharpe": dsr.deflated_sharpe,
            "probability_sharpe_is_real": dsr.probability_sharpe_is_real,
            "n_trials": dsr.n_trials,
            "n_observations": dsr.n_observations,
        }
    else:
        dsr_report = {"note": "insufficient data"}

    return {
        "per_symbol": per_symbol,
        "pooled": {
            "aggregate_sharpe": agg_sharpe,
            "fold_sharpes": all_fold_sharpes,
            "deflated_sharpe": dsr_report,
            "n_observations": n_obs,
        },
    }


def _build_verdict(pooled: dict[str, Any]) -> tuple[str, str]:
    dsr_block = pooled.get("deflated_sharpe", {})
    if isinstance(dsr_block, dict) and "deflated_sharpe" in dsr_block:
        dsr_val = float(dsr_block["deflated_sharpe"])
        prob = float(dsr_block.get("probability_sharpe_is_real", 0.0))
        agg = float(pooled.get("aggregate_sharpe", float("nan")))
        if dsr_val > 0.5 and prob > 0.95:
            return "ACCEPT", f"Aggregate Sharpe {agg:.3f}, DSR {dsr_val:.3f}, P(real) {prob:.3f}."
        return "HEADROOM_ONLY", (
            f"Aggregate Sharpe {agg:.3f}, DSR {dsr_val:.3f}, P(real) {prob:.3f}. "
            f"Does not clear DSR > 0.5 with P > 0.95."
        )
    return "ABORT", "insufficient data for deflated Sharpe"


def _replay_hash_short(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k not in {"timestamp_utc", "replay_hash_short"}}
    full = hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()
    return full[:16]


def run(
    panel_path: Path,
    symbols: tuple[str, ...],
    *,
    k: int,
    window: int,
    step: int,
    momentum_lag: int,
    cost_bp: float,
    max_bars: int | None,
    out_path: Path,
) -> dict[str, Any]:
    np.random.seed(SEED)
    if not panel_path.exists():
        raise FileNotFoundError(f"panel not found: {panel_path}")
    panel = pd.read_parquet(panel_path)
    measurement = walk_forward(
        panel,
        symbols,
        k=k,
        window=window,
        step=step,
        momentum_lag=momentum_lag,
        cost_bp=cost_bp,
        max_bars=max_bars,
    )
    verdict, reason = _build_verdict(measurement["pooled"])
    payload: dict[str, Any] = {
        "spike_name": "dro_ara_backtest",
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "seed": SEED,
        "folds": k,
        "window": window,
        "step": step,
        "momentum_lag": momentum_lag,
        "cost_bp": cost_bp,
        "symbols": list(symbols),
        "panel": str(panel_path),
        "max_bars": max_bars,
        "measurement": measurement,
        "verdict": verdict,
        "reason": reason,
    }
    payload["replay_hash_short"] = _replay_hash_short(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, default=Path("data/askar_full/panel_hourly.parquet"))
    p.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--window", type=int, default=WINDOW)
    p.add_argument("--step", type=int, default=STEP)
    p.add_argument("--momentum-lag", type=int, default=MOMENTUM_LAG)
    p.add_argument("--cost-bp", type=float, default=COST_BP)
    p.add_argument("--max-bars", type=int, default=20000)
    p.add_argument("--out", type=Path, default=Path("results/dro_ara_backtest.json"))
    args = p.parse_args()

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    try:
        payload = run(
            panel_path=args.panel,
            symbols=symbols,
            k=args.folds,
            window=args.window,
            step=args.step,
            momentum_lag=args.momentum_lag,
            cost_bp=args.cost_bp,
            max_bars=args.max_bars,
            out_path=args.out,
        )
    except Exception as exc:
        err = {
            "spike_name": "dro_ara_backtest",
            "verdict": "ABORT",
            "error": f"{type(exc).__name__}: {exc}",
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(err, indent=2, default=str))
        print(f"[dro-ara-bt] ABORT: {exc}", file=sys.stderr)
        return 1

    print(f"[dro-ara-bt] verdict={payload['verdict']}")
    print(f"[dro-ara-bt] {payload['reason']}")
    for sym, r in payload["measurement"]["per_symbol"].items():
        if "error" in r:
            print(f"[dro-ara-bt] {sym:8s} {r['error']}")
            continue
        print(
            f"[dro-ara-bt] {sym:8s} "
            f"agg_SR={r['aggregate_sharpe']:+.3f} "
            f"median_fold={r['median_fold_sharpe']:+.3f} "
            f"turnover/bar={r['turnover_per_bar']:.4f} "
            f"hit={r['hit_rate']:.3f} active={r['n_active_bars']}"
        )
    print(f"[dro-ara-bt] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
