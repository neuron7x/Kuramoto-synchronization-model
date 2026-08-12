# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""OOS test of rolling Stuart-Landau ES proximity as leading indicator of R(t).

Pre-registered in `results/cross_asset_kuramoto/SL_ES_PREREGISTRATION.md`
(2026-05-06). All parameters frozen by that document — DO NOT TUNE here.

Procedure (matches §5 of pre-registration):
    1. Load 5-asset cross-asset panel (BTC, ETH, SPY, GLD, TLT).
    2. Align to common business-day index, ffill(limit=1), drop NaNs.
    3. Chronological 70/30 split. Train discarded.
    4. Compute rolling ES proximity on OOS via Stuart-Landau substrate.
    5. Compute rolling Kuramoto R via Hilbert-phase order parameter.
    6. Smooth both with box-5 mean.
    7. Find R-peaks (height ≥ q80, prominence ≥ q25 - q5).
    8. For each peak, find ES peak in window; tau = R_peak - ES_peak.
    9. leads_rate = mean(tau ≥ 1).
   10. Permutation test (999 surrogates): circular shift of ES.
   11. Write artifacts/rolling_es_proximity_oos.json.

Usage:
    PYTHONPATH=. python benchmarks/rolling_es_proximity_oos.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.signal import find_peaks, hilbert

from core.physics.stuart_landau_es import rolling_es_proximity

# ──────────────────────────────────────────────────────────────────────────
# FROZEN — match SL_ES_PREREGISTRATION.md exactly. No tuning here.
# ──────────────────────────────────────────────────────────────────────────
DATA_DIR: Path = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"
ASSETS: list[str] = [
    "btc_usdt_1d",
    "eth_usdt_1d",
    "spy_1d",
    "gld_1d",
    "tlt_1d",
]
WINDOW: int = 24
K_STEPS: int = 12
INT_STEPS: int = 120
SEED_ENGINE: int = 20260506
SEED_PERM: int = 20260506
N_PERM: int = 999
SMOOTH_WIDTH: int = 5
TRAIN_FRAC: float = 0.70
PEAK_HEIGHT_Q: float = 0.80
LEADS_RATE_THRESHOLD: float = 0.60
P_VALUE_THRESHOLD: float = 0.05
MIN_EPISODES: int = 3


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load 5-asset close-price panel + per-asset SHA-256 of source files."""
    frames: list[pd.DataFrame] = []
    hashes: dict[str, str] = {}
    for a in ASSETS:
        path = data_dir / f"{a}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing data file: {path}")
        hashes[a] = _file_sha256(path)
        df = pd.read_csv(path, parse_dates=["timestamp"])
        df = df[["timestamp", "close"]].rename(columns={"close": a})
        ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
        df["timestamp"] = ts.dt.normalize()
        df = df.set_index("timestamp")
        frames.append(df)
    panel = pd.concat(frames, axis=1, join="inner").sort_index()
    panel = panel.ffill(limit=1).dropna()
    return panel, hashes


def smooth_box(x: NDArray[np.float64], width: int = SMOOTH_WIDTH) -> NDArray[np.float64]:
    out: NDArray[np.float64] = np.full_like(x, np.nan, dtype=np.float64)
    half = width // 2
    n = len(x)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        seg = x[lo:hi]
        if bool(np.any(np.isfinite(seg))):
            out[i] = float(np.nanmean(seg))
    return out


def rolling_R(prices: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Rolling Kuramoto order parameter via Hilbert-phase analytic signal."""
    T = prices.shape[0]
    out: NDArray[np.float64] = np.full(T, np.nan, dtype=np.float64)
    log_p = np.log(prices)
    for t in range(window, T):
        slab = np.diff(log_p[t - window : t + 1], axis=0)
        slab = slab - slab.mean(axis=0)
        z = hilbert(slab, axis=0)
        phase_last = np.angle(z[-1, :])
        out[t] = float(np.abs(np.mean(np.exp(1j * phase_last))))
    return out


def _peak_es_in_window(es: NDArray[np.float64], r_peak: int, window: int) -> int | None:
    lo = max(0, r_peak - window)
    hi = r_peak + 1
    seg = es[lo:hi]
    if bool(np.all(np.isnan(seg))):
        return None
    seg_inf = np.where(np.isnan(seg), -np.inf, seg)
    return int(lo + int(np.argmax(seg_inf)))


def compute_taus(
    es: NDArray[np.float64],
    r_peaks: NDArray[np.int64],
    window: int,
) -> list[int]:
    taus: list[int] = []
    for p in r_peaks:
        es_peak = _peak_es_in_window(es, int(p), window)
        if es_peak is None:
            continue
        taus.append(int(int(p) - es_peak))
    return taus


def permutation_p_value(
    es: NDArray[np.float64],
    r_peaks: NDArray[np.int64],
    window: int,
    observed_leads_rate: float,
    n_perm: int,
    seed: int,
) -> tuple[float, NDArray[np.float64]]:
    """Circular-shift permutation test on the ES series."""
    rng = np.random.default_rng(seed)
    T = len(es)
    null: list[float] = []
    low_shift, high_shift = window, max(window + 1, T - window)
    for _ in range(n_perm):
        shift = int(rng.integers(low_shift, high_shift))
        shifted = np.roll(es, shift)
        shifted_taus = compute_taus(shifted, r_peaks, window)
        if not shifted_taus:
            continue
        null.append(float(np.mean([t >= 1 for t in shifted_taus])))
    null_arr: NDArray[np.float64] = np.asarray(null, dtype=np.float64)
    if null_arr.size == 0:
        return 1.0, null_arr
    p = float((null_arr >= observed_leads_rate).mean())
    return p, null_arr


def main() -> int:
    panel, hashes = load_panel()
    n_total = len(panel)
    cut = int(n_total * TRAIN_FRAC)
    oos = panel.iloc[cut:]
    prices: NDArray[np.float64] = np.ascontiguousarray(oos.values, dtype=np.float64)
    n_oos = prices.shape[0]

    print(
        f"[OOS] panel n={n_total}, train={cut}, oos={n_oos}, "
        f"start={oos.index[0].date()}, end={oos.index[-1].date()}"
    )

    # Issue #1358 P1-1: this is a physics-evidence generation path, so it runs
    # fail-closed — a failed window must surface with its index and cause, never
    # be silently masked as NaN (which would let a broken window count as quiet).
    es = rolling_es_proximity(
        prices,
        window=WINDOW,
        K_steps=K_STEPS,
        int_steps=INT_STEPS,
        seed=SEED_ENGINE,
        fail_closed=True,
    )
    R = rolling_R(prices, window=WINDOW)
    es_s = smooth_box(es)
    R_s = smooth_box(R)

    valid_R = R_s[~np.isnan(R_s)]
    result: dict[str, Any] = {}
    if valid_R.size < 5:
        result["decision"] = "INSUFFICIENT"
        result["reason"] = "no valid R(t) windows"
        result["n_episodes"] = 0
    else:
        height_thresh = float(np.quantile(valid_R, PEAK_HEIGHT_Q))
        prominence = float(np.quantile(valid_R, 0.25) - np.quantile(valid_R, 0.05))
        if not np.isfinite(prominence) or prominence <= 0.0:
            prominence = 1e-3
        R_for_peaks = np.where(np.isnan(R_s), -np.inf, R_s)
        peaks_arr, _ = find_peaks(R_for_peaks, height=height_thresh, prominence=prominence)
        peaks: NDArray[np.int64] = np.asarray(peaks_arr, dtype=np.int64)

        taus = compute_taus(es_s, peaks, WINDOW)
        n_episodes = len(taus)

        if n_episodes < MIN_EPISODES:
            result.update(
                {
                    "decision": "INSUFFICIENT",
                    "reason": f"<{MIN_EPISODES} valid episodes",
                    "n_episodes": n_episodes,
                    "taus": taus,
                }
            )
        else:
            leads_arr: list[int] = [1 if t >= 1 else 0 for t in taus]
            leads_rate = float(np.mean(leads_arr))
            tau_mean = float(np.mean(taus))
            tau_median = float(np.median(taus))
            p_value, null = permutation_p_value(
                es_s,
                peaks,
                WINDOW,
                observed_leads_rate=leads_rate,
                n_perm=N_PERM,
                seed=SEED_PERM,
            )
            decision = (
                "ACCEPT"
                if (leads_rate >= LEADS_RATE_THRESHOLD and p_value <= P_VALUE_THRESHOLD)
                else "REJECT"
            )
            result.update(
                {
                    "decision": decision,
                    "n_episodes": n_episodes,
                    "leads_rate": leads_rate,
                    "p_value": p_value,
                    "tau_mean": tau_mean,
                    "tau_median": tau_median,
                    "taus": taus,
                    "null_leads_rate_mean": float(null.mean()) if null.size else None,
                    "null_leads_rate_n": int(null.size),
                    "r_peak_indices": [int(p) for p in peaks],
                }
            )

    result.update(
        {
            "registered": "2026-05-06",
            "ran_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "module": "core.physics.stuart_landau_es",
            "config": {
                "window": WINDOW,
                "K_steps": K_STEPS,
                "int_steps": INT_STEPS,
                "seed_engine": SEED_ENGINE,
                "seed_perm": SEED_PERM,
                "n_permutations": N_PERM,
                "smooth_width": SMOOTH_WIDTH,
                "train_frac": TRAIN_FRAC,
                "peak_height_q": PEAK_HEIGHT_Q,
                "leads_rate_threshold": LEADS_RATE_THRESHOLD,
                "p_value_threshold": P_VALUE_THRESHOLD,
                "min_episodes": MIN_EPISODES,
                # Issue #1358 P1-1: record the strict failure policy the ES engine
                # was invoked with, so the artifact schema tracks the code behavior.
                "fail_closed": True,
            },
            # A completed strict run means zero windows raised (any failure would
            # have aborted the replay), so this is the fail-closed witness.
            "strict_replay": {
                "enabled": True,
                "failed_window_count": 0,
                "policy": "raise on fit failure; no NaN masking in evidence mode",
                "reason": "#1358 P1-1 strict evidence path",
            },
            "universe": ASSETS,
            "data_sha256": hashes,
            "n_oos_bars": n_oos,
            "oos_start": str(oos.index[0].date()),
            "oos_end": str(oos.index[-1].date()),
        }
    )

    out_path = Path("artifacts") / "rolling_es_proximity_oos.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
