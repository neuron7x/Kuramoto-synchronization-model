# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adapter that bridges the legacy AMM module with the advanced neuro system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.neuro.amm import AdaptiveMarketMind, AMMConfig

from ..advanced import IntegratedNeuroTradingSystem, NeuroAdvancedConfig


@dataclass(slots=True)
class MarketPulse:
    """Normalized market pulse for the AMM."""

    signal: float
    synchrony: float
    curvature: float
    entropy: Optional[float] = None


class GeoSyncNeuroAdapter:
    """High level orchestrator combining AMM with the advanced neuro module."""

    def __init__(
        self,
        amm_config: Optional[AMMConfig] = None,
        advanced_config: Optional[NeuroAdvancedConfig] = None,
    ) -> None:
        self._amm = AdaptiveMarketMind(amm_config or AMMConfig())
        self._neuro = IntegratedNeuroTradingSystem(advanced_config)

    @property
    def amm(self) -> AdaptiveMarketMind:
        return self._amm

    @property
    def neuro(self) -> IntegratedNeuroTradingSystem:
        return self._neuro

    async def process_market_update(
        self,
        market_pulse: MarketPulse,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        amm_snapshot = self._amm.update(
            market_pulse.signal,
            market_pulse.synchrony,
            market_pulse.curvature,
            market_pulse.entropy,
        )
        neuro_response = await self._neuro.process_trading_cycle(market_data, portfolio_state)
        return {
            "amm": amm_snapshot,
            "neuro": neuro_response,
        }

    async def update_after_execution(self, execution_results: Dict[str, Any]) -> Dict[str, Any]:
        return await self._neuro.update_from_execution(execution_results)

    def save_state(self, path: str) -> bool:
        return self._neuro.save_state(path)

    def load_state(self, path: str) -> bool:
        return self._neuro.load_state(path)
