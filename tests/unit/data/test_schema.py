# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for geosync.data.schema module.

Tests validation of core market data models:
- Bar (OHLCV candle data)
- Tick (tick-level price updates)
- FeatureVector (strategy features)
- MarketSnapshot (point-in-time market state)
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

# Add src to path for proper imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from geosync.data.schema import (  # noqa: E402
    Bar,
    Candle,
    FeatureVector,
    MarketSnapshot,
    OrderSide,
    Tick,
    Timeframe,
)

# ============================================================================
# Timeframe Tests
# ============================================================================


class TestTimeframe:
    """Tests for Timeframe enum."""

    def test_timeframe_seconds(self) -> None:
        """Test timeframe duration in seconds."""
        assert Timeframe.M1.seconds == 60
        assert Timeframe.H1.seconds == 3600
        assert Timeframe.D1.seconds == 86400

    def test_timeframe_from_string(self) -> None:
        """Test parsing timeframe from string."""
        assert Timeframe.from_string("1m") == Timeframe.M1
        assert Timeframe.from_string("1h") == Timeframe.H1
        assert Timeframe.from_string("1min") == Timeframe.M1
        assert Timeframe.from_string("1hour") == Timeframe.H1

    def test_timeframe_from_string_invalid(self) -> None:
        """Test invalid timeframe string raises ValueError."""
        with pytest.raises(ValueError, match="Unknown timeframe"):
            Timeframe.from_string("invalid")


# ============================================================================
# Bar Tests
# ============================================================================


class TestBar:
    """Tests for Bar (OHLCV) model."""

    @pytest.fixture
    def valid_bar_data(self) -> dict:
        """Return valid bar data for testing."""
        return {
            "timestamp": datetime.now(timezone.utc),
            "symbol": "BTCUSDT",
            "timeframe": Timeframe.M1,
            "open": Decimal("45000"),
            "high": Decimal("45100"),
            "low": Decimal("44900"),
            "close": Decimal("45050"),
            "volume": Decimal("100.5"),
        }

    def test_valid_bar_creation(self, valid_bar_data: dict) -> None:
        """Test creating a valid bar."""
        bar = Bar(**valid_bar_data)

        assert bar.symbol == "BTCUSDT"
        assert bar.timeframe == Timeframe.M1
        assert bar.open == Decimal("45000")
        assert bar.high == Decimal("45100")
        assert bar.low == Decimal("44900")
        assert bar.close == Decimal("45050")
        assert bar.volume == Decimal("100.5")

    def test_bar_accepts_string_numbers(self) -> None:
        """Test bar accepts string representations of numbers."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            open="3000",
            high="3100",
            low="2950",
            close="3050",
            volume="500.25",
        )

        assert bar.open == Decimal("3000")
        assert bar.volume == Decimal("500.25")

    def test_bar_accepts_float_numbers(self) -> None:
        """Test bar accepts float representations of numbers."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            open=3000.0,
            high=3100.0,
            low=2950.0,
            close=3050.0,
            volume=500.25,
        )

        assert bar.open == Decimal("3000.0")

    def test_bar_accepts_epoch_timestamp(self) -> None:
        """Test bar accepts epoch seconds as timestamp."""
        epoch = 1700000000.0
        bar = Bar(
            timestamp=epoch,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=45000,
            high=45100,
            low=44900,
            close=45050,
            volume=100,
        )

        assert bar.ts == pytest.approx(epoch)
        assert bar.timestamp.tzinfo is timezone.utc

    def test_bar_normalizes_naive_timestamp_to_utc(self) -> None:
        """Test that naive datetime is converted to UTC."""
        naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        bar = Bar(
            timestamp=naive_dt,
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=45000,
            high=45100,
            low=44900,
            close=45050,
            volume=100,
        )

        assert bar.timestamp.tzinfo is timezone.utc

    def test_bar_symbol_uppercased(self) -> None:
        """Test symbol is automatically uppercased."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="btcusdt",
            timeframe=Timeframe.M1,
            open=45000,
            high=45100,
            low=44900,
            close=45050,
            volume=100,
        )

        assert bar.symbol == "BTCUSDT"

    def test_bar_rejects_negative_price(self) -> None:
        """Test bar rejects negative prices."""
        with pytest.raises(ValidationError, match="price must be positive"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=-1,
                high=100,
                low=50,
                close=75,
                volume=100,
            )

    def test_bar_rejects_zero_price(self) -> None:
        """Test bar rejects zero prices."""
        with pytest.raises(ValidationError, match="price must be positive"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=0,
                high=100,
                low=50,
                close=75,
                volume=100,
            )

    def test_bar_rejects_negative_volume(self) -> None:
        """Test bar rejects negative volume."""
        with pytest.raises(ValidationError, match="volume must be non-negative"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=100,
                high=110,
                low=90,
                close=105,
                volume=-10,
            )

    def test_bar_rejects_high_less_than_low(self) -> None:
        """Test bar rejects high < low."""
        with pytest.raises(ValidationError, match="high price must be >= low"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=100,
                high=80,  # high < low
                low=90,
                close=85,
                volume=100,
            )

    def test_bar_rejects_open_outside_range(self) -> None:
        """Test bar rejects open outside low-high range."""
        with pytest.raises(ValidationError, match="open price must be between"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=200,  # outside range
                high=110,
                low=90,
                close=105,
                volume=100,
            )

    def test_bar_rejects_close_outside_range(self) -> None:
        """Test bar rejects close outside low-high range."""
        with pytest.raises(ValidationError, match="close price must be between"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=100,
                high=110,
                low=90,
                close=50,  # outside range
                volume=100,
            )

    def test_bar_rejects_empty_symbol(self) -> None:
        """Test bar rejects empty symbol."""
        with pytest.raises(
            ValidationError, match="String should have at least 1 character"
        ):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="   ",
                timeframe=Timeframe.M1,
                open=100,
                high=110,
                low=90,
                close=105,
                volume=100,
            )

    def test_bar_rejects_nan_price(self) -> None:
        """Test bar rejects NaN prices."""
        with pytest.raises(ValidationError, match="finite"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=Decimal("NaN"),
                high=110,
                low=90,
                close=105,
                volume=100,
            )

    def test_bar_rejects_infinite_price(self) -> None:
        """Test bar rejects infinite prices."""
        with pytest.raises(ValidationError, match="finite"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=Decimal("Infinity"),
                high=110,
                low=90,
                close=105,
                volume=100,
            )

    def test_bar_rejects_magnitude_exceeding_limit(self) -> None:
        """Test bar rejects values exceeding maximum magnitude."""
        with pytest.raises(ValidationError, match="exceeds maximum magnitude"):
            Bar(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                timeframe=Timeframe.M1,
                open=Decimal("1e20"),
                high=Decimal("1e20"),
                low=Decimal("1e19"),
                close=Decimal("1e20"),
                volume=100,
            )

    def test_bar_with_optional_fields(self) -> None:
        """Test bar with optional trades and vwap fields."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=1000,
            trades=50,
            vwap=102.5,
        )

        assert bar.trades == 50
        assert bar.vwap == Decimal("102.5")

    def test_bar_is_immutable(self) -> None:
        """Test that bar instances are immutable (frozen)."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=100,
        )

        with pytest.raises(ValidationError):
            bar.open = Decimal("200")  # type: ignore

    def test_bar_to_dict(self) -> None:
        """Test bar serialization to dictionary."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=100,
            high=110,
            low=90,
            close=105,
            volume=100,
        )

        data = bar.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["timeframe"] == "1m"
        assert data["open"] == "100"

    def test_candle_is_bar_alias(self) -> None:
        """Test that Candle is an alias for Bar."""
        assert Candle is Bar


# ============================================================================
# Tick Tests
# ============================================================================


class TestTick:
    """Tests for Tick model."""

    def test_valid_tick_creation(self) -> None:
        """Test creating a valid tick."""
        tick = Tick(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            price=Decimal("45000"),
            volume=Decimal("0.5"),
        )

        assert tick.symbol == "BTCUSDT"
        assert tick.price == Decimal("45000")
        assert tick.volume == Decimal("0.5")

    def test_tick_with_side_and_trade_id(self) -> None:
        """Test tick with optional side and trade_id."""
        tick = Tick(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            price=45000,
            volume=0.5,
            side=OrderSide.BUY,
            trade_id="trade123",
        )

        assert tick.side == OrderSide.BUY
        assert tick.trade_id == "trade123"

    def test_tick_rejects_negative_price(self) -> None:
        """Test tick rejects negative price."""
        with pytest.raises(ValidationError, match="price must be positive"):
            Tick(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                price=-1,
                volume=0.5,
            )

    def test_tick_rejects_zero_price(self) -> None:
        """Test tick rejects zero price."""
        with pytest.raises(ValidationError, match="price must be positive"):
            Tick(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                price=0,
                volume=0.5,
            )

    def test_tick_rejects_negative_volume(self) -> None:
        """Test tick rejects negative volume."""
        with pytest.raises(ValidationError, match="volume must be non-negative"):
            Tick(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                price=45000,
                volume=-0.5,
            )

    def test_tick_default_volume_is_zero(self) -> None:
        """Test tick default volume is zero."""
        tick = Tick(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            price=45000,
        )

        assert tick.volume == Decimal("0")

    def test_tick_symbol_uppercased(self) -> None:
        """Test tick symbol is uppercased."""
        tick = Tick(
            timestamp=datetime.now(timezone.utc),
            symbol="btcusdt",
            price=45000,
        )

        assert tick.symbol == "BTCUSDT"


# ============================================================================
# FeatureVector Tests
# ============================================================================


class TestFeatureVector:
    """Tests for FeatureVector model."""

    def test_valid_feature_vector_creation(self) -> None:
        """Test creating a valid feature vector."""
        fv = FeatureVector(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            features={"rsi": 65.0, "macd": 0.5, "momentum": 1.2},
        )

        assert fv.symbol == "BTCUSDT"
        assert fv.features["rsi"] == 65.0
        assert fv.get("macd") == 0.5

    def test_feature_vector_with_metadata(self) -> None:
        """Test feature vector with metadata."""
        fv = FeatureVector(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            features={"rsi": 65.0},
            metadata={"source": "binance", "computed_at": "2024-01-01"},
        )

        assert fv.metadata["source"] == "binance"

    def test_feature_vector_get_with_default(self) -> None:
        """Test feature vector get with default value."""
        fv = FeatureVector(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            features={"rsi": 65.0},
        )

        assert fv.get("rsi") == 65.0
        assert fv.get("nonexistent") is None
        assert fv.get("nonexistent", 0.0) == 0.0

    def test_feature_vector_empty_features(self) -> None:
        """Test feature vector with empty features dict."""
        fv = FeatureVector(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
        )

        assert fv.features == {}


# ============================================================================
# MarketSnapshot Tests
# ============================================================================


class TestMarketSnapshot:
    """Tests for MarketSnapshot model."""

    def test_valid_market_snapshot_creation(self) -> None:
        """Test creating a valid market snapshot."""
        snapshot = MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            last_price=Decimal("45000"),
        )

        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.last_price == Decimal("45000")

    def test_market_snapshot_with_book_data(self) -> None:
        """Test market snapshot with order book data."""
        snapshot = MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            last_price=45000,
            bid=44999,
            ask=45001,
            bid_volume=10.5,
            ask_volume=8.3,
        )

        assert snapshot.bid == Decimal("44999")
        assert snapshot.ask == Decimal("45001")
        assert snapshot.spread == Decimal("2")
        assert snapshot.mid_price == Decimal("45000")

    def test_market_snapshot_rejects_bid_greater_than_ask(self) -> None:
        """Test market snapshot rejects bid > ask."""
        with pytest.raises(ValidationError, match="bid cannot be greater than ask"):
            MarketSnapshot(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                last_price=45000,
                bid=45005,  # > ask
                ask=44995,
            )

    def test_market_snapshot_rejects_negative_bid(self) -> None:
        """Test market snapshot rejects negative bid."""
        with pytest.raises(ValidationError, match="bid must be positive"):
            MarketSnapshot(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                last_price=45000,
                bid=-1,
                ask=45001,
            )

    def test_market_snapshot_rejects_negative_bid_volume(self) -> None:
        """Test market snapshot rejects negative bid volume."""
        with pytest.raises(ValidationError, match="bid_volume must be non-negative"):
            MarketSnapshot(
                timestamp=datetime.now(timezone.utc),
                symbol="BTCUSDT",
                last_price=45000,
                bid=44999,
                ask=45001,
                bid_volume=-5,
            )

    def test_market_snapshot_spread_none_without_book(self) -> None:
        """Test spread is None when bid/ask not available."""
        snapshot = MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            last_price=45000,
        )

        assert snapshot.spread is None
        assert snapshot.mid_price is None

    def test_market_snapshot_with_nested_bar(self) -> None:
        """Test market snapshot with nested bar."""
        bar = Bar(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            timeframe=Timeframe.M1,
            open=44900,
            high=45100,
            low=44850,
            close=45050,
            volume=1000,
        )

        snapshot = MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            last_price=45050,
            last_bar=bar,
        )

        assert snapshot.last_bar is not None
        assert snapshot.last_bar.close == Decimal("45050")

    def test_market_snapshot_with_feature_vector(self) -> None:
        """Test market snapshot with nested feature vector."""
        fv = FeatureVector(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            features={"rsi": 65.0},
        )

        snapshot = MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            last_price=45000,
            features=fv,
        )

        assert snapshot.features is not None
        assert snapshot.features.get("rsi") == 65.0
