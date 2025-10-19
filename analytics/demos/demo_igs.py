"""
IGS batch and streaming demonstration. Saves CSV outputs.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from analytics.signals.irreversibility import IGSConfig, compute_igs_features, igs_directional_signal, StreamingIGS

np.random.seed(0)
n = 3000
parts = [
    np.cumsum(0.05 + 0.6*np.random.randn(600)),
    np.cumsum(0.00 + 1.0*np.random.randn(600)),
    np.cumsum(-0.03 + 0.5*np.random.randn(600)),
    np.cumsum(0.02 + 0.7*np.random.randn(n-1800)),
]
trend = np.concatenate(parts)
price = 100.0 * np.exp(trend / 100.0)
idx = pd.date_range("2024-01-01", periods=n, freq="min")
price_series = pd.Series(price, index=idx, name="close")

cfg = IGSConfig(window=400, n_states=7)
features = compute_igs_features(price_series, cfg)
signal = igs_directional_signal(features, epr_q=0.7, flux_min=0.0)
out = pd.concat([price_series.rename("close"), features, signal.rename("igs_signal")], axis=1)
Path("igs_demo_features_signal.csv").write_text(out.to_csv())

eng = StreamingIGS(cfg)
rows = []
for t, p in price_series.items():
    m = eng.update(t, float(p))
    if m:
        rows.append([t, m.epr, m.flux_index, m.tra, m.pe, m.regime_score, m.regime, m.n_states_used])
stream_df = pd.DataFrame(rows, columns=["ts", "epr", "flux", "tra", "pe", "regime_score", "regime", "K"]).set_index("ts")
Path("igs_demo_stream.csv").write_text(stream_df.to_csv())
