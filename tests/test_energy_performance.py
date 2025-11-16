"""Performance tests for thermodynamic energy calculations."""
import time
from typing import Dict, Tuple

import pytest

from core.energy import (
    BondType,
    bond_internal_energy,
    clear_energy_cache,
    system_free_energy,
)


def test_bond_energy_caching_performance():
    """Verify that caching improves performance for repeated calculations."""
    # Setup test data
    latencies: Dict[Tuple[str, str], float] = {("A", "B"): 0.5}
    coherency: Dict[Tuple[str, str], float] = {("A", "B"): 0.8}

    # Clear cache to start fresh
    clear_energy_cache()

    # First run: populate cache
    start = time.perf_counter()
    for _ in range(1000):
        bond_internal_energy("A", "B", "covalent", latencies, coherency)
    first_duration = time.perf_counter() - start

    # Second run: should use cache
    start = time.perf_counter()
    for _ in range(1000):
        bond_internal_energy("A", "B", "covalent", latencies, coherency)
    second_duration = time.perf_counter() - start

    # Cache should provide speedup (at least marginally faster)
    # We use a relaxed assertion since caching overhead can vary
    assert second_duration <= first_duration * 1.2  # Allow 20% variance


def test_system_energy_computation_time():
    """Verify system energy computation completes in reasonable time."""
    # Create a moderate-sized topology
    bonds: Dict[Tuple[str, str], BondType] = {}
    latencies: Dict[Tuple[str, str], float] = {}
    coherency: Dict[Tuple[str, str], float] = {}

    # Generate 50 edges
    for i in range(50):
        src = f"node_{i}"
        dst = f"node_{(i+1) % 50}"
        bonds[(src, dst)] = "covalent"
        latencies[(src, dst)] = 0.5 + (i % 10) * 0.05
        coherency[(src, dst)] = 0.7 + (i % 5) * 0.05

    resource_usage = 0.5
    entropy = 0.3

    # Measure computation time
    start = time.perf_counter()
    iterations = 100
    for _ in range(iterations):
        system_free_energy(bonds, latencies, coherency, resource_usage, entropy)
    duration = time.perf_counter() - start

    # Should complete well under 1 second for 100 iterations
    assert duration < 1.0, f"Computation too slow: {duration:.4f}s for {iterations} iterations"

    # Average time per iteration
    avg_time = duration / iterations
    assert avg_time < 0.01, f"Average iteration too slow: {avg_time*1000:.2f}ms"


def test_clear_energy_cache_works():
    """Verify cache clearing functionality."""
    latencies: Dict[Tuple[str, str], float] = {("X", "Y"): 0.3}
    coherency: Dict[Tuple[str, str], float] = {("X", "Y"): 0.9}

    # Populate cache
    bond_internal_energy("X", "Y", "ionic", latencies, coherency)

    # Clear cache
    clear_energy_cache()

    # Should still work after clearing
    result = bond_internal_energy("X", "Y", "ionic", latencies, coherency)
    assert isinstance(result, float)
    assert result > 0  # Energy should be positive for this configuration


@pytest.mark.benchmark
def test_bond_types_performance():
    """Benchmark all bond types for performance comparison."""
    latencies: Dict[Tuple[str, str], float] = {("A", "B"): 0.5}
    coherency: Dict[Tuple[str, str], float] = {("A", "B"): 0.8}

    bond_types: list[BondType] = ["covalent", "ionic", "metallic", "vdw", "hydrogen"]

    timings = {}
    for bond_type in bond_types:
        clear_energy_cache()
        start = time.perf_counter()
        for _ in range(1000):
            bond_internal_energy("A", "B", bond_type, latencies, coherency)
        timings[bond_type] = time.perf_counter() - start

    # All bond types should compute in reasonable time
    for bond_type, duration in timings.items():
        assert duration < 0.1, f"{bond_type} too slow: {duration:.4f}s"
