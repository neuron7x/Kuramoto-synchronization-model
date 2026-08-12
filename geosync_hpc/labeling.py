# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Label generation utilities."""

from __future__ import annotations

import pandas as pd


def triple_barrier_labels(
    prices: pd.Series, up_mult: float = 2.0, dn_mult: float = 1.5, max_h: int = 120
) -> pd.DataFrame:
    idx = prices.index
    records: list[tuple[pd.Timestamp, int, pd.Timestamp]] = []
    for i, t0 in enumerate(idx):
        p0 = prices.iloc[i]
        up = p0 * (1 + up_mult * 1e-4)
        dn = p0 * (1 - dn_mult * 1e-4)
        t_end = idx[min(i + max_h, len(idx) - 1)]
        path = prices.iloc[i : min(i + max_h + 1, len(idx))]
        hit = 0
        for t, p in path.items():
            if p >= up:
                hit = 1
                t_end = t
                break
            if p <= dn:
                hit = -1
                t_end = t
                break
        if hit == 0:
            ret = (prices.loc[t_end] / p0) - 1.0
            hit = 1 if ret > 0 else (-1 if ret < 0 else 0)
        records.append((t0, hit, t_end))
    return pd.DataFrame(records, columns=["t0", "label", "t_end"]).set_index("t0")
