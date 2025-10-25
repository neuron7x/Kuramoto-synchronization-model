---
owner: integrations@tradepulse
review_cadence: quarterly
last_reviewed: 2025-10-25
links:
  - docs/api/overview.md
  - docs/api/webhooks.md
---

# Integration API Reference

This document provides a comprehensive reference for integrating TradePulse with external systems, exchanges, and data providers.

---

## Table of Contents

- [Overview](#overview)
- [Core Interfaces](#core-interfaces)
- [Data Ingestion API](#data-ingestion-api)
- [Execution API](#execution-api)
- [Strategy API](#strategy-api)
- [Metrics API](#metrics-api)
- [WebSocket API](#websocket-api)
- [REST API](#rest-api)
- [gRPC API](#grpc-api)

---

## Overview

TradePulse provides multiple integration points for connecting with external systems:

- **Data Ingestion**: Connect market data providers
- **Execution**: Route orders to exchanges
- **Strategy**: Implement custom trading logic
- **Metrics**: Export performance data
- **APIs**: REST, WebSocket, and gRPC interfaces

### Integration Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│  Data       │─────>│  TradePulse  │─────>│  Execution  │
│  Sources    │      │    Core      │      │  Adapters   │
└─────────────┘      └──────────────┘      └─────────────┘
      │                     │                      │
      │                     ▼                      │
      │              ┌──────────────┐              │
      │              │  Strategy    │              │
      │              │  Engine      │              │
      │              └──────────────┘              │
      │                     │                      │
      ▼                     ▼                      ▼
┌─────────────────────────────────────────────────────┐
│              Metrics & Monitoring                    │
└─────────────────────────────────────────────────────┘
```

---

## Core Interfaces

### Ticker Interface

Market data ticks are represented by immutable Pydantic models so every
ingestion path enforces the same validation (strict decimals, UTC timestamps,
and instrument metadata):

```python
from datetime import datetime, timezone
from decimal import Decimal

from core.data.models import MarketMetadata, Ticker

metadata = MarketMetadata(symbol="BTCUSD", venue="BINANCE")
tick = Ticker(
    metadata=metadata,
    timestamp=datetime.now(timezone.utc),
    price=Decimal("50000"),
    volume=Decimal("0.5"),
)

assert tick.kind.value == "tick"
assert tick.timestamp.tzinfo is timezone.utc

# Convenience helper for legacy style construction
tick = Ticker.create(
    symbol="BTCUSD",
    venue="BINANCE",
    price=50000.0,
    volume=0.5,
    timestamp=datetime.now(timezone.utc),
)
```

### Order Interface

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class OrderSide(Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    """Trading order.
    
    Attributes:
        symbol: Trading symbol
        side: Buy or sell
        order_type: Market, limit, stop, etc.
        quantity: Order quantity
        price: Limit price (for limit orders)
        stop_price: Stop price (for stop orders)
        order_id: Unique order identifier
        status: Current order status
        filled_quantity: Amount filled
        average_price: Average fill price
        
    Example:
        >>> order = Order(
        ...     symbol="BTCUSD",
        ...     side=OrderSide.BUY,
        ...     order_type=OrderType.LIMIT,
        ...     quantity=0.1,
        ...     price=50000.0
        ... )
    """
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
```

### Position Interface

```python
@dataclass
class Position:
    """Trading position.
    
    Attributes:
        symbol: Trading symbol
        quantity: Position size (positive=long, negative=short)
        entry_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss
        
    Example:
        >>> position = Position(
        ...     symbol="BTCUSD",
        ...     quantity=0.5,
        ...     entry_price=48000.0,
        ...     current_price=50000.0,
        ...     unrealized_pnl=1000.0
        ... )
    """
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
```

---

## Data Ingestion API

### DataSource Interface

Implement this interface to connect custom data sources:

```python
from abc import ABC, abstractmethod
from typing import Callable

class DataSource(ABC):
    """Base class for data sources.
    
    Subclass this to implement custom data sources.
    """
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to data source.
        
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source."""
        pass
    
    @abstractmethod
    def subscribe(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> None:
        """Subscribe to symbol updates.
        
        Args:
            symbol: Trading symbol to subscribe to
            callback: Function called on each tick
        """
        pass
    
    @abstractmethod
    def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from symbol updates.
        
        Args:
            symbol: Trading symbol to unsubscribe from
        """
        pass
```

### Example: CSV Data Source

```python
import pandas as pd
from datetime import datetime, timezone
from core.data.ingestion import DataSource, Ticker

class CSVDataSource(DataSource):
    """CSV file data source for backtesting.
    
    Args:
        filepath: Path to CSV file
        time_column: Name of timestamp column (default: "timestamp")
        price_column: Name of price column (default: "close")
        volume_column: Name of volume column (default: "volume")
    
    Example:
        >>> source = CSVDataSource("data.csv")
        >>> source.connect()
        >>> source.subscribe("BTCUSD", lambda tick: print(tick.price))
        >>> source.replay()
    """
    
    def __init__(
        self,
        filepath: str,
        time_column: str = "timestamp",
        price_column: str = "close",
        volume_column: str = "volume"
    ):
        self.filepath = filepath
        self.time_column = time_column
        self.price_column = price_column
        self.volume_column = volume_column
        self.df = None
        self.callbacks = {}
    
    def connect(self) -> None:
        """Load CSV file."""
        self.df = pd.read_csv(self.filepath)
        
        # Parse timestamps
        if self.time_column in self.df.columns:
            self.df[self.time_column] = pd.to_datetime(
                self.df[self.time_column]
            )
    
    def disconnect(self) -> None:
        """Clean up resources."""
        self.df = None
        self.callbacks.clear()
    
    def subscribe(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> None:
        """Register callback for symbol."""
        self.callbacks[symbol] = callback
    
    def unsubscribe(self, symbol: str) -> None:
        """Remove callback for symbol."""
        self.callbacks.pop(symbol, None)
    
    def replay(self, symbol: str = "SYMBOL") -> None:
        """Replay historical data.
        
        Args:
            symbol: Symbol name for ticks
        """
        if symbol not in self.callbacks:
            raise ValueError(f"No callback registered for {symbol}")
        
        callback = self.callbacks[symbol]
        
        for _, row in self.df.iterrows():
            tick = Ticker.create(
                symbol=symbol,
                venue=self.source.upper(),
                price=float(row[self.price_column]),
                volume=float(row.get(self.volume_column, 0.0)),
                timestamp=row[self.time_column] if self.time_column in row else datetime.now(timezone.utc),
            )
            callback(tick)
```

---

## Execution API

### ExecutionAdapter Interface

Implement this to connect to exchanges:

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class ExecutionAdapter(ABC):
    """Base class for execution adapters.
    
    Subclass this to implement exchange connectors.
    """
    
    @abstractmethod
    def connect(self, credentials: dict) -> None:
        """Connect to exchange.
        
        Args:
            credentials: API keys and secrets
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from exchange."""
        pass
    
    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Place an order.
        
        Args:
            order: Order to place
            
        Returns:
            Order with assigned order_id and status
            
        Raises:
            OrderError: If order placement fails
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.
        
        Args:
            order_id: Order to cancel
            
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """Get order status.
        
        Args:
            order_id: Order to query
            
        Returns:
            Order with current status
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get all open positions.
        
        Returns:
            List of open positions
        """
        pass
    
    @abstractmethod
    def get_balance(self) -> dict:
        """Get account balance.
        
        Returns:
            Dictionary with balance by currency
        """
        pass
```

### Example: Binance Execution Adapter

```python
from binance.client import Client
from binance.exceptions import BinanceAPIException
from execution.order import ExecutionAdapter, Order, OrderSide, OrderType

class BinanceAdapter(ExecutionAdapter):
    """Binance exchange adapter.
    
    Args:
        testnet: Use testnet instead of production
    
    Example:
        >>> adapter = BinanceAdapter(testnet=True)
        >>> adapter.connect({
        ...     "api_key": "your_key",
        ...     "api_secret": "your_secret"
        ... })
        >>> order = Order(
        ...     symbol="BTCUSDT",
        ...     side=OrderSide.BUY,
        ...     order_type=OrderType.MARKET,
        ...     quantity=0.001
        ... )
        >>> result = adapter.place_order(order)
    """
    
    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.client = None
    
    def connect(self, credentials: dict) -> None:
        """Connect to Binance."""
        self.client = Client(
            credentials["api_key"],
            credentials["api_secret"],
            testnet=self.testnet
        )
    
    def disconnect(self) -> None:
        """Disconnect from Binance."""
        self.client = None
    
    def place_order(self, order: Order) -> Order:
        """Place order on Binance."""
        try:
            # Convert to Binance format
            side = "BUY" if order.side == OrderSide.BUY else "SELL"
            
            if order.order_type == OrderType.MARKET:
                result = self.client.create_order(
                    symbol=order.symbol,
                    side=side,
                    type="MARKET",
                    quantity=order.quantity
                )
            elif order.order_type == OrderType.LIMIT:
                result = self.client.create_order(
                    symbol=order.symbol,
                    side=side,
                    type="LIMIT",
                    timeInForce="GTC",
                    quantity=order.quantity,
                    price=order.price
                )
            else:
                raise ValueError(f"Unsupported order type: {order.order_type}")
            
            # Update order with result
            order.order_id = str(result["orderId"])
            order.status = OrderStatus.OPEN
            
            return order
            
        except BinanceAPIException as e:
            raise OrderError(f"Binance order failed: {e}")
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order on Binance."""
        try:
            self.client.cancel_order(orderId=int(order_id))
            return True
        except BinanceAPIException:
            return False
    
    def get_positions(self) -> List[Position]:
        """Get positions from Binance."""
        account = self.client.get_account()
        positions = []
        
        for balance in account["balances"]:
            if float(balance["free"]) > 0 or float(balance["locked"]) > 0:
                # Convert balance to position
                # (simplified - real implementation needs price data)
                pass
        
        return positions
    
    def get_balance(self) -> dict:
        """Get account balance."""
        account = self.client.get_account()
        return {
            b["asset"]: float(b["free"]) + float(b["locked"])
            for b in account["balances"]
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        }
```

---

## Strategy API

### Strategy Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
import numpy as np

@dataclass
class Signal:
    """Trading signal.
    
    Attributes:
        action: 'buy', 'sell', or 'hold'
        confidence: Confidence level (0.0 to 1.0)
        metadata: Additional signal information
    """
    action: str
    confidence: float
    metadata: Dict[str, Any]

class Strategy(ABC):
    """Base strategy interface."""
    
    @abstractmethod
    def generate_signal(
        self,
        prices: np.ndarray,
        indicators: Dict[str, float]
    ) -> Signal:
        """Generate trading signal.
        
        Args:
            prices: Historical price data
            indicators: Pre-computed indicators
            
        Returns:
            Trading signal with action and confidence
        """
        pass
```

See [Extending TradePulse](extending.md) for detailed strategy implementation examples.

### End-to-end orchestration helper

TradePulse ships with :class:`TradePulseOrchestrator`, a high-level façade that
assembles ingestion, feature engineering, strategy execution, and live order
submission behind a single interface. This makes it straightforward to stitch
the Python analytics loop to UI or API layers without rewriting the wiring in
every service.

```python
from pathlib import Path
import numpy as np

from application.system_orchestrator import (
    ExecutionRequest,
    MarketDataSource,
    TradePulseOrchestrator,
    build_tradepulse_system,
)

data_root = Path("data")
system = build_tradepulse_system(allowed_data_roots=[data_root])
orchestrator = TradePulseOrchestrator(system)

source = MarketDataSource(
    path=data_root / "sample.csv",
    symbol="BTCUSDT",
    venue="BINANCE",
)

def momentum_strategy(prices: np.ndarray) -> np.ndarray:
    window = 10
    rolling = np.convolve(prices, np.ones(window) / window, mode="valid")
    padded = np.concatenate([np.repeat(rolling[0], window - 1), rolling])
    return np.where(prices >= padded, 1.0, -1.0)

run = orchestrator.run_strategy(source, strategy=momentum_strategy)

# Forward the latest signal to the simulated Binance connector
orchestrator.ensure_live_loop()
order = orchestrator.submit_signal(
    ExecutionRequest(
        signal=run.signals[-1],
        venue="binance",
        quantity=0.1,
        price=float(run.feature_frame[system.feature_pipeline.config.price_col].iloc[-1]),
    )
)

print(order.order_id, order.side, order.quantity)
```

The orchestrator exposes the resulting pandas frames and signal payloads so
callers can pipe analytics into dashboards, persistence layers, or downstream
services using the documented integration contracts.

---

## Metrics API

### Performance Metrics

```python
from core.metrics import (
    sharpe_ratio,
    max_drawdown,
    win_rate,
    profit_factor
)

# Calculate metrics from trades
returns = np.array([0.01, -0.02, 0.03, 0.01, -0.01])

sharpe = sharpe_ratio(returns, risk_free_rate=0.02)
max_dd = max_drawdown(returns)
win_pct = win_rate(returns)
pf = profit_factor(returns)

print(f"Sharpe: {sharpe:.2f}")
print(f"Max Drawdown: {max_dd:.2%}")
print(f"Win Rate: {win_pct:.2%}")
print(f"Profit Factor: {pf:.2f}")
```

---

## WebSocket API

### Real-time Updates

```python
import asyncio
import websockets
import json

async def tradepulse_websocket():
    """Connect to TradePulse WebSocket for real-time updates."""
    uri = "ws://localhost:8080/ws"
    
    async with websockets.connect(uri) as websocket:
        # Subscribe to updates
        await websocket.send(json.dumps({
            "action": "subscribe",
            "channels": ["trades", "positions", "signals"]
        }))
        
        # Receive updates
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data}")

# Run
asyncio.run(tradepulse_websocket())
```

---

## REST API

### Endpoints

#### Get System Status
```http
GET /api/v1/status
```

Response:
```json
{
  "status": "running",
  "uptime_seconds": 3600,
  "version": "1.0.0"
}
```

#### Get Positions
```http
GET /api/v1/positions
```

Response:
```json
{
  "positions": [
    {
      "symbol": "BTCUSD",
      "quantity": 0.5,
      "entry_price": 48000.0,
      "current_price": 50000.0,
      "unrealized_pnl": 1000.0
    }
  ]
}
```

#### Place Order
```http
POST /api/v1/orders
Content-Type: application/json

{
  "symbol": "BTCUSD",
  "side": "buy",
  "order_type": "market",
  "quantity": 0.1
}
```

Response:
```json
{
  "order_id": "12345",
  "status": "filled",
  "filled_quantity": 0.1,
  "average_price": 50000.0
}
```

---

## gRPC API

### Protocol Buffers Definition

```protobuf
// market/v1/market.proto
syntax = "proto3";

package market.v1;

message Ticker {
  string symbol = 1;
  double price = 2;
  double volume = 3;
  int64 timestamp = 4;
}

message Order {
  string symbol = 1;
  string side = 2;  // "buy" or "sell"
  string order_type = 3;  // "market" or "limit"
  double quantity = 4;
  double price = 5;
}

message OrderResponse {
  string order_id = 1;
  string status = 2;
  double filled_quantity = 3;
  double average_price = 4;
}

service TradingService {
  rpc PlaceOrder(Order) returns (OrderResponse);
  rpc CancelOrder(OrderID) returns (CancelResponse);
  rpc GetPositions(Empty) returns (PositionList);
  rpc StreamTickers(SymbolList) returns (stream Ticker);
}
```

### gRPC Client Example

```python
import grpc
from market.v1 import market_pb2, market_pb2_grpc

# Connect to gRPC server
channel = grpc.insecure_channel('localhost:50051')
stub = market_pb2_grpc.TradingServiceStub(channel)

# Place order
order = market_pb2.Order(
    symbol="BTCUSD",
    side="buy",
    order_type="market",
    quantity=0.1
)
response = stub.PlaceOrder(order)
print(f"Order ID: {response.order_id}")

# Stream tickers
symbols = market_pb2.SymbolList(symbols=["BTCUSD", "ETHUSD"])
for ticker in stub.StreamTickers(symbols):
    print(f"{ticker.symbol}: {ticker.price}")
```

---

## Error Handling

### Error Types

```python
class TradePulseError(Exception):
    """Base exception for TradePulse."""
    pass

class ConnectionError(TradePulseError):
    """Data source or exchange connection error."""
    pass

class OrderError(TradePulseError):
    """Order placement or management error."""
    pass

class ValidationError(TradePulseError):
    """Input validation error."""
    pass

class InsufficientDataError(TradePulseError):
    """Insufficient historical data for calculation."""
    pass
```

### Error Handling Example

```python
from core.data.ingestion import DataSource, ConnectionError
import logging

logger = logging.getLogger(__name__)

def connect_with_retry(source: DataSource, max_retries: int = 3):
    """Connect to data source with retries."""
    for attempt in range(max_retries):
        try:
            source.connect()
            logger.info("Connected successfully")
            return
        except ConnectionError as e:
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
```

---

## Authentication

### API Key Authentication

```python
from dataclasses import dataclass

@dataclass
class Credentials:
    """API credentials."""
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None

# Usage
creds = Credentials(
    api_key="your_api_key",
    api_secret="your_api_secret"
)

adapter = ExchangeAdapter()
adapter.connect(creds.__dict__)
```

### Environment Variables

```bash
# .env file
EXCHANGE_API_KEY=your_api_key
EXCHANGE_API_SECRET=your_api_secret
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

credentials = {
    "api_key": os.getenv("EXCHANGE_API_KEY"),
    "api_secret": os.getenv("EXCHANGE_API_SECRET")
}
```

---

## Rate Limiting

```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=10, period=60)  # 10 calls per minute
def api_call():
    """Rate-limited API call."""
    pass
```

---

## Best Practices

1. **Error Handling**: Always handle connection failures and API errors
2. **Rate Limiting**: Respect exchange rate limits
3. **Logging**: Log all API interactions for debugging
4. **Retries**: Implement exponential backoff for transient failures
5. **Validation**: Validate all inputs before API calls
6. **Testing**: Test with paper trading before live trading
7. **Monitoring**: Monitor API latency and error rates
8. **Security**: Never commit API keys; use environment variables

---

## Examples

See [examples/integrations/](../examples/integrations/) for complete examples:
- Exchange connectors (Binance, Coinbase, etc.)
- Data providers (IEX, Alpha Vantage, etc.)
- Custom strategies
- API usage patterns

---

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [API Documentation](https://docs.tradepulse.local)
- [Examples Repository](../examples/)

---

**Last Updated**: 2025-01-01
