"""Demo script for computing Irreversibility-Gated Signal features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.signals.irreversibility import (
    IGSConfig,
    compute_igs_features,
    igs_directional_signal,
)


def main() -> None:
    np.random.seed(0)
    total = 3000
    segments = [
        np.cumsum(0.05 + 0.6 * np.random.randn(600)),
        np.cumsum(0.00 + 1.0 * np.random.randn(600)),
        np.cumsum(-0.03 + 0.5 * np.random.randn(600)),
        np.cumsum(0.02 + 0.7 * np.random.randn(total - 1800)),
    ]
    trend = np.concatenate(segments)
    price = 100.0 * np.exp(trend / 100.0)
    index = pd.date_range("2024-01-01", periods=total, freq="min")
    series = pd.Series(price, index=index, name="close")

    cfg = IGSConfig(window=400, n_states=7)
    features = compute_igs_features(series, cfg)
    signal = igs_directional_signal(features, epr_q=0.7)

    output = pd.concat([features, signal.rename("signal")], axis=1)
    output.to_csv("igs_demo_features_signal.csv")
    print("Saved igs_demo_features_signal.csv")


if __name__ == "__main__":
    main()
