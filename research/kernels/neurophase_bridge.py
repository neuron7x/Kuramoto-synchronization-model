"""Task 9: market -> neurophase execution gate history exporter."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import hilbert


def _order_parameter(phases: np.ndarray) -> float:
    if len(phases) == 0:
        return 0.0
    return float(abs(np.mean(np.exp(1j * phases))))


def _causal_phase(arr: np.ndarray, window: int) -> np.ndarray:
    """Instantaneous analytic phase at each bar using only trailing samples.

    The global-mean + whole-array ``hilbert(arr)`` phase is NON-causal: the
    analytic signal at index ``i`` is an FFT over the entire series, so
    ``phase[i]`` depends on future samples ``j > i``. Any downstream backtest
    of the exported execution gate then leaks look-ahead information.

    For every bar ``i`` this instead computes the analytic phase inside the
    trailing window ``arr[i - window + 1 : i + 1]`` (an expanding window during
    warm-up), centered by that window's own TRAILING mean, and takes the last
    element ``hilbert(centered_window)[-1]``. ``phase[i]`` therefore depends
    only on samples ``j <= i`` and is invariant to any change after bar ``i``.
    """
    n = len(arr)
    phase = np.zeros(n, dtype=float)
    for i in range(n):
        start = max(0, i - window + 1)
        w = arr[start : i + 1]
        centered_window = w - np.mean(w)  # trailing mean: no future samples
        analytic = hilbert(centered_window)
        phase[i] = float(np.angle(analytic[-1]))
    return phase


def run(
    input_csv: Path, output_csv: Path, window: int = 256, threshold: float = 0.65
) -> pd.DataFrame:
    df = pd.read_csv(input_csv)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").dropna(subset=["mid", "mid_returns"]).reset_index(drop=True)

    arr = df["mid_returns"].to_numpy(dtype=float)
    # Causal instantaneous phase: phase[i] uses only trailing samples j <= i,
    # so the exported execution gate carries no look-ahead (see _causal_phase).
    phase = _causal_phase(arr, window)

    r_vals: list[float | None] = []
    states: list[str] = []
    allowed: list[bool] = []

    for i in range(len(df)):
        if i + 1 < window:
            r_vals.append(None)
            states.append("SENSOR_ABSENT")
            allowed.append(False)
            continue
        p_window = phase[i - window + 1 : i + 1]
        r = _order_parameter(p_window)
        st = "READY" if r >= threshold else "BLOCKED"
        r_vals.append(r)
        states.append(st)
        allowed.append(st == "READY")

    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "mid": df["mid"],
            "phase": phase,
            "R": r_vals,
            "gate_state": states,
            "execution_allowed": allowed,
        }
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_csv, index=False)

    n = len(out)
    ready = float((out["gate_state"] == "READY").mean() * 100.0)
    blocked = float((out["gate_state"] == "BLOCKED").mean() * 100.0)
    warmup = float((out["gate_state"] == "SENSOR_ABSENT").mean() * 100.0)
    print(f"Saved: {output_csv}")
    print(f"Rows: {n}")
    print(f"READY={ready:.2f}% BLOCKED={blocked:.2f}% WARMUP={warmup:.2f}%")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run neurophase bridge")
    parser.add_argument(
        "--input-csv", type=Path, default=Path("data/dukascopy/xauusd_l2_hourly.csv")
    )
    parser.add_argument(
        "--output-csv", type=Path, default=Path("results/neurophase_gate_history.csv")
    )
    parser.add_argument("--window", type=int, default=256)
    parser.add_argument("--threshold", type=float, default=0.65)
    args = parser.parse_args()

    run(args.input_csv, args.output_csv, window=args.window, threshold=args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
