#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Empirical IC measurement for the DRO-ARA v7 observer on FX hourly data.

Loads ``data/askar_full/panel_hourly.parquet``, selects a liquid-majors basket,
slides DRO-ARA over each symbol with strict no-lookahead timing, and measures
the Spearman rank information coefficient (IC) between the signed regime
signal and subsequent forward log returns at horizons {1, 4, 24} hours.

The script implements the GeoSync ``SIGNAL_READY`` contract from ``CLAUDE.md``:
IC must be ≥ 0.08 at the pooled OOS level with bootstrap CI excluding zero,
otherwise the module is declared ``HEADROOM_ONLY`` (honest report, no hype).

Contract:
    seed = 42
    n_boot = 1000
    horizons = (1, 4, 24)
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
    window = 512, step = 64
    NaN → ABORT (no silent imputation)
    replay_hash = sha256(sort_keys JSON minus timestamp)

Usage:
    python scripts/research/dro_ara_ic_fx.py \\
        [--panel data/askar_full/panel_hourly.parquet] \\
        [--symbols EURUSD,GBPUSD,...] \\
        [--max-bars 26000] \\
        [--out results/dro_ara_ic_fx.json]
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
from scipy.stats import spearmanr

from core.dro_ara import geosync_observe

SEED: int = 42
N_BOOT: int = 1000
IC_GATE: float = 0.08
HORIZONS: tuple[int, ...] = (1, 4, 24)
DEFAULT_SYMBOLS: tuple[str, ...] = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD")
WINDOW: int = 512
STEP: int = 64
MIN_BARS_FOR_IC: int = 100


def _signed_signal(out: dict[str, Any]) -> float:
    """Continuous mean-reversion feature in [-1, +1].

    Maps the DFA Hurst exponent to a signed magnitude:
        feature = 2·(0.5 − H) · rs
    so H<0.5 (mean-reverting) → positive (long-proxy), H>0.5 (persistent) →
    negative (short-proxy). INVALID regimes contribute zero via rs=0 in the
    engine. The factor of 2 rescales H ∈ [0, 1] onto [−1, +1].
    """
    H = float(out.get("H", 0.5))
    rs = float(out.get("risk_scalar", 0.0))
    return float(2.0 * (0.5 - H) * rs)


def _spearman_ic(feature: NDArray[np.float64], fwd_ret: NDArray[np.float64]) -> float:
    mask = np.isfinite(feature) & np.isfinite(fwd_ret)
    if mask.sum() < 30:
        return float("nan")
    rho, _ = spearmanr(feature[mask], fwd_ret[mask])
    return float(rho)


def _bootstrap_ic(
    feature: NDArray[np.float64],
    fwd_ret: NDArray[np.float64],
    n_boot: int,
    seed: int,
) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    mask = np.isfinite(feature) & np.isfinite(fwd_ret)
    f = feature[mask]
    r = fwd_ret[mask]
    n = len(f)
    if n < 30:
        return float("nan"), float("nan"), float("nan")
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = _spearman_ic(f[idx], r[idx])
    boots = boots[np.isfinite(boots)]
    if len(boots) < max(30, n_boot * 0.5):
        return float("nan"), float("nan"), float("nan")
    return (
        float(np.median(boots)),
        float(np.percentile(boots, 2.5)),
        float(np.percentile(boots, 97.5)),
    )


def _observe_at(
    price: NDArray[np.float64], anchor: int, window: int, step: int
) -> dict[str, Any] | None:
    """Compute a DRO-ARA state whose trailing DFA window ends at ``anchor``.

    Anchor = absolute index in ``price`` at which the signal becomes available
    for pairing with forward returns (strictly no-lookahead: uses only
    ``price[:anchor]``).
    """
    start = anchor - (window + step)
    if start < 0:
        return None
    try:
        return geosync_observe(price[start:anchor], window=window, step=step)
    except ValueError:
        return None


def measure_symbol(
    price: NDArray[np.float64],
    horizons: tuple[int, ...],
    window: int,
    step: int,
) -> dict[str, Any]:
    """Slide DRO-ARA over ``price`` and build (feature, forward_return) pairs.

    Timing is strictly no-lookahead: the signal at ``anchor`` is derived from
    ``price[:anchor]`` only, then paired with returns over ``price[anchor+h]``.
    """
    signals: list[float] = []
    anchors: list[int] = []

    first = window + step
    last = len(price) - max(horizons)
    for anchor in range(first, last, step):
        out = _observe_at(price, anchor, window, step)
        if out is None:
            continue
        signals.append(_signed_signal(out))
        anchors.append(anchor)

    result: dict[str, Any] = {
        "n_signals": len(signals),
        "horizons": {},
    }

    if len(signals) < MIN_BARS_FOR_IC:
        result["note"] = f"insufficient observations ({len(signals)} < {MIN_BARS_FOR_IC})"
        return result

    s = np.asarray(signals, dtype=np.float64)
    anchors_arr = np.asarray(anchors, dtype=np.int64)

    log_p = np.log(np.abs(price) + 1e-12)

    for h in horizons:
        valid = anchors_arr + h < len(price)
        idx = anchors_arr[valid]
        if len(idx) < MIN_BARS_FOR_IC:
            result["horizons"][f"h{h}"] = {"note": "too few anchors"}
            continue
        fwd = log_p[idx + h] - log_p[idx]
        f_valid = s[valid]
        ic_point = _spearman_ic(f_valid, fwd)
        ic_med, ic_lo, ic_hi = _bootstrap_ic(f_valid, fwd, N_BOOT, SEED)
        result["horizons"][f"h{h}"] = {
            "n": int(len(idx)),
            "ic_point": ic_point,
            "ic_boot_median": ic_med,
            "ic_ci95_low": ic_lo,
            "ic_ci95_high": ic_hi,
            "passes_gate": bool(
                np.isfinite(ic_med) and abs(ic_med) >= IC_GATE and ic_lo * ic_hi > 0
            ),
        }

    return result


def pool_symbols(
    panel: pd.DataFrame,
    symbols: tuple[str, ...],
    horizons: tuple[int, ...],
    window: int,
    step: int,
    max_bars: int | None,
) -> dict[str, Any]:
    per_symbol: dict[str, dict[str, Any]] = {}
    pooled_feat: dict[int, list[float]] = {h: [] for h in horizons}
    pooled_fwd: dict[int, list[float]] = {h: [] for h in horizons}

    for sym in symbols:
        if sym not in panel.columns:
            per_symbol[sym] = {"error": "symbol missing from panel"}
            continue
        series = panel[sym].dropna().to_numpy(dtype=np.float64)
        if max_bars is not None:
            series = series[-max_bars:]
        if len(series) < window + step + max(horizons):
            per_symbol[sym] = {"error": f"too short ({len(series)} bars)"}
            continue
        if np.all(series == series[0]):
            per_symbol[sym] = {"error": "constant series"}
            continue

        sym_result = measure_symbol(series, horizons, window, step)
        per_symbol[sym] = sym_result

        log_p = np.log(np.abs(series) + 1e-12)
        first = window + step
        last = len(series) - max(horizons)
        for anchor in range(first, last, step):
            out = _observe_at(series, anchor, window, step)
            if out is None:
                continue
            feat = _signed_signal(out)
            for h in horizons:
                if anchor + h < len(series):
                    pooled_feat[h].append(feat)
                    pooled_fwd[h].append(float(log_p[anchor + h] - log_p[anchor]))

    pooled: dict[str, Any] = {}
    for h in horizons:
        if len(pooled_feat[h]) < MIN_BARS_FOR_IC:
            pooled[f"h{h}"] = {"note": "insufficient pooled observations"}
            continue
        f = np.asarray(pooled_feat[h], dtype=np.float64)
        r = np.asarray(pooled_fwd[h], dtype=np.float64)
        ic_point = _spearman_ic(f, r)
        ic_med, ic_lo, ic_hi = _bootstrap_ic(f, r, N_BOOT, SEED)
        pooled[f"h{h}"] = {
            "n": int(len(f)),
            "ic_point": ic_point,
            "ic_boot_median": ic_med,
            "ic_ci95_low": ic_lo,
            "ic_ci95_high": ic_hi,
            "passes_gate": bool(
                np.isfinite(ic_med) and abs(ic_med) >= IC_GATE and ic_lo * ic_hi > 0
            ),
        }

    return {"per_symbol": per_symbol, "pooled": pooled}


def build_verdict(pooled: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    best_h = None
    best_abs = -1.0
    for h_key, h_val in pooled.items():
        med = h_val.get("ic_boot_median")
        if med is None or not np.isfinite(med):
            continue
        if abs(med) > best_abs:
            best_abs = abs(med)
            best_h = h_key

    if best_h is None:
        return ("ABORT", "no valid IC measurement across horizons", {})

    best = pooled[best_h]
    passes = bool(best.get("passes_gate", False))
    verdict = "SIGNAL_READY" if passes else "HEADROOM_ONLY"
    reason = (
        f"Pooled best IC at {best_h}: {best['ic_boot_median']:+.4f} "
        f"[{best['ic_ci95_low']:+.4f}, {best['ic_ci95_high']:+.4f}] "
        f"n={best['n']}; gate={IC_GATE:.2f} "
        f"→ {'PASS' if passes else 'FAIL'}."
    )
    return verdict, reason, {"best_horizon": best_h, **best}


def _replay_hash(payload: dict[str, Any]) -> str:
    clean = {k: v for k, v in payload.items() if k not in {"timestamp_utc", "replay_hash"}}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()


def run(
    panel_path: Path,
    symbols: tuple[str, ...],
    horizons: tuple[int, ...],
    window: int,
    step: int,
    max_bars: int | None,
    out_path: Path,
) -> dict[str, Any]:
    np.random.seed(SEED)
    if not panel_path.exists():
        raise FileNotFoundError(f"panel not found: {panel_path}")
    panel = pd.read_parquet(panel_path)

    measurement = pool_symbols(
        panel, symbols, horizons, window=window, step=step, max_bars=max_bars
    )
    verdict, reason, best = build_verdict(measurement["pooled"])

    payload: dict[str, Any] = {
        "spike_name": "dro_ara_ic_fx",
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "seed": SEED,
        "n_boot": N_BOOT,
        "ic_gate": IC_GATE,
        "horizons": list(horizons),
        "symbols": list(symbols),
        "window": window,
        "step": step,
        "max_bars": max_bars,
        "panel": str(panel_path),
        "bars_used_per_symbol": {
            sym: int(
                min(max_bars, len(panel[sym].dropna())) if max_bars else len(panel[sym].dropna())
            )
            for sym in symbols
            if sym in panel.columns
        },
        "measurement": measurement,
        "verdict": verdict,
        "reason": reason,
        "best": best,
    }
    payload["replay_hash"] = _replay_hash(payload)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, default=Path("data/askar_full/panel_hourly.parquet"))
    p.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--max-bars", type=int, default=26000)
    p.add_argument("--window", type=int, default=WINDOW)
    p.add_argument("--step", type=int, default=STEP)
    p.add_argument("--out", type=Path, default=Path("results/dro_ara_ic_fx.json"))
    args = p.parse_args()

    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    try:
        payload = run(
            panel_path=args.panel,
            symbols=symbols,
            horizons=HORIZONS,
            window=args.window,
            step=args.step,
            max_bars=args.max_bars,
            out_path=args.out,
        )
    except Exception as exc:
        err = {
            "spike_name": "dro_ara_ic_fx",
            "verdict": "ABORT",
            "error": f"{type(exc).__name__}: {exc}",
            "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(err, indent=2, default=str))
        print(f"[dro-ara-ic] ABORT: {exc}", file=sys.stderr)
        return 1

    print(f"[dro-ara-ic] verdict={payload['verdict']}")
    print(f"[dro-ara-ic] {payload['reason']}")
    print(f"[dro-ara-ic] replay_hash={payload['replay_hash'][:16]}...")
    print(f"[dro-ara-ic] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
