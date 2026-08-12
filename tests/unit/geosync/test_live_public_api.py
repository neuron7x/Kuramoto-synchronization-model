# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync.live module public API."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLiveModuleImports:
    """Test that all public API imports work correctly."""

    def test_import_live_trader(self) -> None:
        """Test LiveTrader import from geosync.live."""
        from geosync.live import LiveTrader

        assert LiveTrader is not None

    def test_import_live_trader_config(self) -> None:
        """Test LiveTraderConfig import from geosync.live."""
        from geosync.live import LiveTraderConfig

        assert LiveTraderConfig is not None

    def test_import_trading_mode(self) -> None:
        """Test TradingMode import from geosync.live."""
        from geosync.live import TradingMode

        assert TradingMode is not None

    def test_import_strategy_protocol(self) -> None:
        """Test Strategy protocol import from geosync.live."""
        from geosync.live import Strategy

        assert Strategy is not None


class TestTradingMode:
    """Test TradingMode enum."""

    def test_paper_mode(self) -> None:
        """Test paper trading mode."""
        from geosync.live import TradingMode

        assert TradingMode.PAPER.value == "paper"

    def test_live_mode(self) -> None:
        """Test live trading mode."""
        from geosync.live import TradingMode

        assert TradingMode.LIVE.value == "live"


class TestLiveTraderCreation:
    """Test LiveTrader instantiation."""

    def test_create_live_trader_defaults(self) -> None:
        """Test creating LiveTrader with default settings."""
        from geosync.live import LiveTrader

        trader = LiveTrader()

        assert trader is not None
        assert trader.exchange == "binance"
        assert trader.is_paper_trading is True
        assert trader.is_running is False

    def test_create_live_trader_with_exchange(self) -> None:
        """Test creating LiveTrader with custom exchange."""
        from geosync.live import LiveTrader

        trader = LiveTrader(exchange="kraken")

        assert trader.exchange == "kraken"

    def test_create_live_trader_with_symbols(self) -> None:
        """Test creating LiveTrader with symbols."""
        from geosync.live import LiveTrader

        symbols = ["BTC/USDT", "ETH/USDT"]
        trader = LiveTrader(symbols=symbols)

        assert list(trader.symbols) == symbols

    def test_create_live_trader_paper_mode(self) -> None:
        """Test creating LiveTrader in paper mode."""
        from geosync.live import LiveTrader

        trader = LiveTrader(mode="paper")

        assert trader.is_paper_trading is True

    def test_create_live_trader_live_mode(self) -> None:
        """Test creating LiveTrader in live mode."""
        from geosync.live import LiveTrader, TradingMode

        trader = LiveTrader(mode=TradingMode.LIVE)

        assert trader.is_paper_trading is False


class TestLiveTraderConfigCreation:
    """Test LiveTraderConfig instantiation."""

    def test_create_config_minimal(self) -> None:
        """Test creating config with minimal settings."""
        from geosync.live import LiveTraderConfig

        config = LiveTraderConfig(exchange="binance")

        assert config.exchange == "binance"
        assert config.initial_capital == 100_000.0
        assert config.risk_percent == 1.0

    def test_create_config_full(self) -> None:
        """Test creating config with all settings."""
        from geosync.live import LiveTraderConfig, TradingMode

        config = LiveTraderConfig(
            exchange="kraken",
            symbols=["BTC/USD", "ETH/USD"],
            mode=TradingMode.PAPER,
            initial_capital=50_000.0,
            risk_percent=2.0,
        )

        assert config.exchange == "kraken"
        assert list(config.symbols) == ["BTC/USD", "ETH/USD"]
        assert config.mode == TradingMode.PAPER
        assert config.initial_capital == 50_000.0
        assert config.risk_percent == 2.0


class TestLiveTraderStartStop:
    """Test LiveTrader start/stop behavior."""

    def test_start_raises_without_config(self) -> None:
        """Test that start raises when config file is missing."""
        from geosync.live import LiveTrader

        trader = LiveTrader(config_path=Path("/nonexistent/config.toml"))

        with pytest.raises(FileNotFoundError):
            trader.start()

    def test_stop_does_nothing_when_not_running(self) -> None:
        """Test that stop is safe when not running."""
        from geosync.live import LiveTrader

        trader = LiveTrader()
        trader.stop()  # Should not raise

        assert trader.is_running is False

    def test_wait_returns_true_when_not_running(self) -> None:
        """Test that wait returns True when not running."""
        from geosync.live import LiveTrader

        trader = LiveTrader()
        result = trader.wait(timeout=0.1)

        assert result is True


class TestLiveTraderWithMockedRunner:
    """Test LiveTrader with mocked LiveTradingRunner."""

    @patch("geosync.live.LiveTradingRunner")
    def test_start_creates_runner(self, mock_runner_cls: MagicMock) -> None:
        """Test that start creates a LiveTradingRunner."""
        from geosync.live import LiveTrader

        # Mock the config path to exist
        with patch.object(Path, "exists", return_value=True):
            trader = LiveTrader()
            trader.start()

            mock_runner_cls.assert_called_once()
            assert trader.is_running is True

    @patch("geosync.live.LiveTradingRunner")
    def test_stop_shuts_down_runner(self, mock_runner_cls: MagicMock) -> None:
        """Test that stop properly shuts down the runner."""
        from geosync.live import LiveTrader

        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner

        with patch.object(Path, "exists", return_value=True):
            trader = LiveTrader()
            trader.start()
            trader.stop(reason="test shutdown")

            mock_runner.request_stop.assert_called_once_with(reason="test shutdown")
            mock_runner.shutdown.assert_called_once()
            assert trader.is_running is False

    @patch("geosync.live.LiveTradingRunner")
    def test_double_start_raises(self, mock_runner_cls: MagicMock) -> None:
        """Test that starting twice raises RuntimeError."""
        from geosync.live import LiveTrader

        with patch.object(Path, "exists", return_value=True):
            trader = LiveTrader()
            trader.start()

            with pytest.raises(RuntimeError, match="already running"):
                trader.start()
