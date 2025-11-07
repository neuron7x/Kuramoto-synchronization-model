# Test Architecture Guide

## Overview

TradePulse employs a comprehensive, multi-layered testing strategy designed to ensure reliability, performance, and correctness across all system components. This document describes the testing philosophy, patterns, and best practices used throughout the project.

## Testing Philosophy

### Core Principles

1. **Test Pyramid**: Most tests are fast unit tests, fewer integration tests, minimal e2e tests
2. **Deterministic**: Tests produce consistent results across environments and executions
3. **Independent**: Tests don't depend on execution order or external state
4. **Maintainable**: Clear, documented tests that are easy to update as code evolves
5. **Comprehensive**: Critical paths have multiple test types (unit, integration, property)

### Quality Gates

- **Unit Tests**: ≥95% line coverage for core modules
- **Integration Tests**: All major workflows covered
- **Property Tests**: Invariants validated for numerical components
- **Performance Tests**: Regression detection for critical paths
- **Security Tests**: Audit logs, access control, data validation

## Test Organization

### Directory Structure

```
tests/
├── unit/                    # Fast, isolated component tests
│   ├── core/               # Core indicators and algorithms
│   ├── backtest/           # Backtesting engine
│   ├── execution/          # Order execution and risk
│   └── ...
├── integration/            # Multi-component workflow tests
├── property/               # Hypothesis-based property tests
├── e2e/                    # End-to-end user journey tests
├── performance/            # Benchmark and regression tests
├── security/               # Security and compliance tests
├── fuzz/                   # Fuzzing and chaos tests
├── contracts/              # API contract tests
├── fixtures/               # Shared test data and builders
└── utils/                  # Test helpers and factories
```

### Test Naming Conventions

#### Test Files
- Pattern: `test_<module_name>.py`
- Examples: `test_agents.py`, `test_execution.py`

#### Test Functions
- Pattern: `test_<what>_<condition>_<expected_result>`
- Examples:
  - `test_epsilon_greedy_prefers_best_arm_when_exploit()`
  - `test_risk_manager_enforces_position_caps()`
  - `test_zero_signal_yields_zero_pnl()`

#### Test Classes (Optional)
- Pattern: `Test<ComponentName><Aspect>`
- Example: `TestBacktestEngineProperties`

## Test Types and Patterns

### Unit Tests

**Purpose**: Validate individual functions and classes in isolation

**Characteristics**:
- Fast (< 100ms per test)
- No external dependencies (databases, networks, files)
- Use mocks/stubs for dependencies
- Test single responsibility

**Example**:
```python
def test_position_sizing_never_exceeds_balance() -> None:
    """Test that position sizing respects maximum balance constraints.
    
    Validates:
    - Calculated size doesn't exceed available balance
    - Result is always non-negative
    - Works with various risk parameters
    """
    balance = 1000.0
    risk = 0.1
    price = 50.0
    size = position_sizing(balance, risk, price)
    
    assert size <= balance / price, f"Size {size} exceeds max {balance/price}"
    assert size >= 0.0, "Size must be non-negative"
```

### Integration Tests

**Purpose**: Validate interactions between multiple components

**Characteristics**:
- Slower than unit tests (< 5s per test)
- May use in-memory databases or temporary files
- Test realistic workflows
- Validate component integration

**Example**:
```python
def test_csv_ingestion_to_strategy_evaluation(tmp_path) -> None:
    """Test complete flow from CSV ingestion to strategy evaluation.
    
    Validates end-to-end data pipeline:
    1. CSV parsing and validation
    2. Feature computation
    3. Strategy evaluation
    4. Result aggregation
    """
    csv_file = tmp_path / "market_data.csv"
    write_sample_data(csv_file)
    
    # Ingest and process
    data = ingest_csv(csv_file)
    features = compute_features(data)
    result = evaluate_strategy(features)
    
    assert result.trades > 0, "Strategy should generate trades"
    assert result.sharpe_ratio > 0, "Strategy should have positive Sharpe"
```

### Property-Based Tests

**Purpose**: Validate invariants across wide input ranges

**Characteristics**:
- Use Hypothesis to generate test cases
- Focus on properties that should always hold
- Catch edge cases automatically
- Excellent for numerical code

**Example**:
```python
@settings(max_examples=100, deadline=None)
@given(
    prices=arrays(
        dtype=np.float64,
        shape=st.integers(min_value=10, max_value=200),
        elements=st.floats(min_value=10.0, max_value=1000.0),
    ),
    fee=st.floats(min_value=0.0, max_value=0.01),
)
def test_fees_reduce_pnl(prices: np.ndarray, fee: float) -> None:
    """Property: Trading fees should always reduce or maintain PnL."""
    result_no_fee = walk_forward(prices, strategy, fee=0.0)
    result_with_fee = walk_forward(prices, strategy, fee=fee)
    
    assert result_with_fee.pnl <= result_no_fee.pnl + 1e-9
```

### Performance Tests

**Purpose**: Detect performance regressions and validate scalability

**Characteristics**:
- Use pytest-benchmark
- Set performance budgets
- Test with realistic data volumes
- Monitor memory usage

**Example**:
```python
@pytest.mark.slow
def test_kuramoto_indicator_performance(benchmark) -> None:
    """Validate Kuramoto indicator performance stays within budget.
    
    Performance target: < 50ms for 1000 data points
    """
    data = generate_test_series(length=1000)
    indicator = KuramotoIndicator(window=50)
    
    result = benchmark(indicator.compute, data)
    
    assert benchmark.stats['mean'] < 0.050, "Mean time exceeds 50ms budget"
```

## Fixture Patterns

### Shared Fixtures

Located in `tests/fixtures/` and `conftest.py`:

```python
@pytest.fixture
def sample_market_data():
    """Provide consistent OHLCV data for tests."""
    return pd.DataFrame({
        'open': [100, 101, 99, 102],
        'high': [102, 103, 101, 104],
        'low': [99, 100, 98, 101],
        'close': [101, 100, 102, 103],
        'volume': [1000, 1100, 900, 1200],
    })
```

### Factory Fixtures

For creating test objects with various configurations:

```python
@pytest.fixture
def strategy_factory():
    """Factory for creating strategy instances with custom parameters."""
    def _create_strategy(**kwargs):
        defaults = {'window': 20, 'threshold': 0.5}
        defaults.update(kwargs)
        return Strategy(**defaults)
    return _create_strategy

def test_strategy_with_custom_params(strategy_factory):
    strategy = strategy_factory(window=50, threshold=0.7)
    # Test with custom configuration
```

### Temporary Resource Fixtures

For tests requiring files or databases:

```python
@pytest.fixture
def temp_database(tmp_path):
    """Provide temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    
    yield engine
    
    engine.dispose()
```

## Mocking and Stubbing

### When to Mock

1. **External Services**: APIs, databases, message queues
2. **Time-Dependent Code**: Use time stubs for deterministic tests
3. **Non-Deterministic Operations**: Random number generation
4. **Slow Operations**: File I/O, network calls

### Mock Patterns

#### Time Stubbing
```python
class TimeStub:
    """Controllable time source for deterministic testing."""
    def __init__(self):
        self._now = 0.0
    
    def advance(self, delta: float):
        self._now += delta
    
    def __call__(self) -> float:
        return self._now

def test_rate_limiter_with_time_control():
    clock = TimeStub()
    limiter = RateLimiter(max_rate=10, interval=1.0, time_source=clock)
    
    # Simulate passage of time
    clock.advance(1.1)
    assert limiter.can_proceed()
```

#### Service Mocking
```python
def test_with_mock_exchange(monkeypatch):
    """Test order execution with mocked exchange API."""
    class MockExchange:
        def place_order(self, symbol, side, quantity):
            return {'id': '12345', 'status': 'filled'}
    
    monkeypatch.setattr('execution.exchange', MockExchange())
    
    # Test execution logic without real exchange
```

## Test Data Management

### Synthetic Data Generation

Prefer synthetic data over real data for reproducibility:

```python
def generate_price_series(
    length: int,
    start_price: float = 100.0,
    volatility: float = 0.02,
    seed: int = 42
) -> np.ndarray:
    """Generate synthetic price series with controlled characteristics."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, volatility, length)
    prices = start_price * np.exp(np.cumsum(returns))
    return prices
```

### Fixture Data Files

For complex test data, use fixture files in `tests/fixtures/`:

```python
def load_test_data(filename: str) -> pd.DataFrame:
    """Load test data from fixtures directory."""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    return pd.read_csv(fixture_path)
```

## Test Documentation

### Module Docstrings

Every test file should have a module docstring:

```python
"""Unit tests for risk management components.

This module validates:
- Position size calculations
- Risk limit enforcement
- Portfolio heat computation
- Order rate limiting

Coverage: execution/risk.py (98%)
"""
```

### Test Function Docstrings

All test functions should have docstrings:

```python
def test_risk_manager_enforces_position_caps() -> None:
    """Test that risk manager prevents positions exceeding configured limits.
    
    Validates:
    - Position limits are enforced on new orders
    - Both long and short positions are checked
    - Limit violations raise appropriate exceptions
    
    Related: test_risk_manager_rate_limiter_blocks_excess_orders
    """
```

### Assertion Messages

Provide clear assertion messages:

```python
# Good
assert result > 0, f"Expected positive result, got {result}"

# Better
assert result > 0, (
    f"Risk score should be positive for this configuration. "
    f"Got {result} with params: {params}"
)
```

## Performance Optimization

### Test Execution Speed

1. **Parallelize**: Use `pytest-xdist` for parallel execution
2. **Mark Slow Tests**: Tag with `@pytest.mark.slow`
3. **Cache Fixtures**: Use `scope="module"` or `scope="session"`
4. **Skip Expensive Setup**: Use `pytest.mark.skipif` conditionally

### Resource Management

```python
@pytest.fixture(scope="module")
def expensive_model():
    """Load ML model once per test module."""
    model = load_trained_model()
    yield model
    # Cleanup if needed
```

## Continuous Integration

### CI Test Strategy

Tests run in multiple stages:

1. **Fast Feedback** (< 2 min): Unit tests, linting
2. **Integration** (< 10 min): Integration tests, contracts
3. **Comprehensive** (< 30 min): Property tests, performance
4. **Nightly**: Heavy workloads, mutation testing

### Test Selection

```bash
# Fast feedback loop
pytest tests/unit -m "not slow"

# Full test suite
pytest tests/

# Specific category
pytest tests/property -m property

# With coverage
pytest tests/ --cov=core --cov=backtest --cov=execution
```

## Common Pitfalls and Solutions

### Flaky Tests

**Problem**: Tests that pass/fail intermittently

**Solutions**:
- Use fixed random seeds
- Avoid time-based assertions
- Increase Hypothesis deadline
- Mark with `@pytest.mark.flaky`

### Slow Tests

**Problem**: Test suite takes too long

**Solutions**:
- Profile tests: `pytest --durations=10`
- Mark slow tests: `@pytest.mark.slow`
- Parallelize: `pytest -n auto`
- Use module-scoped fixtures

### Test Coupling

**Problem**: Tests depend on execution order

**Solutions**:
- Each test should set up its own state
- Use fixtures for common setup
- Avoid global state
- Run tests in random order: `pytest --random-order`

## Best Practices Summary

### DO

✅ Write tests first (TDD) or alongside code
✅ Test behavior, not implementation
✅ Use descriptive test names
✅ Add docstrings to all tests
✅ Keep tests simple and focused
✅ Use fixtures for common setup
✅ Test edge cases and error paths
✅ Add assertion messages
✅ Run tests frequently during development

### DON'T

❌ Test private methods directly
❌ Copy-paste test code
❌ Use production data in tests
❌ Skip writing tests for "trivial" code
❌ Leave failing tests in the codebase
❌ Write tests that require manual setup
❌ Ignore flaky tests
❌ Test multiple things in one test

## Further Reading

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html)
- [TradePulse TESTING.md](../TESTING.md) - Execution instructions
- [TradePulse TEST_PLAN.md](../tests/TEST_PLAN.md) - Coverage matrix
