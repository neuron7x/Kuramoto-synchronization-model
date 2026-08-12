---
owner: quant-systems@geosync
review_cadence: quarterly
last_reviewed: 2025-11-04
links:
  - ../../docs/architecture/system_modules_reference.md
  - ../../docs/cookbook_backtest_live.md
---

# Core Strategies Module

## Purpose

The `core/strategies` module is GeoSync's **strategy orchestration layer**: a
contract-driven router that composes analytical signals from lower-level modules
into executable trading decisions with mode control (live/paper/paused),
hot-swap, and per-strategy risk budgets.

> ⚠️ **SCOPE OF BIO-NAMING.** The "PFC / OFC / striatum / basal ganglia /
> working memory" labels below are **analogical shorthand** for the
> orchestration role each component plays — they are **not** a claim that
> the implementation reproduces the cellular mechanisms of those brain
> regions. The contracts a buyer or auditor relies on are the engineering
> ones: type-safe composition (IO contracts), <100 ms hot-swap, 100+
> concurrent strategies, audit-logged mode transitions. The complete
> neuroanatomy map for GeoSync is `~/CANONICAL_NEURO_MAPPING_2026_05_05.md`.

**Orchestration analogy (informal mapping):**
- **Prefrontal Cortex (Executive Control)**: `engine.py` orchestrates strategy execution with mode control (live/paper/paused)
- **Orbitofrontal Cortex (Value Assignment)**: `objectives.py` defines reward functions and optimization targets
- **Dorsal Striatum (Action Selection)**: `dsl.py` and `fete.py` provide declarative strategy composition
- **Basal Ganglia (Go/No-Go)**: Risk advisories and cancellation signals implement action gating
- **Working Memory**: `StrategyContext` maintains active strategy state across decision cycles

**Key Objectives:**
- Guarantee type-safe strategy composition through IO contracts
- Provide deterministic mode transitions (live ↔ paper ↔ paused) with audit logging
- Enable strategy hot-swapping without system restart (< 100ms switchover)
- Support 100+ concurrent strategies with isolated resource budgets
- Maintain strategy-level risk limits with automatic circuit breakers

## Key Responsibilities

- **Contract-First Orchestration**: Define and enforce IO contracts between strategy modules for structural compatibility
- **Mode Management**: Safe transitions between live trading, paper trading, and paused states with persistent state
- **Strategy Context**: Maintain isolated execution context per strategy (capital, positions, metadata, risk state)
- **Signal Routing**: Route strategy signals to execution layer with risk checks and compliance validation
- **Risk Integration**: Embed risk advisories, position limits, and kill-switch controls at strategy level
- **DSL Composition**: Declarative strategy definition language for rapid prototyping (FETE: Functional Event-driven Trading Engine)
- **Strategy Versioning**: Track strategy version, parameters, and performance across deployments
- **Hot Reload**: Dynamic strategy loading and unloading without system downtime
- **Replay Support**: Deterministic strategy replay for backtesting and audit

## Public Interfaces

| Interface | Type | Location | Description |
| --------- | ---- | -------- | ----------- |
| `StrategyEngine` | Class | `engine.py` | Main orchestration engine with mode control and contract validation |
| `IOContract` | Dataclass | `engine.py` | Declarative input/output contract specification |
| `StrategyContext` | Dataclass | `engine.py` | Isolated execution context (capital, positions, metadata) |
| `StrategySignal` | Dataclass | `engine.py` | Structured signal output with confidence and metadata |
| `RiskAdvisory` | Dataclass | `engine.py` | Risk warning or limit breach notification |
| `CancellationSignal` | Dataclass | `engine.py` | Signal to cancel pending orders (risk mitigation) |
| `StrategyEngineMode` | Enum | `engine.py` | Operational modes: LIVE, PAPER, PAUSED |
| `StrategyDSL` | Class | `dsl.py` | Declarative strategy composition language |
| `FETERuntime` | Class | `fete_runtime.py` | Functional event-driven runtime for strategy execution |
| `StrategyObjective` | Protocol | `objectives.py` | Strategy optimization objective interface |
| `TradingStrategy` | Protocol | `trading.py` | Base protocol for strategy implementations |

## Configuration

### Environment Variables:
- `GEOSYNC_STRATEGY_ROOT`: Directory for strategy definitions (default: `~/.geosync/strategies`)
- `GEOSYNC_DEFAULT_MODE`: Default execution mode on startup: `paper`, `live` (default: `paper`)
- `GEOSYNC_ENABLE_HOT_RELOAD`: Enable dynamic strategy reloading (default: `true`)
- `GEOSYNC_STRATEGY_TIMEOUT_SECONDS`: Maximum strategy execution time per decision cycle (default: `5`)
- `GEOSYNC_MAX_CONCURRENT_STRATEGIES`: Maximum active strategies (default: `100`)

### Configuration Files:
Strategy orchestration is configured via `configs/strategies/`:
- `engine.yaml`: Mode policies, timeout settings, resource limits
- `contracts.yaml`: Reusable IO contract definitions
- `risk_limits.yaml`: Per-strategy risk budgets and circuit breaker thresholds
- `strategies/*.yaml`: Individual strategy configurations (params, capital, mode)

### Feature Flags:
- `strategies.enforce_contracts`: Runtime IO contract validation (10-15% overhead)
- `strategies.enable_risk_integration`: Embed risk checks in signal routing
- `strategies.enable_hot_reload`: Dynamic strategy loading/unloading
- `strategies.enable_replay`: Support deterministic replay for backtesting

## Dependencies

### Internal:
- `core.events`: Event models (SignalEvent, OrderEvent)
- `core.indicators`: Indicator libraries for strategy logic
- `core.utils.logging`: Structured logging with strategy correlation
- `core.utils.metrics`: Strategy performance metrics
- `domain`: Core domain models (Order, Position)

### External Services/Libraries:
- **Pydantic** (>=2.0): Dataclass validation and serialization
- **Hydra** (>=1.3): Strategy configuration management
- **Pydantic-Core**: Fast validation runtime

## Module Structure

```
core/strategies/
├── __init__.py                      # Public API exports
├── engine.py                        # StrategyEngine orchestration
├── dsl.py                           # Declarative strategy composition DSL
├── fete.py                          # FETE (Functional Event-driven Trading Engine) core
├── fete_runtime.py                  # FETE runtime execution environment
├── objectives.py                    # Strategy optimization objectives
├── signals.py                       # Signal type definitions
└── trading.py                       # TradingStrategy protocol
```

## Neuroeconomic Principles

### Executive Function (Prefrontal Cortex)
The `StrategyEngine` implements cognitive control mechanisms:

1. **Goal Maintenance**: `StrategyContext` holds active goals (target return, max drawdown)
2. **Action Selection**: Signal generation based on indicator inputs and objectives
3. **Performance Monitoring**: Track realized vs expected outcomes (prediction error)
4. **Cognitive Flexibility**: Mode switching (live/paper) without losing state

### Value-Based Decision Making (Orbitofrontal Cortex)
Strategy objectives encode reward expectations:
```python
class SharpeObjective:
    """Maximize risk-adjusted returns (OFC value signal)"""
    def evaluate(self, returns, volatility):
        return returns / (volatility + 1e-9)
```

### Action Gating (Basal Ganglia)
Risk advisories implement go/no-go decision mechanism:
```python
if risk_advisory.breach_type == "position_limit":
    return CancellationSignal(...)  # NO-GO pathway
else:
    return StrategySignal(...)      # GO pathway
```

### Working Memory (Dorsolateral PFC)
`StrategyContext` maintains transient state across decision cycles:
- Recent signals (short-term memory buffer)
- Current positions (active representations)
- Performance metrics (cached computations)
- Risk state (threat monitoring)

### Contextual Modulation
Strategy signals modulated by market regime (context-dependent processing):
```python
signal_strength = base_signal * regime_confidence * (1 - risk_factor)
```

## Operational Notes

### SLIs / Metrics:
- `strategy_execution_latency_seconds{strategy_name}`: Time from indicator update to signal emission
- `strategy_signal_rate{strategy_name, direction}`: Signals generated per minute
- `strategy_mode_duration_seconds{strategy_name, mode}`: Time spent in each mode
- `strategy_contract_violation_total{strategy_name, contract_type}`: IO contract failures
- `strategy_risk_advisory_total{strategy_name, advisory_type}`: Risk warnings issued
- `strategy_cancellation_total{strategy_name, reason}`: Order cancellations triggered
- `strategy_hot_reload_duration_seconds{strategy_name}`: Time to reload strategy

### Alarms:
- **Critical: Strategy Timeout**: Execution exceeds timeout (> 5 seconds)
- **High: Contract Violations**: Contract failures > 5 per minute
- **High: Risk Advisory Storm**: > 10 risk advisories in 1 minute
- **Medium: Mode Transition Failure**: Failed live/paper/paused transition
- **Low: Hot Reload Failure**: Strategy reload failed (fallback to previous version)

### Runbooks:
- [Strategy Deployment Guide](../../docs/cookbook_backtest_live.md)
- [Mode Transition Procedures](../../docs/operational_handbook.md#strategy-modes)
- [Strategy Debugging](../../docs/troubleshooting.md#strategy-execution)
- [Hot Reload Recovery](../../docs/operational_handbook.md#hot-reload)

## Testing Strategy

### Unit Tests:
- **Test Coverage**: 91% (target: 95%)
- **Location**: `tests/core/test_strategies*.py`
- **Focus Areas**:
  - IO contract validation (valid/invalid payloads)
  - Mode transition state machine correctness
  - Signal routing with risk checks
  - Context isolation between strategies
  - DSL compilation and execution

### Integration Tests:
- **Location**: `tests/integration/test_strategy_engine.py`
- **Scenarios**:
  - Multi-strategy orchestration with shared indicators
  - Mode transitions under load (live → paused → paper)
  - Risk advisory propagation to execution layer
  - Hot reload with active positions

### End-to-End Tests:
- **Location**: `tests/e2e/test_strategy_backtest.py`
- **Validation**:
  - Full strategy lifecycle: init → signal → order → fill → P&L
  - Deterministic replay matches historical results
  - Paper trading parity with backtesting

### Property-Based Tests:
- **Framework**: Hypothesis
- **Properties Validated**:
  - Mode transitions never lose state
  - Signal generation deterministic for fixed inputs
  - Risk advisories always respected (never bypassed)
  - Contract validation catches all type mismatches

## Usage Examples

### Basic Strategy Definition
```python
from core.strategies import StrategyEngine, IOContract, StrategyContext
from core.indicators import KuramotoIndicator

# Define IO contract
input_contract = IOContract(
    required={"prices": (list, tuple), "volume": (list, tuple)},
    optional={"regime": str},
    description="Price and volume arrays for momentum analysis",
)

output_contract = IOContract(
    required={"direction": str, "confidence": float},
    optional={"metadata": dict},
    description="Trading signal with confidence score",
)

# Initialize engine
engine = StrategyEngine(
    mode=StrategyEngineMode.PAPER,
    input_contract=input_contract,
    output_contract=output_contract,
)

# Strategy logic function
def momentum_strategy(context: StrategyContext, inputs: dict) -> dict:
    """Simple momentum strategy using Kuramoto indicator"""
    indicator = KuramotoIndicator(window=80, coupling=0.9)
    
    order_param = indicator.compute(inputs["prices"])
    
    if order_param > 0.75:
        direction = "BUY"
        confidence = order_param
    elif order_param < 0.25:
        direction = "SELL"
        confidence = 1.0 - order_param
    else:
        direction = "FLAT"
        confidence = 0.5
    
    return {
        "direction": direction,
        "confidence": confidence,
        "metadata": {"order_param": order_param},
    }

# Execute strategy
result = engine.execute(
    context=StrategyContext(capital=100_000, strategy_id="momentum_v1"),
    inputs={"prices": [100, 101, 102, 103], "volume": [1000, 1100, 1050, 1200]},
    strategy_fn=momentum_strategy,
)

print(f"Signal: {result['direction']}, Confidence: {result['confidence']:.2f}")
```

### Mode Management
```python
from core.strategies import StrategyEngine, StrategyEngineMode

engine = StrategyEngine(mode=StrategyEngineMode.PAPER)

# Transition to live trading (with confirmation)
assert engine.can_transition_to(StrategyEngineMode.LIVE)
engine.set_mode(StrategyEngineMode.LIVE, confirmed=True)

print(f"Current mode: {engine.mode}")
# Output: Current mode: StrategyEngineMode.LIVE

# Pause strategy (e.g., during market anomaly)
engine.set_mode(StrategyEngineMode.PAUSED)

# Resume paper trading
engine.set_mode(StrategyEngineMode.PAPER)
```

### Risk Integration
```python
from core.strategies import StrategyEngine, RiskAdvisory, CancellationSignal

def risk_aware_strategy(context, inputs):
    # Generate base signal
    base_signal = generate_signal(inputs)
    
    # Check risk limits
    if context.current_position > context.max_position:
        return RiskAdvisory(
            breach_type="position_limit",
            severity="high",
            message=f"Position {context.current_position} exceeds limit {context.max_position}",
            recommended_action="reduce_position",
        )
    
    if context.daily_pnl < -context.max_daily_loss:
        return CancellationSignal(
            reason="daily_loss_limit",
            cancel_all_orders=True,
            message=f"Daily loss ${-context.daily_pnl} exceeds limit ${context.max_daily_loss}",
        )
    
    return base_signal

# Engine automatically handles risk advisories
result = engine.execute(context, inputs, risk_aware_strategy)

if isinstance(result, RiskAdvisory):
    print(f"⚠️ Risk Advisory: {result.message}")
elif isinstance(result, CancellationSignal):
    print(f"🛑 Cancellation: {result.message}")
else:
    print(f"✓ Signal: {result}")
```

### Declarative DSL
```python
from core.strategies import StrategyDSL
from core.indicators import KuramotoIndicator, HurstIndicator

# Define strategy using DSL
dsl = StrategyDSL()

strategy = dsl.define(
    name="multi_indicator_momentum",
    indicators=[
        ("kuramoto", KuramotoIndicator(window=80)),
        ("hurst", HurstIndicator(window=100)),
    ],
    rules=[
        # Buy when Kuramoto > 0.75 AND Hurst > 0.6 (trending)
        dsl.rule(
            condition=lambda ctx: ctx.indicators.kuramoto > 0.75 and ctx.indicators.hurst > 0.6,
            action=dsl.signal("BUY", confidence=lambda ctx: ctx.indicators.kuramoto),
        ),
        # Sell when Kuramoto < 0.25 AND Hurst < 0.4 (mean-reverting)
        dsl.rule(
            condition=lambda ctx: ctx.indicators.kuramoto < 0.25 and ctx.indicators.hurst < 0.4,
            action=dsl.signal("SELL", confidence=lambda ctx: 1.0 - ctx.indicators.kuramoto),
        ),
        # Flat otherwise
        dsl.rule(
            condition=lambda ctx: True,  # Default
            action=dsl.signal("FLAT", confidence=0.5),
        ),
    ],
)

# Execute DSL strategy
result = strategy.execute(prices=[...], volume=[...])
```

### Hot Reload
```python
from core.strategies import StrategyEngine

engine = StrategyEngine()

# Load initial strategy
engine.load_strategy(
    name="momentum_v1",
    module_path="strategies/momentum_v1.py",
)

# Later: deploy new version without restart
engine.hot_reload_strategy(
    name="momentum_v1",
    module_path="strategies/momentum_v2.py",  # New version
    graceful=True,  # Wait for current signals to complete
)

print(f"Loaded strategy version: {engine.get_strategy_version('momentum_v1')}")
```

### FETE Runtime (Functional Event-Driven)
```python
from core.strategies import FETERuntime

# Define strategy as pure function
def fete_strategy(market_data, portfolio_state):
    """Pure functional strategy (no side effects)"""
    price_momentum = market_data["close"][-20:].mean() - market_data["close"][-100:].mean()
    
    if price_momentum > 0 and portfolio_state["cash"] > 10000:
        return {"action": "BUY", "quantity": 1.0, "reason": "positive_momentum"}
    elif price_momentum < 0 and portfolio_state["position"] > 0:
        return {"action": "SELL", "quantity": 1.0, "reason": "negative_momentum"}
    else:
        return {"action": "HOLD"}

# Create runtime
runtime = FETERuntime()

# Execute strategy in isolated environment
result = runtime.execute(
    strategy_fn=fete_strategy,
    market_data={"close": [100, 101, 102, ...]},
    portfolio_state={"cash": 50000, "position": 0},
)

print(f"Action: {result['action']}, Reason: {result.get('reason', 'N/A')}")
```

## Performance Characteristics

### Execution Latency:
- Contract validation: 0.1ms
- Strategy execution: 1-10ms (depends on indicator complexity)
- Mode transition: 50ms (persistent state update)
- Hot reload: 100ms (compilation + validation)

### Throughput:
- Single strategy: 1,000 decisions/second
- 100 concurrent strategies: 10,000 decisions/second aggregate
- Event processing: 50,000 market updates/second

### Memory:
- Strategy context: ~10 KB per strategy
- DSL compiled strategy: ~50 KB
- FETE runtime: ~5 MB (interpreter overhead)

### Scalability:
- Horizontal: Shard strategies across multiple engine instances
- Vertical: Tested with 500 concurrent strategies on 16-core CPU

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-11-04 | quant-systems@geosync | Created comprehensive README with neuroeconomic executive function mapping |

## See Also

- [System Modules Reference](../../docs/architecture/system_modules_reference.md)
- [Backtest to Live Cookbook](../../docs/cookbook_backtest_live.md)
- [Strategy Development Guide](../../docs/examples/README.md)
- [Operational Handbook: Strategy Management](../../docs/operational_handbook.md#strategies)
