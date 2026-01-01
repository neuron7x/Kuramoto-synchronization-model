"""Adapters translating TradePulse market state into controller observations."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Tuple

import numpy as np

from ..core.params import OBSERVATION_KEYS
from ..core.sensory_schema import SCHEMA_VERSION

log = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isnan(resolved) or np.isinf(resolved):
        return float(default)
    return resolved


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
        eps: float = 1e-6,
        schema_version: int = SCHEMA_VERSION,
        expected_fields: Iterable[str] = OBSERVATION_KEYS,
    ) -> None:
        self.max_dd_limit = float(max_drawdown_limit)
        self.spread_thr = float(spread_threshold)
        self.reg_thr = float(regime_threshold)
        self.hist_max_vol = float(hist_max_vol)
        self.risk_free = float(risk_free)
        self.eps = float(eps)
        self.schema_version = int(schema_version)
        self.expected_fields = self._normalize_expected_fields(expected_fields)

    @staticmethod
    def _normalize_expected_fields(fields: Iterable[str]) -> Tuple[str, ...]:
        normalized = tuple(fields)
        if not normalized:
            raise ValueError("MarketDataAdapter expected_fields must be non-empty.")
        if any(not key for key in normalized):
            raise ValueError("MarketDataAdapter expected_fields must be non-empty strings.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("MarketDataAdapter expected_fields must be unique.")
        unexpected = set(normalized) - set(OBSERVATION_KEYS)
        if unexpected:
            allowed = ", ".join(OBSERVATION_KEYS)
            raise ValueError(
                "MarketDataAdapter expected_fields contains unexpected values "
                f"{sorted(unexpected)}. Allowed keys: {allowed}."
            )
        return normalized

    def transform(
        self, candles: Dict[str, Any], portfolio: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return a normalized observation dictionary safe for controller ingestion."""

        dd_raw = _safe_float(portfolio.get("current_drawdown"))
        liq_raw = _safe_float(candles.get("bid_ask_spread"))
        reg_raw = _safe_float(candles.get("regime_deviation"))
        vol_obs = _safe_float(candles.get("realized_vol_20"))
        reward_obs = _safe_float(portfolio.get("return"), default=self.risk_free)
        loss = _safe_float(portfolio.get("loss"))
        var_limit = _safe_float(portfolio.get("VaR_95"), default=0.05)
        m_proxy = _safe_float(portfolio.get("strategy_alpha_estimate"), default=0.5)

        dd_norm = dd_raw / max(self.max_dd_limit, self.eps)
        liq_norm = liq_raw / max(self.spread_thr, self.eps)
        reg_norm = reg_raw / max(self.reg_thr, self.eps)
        vol_norm = vol_obs / max(self.hist_max_vol, self.eps)

        reward = float(
            np.tanh((reward_obs - self.risk_free) / max(abs(vol_obs), self.eps))
        )

        var_breach = bool(loss > var_limit)

        payload: Dict[str, float | bool] = {
            "dd": _clamp_unit(np.nan_to_num(dd_norm, nan=0.0, posinf=1.0, neginf=0.0)),
            "liq": _clamp_unit(
                np.nan_to_num(liq_norm, nan=0.0, posinf=1.0, neginf=0.0)
            ),
            "reg": _clamp_unit(
                np.nan_to_num(reg_norm, nan=0.0, posinf=1.0, neginf=0.0)
            ),
            "vol": _clamp_unit(
                np.nan_to_num(vol_norm, nan=0.0, posinf=1.0, neginf=0.0)
            ),
            "reward": reward,
            "var_breach": var_breach,
            "m_proxy": _clamp_unit(
                np.nan_to_num(m_proxy, nan=0.5, posinf=1.0, neginf=0.0)
            ),
        }

        numeric_values = [
            value for value in payload.values() if isinstance(value, float)
        ]
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

        payload["schema_version"] = self.schema_version
        payload["expected_fields"] = self.expected_fields
        return payload
