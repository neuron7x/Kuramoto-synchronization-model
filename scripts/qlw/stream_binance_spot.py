"""Live Binance spot market streaming with QLW analysis."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import websockets

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tradepulse_qlw.config import QLWConfig
from src.tradepulse_qlw.engine import QLWEngine


async def stream(symbol="btcusdt"):
    """Stream market data and run QLW analysis."""
    # Load config
    config_path = Path(__file__).parent.parent.parent / "configs" / "profiles" / "balanced.yml"
    if YAML_AVAILABLE and config_path.exists():
        with open(config_path) as f:
            cfg_dict = yaml.safe_load(f)
        cfg = QLWConfig(**cfg_dict)
    else:
        cfg = QLWConfig()

    engine = QLWEngine(cfg)
    uri = f"wss://stream.binance.com:9443/ws/{symbol}@depth20@100ms"
    log, fmn_buffer, dv_buffer = [], [], []

    async with websockets.connect(uri, ping_interval=20) as ws:
        end = datetime.now().timestamp() + 2 * 3600
        while datetime.now().timestamp() < end:
            try:
                msg = json.loads(await ws.recv())
                if "b" not in msg or "a" not in msg:
                    continue
                bids = np.array(msg["b"], dtype=float)[:, 0][:20]
                asks = np.array(msg["a"], dtype=float)[:, 0][:20]
                mid = (bids.mean() + asks.mean()) / 2
                fmn = np.concatenate([bids / mid, asks / mid])
                dv = (bids.sum() - asks.sum()) / (bids.sum() + asks.sum() + 1e-12)
                fmn_buffer.append(fmn)
                dv_buffer.append(dv)

                if len(fmn_buffer) >= cfg.nt:
                    fmn_arr = np.array(fmn_buffer[-cfg.nt :])
                    dv_arr = np.array(dv_buffer[-cfg.nt :])
                    out = engine.run(fmn_arr, delta_volume=dv_arr)
                    metrics = {
                        "ts": datetime.now().isoformat(),
                        "forbidden_ratio": float(out.forbidden_mask.mean()),
                        "tau": out.meta["tau"],
                        "c": out.meta["c"],
                        "gamma": out.meta["gamma"],
                        "R_auc": out.meta["R_auc"],
                        "energy_mean": float(np.mean(out.psi**2)),
                    }
                    log.append(metrics)
                    output_path = (
                        Path(__file__).parent.parent.parent
                        / "reports"
                        / "binance_metrics.csv"
                    )
                    pd.DataFrame(log).to_csv(output_path, index=False)
                    print(f"Updated metrics: tau={metrics['tau']:.3f}, gamma={metrics['gamma']:.3f}")
                    await asyncio.sleep(10)
                await asyncio.sleep(0.02)
            except Exception as e:
                print(f"Error: {e}")
                break


if __name__ == "__main__":
    asyncio.run(stream())
