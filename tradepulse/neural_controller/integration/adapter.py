"""Adapters translating TradePulse market state into controller observations."""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

log = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp_unit(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


class MarketDataAdapter:
    """Adapt raw data into bounded observations expected by the EMH controller."""

    def __init__(
        self,
        max_drawdown_limit: float = 0.20,
        spread_threshold: float = 0.01,
        regime_threshold: float = 0.05,
        hist_max_vol: float = 1.0,
        risk_free: float = 0.02,
    ) -> None:
        self.max_dd_limit = float(max_drawdown_limit)
        self.spread_thr = float(spread_threshold)
        self.reg_thr = float(regime_threshold)
        self.hist_max_vol = float(hist_max_vol)
        self.risk_free = float(risk_free)

    def transform(
        self, candles: Dict[str, Any], portfolio: Dict[str, Any]
    ) -> Dict[str, float | bool]:
        """Return a normalized observation dictionary safe for controller ingestion."""

        dd_raw = _safe_float(portfolio.get("current_drawdown"))
        liq_raw = _safe_float(candles.get("bid_ask_spread"))
        reg_raw = _safe_float(candles.get("regime_deviation"))
        vol_obs = _safe_float(candles.get("realized_vol_20"))
        reward_obs = _safe_float(portfolio.get("return"))
        loss = _safe_float(portfolio.get("loss"))
        var_limit = _safe_float(portfolio.get("VaR_95"), default=0.05)
        m_proxy = _safe_float(portfolio.get("strategy_alpha_estimate"), default=0.5)

        dd_norm = dd_raw / max(self.max_dd_limit, 1e-9)
        liq_norm = liq_raw / max(self.spread_thr, 1e-9)
        reg_norm = reg_raw / max(self.reg_thr, 1e-9)
        vol_norm = vol_obs / max(self.hist_max_vol, 1e-9)

        vol_eps = max(abs(vol_obs), 1e-6)
        reward = float(np.tanh((reward_obs - self.risk_free) / vol_eps))

        var_breach = bool(loss > var_limit)

        payload: Dict[str, float | bool] = {
            "dd": _clamp_unit(dd_norm),
            "liq": _clamp_unit(liq_norm),
            "reg": _clamp_unit(reg_norm),
            "vol": _clamp_unit(vol_norm),
            "reward": reward,
            "var_breach": var_breach,
            "m_proxy": _clamp_unit(m_proxy),
        }

        numeric_values = [value for value in payload.values() if isinstance(value, float)]
        if any(np.isnan(value) or np.isinf(value) for value in numeric_values):
            log.warning(
                "adapter produced invalid payload",  # noqa: TRY400 - structured logging
                extra={"event": "neuro.adapter_invalid", "payload": payload},
            )
            payload = {
                "dd": 0.0,
                "liq": 0.0,
                "reg": 0.0,
                "vol": 0.0,
                "reward": 0.0,
                "var_breach": False,
                "m_proxy": 0.5,
            }

        return payload
