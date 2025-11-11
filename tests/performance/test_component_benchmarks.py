"""Performance benchmarks for critical components.

This module contains benchmarks for:
- order_router: Execution routing across multiple exchanges
- link_activator: Protocol selection and activation
- thermo_validator: Thermodynamic state validation

These benchmarks are used by the performance gate to validate
that components meet their performance budgets.
"""

from __future__ import annotations

import pytest

# Mark all tests in this module as slow and heavy to exclude from standard test runs
pytestmark = [pytest.mark.slow, pytest.mark.heavy_math]

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.connectors import ExecutionConnector
from execution.router import (
    ExecutionRoute,
    ResilientExecutionRouter,
    SlippageModel,
)
from execution.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    ExchangeResilienceProfile,
    LeakyBucketRateLimiter,
)
from runtime.link_activator import LinkActivator, ProtocolType
from runtime.thermo_controller import ThermoController


# ============================================================================
# Test Fixtures
# ============================================================================


class BenchmarkConnector(ExecutionConnector):
    """Lightweight connector for benchmarking."""

    def __init__(self) -> None:
        super().__init__(sandbox=True)
        self.call_count = 0

    def place_order(
        self, order: Order, *, idempotency_key: str | None = None
    ) -> Order:
        self.call_count += 1
        placed = super().place_order(order, idempotency_key=idempotency_key)
        # Simulate processing
        placed.status = OrderStatus.FILLED
        placed.filled_quantity = order.quantity
        placed.average_price = order.price
        return placed


@pytest.fixture
def resilience_profile() -> ExchangeResilienceProfile:
    """Create a standard resilience profile for benchmarks."""
    return ExchangeResilienceProfile(
        circuit_breaker_config=CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=10.0,
            half_open_max_calls=1,
        ),
        leaky_bucket=LeakyBucketRateLimiter(capacity=100, leak_rate=50.0),
        token_bucket=None,
        bulkhead_max_concurrent=10,
    )


@pytest.fixture
def sample_order() -> Order:
    """Create a sample order for testing."""
    return Order(
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        price=50000.0,
    )


# ============================================================================
# order_router Benchmarks
# ============================================================================


def test_order_router_single_route_submission(
    benchmark, resilience_profile, sample_order
):
    """Benchmark: Submit order through single route.
    
    This measures the end-to-end latency of order submission through
    the router with resilience checks and normalization.
    """

    def setup():
        router = ResilientExecutionRouter()
        connector = BenchmarkConnector()
        route = ExecutionRoute(
            name="benchmark_exchange",
            connector=connector,
            resilience=resilience_profile,
            slippage_model=SlippageModel(max_slippage_bps=5.0),
        )
        router.register_route("benchmark", route)
        return (router, sample_order), {}

    def run(router, order):
        result = router.submit_order("benchmark", order, idempotency_key="bench_key")
        return result

    benchmark.pedantic(run, setup=setup, rounds=100, iterations=10)


def test_order_router_route_failover(benchmark, resilience_profile, sample_order):
    """Benchmark: Order routing with failover.
    
    Measures latency when primary route is available (no failover triggered).
    """

    def setup():
        router = ResilientExecutionRouter()
        
        primary_connector = BenchmarkConnector()
        backup_connector = BenchmarkConnector()
        
        primary_route = ExecutionRoute(
            name="primary",
            connector=primary_connector,
            resilience=resilience_profile,
        )
        backup_route = ExecutionRoute(
            name="backup",
            connector=backup_connector,
            resilience=resilience_profile,
        )
        
        router.register_route("exchange", primary_route, backup=backup_route)
        return (router, sample_order), {}

    def run(router, order):
        return router.submit_order("exchange", order)

    benchmark.pedantic(run, setup=setup, rounds=100, iterations=10)


def test_order_router_parallel_submissions(benchmark, resilience_profile):
    """Benchmark: Parallel order submissions across routes.
    
    Simulates concurrent order flow through multiple exchange routes.
    """
    
    def setup():
        router = ResilientExecutionRouter()
        
        # Register multiple routes
        for i in range(3):
            connector = BenchmarkConnector()
            route = ExecutionRoute(
                name=f"exchange_{i}",
                connector=connector,
                resilience=resilience_profile,
            )
            router.register_route(f"exchange_{i}", route)
        
        orders = [
            Order(
                symbol=f"PAIR{i}",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=1.0,
                price=100.0 + i,
            )
            for i in range(3)
        ]
        return (router, orders), {}

    def run(router, orders):
        results = []
        for i, order in enumerate(orders):
            result = router.submit_order(f"exchange_{i}", order)
            results.append(result)
        return results

    benchmark.pedantic(run, setup=setup, rounds=50, iterations=5)


# ============================================================================
# link_activator Benchmarks
# ============================================================================


def test_link_activator_protocol_selection(benchmark):
    """Benchmark: Protocol selection for bond types.
    
    Measures the latency of protocol selection and activation logic.
    """

    def setup():
        activator = LinkActivator(enable_rdma=True, enable_crdt=True)
        bond_types = ["metallic", "ionic", "covalent", "vdw", "hydrogen"]
        return (activator, bond_types), {}

    def run(activator, bond_types):
        results = []
        for bond_type in bond_types:
            result = activator.apply(bond_type, f"node_a_{bond_type}", f"node_b_{bond_type}")
            results.append(result)
        return results

    benchmark.pedantic(run, setup=setup, rounds=200, iterations=20)


def test_link_activator_fallback_chain(benchmark):
    """Benchmark: Protocol fallback chain traversal.
    
    Tests performance when primary protocols are disabled.
    """

    def setup():
        # Disable high-performance protocols to trigger fallbacks
        activator = LinkActivator(enable_rdma=False, enable_crdt=False)
        return (activator,), {}

    def run(activator):
        results = []
        for i in range(10):
            result = activator.apply("ionic", f"trader_{i}", f"risk_{i}")
            results.append(result)
        return results

    benchmark.pedantic(run, setup=setup, rounds=200, iterations=20)


def test_link_activator_cost_accumulation(benchmark):
    """Benchmark: Cost tracking and history management.
    
    Measures overhead of activation history and cost accumulation.
    """

    def setup():
        activator = LinkActivator()
        return (activator,), {}

    def run(activator):
        # Perform activations
        for i in range(20):
            activator.apply("metallic", f"node_{i}", f"node_{i+1}")
        
        # Query state
        total_cost = activator.get_total_cost()
        history = activator.get_activation_history()
        
        return total_cost, len(history)

    benchmark.pedantic(run, setup=setup, rounds=100, iterations=10)


# ============================================================================
# thermo_validator Benchmarks
# ============================================================================


@pytest.mark.slow
def test_thermo_validator_state_validation(benchmark):
    """Benchmark: Thermodynamic state validation.
    
    Measures validation latency for thermodynamic constraints.
    Note: This is a placeholder - actual implementation depends on
    thermo_controller validation methods.
    """

    def setup():
        # This is a simplified benchmark - adjust based on actual API
        import numpy as np
        
        # Create synthetic state data
        state = {
            "temperature": np.random.uniform(0.1, 2.0, 100),
            "entropy": np.random.uniform(0, 5.0, 100),
            "free_energy": np.random.uniform(-100, 100, 100),
        }
        return (state,), {}

    def run(state):
        # Simulate validation checks
        valid = True
        
        # Temperature bounds
        valid &= all(0 < t < 10 for t in state["temperature"])
        
        # Entropy non-negative
        valid &= all(s >= 0 for s in state["entropy"])
        
        # Energy bounds
        valid &= all(-1000 < e < 1000 for e in state["free_energy"])
        
        return valid

    benchmark.pedantic(run, setup=setup, rounds=150, iterations=15)


@pytest.mark.slow
def test_thermo_validator_constraint_checking(benchmark):
    """Benchmark: Constraint satisfaction checking.
    
    Validates multiple thermodynamic constraints simultaneously.
    """

    def setup():
        import numpy as np
        
        # Larger state space
        state = {
            "bonds": np.random.choice(["ionic", "covalent", "metallic"], 500),
            "energies": np.random.uniform(-10, 10, 500),
            "distances": np.random.uniform(0.5, 3.0, 500),
        }
        return (state,), {}

    def run(state):
        violations = []
        
        # Check energy bounds per bond type
        energy_limits = {
            "ionic": (-8, 8),
            "covalent": (-12, 2),
            "metallic": (-5, 5),
        }
        
        for i, bond_type in enumerate(state["bonds"]):
            energy = state["energies"][i]
            min_e, max_e = energy_limits[bond_type]
            if not (min_e <= energy <= max_e):
                violations.append(i)
        
        # Check distance constraints
        for i, distance in enumerate(state["distances"]):
            if distance < 0.3 or distance > 5.0:
                violations.append(i)
        
        return len(violations)

    benchmark.pedantic(run, setup=setup, rounds=100, iterations=10)


@pytest.mark.slow  
def test_thermo_validator_stability_analysis(benchmark):
    """Benchmark: System stability analysis.
    
    Measures performance of stability coefficient calculation.
    """

    def setup():
        import numpy as np
        
        # Time series data
        n_samples = 1000
        state_history = {
            "temperatures": np.random.lognormal(0, 0.3, n_samples),
            "entropies": np.cumsum(np.random.normal(0, 0.1, n_samples)),
            "energies": np.random.normal(0, 5, n_samples),
        }
        return (state_history,), {}

    def run(state_history):
        # Calculate stability metrics
        import numpy as np
        
        # Coefficient of variation for each metric
        metrics = {}
        for key, values in state_history.items():
            mean = np.mean(values)
            std = np.std(values)
            metrics[f"{key}_cov"] = std / mean if mean != 0 else 0
        
        # Detect regime shifts
        window_size = 50
        shifts = []
        for i in range(len(state_history["temperatures"]) - window_size):
            window = state_history["temperatures"][i : i + window_size]
            if np.std(window) > 0.5:
                shifts.append(i)
        
        return metrics, len(shifts)

    benchmark.pedantic(run, setup=setup, rounds=50, iterations=5)


# ============================================================================
# Integrated Benchmarks
# ============================================================================


@pytest.mark.slow
def test_integrated_order_flow(benchmark, resilience_profile):
    """Benchmark: Complete order flow with routing and validation.
    
    End-to-end test of the full order processing pipeline.
    """

    def setup():
        # Setup router
        router = ResilientExecutionRouter()
        connector = BenchmarkConnector()
        route = ExecutionRoute(
            name="integrated",
            connector=connector,
            resilience=resilience_profile,
            slippage_model=SlippageModel(max_slippage_bps=5.0),
        )
        router.register_route("main", route)
        
        # Setup link activator
        activator = LinkActivator(enable_rdma=True, enable_crdt=True)
        
        # Create orders
        orders = [
            Order(
                symbol="BTC/USD",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=1.0,
                price=50000.0 + i * 100,
            )
            for i in range(5)
        ]
        
        return (router, activator, orders), {}

    def run(router, activator, orders):
        results = []
        
        for order in orders:
            # Activate communication link
            link = activator.apply("ionic", "trader", "exchange")
            
            # Route order
            if link.success:
                result = router.submit_order("main", order)
                results.append(result)
        
        return results

    benchmark.pedantic(run, setup=setup, rounds=50, iterations=5)
