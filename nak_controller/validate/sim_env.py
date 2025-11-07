from typing import Dict, Iterator

import numpy as np


def multi_regime_stream(steps: int, seed: int) -> Iterator[Dict[str, float]]:
    rng = np.random.default_rng(seed)
    regime_len = 200
    regimes = ["normal", "volatile", "crash"]
    for t in range(steps):
        reg = regimes[(t // regime_len) % len(regimes)]
        if reg == "normal":
            drift, vol = 0.0004, 0.01
        elif reg == "volatile":
            drift, vol = 0.0006, 0.03
        else:  # crash
            drift, vol = -0.0012, 0.05
        ret = drift + vol * rng.standard_normal()
        yield {
            "ret": ret,
            "global_vol": min(1.0, abs(vol * 30)),
            "portfolio_dd_proxy": 0.0,
        }
