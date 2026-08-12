# Execution

The execution layer converts strategy intentions into orders while enforcing
risk controls. GeoSync currently provides thin utility functions for sizing
positions and estimating aggregate risk; these utilities are intended to be
wrapped by exchange adapters or execution daemons.

---

## Order Model

```python
from execution.order import Order

order = Order(side="buy", qty=0.5, price=25_000.0, type="limit")
```

- `side` – direction (`"buy"` or `"sell"`).
- `qty` – base-asset quantity.
- `price` – optional limit price; leave `None` for market orders.
- `type` – order type label; defaults to `"market"`. 【F:execution/order.py†L1-L11】

The dataclass can be extended with venue-specific metadata (time-in-force,
client IDs) when integrating with real exchanges.

---

## Position Sizing

`execution.order.position_sizing(balance, risk, price, max_leverage=5.0)` returns
risk-aware quantity in base units:

1. Validates that `price` is positive.
2. Caps `risk` between 0 and 1 (fraction of account equity to deploy).
3. Limits exposure by both the risk budget (`balance * risk / price`) and the
   leverage ceiling (`balance * max_leverage / price`).
4. Returns the minimum of those limits, floored at zero. 【F:execution/order.py†L13-L23】

Example:

```python
from execution.order import position_sizing

size = position_sizing(balance=25_000, risk=0.02, price=20_000, max_leverage=3.0)
# -> 0.75 BTC equivalent
```

---

## Portfolio Heat

`execution.risk.portfolio_heat(positions)` computes aggregate notional exposure
with optional directionality and risk weights. It expects each position mapping
(`dict` or similar) to contain:

- `qty` – signed or absolute quantity
- `price` – entry price
- `risk_weight` – multiplier for instrument-specific scaling (defaults to 1.0)
- `side` – `"long"` or `"short"` to inject direction into the heat total

The helper iterates through positions, multiplies `qty * price * risk_weight`,
adjusts sign based on `side`, and accumulates the absolute contribution. 【F:execution/risk.py†L1-L18】

```python
from execution.risk import portfolio_heat

positions = [
    {"side": "long", "qty": 1.2, "price": 30_000, "risk_weight": 0.8},
    {"side": "short", "qty": 0.5, "price": 25_000, "risk_weight": 1.2},
]
heat = portfolio_heat(positions)
```

Use the resulting scalar to enforce account-level limits or trigger staged
liquidations when exposure exceeds policy thresholds.

---

## Implementation Notes

- Layer venue integrations on top of these primitives so that deterministic
  behaviour in tests is preserved.
- Validate upstream strategy outputs before forwarding to exchanges—e.g., check
  that `PiAgent` actions map cleanly to order intents.
- Extend this guide whenever new adapters (FIX, REST, websockets) or risk checks
  (e.g., pre-trade credit, margin requirements) are added.

---

## Execution Quality Analytics

The `analytics.execution_quality` module captures post-trade diagnostics such as
implementation shortfall, VWAP slippage, and fill efficiency. Use these helpers
to quantify execution drift versus a benchmark or arrival price:

```python
from analytics.execution_quality import (
    FillSample,
    implementation_shortfall,
    vwap_slippage,
    fill_rate,
)

fills = [
    FillSample(quantity=1.0, price=100.5),
    FillSample(quantity=0.5, price=100.8, fees=0.15),
]

shortfall = implementation_shortfall("buy", arrival_price=100.0, fills=fills)
slippage = vwap_slippage("buy", benchmark_price=99.8, fills=fills)
fill = fill_rate(target_quantity=2.0, fills=fills)
```

- `implementation_shortfall` normalises by side so that positive numbers always
  represent underperformance relative to the arrival price and includes fees in
  the realised outcome. 【F:analytics/execution_quality.py†L36-L73】
- `vwap_slippage` compares the realised VWAP to a benchmark, again adjusting for
  side. 【F:analytics/execution_quality.py†L76-L97】
- `fill_rate` reports the executed fraction of the order target. 【F:analytics/execution_quality.py†L100-L109】
- `cancel_replace_latency` summarises cancel/replace turnaround times to spot
  venue microstructure issues. 【F:analytics/execution_quality.py†L112-L133】

These metrics can be exported to observability pipelines or regression tests to
ensure routing changes do not degrade quality.

---

## Venue Compliance Monitoring

`execution.compliance.ComplianceMonitor` wraps `SymbolNormalizer` to enforce lot
size, tick size, and minimum notional requirements prior to submission:

```python
from execution.compliance import ComplianceMonitor
from execution.normalization import SymbolNormalizer, SymbolSpecification

normalizer = SymbolNormalizer(specifications={
    "BTCUSDT": SymbolSpecification(symbol="BTCUSDT", min_qty=0.001, step_size=0.001, min_notional=5.0)
})

monitor = ComplianceMonitor(normalizer, strict=True, auto_round=True)
report = monitor.check("BTCUSDT", quantity=0.00125, price=26850.0)
```

- When `auto_round=True`, quantities and prices are rounded to the nearest
  exchange increment prior to validation. 【F:execution/compliance.py†L35-L47】
- Violations raise `ComplianceViolation` when `strict=True`, guaranteeing that
  orders breaching minimums are blocked before hitting the wire. 【F:execution/compliance.py†L23-L67】
- The returned `ComplianceReport` retains both the requested and normalised
  values so execution services can log discrepancies for QA. 【F:execution/compliance.py†L26-L67】

Leverage this monitor alongside throttles in `RiskManager` to keep order flow
inside venue guardrails.

---

## Circuit Breaker Protection

All exchange adapters built on `RESTWebSocketConnector` include automatic circuit
breaker protection to prevent cascade failures during exchange outages. The circuit
breaker monitors request failures and automatically opens when failure thresholds
are exceeded.

### Circuit Breaker States

- **CLOSED** – Normal operation; all requests are allowed
- **OPEN** – Too many failures detected; requests are blocked to prevent cascade failures
- **HALF_OPEN** – Recovery period; limited requests allowed to test if service recovered

### Configuration

Circuit breaker behavior can be customized via `CircuitBreakerConfig`:

```python
from execution.adapters.binance import BinanceRESTConnector
from execution.resilience.circuit_breaker import CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,        # Open after 5 consecutive failures
    recovery_timeout=30.0,      # Wait 30s before attempting recovery
    half_open_max_calls=3,      # Allow 3 test calls in HALF_OPEN state
)

connector = BinanceRESTConnector(
    sandbox=False,
    circuit_breaker_config=config
)
```

### Monitoring Circuit Breaker State

```python
# Get current state
state = connector.get_circuit_breaker_state()  # CLOSED, OPEN, or HALF_OPEN

# Get detailed metrics
metrics = connector.get_circuit_breaker_metrics()
# Returns:
# {
#   "state": "closed",
#   "failure_rate": 0.05,
#   "time_until_recovery": 0.0,
#   "last_trip_reason": None
# }

# Manual reset (administrative use only)
connector.reset_circuit_breaker()
```

### Failure Detection

The circuit breaker records failures for:
- HTTP 500-599 server errors
- HTTP 429 rate limit responses
- Network timeouts and connection errors
- Request exceptions

Successful responses (2xx status codes) are recorded as successes and help the
circuit breaker transition from HALF_OPEN back to CLOSED state.

【F:execution/adapters/base.py†L27-L30,L153-L155,L276-L285,L441-L460】
【F:execution/resilience/circuit_breaker.py†L41-L160】
