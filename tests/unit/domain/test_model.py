"""Tests for unified domain model."""

import pytest
from datetime import datetime, timezone, timedelta

from domain.model import (
    # Type aliases and generators
    OrderId,
    StrategyId,
    TradeId,
    SignalId,
    generate_order_id,
    generate_trade_id,
    generate_signal_id,
    # Enums
    EnvironmentMode,
    ActionType,
    SignalDirection,
    OrderRequestType,
    ExecutionStatus,
    # Order entities
    OrderRequest,
    OrderExecution,
    Trade,
    # Position/Portfolio entities
    PositionState,
    PortfolioState,
    # Strategy entities
    StrategySignal,
    StrategyContext,
    MarketDataSnapshot,
    # Decision entities
    ActionDecision,
    # AAR entities
    AAREvent,
)


class TestIdGenerators:
    """Tests for ID generation functions."""

    def test_generate_order_id_is_unique(self) -> None:
        id1 = generate_order_id()
        id2 = generate_order_id()
        assert id1 != id2
        assert id1.startswith("ord_")

    def test_generate_trade_id_is_unique(self) -> None:
        id1 = generate_trade_id()
        id2 = generate_trade_id()
        assert id1 != id2
        assert id1.startswith("trd_")

    def test_generate_signal_id_is_unique(self) -> None:
        id1 = generate_signal_id()
        id2 = generate_signal_id()
        assert id1 != id2
        assert id1.startswith("sig_")


class TestOrderRequest:
    """Tests for OrderRequest entity."""

    def test_valid_market_order(self) -> None:
        order = OrderRequest(
            symbol="BTCUSD",
            side=ActionType.BUY,
            quantity=1.0,
        )
        assert order.symbol == "BTCUSD"
        assert order.side == ActionType.BUY
        assert order.quantity == 1.0
        assert order.order_type == OrderRequestType.MARKET

    def test_valid_limit_order(self) -> None:
        order = OrderRequest(
            symbol="ETHUSD",
            side=ActionType.SELL,
            quantity=2.5,
            order_type=OrderRequestType.LIMIT,
            price=2000.0,
        )
        assert order.price == 2000.0
        assert order.order_type == OrderRequestType.LIMIT

    def test_rejects_zero_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderRequest(symbol="BTCUSD", side=ActionType.BUY, quantity=0.0)

    def test_rejects_negative_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderRequest(symbol="BTCUSD", side=ActionType.BUY, quantity=-1.0)

    def test_limit_order_requires_price(self) -> None:
        with pytest.raises(ValueError, match="limit orders require a price"):
            OrderRequest(
                symbol="BTCUSD",
                side=ActionType.BUY,
                quantity=1.0,
                order_type=OrderRequestType.LIMIT,
            )

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(ValueError, match="price must be positive"):
            OrderRequest(
                symbol="BTCUSD",
                side=ActionType.BUY,
                quantity=1.0,
                order_type=OrderRequestType.LIMIT,
                price=-100.0,
            )

    def test_metadata_is_frozen(self) -> None:
        order = OrderRequest(
            symbol="BTCUSD",
            side=ActionType.BUY,
            quantity=1.0,
            metadata={"key": "value"},
        )
        with pytest.raises(TypeError):
            order.metadata["new_key"] = "new_value"  # type: ignore


class TestOrderExecution:
    """Tests for OrderExecution entity."""

    def test_valid_execution(self) -> None:
        execution = OrderExecution(
            order_id=OrderId("ord_123"),
            symbol="BTCUSD",
            side=ActionType.BUY,
            quantity=1.0,
            price=50000.0,
            fee=5.0,
        )
        assert execution.order_id == "ord_123"
        assert execution.quantity == 1.0
        assert execution.price == 50000.0
        assert execution.fee == 5.0

    def test_rejects_zero_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderExecution(
                order_id=OrderId("ord_123"),
                symbol="BTCUSD",
                side=ActionType.BUY,
                quantity=0.0,
                price=50000.0,
            )

    def test_rejects_zero_price(self) -> None:
        with pytest.raises(ValueError, match="price must be positive"):
            OrderExecution(
                order_id=OrderId("ord_123"),
                symbol="BTCUSD",
                side=ActionType.BUY,
                quantity=1.0,
                price=0.0,
            )

    def test_rejects_negative_fee(self) -> None:
        with pytest.raises(ValueError, match="fee cannot be negative"):
            OrderExecution(
                order_id=OrderId("ord_123"),
                symbol="BTCUSD",
                side=ActionType.BUY,
                quantity=1.0,
                price=50000.0,
                fee=-1.0,
            )


class TestTrade:
    """Tests for Trade entity."""

    def test_valid_open_trade(self) -> None:
        trade = Trade(
            trade_id=TradeId("trd_123"),
            symbol="BTCUSD",
            side=ActionType.BUY,
            entry_price=50000.0,
            quantity=1.0,
        )
        assert trade.trade_id == "trd_123"
        assert trade.entry_price == 50000.0
        assert trade.is_closed is False

    def test_valid_closed_trade(self) -> None:
        now = datetime.now(timezone.utc)
        trade = Trade(
            trade_id=TradeId("trd_123"),
            symbol="BTCUSD",
            side=ActionType.BUY,
            entry_price=50000.0,
            quantity=1.0,
            exit_price=55000.0,
            realized_pnl=5000.0,
            closed_at=now,
        )
        assert trade.is_closed is True
        assert trade.exit_price == 55000.0
        assert trade.realized_pnl == 5000.0

    def test_rejects_negative_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be positive"):
            Trade(
                trade_id=TradeId("trd_123"),
                symbol="BTCUSD",
                side=ActionType.BUY,
                entry_price=50000.0,
                quantity=-1.0,
            )


class TestPositionState:
    """Tests for PositionState entity."""

    def test_flat_position(self) -> None:
        position = PositionState(symbol="BTCUSD")
        assert position.is_flat is True
        assert position.is_long is False
        assert position.is_short is False

    def test_long_position(self) -> None:
        position = PositionState(
            symbol="BTCUSD",
            quantity=1.0,
            entry_price=50000.0,
            current_price=55000.0,
            unrealized_pnl=5000.0,
        )
        assert position.is_long is True
        assert position.is_short is False
        assert position.market_value == 55000.0

    def test_short_position(self) -> None:
        position = PositionState(
            symbol="BTCUSD",
            quantity=-1.0,
            entry_price=50000.0,
            current_price=45000.0,
            unrealized_pnl=5000.0,
        )
        assert position.is_short is True
        assert position.is_long is False

    def test_rejects_missing_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol must be provided"):
            PositionState(symbol="")

    def test_open_position_requires_entry_price(self) -> None:
        with pytest.raises(ValueError, match="entry_price must be positive"):
            PositionState(symbol="BTCUSD", quantity=1.0, entry_price=0.0)


class TestPortfolioState:
    """Tests for PortfolioState entity."""

    def test_empty_portfolio(self) -> None:
        portfolio = PortfolioState(
            cash=10000.0,
            equity=10000.0,
            peak_equity=10000.0,
        )
        assert portfolio.cash == 10000.0
        assert portfolio.drawdown == 0.0
        assert portfolio.net_exposure == 0.0
        assert portfolio.gross_exposure == 0.0

    def test_portfolio_with_positions(self) -> None:
        btc_position = PositionState(
            symbol="BTCUSD",
            quantity=1.0,
            entry_price=50000.0,
            current_price=55000.0,
        )
        portfolio = PortfolioState(
            positions={"BTCUSD": btc_position},
            cash=5000.0,
            equity=60000.0,
            peak_equity=60000.0,
        )
        assert portfolio.position_for("BTCUSD") == btc_position
        assert portfolio.position_for("ETHUSD") is None
        assert portfolio.net_exposure == 55000.0
        assert portfolio.gross_exposure == 55000.0

    def test_drawdown_calculation(self) -> None:
        portfolio = PortfolioState(
            cash=10000.0,
            equity=8000.0,
            peak_equity=10000.0,
        )
        assert portfolio.drawdown == pytest.approx(0.2)

    def test_mixed_positions_exposure(self) -> None:
        long_pos = PositionState(
            symbol="BTCUSD",
            quantity=1.0,
            entry_price=50000.0,
            current_price=50000.0,
        )
        short_pos = PositionState(
            symbol="ETHUSD",
            quantity=-10.0,
            entry_price=2000.0,
            current_price=2000.0,
        )
        portfolio = PortfolioState(
            positions={"BTCUSD": long_pos, "ETHUSD": short_pos},
            cash=10000.0,
            equity=40000.0,
            peak_equity=40000.0,
        )
        # Net: 50000 - 20000 = 30000
        assert portfolio.net_exposure == pytest.approx(30000.0)
        # Gross: 50000 + 20000 = 70000
        assert portfolio.gross_exposure == pytest.approx(70000.0)


class TestStrategySignal:
    """Tests for StrategySignal entity."""

    def test_valid_signal(self) -> None:
        signal = StrategySignal(
            signal_id=SignalId("sig_123"),
            symbol="BTCUSD",
            direction=SignalDirection.LONG,
            strength=0.8,
            confidence=0.9,
            target_position=0.5,
        )
        assert signal.symbol == "BTCUSD"
        assert signal.direction == SignalDirection.LONG
        assert signal.strength == 0.8
        assert signal.confidence == 0.9
        assert signal.target_position == 0.5

    def test_rejects_missing_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol must be provided"):
            StrategySignal(
                signal_id=SignalId("sig_123"),
                symbol="",
                direction=SignalDirection.LONG,
            )

    def test_rejects_invalid_strength(self) -> None:
        with pytest.raises(ValueError, match="strength must be between 0 and 1"):
            StrategySignal(
                signal_id=SignalId("sig_123"),
                symbol="BTCUSD",
                direction=SignalDirection.LONG,
                strength=1.5,
            )

    def test_rejects_invalid_confidence(self) -> None:
        with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
            StrategySignal(
                signal_id=SignalId("sig_123"),
                symbol="BTCUSD",
                direction=SignalDirection.LONG,
                confidence=-0.1,
            )

    def test_rejects_invalid_target_position(self) -> None:
        with pytest.raises(ValueError, match="target_position must be between -1 and 1"):
            StrategySignal(
                signal_id=SignalId("sig_123"),
                symbol="BTCUSD",
                direction=SignalDirection.LONG,
                target_position=2.0,
            )

    def test_signal_expiry(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_signal = StrategySignal(
            signal_id=SignalId("sig_123"),
            symbol="BTCUSD",
            direction=SignalDirection.LONG,
            valid_until=past,
        )
        assert expired_signal.is_expired is True

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        valid_signal = StrategySignal(
            signal_id=SignalId("sig_456"),
            symbol="BTCUSD",
            direction=SignalDirection.LONG,
            valid_until=future,
        )
        assert valid_signal.is_expired is False


class TestMarketDataSnapshot:
    """Tests for MarketDataSnapshot entity."""

    def test_valid_snapshot(self) -> None:
        snapshot = MarketDataSnapshot(
            symbol="BTCUSD",
            bid=49999.0,
            ask=50001.0,
            last=50000.0,
            volume=1000.0,
        )
        assert snapshot.symbol == "BTCUSD"
        assert snapshot.mid == pytest.approx(50000.0)
        assert snapshot.spread == pytest.approx(2.0)

    def test_mid_falls_back_to_last(self) -> None:
        snapshot = MarketDataSnapshot(
            symbol="BTCUSD",
            last=50000.0,
        )
        assert snapshot.mid == 50000.0
        assert snapshot.spread == 0.0


class TestStrategyContext:
    """Tests for StrategyContext entity."""

    def test_valid_context(self) -> None:
        portfolio = PortfolioState(cash=10000.0, equity=10000.0, peak_equity=10000.0)
        market_data = MarketDataSnapshot(symbol="BTCUSD", last=50000.0)
        context = StrategyContext(
            mode=EnvironmentMode.PAPER,
            portfolio=portfolio,
            market_data={"BTCUSD": market_data},
        )
        assert context.mode == EnvironmentMode.PAPER
        assert context.get_market_data("BTCUSD") == market_data
        assert context.get_market_data("ETHUSD") is None

    def test_get_position_from_context(self) -> None:
        btc_position = PositionState(
            symbol="BTCUSD",
            quantity=1.0,
            entry_price=50000.0,
            current_price=50000.0,
        )
        portfolio = PortfolioState(
            positions={"BTCUSD": btc_position},
            cash=10000.0,
            equity=60000.0,
            peak_equity=60000.0,
        )
        context = StrategyContext(
            mode=EnvironmentMode.LIVE,
            portfolio=portfolio,
        )
        assert context.get_position("BTCUSD") == btc_position
        assert context.get_position("ETHUSD") is None


class TestActionDecision:
    """Tests for ActionDecision entity."""

    def test_valid_buy_decision(self) -> None:
        decision = ActionDecision(
            action_id="act_123",
            action_type=ActionType.BUY,
            symbol="BTCUSD",
            quantity=1.0,
            confidence=0.9,
        )
        assert decision.is_entry is True
        assert decision.is_exit is False

    def test_valid_close_decision(self) -> None:
        decision = ActionDecision(
            action_id="act_456",
            action_type=ActionType.CLOSE,
            symbol="BTCUSD",
            quantity=1.0,
        )
        assert decision.is_exit is True
        assert decision.is_entry is False

    def test_hold_decision(self) -> None:
        decision = ActionDecision(
            action_id="act_789",
            action_type=ActionType.HOLD,
            symbol="BTCUSD",
        )
        assert decision.is_entry is False
        assert decision.is_exit is False

    def test_rejects_missing_symbol(self) -> None:
        with pytest.raises(ValueError, match="symbol must be provided"):
            ActionDecision(
                action_id="act_123",
                action_type=ActionType.BUY,
                symbol="",
            )

    def test_rejects_negative_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity cannot be negative"):
            ActionDecision(
                action_id="act_123",
                action_type=ActionType.BUY,
                symbol="BTCUSD",
                quantity=-1.0,
            )


class TestAAREvent:
    """Tests for AAREvent entity."""

    def test_valid_aar_event(self) -> None:
        event = AAREvent(
            action_id="act_123",
            prediction=100.0,
            outcome=110.0,
            error=10.0,
            error_sign=1,
            error_magnitude=0.1,
        )
        assert event.action_id == "act_123"
        assert event.error == 10.0
        assert event.error_sign == 1

    def test_from_prediction_outcome_positive(self) -> None:
        event = AAREvent.from_prediction_outcome(
            action_id="act_123",
            prediction=100.0,
            outcome=110.0,
        )
        assert event.error == 10.0
        assert event.error_sign == 1  # outcome > prediction = better
        assert event.error_magnitude > 0

    def test_from_prediction_outcome_negative(self) -> None:
        event = AAREvent.from_prediction_outcome(
            action_id="act_456",
            prediction=100.0,
            outcome=90.0,
        )
        assert event.error == -10.0
        assert event.error_sign == -1  # outcome < prediction = worse
        assert event.error_magnitude > 0

    def test_from_prediction_outcome_equal(self) -> None:
        event = AAREvent.from_prediction_outcome(
            action_id="act_789",
            prediction=100.0,
            outcome=100.0,
        )
        assert event.error == pytest.approx(0.0)
        assert event.error_sign == 0

    def test_rejects_invalid_error_sign(self) -> None:
        with pytest.raises(ValueError, match="error_sign must be -1, 0, or 1"):
            AAREvent(
                action_id="act_123",
                error_sign=2,
            )

    def test_rejects_negative_error_magnitude(self) -> None:
        with pytest.raises(ValueError, match="error_magnitude cannot be negative"):
            AAREvent(
                action_id="act_123",
                error_magnitude=-0.5,
            )
