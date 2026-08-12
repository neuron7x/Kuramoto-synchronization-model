#!/usr/bin/env python3
"""Forward-horizon sweep: where does the Ricci edge peak, and how does it decay?

Computes pooled Spearman IC of Ricci κ_min vs forward log-return at
many horizons (seconds). Tells us:
    * The horizon where the edge is strongest.
    * Whether the edge decays monotonically (typical microstructure
      signal) or is concentrated at a specific scale.
    * Whether conditioning on the RV regime shifts the peak.

Both unconditional and q75-regime-conditional ICs are reported per
horizon. Threshold for q75 is derived from the full-substrate rv
distribution for simplicity (the l2_regime_oos test already confirmed
this threshold is not look-ahead-sensitive in the 50/50 split).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)

_HORIZONS_SEC: tuple[int, ...] = (30, 60, 90, 120, 180, 240, 300, 450, 600, 900, 1200)


def _forward_log_return(mid: np.ndarray, horizon_rows: int) -> np.ndarray:
    log_mid = np.log(mid)
    fwd = np.full_like(log_mid, np.nan)
    if horizon_rows >= log_mid.shape[0]:
        return fwd
    fwd[:-horizon_rows] = log_mid[horizon_rows:] - log_mid[:-horizon_rows]
    return fwd


def _pooled_spearman(signal_panel: np.ndarray, target_panel: np.ndarray) -> tuple[float, int]:
    s_flat = signal_panel.ravel()
    t_flat = target_panel.ravel()
    mask = np.isfinite(s_flat) & np.isfinite(t_flat)
    if mask.sum() < 50:
        return float("nan"), int(mask.sum())
    s = s_flat[mask]
    t = t_flat[mask]
    if float(np.std(s)) < 1e-14 or float(np.std(t)) < 1e-14:
        return float("nan"), int(mask.sum())
    rho, _ = spearmanr(s, t)
    return float(rho), int(mask.sum())


def main() -> int:
    data_dir = Path("data/binance_l2_perp")
    frames = load_parquets(data_dir, DEFAULT_SYMBOLS)
    features = build_feature_frame(frames, DEFAULT_SYMBOLS)
    print(f"substrate: n_rows={features.n_rows}  n_symbols={features.n_symbols}\n")

    signal_1d = cross_sectional_ricci_signal(features.ofi)
    signal_panel = np.repeat(signal_1d[:, None], features.n_symbols, axis=1)

    # q75 mask from full-sample rv
    rv_score = rolling_rv_regime(features, window_rows=300)
    mask_q75 = regime_mask_from_quantile(rv_score, quantile=0.75)
    panel_mask_q75 = np.broadcast_to(mask_q75[:, None], signal_panel.shape)
    signal_panel_q75 = np.where(panel_mask_q75, signal_panel, np.nan)

    rows: list[dict[str, float | int]] = []
    header = f"{'h_sec':>6} {'IC_uncond':>11} {'n_uncond':>10} {'IC_q75':>9} {'n_q75':>8}"
    print(header)
    print("-" * len(header))
    for h in _HORIZONS_SEC:
        target = _forward_log_return(features.mid, h)
        ic_un, n_un = _pooled_spearman(signal_panel, target)
        target_masked = np.where(panel_mask_q75, target, np.nan)
        ic_q75, n_q75 = _pooled_spearman(signal_panel_q75, target_masked)
        rows.append(
            {
                "horizon_sec": int(h),
                "ic_unconditional": float(ic_un) if np.isfinite(ic_un) else float("nan"),
                "n_unconditional": int(n_un),
                "ic_q75": float(ic_q75) if np.isfinite(ic_q75) else float("nan"),
                "n_q75": int(n_q75),
            }
        )
        print(f"{h:>6} {ic_un:>+11.4f} {n_un:>10} {ic_q75:>+9.4f} {n_q75:>8}")

    # Find peak unconditional + peak conditional
    finite_un = [
        r
        for r in rows
        if isinstance(r["ic_unconditional"], float) and np.isfinite(r["ic_unconditional"])
    ]
    finite_q75 = [r for r in rows if isinstance(r["ic_q75"], float) and np.isfinite(r["ic_q75"])]
    if finite_un:
        best_un = max(finite_un, key=lambda r: float(r["ic_unconditional"]))
        print(
            f"\npeak unconditional: h={best_un['horizon_sec']}s  IC={float(best_un['ic_unconditional']):+.4f}"
        )
    if finite_q75:
        best_q75 = max(finite_q75, key=lambda r: float(r["ic_q75"]))
        print(
            f"peak q75-conditional:  h={best_q75['horizon_sec']}s  IC={float(best_q75['ic_q75']):+.4f}"
        )

    Path("results").mkdir(exist_ok=True)
    Path("results/L2_HORIZON_SWEEP.json").write_text(
        json.dumps({"horizons_sec": list(_HORIZONS_SEC), "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print("\nwrote results/L2_HORIZON_SWEEP.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
