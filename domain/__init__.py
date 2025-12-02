"""Domain layer containing core bounded contexts.

The package is organised according to domain-driven design (DDD) principles
with dedicated subpackages for orders, positions, signals, and portfolio.

The unified domain model in :mod:`domain.model` provides the canonical
entities for the decision loop across all execution modes (backtest/paper/live).
"""

from .orders import Order, OrderSide, OrderStatus, OrderType
from .portfolio import (
    CorporateActionRecord,
    CurrencyExposureSnapshot,
    FXRates,
    PortfolioAccounting,
    PortfolioSnapshot,
    PositionSnapshot,
)
from .positions import Position
from .signals import Signal, SignalAction

# Unified domain model types
from .model import (
    # Type aliases
    OrderId,
    StrategyId,
    TradeId,
    SignalId,
    PositionId,
    # ID generators
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

__all__ = [
    # Legacy entities (from subpackages)
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioAccounting",
    "PortfolioSnapshot",
    "Position",
    "PositionSnapshot",
    "Signal",
    "SignalAction",
    "CorporateActionRecord",
    "CurrencyExposureSnapshot",
    "FXRates",
    # Unified domain model - Type aliases
    "OrderId",
    "StrategyId",
    "TradeId",
    "SignalId",
    "PositionId",
    # Unified domain model - ID generators
    "generate_order_id",
    "generate_trade_id",
    "generate_signal_id",
    # Unified domain model - Enums
    "EnvironmentMode",
    "ActionType",
    "SignalDirection",
    "OrderRequestType",
    "ExecutionStatus",
    # Unified domain model - Order entities
    "OrderRequest",
    "OrderExecution",
    "Trade",
    # Unified domain model - Position/Portfolio entities
    "PositionState",
    "PortfolioState",
    # Unified domain model - Strategy entities
    "StrategySignal",
    "StrategyContext",
    "MarketDataSnapshot",
    # Unified domain model - Decision entities
    "ActionDecision",
    # Unified domain model - AAR entities
    "AAREvent",
]
