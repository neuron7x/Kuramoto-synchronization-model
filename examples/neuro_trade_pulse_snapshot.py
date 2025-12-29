import numpy as np
import pandas as pd

from strategies.neuro_trade_pulse import NeuroTradePulseConfig, NeuroTradePulseStrategy
from core.utils.determinism import DEFAULT_SEED


def sample_df(n=1500, seed=DEFAULT_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="5min")
    price = 100 + np.cumsum(rng.normal(0, 0.6, n))
    volume = np.exp(rng.normal(9.5, 0.35, n))
    return pd.DataFrame({"close": price, "volume": volume}, index=idx)


if __name__ == "__main__":
    bars = sample_df()
    strat = NeuroTradePulseStrategy(NeuroTradePulseConfig())

    # Snapshot (first 720 points)
    snap = strat.analyze_snapshot(bars.iloc[:720])
    print("=== NeuroTradePulse Snapshot ===")
    print("Phase:", snap.phase.value)
    print(
        "Confidence:", round(snap.confidence, 3), "Entry:", round(snap.entry_signal, 3)
    )

    # Full series
    sig = strat.generate_signals(bars)
    print("Tail of actions:\n", sig.tail())
