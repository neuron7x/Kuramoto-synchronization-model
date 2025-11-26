"""Feature engineering for NeuroTrade PRO synthetic datasets."""

from __future__ import annotations

from collections import deque
from typing import Deque

import numpy as np
import pandas as pd


class FeatureStore:
    """Streaming feature accumulator."""

    def __init__(
        self, fracdiff_d: float = 0.4, ofi_window: int = 20, buf_maxlen: int = 600
    ) -> None:
        self.d = fracdiff_d
        self.ofi_window = ofi_window
        self.buf: Deque[dict[str, float]] = deque(maxlen=int(buf_maxlen))

    def update(self, row: dict[str, float]) -> None:
        """Append the latest microstructure snapshot."""
        self.buf.append(row)

    def _fracdiff(
        self, x: np.ndarray | list[float], d: float = 0.4, window: int = 200
    ) -> float:
        w, k = [1.0], 1
        while True:
            w_ = -w[-1] * (d - k + 1) / k
            if abs(w_) < 1e-5 or k > window:
                break
            w.append(w_)
            k += 1
        w_arr = np.array(w)[::-1]
        x_ser = pd.Series(x)
        if len(x_ser) < len(w_arr):
            return float("nan")
        return float(np.dot(w_arr, x_ser.values[-len(w_arr) :]))

    def snapshot(self, lookbacks: list[int]) -> dict[str, float] | None:
        if not self.buf:
            return None
        df = pd.DataFrame(list(self.buf))
        mid = float(df["mid"].iloc[-1])
        spread = (df["ask"].iloc[-1] - df["bid"].iloc[-1]) / mid
        depth_imb = (df["bid_size"].iloc[-1] - df["ask_size"].iloc[-1]) / (
            1e-9 + df["bid_size"].iloc[-1] + df["ask_size"].iloc[-1]
        )

        eff_spread = 2.0 * abs(df["last"].iloc[-1] - mid) / mid
        if len(df) > 1:
            prev_mid = float(df["mid"].iloc[-2])
            realized_spread = (df["last"].iloc[-1] - prev_mid) / prev_mid
        else:
            realized_spread = 0.0

        sign = np.sign(df["last"] - df["mid"])
        signed_vol = sign * df["last_size"]
        if len(df) >= self.ofi_window:
            ofi = signed_vol.tail(self.ofi_window).sum()
        else:
            ofi = signed_vol.sum()

        if len(df) > 1:
            dp = float(df["mid"].iloc[-1] - df["mid"].iloc[-2])
            lam = abs(dp) / (1e-6 + float(df["last_size"].iloc[-1]))
        else:
            lam = 0.0

        snap: dict[str, float] = {
            "mid": mid,
            "spread": float(spread),
            "depth_imb": float(depth_imb),
            "eff_spread": float(eff_spread),
            "realized_spread": float(realized_spread),
            "ofi_sh": float(ofi),
            "signed_vol": float(signed_vol.iloc[-1]),
            "kyle_lambda": float(lam),
        }

        for lb in lookbacks:
            if len(df) >= lb:
                v = df["last_size"].tail(lb).values
                p = df["last"].tail(lb).values
                vwap = np.sum(v * p) / (1e-9 + np.sum(v))
                snap[f"vwap_dist_{lb}"] = (mid - vwap) / mid
                snap[f"ret_{lb}"] = (mid / float(df["mid"].iloc[-lb])) - 1.0
            else:
                snap[f"vwap_dist_{lb}"] = float("nan")
                snap[f"ret_{lb}"] = float("nan")

        mids = df["mid"].values
        snap["fracdiff"] = self._fracdiff(mids, d=self.d)

        if len(mids) > 10:
            if len(mids) >= 60:
                returns = np.diff(np.log(mids[-60:]))
            else:
                returns = np.diff(np.log(mids))
            rv = np.sqrt(np.sum(returns**2))
            snap["rv"] = 1e4 * rv
            if len(mids) >= 120:
                r2 = np.diff(np.log(mids[-120:]))
                rv2 = pd.Series(r2).rolling(20).std().fillna(0).values
                snap["vov"] = float(np.nan_to_num(np.std(rv2)))
            else:
                snap["vov"] = 0.0
        else:
            snap["rv"] = float("nan")
            snap["vov"] = float("nan")

        return snap
