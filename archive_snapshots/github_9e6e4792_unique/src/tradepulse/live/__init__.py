# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""TradePulse live trading module - Public API for live trading capabilities.

This module provides convenient access to live trading functionality
through the tradepulse namespace, as documented in the README.

Example:
    >>> from tradepulse.live import LiveTrader
    >>> trader = LiveTrader(strategy=my_strategy, exchange="binance", mode="paper")
    >>> trader.start()
"""

from __future__ import annotations

__CANONICAL__ = True

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from interfaces.live_runner import DEFAULT_CONFIG_PATH, LiveTradingRunner


class TradingMode(str, Enum):
    """Live trading execution mode."""

    PAPER = "paper"
    LIVE = "live"


class Strategy(Protocol):
    """Protocol for trading strategies compatible with LiveTrader."""

    def generate_signals(self, market_data: Any) -> Mapping[str, float]:
        """Generate trading signals from market data.

        Args:
            market_data: Market data to analyze.

        Returns:
            Dictionary mapping symbols to signal strengths (-1 to 1).
        """
        ...

    def on_tick(self, tick: Any) -> None:
        """Process incoming market tick."""
        ...


@dataclass
class LiveTraderConfig:
    """Configuration for LiveTrader.

    Attributes:
        exchange: Exchange to connect to (e.g., "binance", "kraken").
        symbols: List of trading symbols.
        mode: Trading mode - "paper" for simulation, "live" for real trading.
        config_path: Path to TOML configuration file.
        initial_capital: Starting capital for paper trading.
        risk_percent: Maximum risk per trade as percentage.
    """

    exchange: str
    symbols: Sequence[str] = field(default_factory=list)
    mode: TradingMode = TradingMode.PAPER
    config_path: Path | None = None
    initial_capital: float = 100_000.0
    risk_percent: float = 1.0


class LiveTrader:
    """High-level interface for live trading.

    Provides a simple API for starting and managing live trading sessions
    with configurable strategies and risk management.

    Example:
        >>> trader = LiveTrader(
        ...     strategy=my_strategy,
        ...     exchange="binance",
        ...     mode="paper",
        ... )
        >>> trader.start()
    """

    def __init__(
        self,
        strategy: Strategy | Callable[..., Any] | None = None,
        *,
        exchange: str = "binance",
        symbols: Sequence[str] | None = None,
        mode: str | TradingMode = TradingMode.PAPER,
        config_path: Path | str | None = None,
        initial_capital: float = 100_000.0,
        risk_percent: float = 1.0,
    ) -> None:
        """Initialize LiveTrader.

        Args:
            strategy: Trading strategy implementing the Strategy protocol.
            exchange: Exchange to connect to (e.g., "binance", "kraken").
            symbols: List of trading symbols to trade.
            mode: Trading mode - "paper" for simulation, "live" for real trading.
            config_path: Path to TOML configuration file. Defaults to
                configs/live/default.toml.
            initial_capital: Starting capital for paper trading.
            risk_percent: Maximum risk per trade as percentage (1-100).
        """
        self._strategy = strategy
        self._exchange = exchange
        self._symbols = list(symbols or [])
        self._mode = TradingMode(mode) if isinstance(mode, str) else mode
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._initial_capital = initial_capital
        self._risk_percent = risk_percent
        self._runner: LiveTradingRunner | None = None
        self._running = False

    @property
    def is_paper_trading(self) -> bool:
        """Return True if running in paper trading mode."""
        return self._mode == TradingMode.PAPER

    @property
    def is_running(self) -> bool:
        """Return True if the trader is currently active."""
        return self._running

    @property
    def exchange(self) -> str:
        """Return the configured exchange."""
        return self._exchange

    @property
    def symbols(self) -> Sequence[str]:
        """Return the list of trading symbols."""
        return tuple(self._symbols)

    def start(self, *, cold_start: bool = True) -> None:
        """Start the live trading session.

        Args:
            cold_start: If True, start fresh without restoring previous state.

        Raises:
            RuntimeError: If trader is already running or configuration is missing.
            FileNotFoundError: If config file doesn't exist.
        """
        if self._running:
            raise RuntimeError("LiveTrader is already running")

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Live trading config not found: {self._config_path}. "
                "Create a configuration file or specify a valid path."
            )

        self._runner = LiveTradingRunner(
            config_path=self._config_path,
            venues=[self._exchange],
        )
        self._running = True
        self._runner.start(cold_start=cold_start)

    def stop(self, reason: str | None = None) -> None:
        """Stop the live trading session gracefully.

        Args:
            reason: Optional reason for stopping.
        """
        if not self._running or self._runner is None:
            return

        self._runner.request_stop(reason=reason)
        self._runner.shutdown()
        self._running = False
        self._runner = None

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the trader to stop.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if trader stopped within timeout, False otherwise.
        """
        if self._runner is None:
            return True
        return self._runner.wait(timeout)

    def run(self, *, cold_start: bool = True) -> None:
        """Run the trading loop until interrupted.

        This is a blocking call that runs until the trader is stopped
        via signal or kill switch.

        Args:
            cold_start: If True, start fresh without restoring previous state.
        """
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Live trading config not found: {self._config_path}"
            )

        self._runner = LiveTradingRunner(
            config_path=self._config_path,
            venues=[self._exchange],
        )
        self._running = True
        try:
            self._runner.run(cold_start=cold_start)
        finally:
            self._running = False
            self._runner = None


__all__ = [
    "LiveTrader",
    "LiveTraderConfig",
    "TradingMode",
    "Strategy",
]
