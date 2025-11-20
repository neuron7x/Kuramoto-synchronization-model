"""Event-driven trading environment tailored for RL agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

import numpy as np
import pandas as pd

from application.system import TradePulseSystem

from .config import AgentDataFeedConfig, AgentEnvironmentConfig
from .data import AgentDataLoader, LoadedData


class AgentAction(Enum):
    """Discrete action space exposed to the reinforcement-learning agent."""

    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass(slots=True)
class AgentObservation:
    """Observation emitted by :class:`TradingAgentEnvironment`."""

    market_window: pd.DataFrame
    feature_window: pd.DataFrame
    feature_matrix: np.ndarray
    price: float
    position: float
    cash: float

    def to_market_state_frame(self) -> pd.DataFrame:
        """Return a deep copy suitable for :class:`~tradepulse.sdk.MarketState`."""

        return self.market_window.copy(deep=True)


@dataclass(slots=True)
class AgentStepResult:
    """Transition tuple returned by :meth:`TradingAgentEnvironment.step`."""

    observation: AgentObservation
    reward: float
    done: bool
    info: Dict[str, float]


class TradingAgentEnvironment:
    """A lightweight portfolio simulator grounded in TradePulse feature data."""

    def __init__(
        self,
        system: TradePulseSystem,
        loader: AgentDataLoader,
        feed_config: AgentDataFeedConfig,
        env_config: AgentEnvironmentConfig,
    ) -> None:
        self._system = system
        self._loader = loader
        self._feed_config = feed_config
        self._env_config = env_config
        self._data: LoadedData | None = None
        self._cursor: int = 0
        self._position: float = 0.0
        self._cash: float = env_config.initial_cash
        self._prev_value: float = env_config.initial_cash
        self._price_column = system.feature_pipeline.config.price_col

    # ------------------------------------------------------------------
    # RL API
    def reset(self) -> AgentObservation:
        """Reset the environment state and return the initial observation."""

        self._data = self._loader.load(self._feed_config)
        feature_frame = self._data.feature_frame
        if feature_frame.shape[0] <= self._env_config.lookback_window:
            raise ValueError("Not enough samples to satisfy the lookback window")

        self._cursor = self._env_config.lookback_window
        self._position = 0.0
        self._cash = self._env_config.initial_cash
        self._prev_value = self._env_config.initial_cash
        return self._build_observation()

    def step(self, action: AgentAction) -> AgentStepResult:
        """Advance one timestep using *action* and return the transition tuple."""

        if self._data is None:
            raise RuntimeError("Environment must be reset before stepping")
        if self._cursor >= self._data.feature_frame.shape[0]:
            raise RuntimeError("Episode has already terminated")

        current_price = self._current_price
        prev_value = self._portfolio_value(current_price)

        target_position = self._position
        cfg = self._env_config
        if action is AgentAction.BUY:
            target_position = min(
                self._position + cfg.position_increment, cfg.max_position
            )
        elif action is AgentAction.SELL:
            target_position = max(
                self._position - cfg.position_increment, -cfg.max_position
            )

        delta = target_position - self._position
        trade_value = delta * current_price
        fee = abs(trade_value) * (cfg.trading_fee_bps / 10_000.0)
        self._cash -= trade_value + fee
        self._position = target_position

        self._cursor += 1
        done = self._cursor >= self._data.feature_frame.shape[0]
        next_price = self._current_price
        portfolio_value = self._portfolio_value(next_price)
        reward = ((portfolio_value - prev_value) / prev_value) * cfg.reward_scaling
        self._prev_value = portfolio_value

        observation = self._build_observation()
        info: Dict[str, float] = {
            "price": float(next_price),
            "position": float(self._position),
            "cash": float(self._cash),
            "portfolio_value": float(portfolio_value),
            "trade_value": float(trade_value),
        }
        return AgentStepResult(
            observation=observation, reward=float(reward), done=done, info=info
        )

    # ------------------------------------------------------------------
    # Helpers
    def _build_observation(self) -> AgentObservation:
        assert self._data is not None
        start = self._cursor - self._env_config.lookback_window
        end = self._cursor
        market_window = self._data.market_frame.iloc[start:end]
        feature_window = self._data.feature_frame.iloc[start:end]
        features = feature_window.to_numpy(dtype=np.float32)
        price = float(market_window[self._price_column].iloc[-1])
        return AgentObservation(
            market_window=market_window.copy(deep=True),
            feature_window=feature_window.copy(deep=True),
            feature_matrix=features,
            price=price,
            position=float(self._position),
            cash=float(self._cash),
        )

    @property
    def _current_price(self) -> float:
        assert self._data is not None
        price_series = self._data.feature_frame[self._price_column]
        return float(price_series.iloc[self._cursor - 1])

    def _portfolio_value(self, price: float) -> float:
        return self._cash + self._position * price
