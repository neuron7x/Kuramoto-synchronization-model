# TradePulse Performance Optimization Guide

This document outlines best practices and patterns for maximizing system efficiency and productivity in the TradePulse trading platform.

## Table of Contents

1. [Memory Optimization](#memory-optimization)
2. [Import Optimization](#import-optimization)
3. [Computation Optimization](#computation-optimization)
4. [Caching Strategies](#caching-strategies)
5. [Performance Monitoring](#performance-monitoring)

## Memory Optimization

### Use __slots__ in Dataclasses

Python dataclasses without `__slots__` use a `__dict__` for attribute storage, consuming ~40% more memory than necessary. For frequently instantiated classes, always use `__slots__`:

```python
from dataclasses import dataclass

# ❌ Without slots (more memory)
@dataclass
class TradeSignal:
    symbol: str
    price: float
    quantity: int

# ✅ With slots (15-20% less memory)
@dataclass(slots=True)
class TradeSignal:
    symbol: str
    price: float
    quantity: int
```

**When to use:**
- Classes instantiated frequently (>1000 times)
- Event/message classes
- Cache entries
- Data transfer objects

**Memory savings:**
- ~200 bytes per instance for typical dataclasses
- ~15-20% reduction in overall memory footprint

### Object Pooling

For objects created and destroyed frequently, use object pools to reduce GC pressure:

```python
from core.utils.performance_optimization import ObjectPool
import numpy as np

# Create pool for numpy arrays
array_pool = ObjectPool(
    factory=lambda: np.zeros(1000),
    maxsize=10,
    reset=lambda arr: arr.fill(0)
)

# Reuse instead of allocate
def process_data():
    arr = array_pool.acquire()
    try:
        # use array
        result = compute(arr)
        return result
    finally:
        array_pool.release(arr)
```

**Best for:**
- NumPy arrays with fixed shapes
- Connection objects
- Protocol buffers
- Large dataclasses

**Performance impact:**
- 30-50% reduction in allocation time
- Significant GC pressure reduction
- Lower memory fragmentation

## Import Optimization

### Lazy Imports with TYPE_CHECKING

Defer expensive imports to improve module initialization time:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scipy import stats
    from sklearn.ensemble import RandomForestClassifier
else:
    stats = None
    RandomForestClassifier = None

def _get_scipy_stats():
    """Lazy load scipy.stats on first use."""
    global stats
    if stats is None:
        from scipy import stats as _stats
        stats = _stats
    return stats

def compute_statistics(data):
    scipy_stats = _get_scipy_stats()
    return scipy_stats.describe(data)
```

**Benefits:**
- 2-5x faster module import time
- Reduced memory footprint
- Better separation of concerns

**Use for:**
- Heavy numerical libraries (scipy, sklearn)
- Optional dependencies
- Large modules only used in specific code paths

### Lazy Module Loading

For truly deferred loading, use the lazy_import utility:

```python
from core.utils.performance_optimization import lazy_import

# Module not loaded yet
torch = lazy_import('torch')

# Loaded on first use
def train_model():
    model = torch.nn.Linear(10, 1)  # torch imported here
```

## Computation Optimization

### Vectorization

Replace loops with NumPy vectorized operations:

```python
import numpy as np

# ❌ Slow loop
result = []
for x in data:
    result.append(np.exp(x) ** 2)
result = np.array(result)

# ✅ Vectorized
result = np.exp(data) ** 2
```

**Performance gain:** 10-100x speedup

### Chunked Processing

For large arrays, process in chunks to manage memory:

```python
from core.utils.performance_optimization import vectorize_safe

# Processes 1M+ element arrays efficiently
large_array = np.random.randn(10_000_000)
result = vectorize_safe(np.exp, large_array, chunk_size=10000)
```

### Use float32 When Appropriate

For indicators and features, float32 often provides sufficient precision with 50% memory savings:

```python
# ✅ Use float32 for indicators
data = np.array(prices, dtype=np.float32)
result = compute_indicator(data)

# Only use float64 for:
# - Financial calculations requiring precision
# - Cumulative operations prone to error accumulation
# - Scientific computations
```

## Caching Strategies

### Memoization

Cache expensive function results:

```python
from core.utils.performance_optimization import memoize

@memoize(maxsize=128, ttl=60.0)
def expensive_computation(symbol: str, window: int) -> float:
    # Expensive calculation
    return result
```

**TTL Guidelines:**
- Real-time data: 1-5 seconds
- Indicators: 10-60 seconds
- Static data: None (infinite)
- Research: 300+ seconds

### LRU Cache with Statistics

Monitor cache effectiveness:

```python
from core.utils.performance_optimization import LRUCache

cache = LRUCache[float](maxsize=100, ttl=60.0)

# Use cache
cache.set("key", 42.0)
value = cache.get("key")

# Monitor performance
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")

# Tune based on stats:
# - Hit rate < 50%: Increase maxsize or TTL
# - Hit rate > 95%: Reduce maxsize to save memory
```

### Multi-Layer Caching

Implement tiered caching for different access patterns:

```python
# L1: Hot data, small, fast
l1_cache = LRUCache(maxsize=100, ttl=10.0)

# L2: Warm data, larger, slower
l2_cache = LRUCache(maxsize=1000, ttl=300.0)

def get_data(key):
    # Check L1
    value = l1_cache.get(key)
    if value is not None:
        return value
    
    # Check L2
    value = l2_cache.get(key)
    if value is not None:
        l1_cache.set(key, value)  # Promote to L1
        return value
    
    # Fetch from source
    value = fetch_from_source(key)
    l2_cache.set(key, value)
    l1_cache.set(key, value)
    return value
```

## Performance Monitoring

### Profiling Decorators

Use the `@timed` decorator to identify bottlenecks:

```python
from core.utils.performance_optimization import timed

@timed
def slow_operation():
    # Automatically logs if > 0.1s
    expensive_work()
```

### Benchmark Tests

Create performance regression tests:

```python
import pytest
from core.utils.performance_optimization import memoize

def test_memoize_performance():
    """Ensure memoization provides expected speedup."""
    
    def expensive_func(n):
        return sum(i**2 for i in range(n))
    
    # Without cache
    start = time.perf_counter()
    for _ in range(100):
        expensive_func(1000)
    no_cache_time = time.perf_counter() - start
    
    # With cache
    cached_func = memoize(maxsize=10)(expensive_func)
    start = time.perf_counter()
    for _ in range(100):
        cached_func(1000)
    cache_time = time.perf_counter() - start
    
    # Should be 10x+ faster
    assert cache_time < no_cache_time * 0.1
```

### Memory Profiling

Track memory usage for optimization targets:

```python
import tracemalloc

tracemalloc.start()

# Code to profile
process_large_dataset()

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1e6:.1f} MB")
print(f"Peak: {peak / 1e6:.1f} MB")

tracemalloc.stop()
```

## Quick Wins Checklist

When optimizing a module, check:

- [ ] All frequently instantiated dataclasses use `slots=True`
- [ ] Heavy imports use TYPE_CHECKING
- [ ] Loops replaced with vectorized operations
- [ ] Expensive functions use `@memoize`
- [ ] Large arrays use chunked processing
- [ ] float32 used for indicators (where appropriate)
- [ ] Object pools for frequently created/destroyed objects
- [ ] Cache statistics monitored and tuned
- [ ] Performance tests prevent regressions

## Performance Targets

### Latency
- P50: < 50ms
- P95: < 100ms
- P99: < 200ms

### Throughput
- Indicators: > 1000 ops/s
- Order processing: > 500 ops/s
- Market data: > 5000 updates/s

### Resource Usage
- Memory: < 4GB per process
- CPU: < 70% average
- GC pauses: < 10ms

## Further Reading

- [Python Performance Tips](https://wiki.python.org/moin/PythonSpeed/PerformanceTips)
- [NumPy Performance](https://numpy.org/doc/stable/user/c-info.beyond-basics.html)
- [Dataclass __slots__](https://docs.python.org/3/library/dataclasses.html#slots)
- [Python Memory Management](https://realpython.com/python-memory-management/)

## Support

For optimization questions or performance issues:
1. Check existing benchmarks in `tests/performance/`
2. Review `core/utils/performance_optimization.py` utilities
3. Consult team performance champion
4. File issue with `performance` label
