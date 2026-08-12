#!/usr/bin/env python3
"""RV-decile IC analysis: is the regime effect monotonic with volatility?

The initial walk-forward result suggested "higher RV → higher IC" with
a Spearman ρ of +0.35. But that's a rank-based summary that can hide
non-monotonic structure. This script bins Session-1 rolling RV into
10 equal-sized deciles and computes IC inside each.

Finding on collected Session-1 substrate:
    D1 (lowest RV): IC = +0.32 *** (surprisingly strong)
    D2-D5:          IC ≈ 0     (not significant)
    D6-D10:         IC grows from +0.12 to +0.40

→ U-shape, NOT monotonic. The edge lives at both tails of the RV
distribution, collapses in the middle.

This is important for cross-session generalization: if Session-2 is
entirely inside the "middle dead zone" RV range, unconditional IC
should be near zero. That it was STRONGLY NEGATIVE in the first 52
minutes of Session-2 indicates the regime has an axis beyond RV —
likely diurnal / liquidity-schedule driven.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
    run_killtest,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS
from research.microstructure.regime import rolling_rv_regime


def main() -> int:
    data_dir = Path("data/binance_l2_perp")
    frames = load_parquets(data_dir, DEFAULT_SYMBOLS)
    features = build_feature_frame(frames, DEFAULT_SYMBOLS)
    print(f"substrate: n_rows={features.n_rows}")

    rv = rolling_rv_regime(features, window_rows=300)
    finite = rv[np.isfinite(rv)]
    print(f"finite rv points: {finite.size}")

    deciles = [float(np.quantile(finite, q)) for q in np.arange(0.1, 1.0, 0.1)]
    edges = [float(finite.min())] + deciles + [float(finite.max()) + 1e-9]

    results: list[dict[str, float | int | str]] = []
    header = f"{'bucket':<8} {'rv<':<10} {'frac':>6} {'IC':>9} {'p_perm':>8} {'verdict':<8}"
    print(header)
    print("-" * len(header))
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        mask = np.isfinite(rv) & (rv >= lo) & (rv < hi)
        if mask.sum() < 100:
            continue
        v = run_killtest(features, regime_mask=mask)
        row = {
            "bucket": f"D{i + 1}",
            "rv_upper": hi,
            "frac": float(mask.sum() / len(mask)),
            "ic": float(v.ic_signal) if np.isfinite(v.ic_signal) else float("nan"),
            "perm_p": float(v.null_test_pvalues["permutation_shuffle"]),
            "verdict": v.verdict,
        }
        results.append(row)
        print(
            f"D{i + 1:<7} {hi:<10.6f} {float(mask.sum()) / len(mask):>6.3f} "
            f"{float(v.ic_signal):>+9.4f} {v.null_test_pvalues['permutation_shuffle']:>8.4f} "
            f"{v.verdict:<8}"
        )

    Path("results").mkdir(exist_ok=True)
    Path("results/L2_RV_DECILE_ANALYSIS.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print("\nwrote results/L2_RV_DECILE_ANALYSIS.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
