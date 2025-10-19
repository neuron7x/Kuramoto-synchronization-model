"""Demonstration script for Irreversibility-Gated Signal features."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, compute_igs_features, igs_directional_signal

OUTPUT_FILE = Path("igs_demo_features_signal.csv")


def _build_synthetic_series(length: int) -> pd.Series:
    rng = np.random.default_rng(0)
    segments = [
        np.cumsum(0.05 + 0.6 * rng.standard_normal(600)),
        np.cumsum(0.0 + 1.0 * rng.standard_normal(600)),
        np.cumsum(-0.03 + 0.5 * rng.standard_normal(600)),
        np.cumsum(0.02 + 0.7 * rng.standard_normal(length - 1800)),
    ]
    log_price = np.concatenate(segments)
    price = 100.0 * np.exp(log_price / 100.0)
    index = pd.date_range("2024-01-01", periods=length, freq="min")
    return pd.Series(price, index=index, name="close")


def main() -> None:
    series = _build_synthetic_series(3000)
    config = IGSConfig(window=400, n_states=7, perm_emb_dim=5, perm_tau=1)
    features = compute_igs_features(series, config)
    signal = igs_directional_signal(features, epr_q=0.7, flux_q=0.6)
    output = pd.concat([series.rename("close"), features, signal.rename("igs_signal")], axis=1)
    output.to_csv(OUTPUT_FILE)
    print(f"Saved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
