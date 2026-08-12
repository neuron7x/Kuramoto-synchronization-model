# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High-level orchestration translating agent actions into GeoSync orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from domain import Signal, SignalAction
from geosync.sdk import (
    ExecutionResult,
    GeoSyncSDK,
    MarketState,
    RiskCheckResult,
    SuggestedOrder,
)
from geosync.sdk.engine import _SymbolContext

from .config import AgentExecutionConfig
from .environment import AgentAction, AgentObservation


@dataclass(slots=True)
class AgentExecutionBundle:
    """Outcome of attempting to execute an agent action via the SDK."""

    action: AgentAction
    signal: Signal | None
    suggested_order: SuggestedOrder | None
    risk_result: RiskCheckResult | Exception | None
    execution: ExecutionResult | None


class AgentTradeOrchestrator:
    """Convert agent outputs into GeoSync SDK interactions."""

    def __init__(
        self,
        sdk: GeoSyncSDK,
        *,
        symbol: str,
        venue: str,
        execution_config: AgentExecutionConfig,
        price_column: str,
        market_strategy: Callable[[np.ndarray], np.ndarray] | None = None,
    ) -> None:
        self._sdk = sdk
        self._symbol = symbol
        self._venue = venue
        self._execution_config = execution_config
        self._price_column = price_column
        self._strategy = market_strategy

    def execute_action(
        self,
        action: AgentAction,
        observation: AgentObservation,
    ) -> AgentExecutionBundle:
        """Translate *action* into GeoSync SDK calls."""

        cfg = self._execution_config
        if action is AgentAction.HOLD and not cfg.execute_hold:
            return AgentExecutionBundle(action, None, None, None, None)

        market_frame = observation.to_market_state_frame()
        market_state = MarketState(
            symbol=self._symbol,
            venue=self._venue,
            market_frame=market_frame,
            strategy=self._strategy,
        )

        try:
            self._sdk.get_signal(market_state)
        except Exception:
            last_price = float(market_frame[self._price_column].iloc[-1])
            context = _SymbolContext(venue=self._venue.lower(), last_price=last_price)
            getattr(self._sdk, "_contexts")[self._symbol] = context

        target_position = observation.position
        if action is AgentAction.BUY:
            target_position = min(observation.position + cfg.position_increment, cfg.max_position)
        elif action is AgentAction.SELL:
            target_position = max(observation.position - cfg.position_increment, -cfg.max_position)

        quantity = abs(target_position - observation.position)
        if quantity <= cfg.flatten_threshold and not cfg.execute_hold:
            return AgentExecutionBundle(action, None, None, None, None)

        signal_action = SignalAction.HOLD
        if quantity > cfg.flatten_threshold:
            if target_position == 0 and observation.position != 0:
                signal_action = SignalAction.EXIT
            elif target_position > observation.position:
                signal_action = SignalAction.BUY
            elif target_position < observation.position:
                signal_action = SignalAction.SELL

        if signal_action is SignalAction.HOLD and not cfg.execute_hold:
            return AgentExecutionBundle(action, None, None, None, None)

        confidence = self._derive_confidence(quantity, market_frame)
        metadata = {
            "quantity": float(quantity if quantity > 0 else cfg.position_increment),
            "target_position": float(target_position),
            "current_position": float(observation.position),
        }

        float(market_frame[self._price_column].iloc[-1])
        signal = Signal(
            symbol=self._symbol,
            action=signal_action,
            confidence=confidence,
            metadata=metadata,
        )

        try:
            suggested = self._sdk.propose_trade(signal)
        except Exception as exc:
            return AgentExecutionBundle(action, signal, None, exc, None)

        try:
            risk = self._sdk.risk_check(suggested.order)
        except Exception as exc:
            return AgentExecutionBundle(action, signal, suggested, exc, None)

        if not getattr(risk, "approved", False):
            return AgentExecutionBundle(action, signal, suggested, risk, None)

        execution = self._sdk.execute(suggested.order)
        return AgentExecutionBundle(action, signal, suggested, risk, execution)

    def _derive_confidence(self, quantity: float, market_frame) -> float:
        cfg = self._execution_config
        fraction = min(1.0, quantity / max(cfg.max_position, 1e-9))
        price_series = market_frame[self._price_column]
        if len(price_series) >= 2:
            delta = abs(float(price_series.iloc[-1] - price_series.iloc[-2]))
        else:
            delta = 0.0
        scaled = fraction + cfg.confidence_scale * delta / max(float(price_series.iloc[-1]), 1e-9)
        confidence = max(cfg.min_confidence, min(1.0, scaled))
        return float(confidence)
