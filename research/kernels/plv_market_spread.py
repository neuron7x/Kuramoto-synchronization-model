"""Task 12: PLV between market phase and spread phase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy.signal import hilbert

from analytics.signals.null_baseline import make_phase_shuffled_surrogate


def _phase(arr: NDArray[np.float64]) -> NDArray[np.float64]:
    centered = arr - np.mean(arr)
    result: NDArray[np.float64] = np.angle(hilbert(centered))
    return result


def _plv(phi1: NDArray[np.float64], phi2: NDArray[np.float64]) -> float:
    return float(abs(np.mean(np.exp(1j * (phi1 - phi2)))))


def run(input_csv: Path, output_json: Path, n: int = 1000, seed: int = 42) -> dict[str, Any]:
    df = pd.read_csv(input_csv)
    midr = (
        pd.Series(df["mid_returns"])
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .to_numpy(dtype=float)
    )
    spr = pd.Series(df["spread"]).replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    m = min(len(midr), len(spr))
    midr, spr = midr[:m], spr[:m]

    split = int(0.7 * m)
    spread_test = spr[split:]
    phi_m = _phase(midr[split:])
    phi_s = _phase(spread_test)
    obs = _plv(phi_m, phi_s)

    # Autocorrelation-preserving null. An i.i.d. permutation of the Hilbert
    # phases (`rng.permutation(phi_s)`) destroys the spread's autocorrelation,
    # so the null PLV collapses to ~1/sqrt(N) and the test turns
    # anti-conservative: two independent-but-autocorrelated series get flagged
    # SIGNAL_READY. Instead each surrogate is an FFT phase-randomised copy of
    # the spread SIGNAL (preserving its power spectrum, hence its linear
    # autocorrelation) from which the phase is re-extracted, so the null carries
    # the same spurious-PLV inflation as the observed statistic.
    rng = np.random.default_rng(seed)
    surrogate_seeds = rng.integers(0, 2**31 - 1, size=n)
    count = 0
    for k in range(n):
        surr_signal, _meta = make_phase_shuffled_surrogate(spread_test, int(surrogate_seeds[k]))
        surr_phase = _phase(surr_signal)
        if _plv(phi_m, surr_phase) >= obs:
            count += 1
    p = (count + 1) / (n + 1)

    verdict = {
        "plv": round(obs, 6),
        "p_value": round(float(p), 6),
        "FINAL": "SIGNAL_READY" if obs > 0 and p < 0.05 else "REJECT",
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv"))
    p.add_argument(
        "--output-json", type=Path, default=Path("results/plv_spread_market_verdict.json")
    )
    args = p.parse_args()
    run(args.input_csv, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
