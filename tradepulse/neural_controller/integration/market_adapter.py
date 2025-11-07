"""Market data adapter for neural controller observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class AdapterConfig:
    max_drawdown_limit: float = 0.2
    spread_threshold: float = 0.01
    vol_threshold: float = 0.05
    historical_max_vol: float = 1.0
    risk_free: float = 0.02
    eps_vol: float = 1e-6

    def __post_init__(self) -> None:
        self.max_drawdown_limit = float(self.max_drawdown_limit)
        self.spread_threshold = float(self.spread_threshold)
        self.vol_threshold = float(self.vol_threshold)
        self.historical_max_vol = float(self.historical_max_vol)
        self.risk_free = float(self.risk_free)
        self.eps_vol = float(self.eps_vol)


class MarketDataAdapter:
    """Convert raw portfolio/candle data into bounded neural inputs."""

    def __init__(self, cfg: AdapterConfig = AdapterConfig()):
        self.cfg = cfg

    def transform(self, candles: Dict, portfolio: Dict) -> Dict[str, float]:
        dd = np.clip(float(portfolio.get("current_drawdown", 0.0)) / max(1e-9, self.cfg.max_drawdown_limit), 0, 1)
        liq = np.clip(float(candles.get("bid_ask_spread", 0.0)) / max(1e-12, self.cfg.spread_threshold), 0, 1)
        reg = np.clip(float(candles.get("regime_deviation", 0.0)) / max(1e-12, self.cfg.vol_threshold), 0, 1)
        vol = np.clip(float(candles.get("realized_vol_20", 0.0)) / max(1e-12, self.cfg.historical_max_vol), 0, 1)
        port_ret = float(portfolio.get("return", 0.0))
        denom = max(self.cfg.eps_vol, float(candles.get("realized_vol_20", 0.0)))
        reward = float(np.tanh((port_ret - self.cfg.risk_free) / denom))
        var_breach = bool(portfolio.get("loss", 0.0) > portfolio.get("VaR_95", 0.05))
        m_proxy = np.clip(float(portfolio.get("strategy_alpha_estimate", 0.5)), 0, 1)
        return {
            "dd": dd,
            "liq": liq,
            "reg": reg,
            "vol": vol,
            "reward": reward,
            "var_breach": var_breach,
            "m_proxy": m_proxy,
        }
