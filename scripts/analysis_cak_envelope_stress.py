"""Phase 5 · Envelope stress packet.

Block-bootstrap from the validated OOS return stream
(`demo/equity_curve.csv`). Different seed (20260501) from the live
shadow envelope (20260422) so the two stress views are independent.

For each horizon H ∈ {20, 40, 60, 90}:
    - draw 500 cumulative paths of length H via block-bootstrap
      (block_length = 20 bars)
    - compute quantiles, max-DD quantiles, and recovery probability
      after an early dip (dip below p25 at H/2, finish above p50 at H)

Descriptive only. No parameter search, no signal re-fit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "results" / "cross_asset_kuramoto" / "offline_robustness"
DEMO_EQUITY = REPO / "results" / "cross_asset_kuramoto" / "demo" / "equity_curve.csv"

SEED = 20260501
BLOCK_LEN = 20
N_PATHS = 500
HORIZONS = (20, 40, 60, 90)


def _oos_log_returns() -> np.ndarray:
    df = pd.read_csv(DEMO_EQUITY)
    cum = df["strategy_cumret"].to_numpy()
    log = np.log(np.maximum(cum, 1e-12))
    r = np.diff(log)
    return r[np.isfinite(r)]


def _paths(oos: np.ndarray, horizon: int, rng: np.random.Generator) -> np.ndarray:
    nb = int(np.ceil(horizon / BLOCK_LEN))
    n = len(oos)
    if n < BLOCK_LEN:
        raise ValueError("OOS stream shorter than block length")
    sims = np.zeros((N_PATHS, horizon))
    for i in range(N_PATHS):
        pieces = []
        for _ in range(nb):
            start = int(rng.integers(0, n - BLOCK_LEN + 1))
            pieces.append(oos[start : start + BLOCK_LEN])
        sims[i] = np.concatenate(pieces)[:horizon]
    return sims


def _max_dd_per_path(sims: np.ndarray) -> np.ndarray:
    cum = np.cumsum(sims, axis=1)
    eq = np.exp(cum)
    peak = np.maximum.accumulate(eq, axis=1)
    dd = 1.0 - eq / peak
    return dd.max(axis=1)


def main() -> int:
    oos = _oos_log_returns()
    rows: list[dict] = []
    for H in HORIZONS:
        rng = np.random.default_rng(SEED + H)  # different seed per horizon
        sims = _paths(oos, H, rng)
        cumret = sims.sum(axis=1)  # log cumulative return at horizon
        p05 = float(np.quantile(cumret, 0.05))
        p25 = float(np.quantile(cumret, 0.25))
        p50 = float(np.quantile(cumret, 0.50))
        p95 = float(np.quantile(cumret, 0.95))
        # Breach frequencies: fraction of simulated paths that end below
        # the sample's own p05 / p25 at this horizon — by definition those
        # are exactly 0.05 and 0.25; we report empirical counts for sanity.
        breach_below_p05 = float((cumret < p05).mean())
        breach_below_p25 = float((cumret < p25).mean())
        dd = _max_dd_per_path(sims)
        dd_median = float(np.median(dd))
        dd_p95 = float(np.quantile(dd, 0.95))
        # Recovery prob: paths whose cum-return at H/2 is < p25 at H/2
        # but whose end-of-horizon cum-return is > p50 at H.
        mid = H // 2
        cum_mid = sims[:, :mid].sum(axis=1)
        # Per-H-midpoint p25: compute on midpoint cum distribution
        mid_sims = sims[:, :mid]
        mid_cum = mid_sims.sum(axis=1)
        mid_p25 = float(np.quantile(mid_cum, 0.25))
        mask_early_dip = cum_mid < mid_p25
        finished_above_p50 = cumret > p50
        denom = int(mask_early_dip.sum())
        recovery_prob = (
            float(np.logical_and(mask_early_dip, finished_above_p50).sum() / denom)
            if denom > 0
            else float("nan")
        )
        rows.append(
            {
                "horizon_bars": H,
                "n_paths": N_PATHS,
                "block_length": BLOCK_LEN,
                "seed": SEED + H,
                "breach_freq_below_p05": round(breach_below_p05, 4),
                "breach_freq_below_p25": round(breach_below_p25, 4),
                "median_cumret_log": round(p50, 6),
                "p05_cumret_log": round(p05, 6),
                "p95_cumret_log": round(p95, 6),
                "max_dd_median": round(dd_median, 6),
                "max_dd_p95": round(dd_p95, 6),
                "early_dip_paths": denom,
                "recovery_prob_after_early_dip": (
                    round(recovery_prob, 4) if np.isfinite(recovery_prob) else None
                ),
            }
        )
    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "envelope_stress.csv", index=False, lineterminator="\n")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
