from __future__ import annotations

from typing import Dict

import numpy as np


class MarketDataAdapter:
    """Normalize TradePulse data into EMH-friendly observations."""

    def __init__(
        self,
        max_drawdown_limit: float = 0.2,
        spread_threshold: float = 0.01,
        regime_threshold: float = 0.05,
        hist_max_vol: float = 1.0,
        risk_free: float = 0.02,
    ):
        self.max_dd_limit = float(max_drawdown_limit)
        self.spread_thr = float(spread_threshold)
        self.reg_thr = float(regime_threshold)
        self.hist_max_vol = float(hist_max_vol)
        self.risk_free = float(risk_free)

    def transform(self, candles: Dict, portfolio: Dict) -> Dict[str, float]:
        dd = float(portfolio.get("current_drawdown", 0.0)) / max(1e-9, self.max_dd_limit)
        liq = float(candles.get("bid_ask_spread", 0.0)) / max(1e-9, self.spread_thr)
        reg = float(candles.get("regime_deviation", 0.0)) / max(1e-9, self.reg_thr)
        vol = float(candles.get("realized_vol_20", 0.0)) / max(1e-9, self.hist_max_vol)
        vol_obs = float(np.clip(vol, 0.0, 1.0))

        vol_eps = max(1e-6, float(candles.get("realized_vol_20", 1.0)))
        reward_raw = (float(portfolio.get("return", 0.0)) - self.risk_free) / vol_eps
        reward = float(np.tanh(reward_raw))

        var_breach = bool(float(portfolio.get("loss", 0.0)) > float(portfolio.get("VaR_95", 0.05)))
        m_proxy = float(portfolio.get("strategy_alpha_estimate", 0.5))

        return {
            "dd": float(np.clip(dd, 0.0, 1.0)),
            "liq": float(np.clip(liq, 0.0, 1.0)),
            "reg": float(np.clip(reg, 0.0, 1.0)),
            "vol": vol_obs,
            "reward": reward,
            "var_breach": var_breach,
            "m_proxy": float(np.clip(m_proxy, 0.0, 1.0)),
        }
