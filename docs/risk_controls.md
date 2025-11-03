# Risk Controls

This document describes the risk control system implemented in TradePulse, including pre-trade compliance checks, circuit breaker protection, kill-switch functionality, and observability.

## Overview

The risk control system provides hard guardrails to prevent excessive losses and manage trading risk. It enforces multiple layers of protection:

1. **Kill Switch** - Global emergency stop for all trading
2. **Pre-Trade Risk Checks** - Order-level validation before submission
3. **Circuit Breaker** - Automatic trading halt after repeated failures
4. **Exposure Limits** - Position and notional caps per symbol and portfolio
5. **Drawdown Protection** - Daily loss limit enforcement

## Architecture

```
Order Submission
    ↓
ComplianceMonitor (venue rules)
    ↓
Circuit Breaker Check
    ↓
RiskCompliance Check
    ↓
RiskController.validate_order()
    ↓
Order Queue
    ↓
Exchange
```

## Components

### 1. RiskCompliance (`execution/compliance.py`)

The `RiskCompliance` class performs comprehensive pre-trade checks:

#### Configuration

```python
from execution.compliance import RiskCompliance, RiskConfig

config = RiskConfig(
    kill_switch=False,
    max_notional_per_order=50000.0,
    per_symbol_position_cap_type="units",
    per_symbol_position_cap_default=10.0,
    per_symbol_position_cap_overrides={"BTC/USD": 5.0},
    max_gross_exposure=150000.0,
    daily_max_drawdown_mode="percent",
    daily_max_drawdown_threshold=0.10,  # 10%
    max_open_orders_per_account=100,
)

compliance = RiskCompliance(config)
```

#### Checks Performed

- **Kill Switch**: Blocks all orders when enabled
- **Max Notional Per Order**: Blocks orders exceeding `abs(price * qty)` limit
- **Per-Symbol Position Cap**: Limits position size per symbol (units or notional)
- **Max Gross Exposure**: Limits total `sum(|position_notional|)` across portfolio
- **Daily Max Drawdown**: Blocks trading when daily loss exceeds threshold
- **Max Open Orders**: Prevents order flood by limiting concurrent orders

#### Usage

```python
from domain import Order, OrderSide

order = Order(
    symbol="BTC/USD",
    side=OrderSide.BUY,
    quantity=1.0,
    price=50000.0,
)

market_data = {"price": 50000.0}
portfolio_state = {
    "positions": {"BTC/USD": 0.5},
    "gross_exposure": 75000.0,
    "equity": 100000.0,
    "peak_equity": 110000.0,
}

decision = compliance.check_order(order, market_data, portfolio_state)

if not decision.allowed:
    print(f"Order blocked: {'; '.join(decision.reasons)}")
    print(f"Breached limits: {decision.breached_limits}")
else:
    # Proceed with order
    pass
```

### 2. Circuit Breaker (`execution/resilience/circuit_breaker.py`)

The circuit breaker automatically halts trading after detecting repeated failures or risk breaches.

#### States

- **CLOSED** - Normal operation, orders allowed
- **OPEN** - Trading halted, orders blocked
- **HALF_OPEN** - Recovery mode, limited orders allowed for testing

#### Configuration

```python
from execution.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=600.0,  # 10 minutes
    half_open_max_calls=3,
    breaches_threshold=5,
    breaches_window_seconds=300.0,  # 5 minutes
)

breaker = CircuitBreaker(config)
```

#### Usage

```python
# Check before executing
if not breaker.can_execute():
    reason = breaker.get_last_trip_reason()
    ttl = breaker.get_time_until_recovery()
    raise Exception(f"Circuit breaker OPEN: {reason}. Recovery in {ttl:.0f}s")

try:
    # Execute operation
    result = execute_order(order)
    breaker.record_success()
except Exception as e:
    breaker.record_failure()
    breaker.record_risk_breach(str(e))
    raise
```

### 3. Admin API (`admin/api.py`)

Secure REST API for risk control operations.

#### Endpoints

**POST /admin/risk/kill_switch**

Toggle the global kill switch:

```bash
curl -X POST https://api.tradepulse.example.com/admin/risk/kill_switch \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'
```

Response:
```json
{
  "success": true,
  "kill_switch": true,
  "message": "Kill switch enabled"
}
```

**GET /admin/risk/state**

Retrieve current risk state:

```bash
curl https://api.tradepulse.example.com/admin/risk/state \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN'
```

Response:
```json
{
  "kill_switch": false,
  "max_notional_per_order": 50000.0,
  "max_gross_exposure": 150000.0,
  "daily_max_drawdown_threshold": 0.10,
  "daily_max_drawdown_mode": "percent",
  "daily_high_equity": 110000.0,
  "last_trip_reason": null,
  "last_trip_time": null,
  "open_orders_count": 5,
  "timestamp": "2025-11-03T14:30:00.000Z",
  "circuit_breaker_state": "closed",
  "circuit_breaker_ttl": 0.0,
  "circuit_breaker_last_trip": null
}
```

#### Authentication

Set the admin token via environment variable:

```bash
export ADMIN_API_TOKEN="your-secret-token-here"
```

**IMPORTANT:** Never commit secrets to the repository. Use a secure secret store in production.

## Configuration

### YAML Configuration (`configs/risk.yaml`)

```yaml
risk:
  kill_switch: false
  max_notional_per_order: 50000
  
  per_symbol_position_cap:
    type: units  # or 'notional'
    default: 10
    overrides:
      BTC/USD: 5
      ETH/USD: 50
  
  max_gross_exposure: 150000
  
  daily_max_drawdown:
    mode: percent  # or 'notional'
    threshold: 0.10
    window: daily
  
  max_open_orders_per_account: 100
  
  circuit_breaker:
    breaches_threshold: 5
    window_seconds: 300
    cool_down_seconds: 600
    half_open_max_calls: 3
```

### Environment Variable Overrides

Override configuration at runtime:

```bash
export RISK_KILL_SWITCH=true
export RISK_MAX_NOTIONAL_PER_ORDER=100000
export RISK_MAX_GROSS_EXPOSURE=200000
export RISK_DAILY_MAX_DRAWDOWN_THRESHOLD=0.15
```

## Integration with OMS

The `OrderManagementSystem` integrates risk controls in the order submission flow:

```python
from execution.oms import OrderManagementSystem, OMSConfig
from execution.compliance import RiskCompliance, RiskConfig
from execution.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

# Create risk components
risk_config = RiskConfig(...)
risk_compliance = RiskCompliance(risk_config)

breaker_config = CircuitBreakerConfig(...)
circuit_breaker = CircuitBreaker(breaker_config)

# Create OMS with risk controls
oms = OrderManagementSystem(
    connector=connector,
    risk_controller=risk_controller,
    config=oms_config,
    risk_compliance=risk_compliance,
    circuit_breaker=circuit_breaker,
)

# Submit order - will be validated by risk checks
try:
    order = oms.submit(order, correlation_id="trade-123")
    oms.process_next()
except ComplianceViolation as e:
    print(f"Order rejected: {e}")
```

## Observability

### Prometheus Metrics

The system exports metrics for monitoring:

**Gauges:**
- `tradepulse_risk_kill_switch{env}` - Kill switch state (0=off, 1=on)
- `tradepulse_risk_gross_exposure{env}` - Current gross exposure
- `tradepulse_risk_daily_drawdown{env,mode}` - Current daily drawdown
- `tradepulse_risk_circuit_state{state}` - Circuit breaker state
- `tradepulse_risk_open_orders{env}` - Current open orders count

**Counters:**
- `tradepulse_risk_rejections_total{reason}` - Total rejections by reason
- `tradepulse_risk_circuit_trips_total{reason}` - Total circuit breaker trips

### Structured Logging

Risk events are logged in JSON format:

```json
{
  "event": "risk_check",
  "symbol": "BTC/USD",
  "side": "buy",
  "quantity": 5.0,
  "price": 50000.0,
  "order_id": "ORDER-123",
  "correlation_id": "trade-456",
  "status": "blocked",
  "reason": "Order notional 250000.00 exceeds max 50000.00",
  "breached_limits": {
    "max_notional_per_order": 250000.0
  },
  "timestamp": "2025-11-03T14:30:00.000Z"
}
```

### Grafana Dashboard

Import the dashboard from `monitoring/grafana/risk_dashboard.json` to visualize:

- Kill switch status
- Circuit breaker state
- Gross exposure trends
- Daily drawdown
- Risk rejection rates
- Circuit breaker trip history
- Open orders count

## Operational Procedures

### Emergency Stop (Kill Switch)

To immediately halt all trading:

```bash
curl -X POST https://api.tradepulse.example.com/admin/risk/kill_switch \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true}'
```

### Investigating Rejections

1. Check the Grafana dashboard for rejection reasons
2. Query the risk state endpoint
3. Review structured logs for detailed information
4. If appropriate, adjust limits in configuration
5. Re-enable trading when safe

### Circuit Breaker Recovery

When the circuit breaker opens:

1. Identify the root cause from last_trip_reason
2. Address the underlying issue
3. Wait for the cool-down period to expire
4. Circuit breaker will transition to HALF_OPEN
5. Test with limited orders
6. Circuit breaker returns to CLOSED if successful

### Adjusting Limits

To adjust risk limits:

1. Update `configs/risk.yaml`
2. Set environment variables for runtime overrides
3. Restart the application to apply changes
4. Verify new limits via `/admin/risk/state` endpoint

## Testing

Comprehensive test suites are available:

```bash
# Unit tests for risk compliance
pytest tests/execution/test_risk_compliance.py

# Circuit breaker tests
pytest tests/execution/test_circuit_breaker_risk.py

# Admin API tests
pytest tests/admin/test_admin_api.py

# E2E integration tests
pytest tests/e2e/test_risk_controls_e2e.py
```

## Security Considerations

1. **Admin Token**: Store `ADMIN_API_TOKEN` in a secure secret store, never in code
2. **HTTPS Only**: Admin endpoints must be served over HTTPS in production
3. **Network Access**: Restrict admin endpoint access to trusted networks
4. **Audit Logging**: All admin operations are logged for compliance
5. **Rate Limiting**: Consider rate limiting admin endpoints

## Precedence of Checks

Checks are applied in order:

1. Kill Switch (highest priority)
2. Circuit Breaker state
3. Risk Compliance checks:
   - Max notional per order
   - Per-symbol position cap
   - Max gross exposure
   - Daily max drawdown
   - Max open orders
4. RiskController.validate_order()

If any check fails, the order is rejected immediately.

## Best Practices

1. **Start Conservative**: Begin with tight limits and gradually relax as confidence grows
2. **Monitor Metrics**: Set up alerts for approaching limits
3. **Regular Review**: Review rejection patterns weekly
4. **Test Failsafes**: Periodically test kill switch and circuit breaker
5. **Document Changes**: Log all limit adjustments with rationale
6. **Incident Response**: Have a runbook for handling risk events

## Troubleshooting

**Q: Orders are blocked but I don't see violations in the state**

A: Check the structured logs for detailed rejection reasons. The state endpoint shows current values, not historical violations.

**Q: Circuit breaker is stuck in OPEN state**

A: Wait for the recovery timeout to expire. Check `circuit_breaker_ttl` for remaining time.

**Q: Daily drawdown keeps blocking orders**

A: Daily metrics reset at UTC midnight. Verify `daily_high_equity` is accurate. Consider adjusting threshold or mode.

**Q: Admin endpoint returns 401 Unauthorized**

A: Verify `ADMIN_API_TOKEN` environment variable is set correctly on the server.

## Future Enhancements

Potential improvements for future releases:

- Dynamic limit adjustment based on volatility
- Per-strategy risk budgets
- Real-time VaR calculation
- Multi-venue aggregated limits
- Machine learning-based anomaly detection
- Automated recovery procedures

## References

- [OMS Documentation](../DOCUMENTATION_SUMMARY.md#execution-layer)
- [Prometheus Client Documentation](https://github.com/prometheus/client_python)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
