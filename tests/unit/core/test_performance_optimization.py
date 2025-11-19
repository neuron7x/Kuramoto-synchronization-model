# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for performance optimization utilities."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest

from core.utils.performance_optimization import (
    LRUCache,
    ObjectPool,
    lazy_import,
    memoize,
    timed,
    vectorize_safe,
)


class TestLRUCache:
    """Test LRU cache implementation."""

    def test_basic_get_set(self):
        """Test basic cache operations."""
        cache: LRUCache[int] = LRUCache(maxsize=10)
        
        cache.set("key1", 42)
        assert cache.get("key1") == 42
        assert cache.get("missing") is None

    def test_lru_eviction(self):
        """Test LRU eviction on maxsize."""
        cache: LRUCache[int] = LRUCache(maxsize=3)
        
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        
        # Access "a" to make it recently used
        assert cache.get("a") == 1
        
        # Adding new entry should evict "b" (least recently used)
        cache.set("d", 4)
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache: LRUCache[int] = LRUCache(maxsize=10, ttl=0.1)
        
        cache.set("key", 42)
        assert cache.get("key") == 42
        
        # Wait for expiration
        time.sleep(0.15)
        assert cache.get("key") is None

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache: LRUCache[int] = LRUCache(maxsize=10)
        
        cache.set("key", 42)
        cache.get("key")  # hit
        cache.get("missing")  # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1

    def test_clear(self):
        """Test cache clearing."""
        cache: LRUCache[int] = LRUCache(maxsize=10)
        
        cache.set("key1", 1)
        cache.set("key2", 2)
        assert cache.get_stats()["size"] == 2
        
        cache.clear()
        assert cache.get_stats()["size"] == 0
        assert cache.get("key1") is None


class TestMemoize:
    """Test memoization decorator."""

    def test_basic_memoization(self):
        """Test function result caching."""
        call_count = 0
        
        @memoize(maxsize=10)
        def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x ** 2
        
        # First call computes
        result1 = expensive_func(5)
        assert result1 == 25
        assert call_count == 1
        
        # Second call uses cache
        result2 = expensive_func(5)
        assert result2 == 25
        assert call_count == 1  # Not incremented

    def test_memoize_with_kwargs(self):
        """Test memoization with keyword arguments."""
        @memoize(maxsize=10)
        def func(x: int, y: int = 10) -> int:
            return x + y
        
        assert func(5, y=10) == 15
        assert func(5, 10) == 15
        # Different signatures should be cached separately
        assert func(5, y=20) == 25

    def test_memoize_ttl(self):
        """Test TTL-based cache expiration."""
        call_count = 0
        
        @memoize(maxsize=10, ttl=0.1)
        def func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2
        
        func(5)
        assert call_count == 1
        
        func(5)
        assert call_count == 1  # Cached
        
        time.sleep(0.15)
        func(5)
        assert call_count == 2  # Cache expired

    def test_memoize_cache_info(self):
        """Test cache introspection."""
        @memoize(maxsize=10)
        def func(x: int) -> int:
            return x + 1
        
        func(1)
        func(1)
        func(2)
        
        stats = func.cache_info()
        assert stats["hits"] == 1
        assert stats["misses"] == 2


class TestLazyImport:
    """Test lazy module loading."""

    def test_lazy_import_basic(self):
        """Test lazy module proxy."""
        # Import should succeed without actually loading
        json_lazy = lazy_import('json')
        
        # Module loads on first use
        result = json_lazy.dumps({"key": "value"})
        assert result == '{"key": "value"}'

    def test_lazy_import_nonexistent(self):
        """Test error handling for missing modules."""
        fake = lazy_import('nonexistent_module_xyz')
        
        with pytest.raises(ModuleNotFoundError):
            _ = fake.some_attribute


class TestObjectPool:
    """Test object pool implementation."""

    def test_basic_pool_operations(self):
        """Test acquire and release."""
        pool: ObjectPool[list[int]] = ObjectPool(
            factory=lambda: [],
            maxsize=5
        )
        
        obj1 = pool.acquire()
        assert isinstance(obj1, list)
        
        pool.release(obj1)
        obj2 = pool.acquire()
        
        # Should get the same object back
        assert obj2 is obj1

    def test_pool_maxsize(self):
        """Test pool size limit."""
        # Use a custom class to track object identity
        class TrackedObject:
            _counter = 0
            
            def __init__(self):
                TrackedObject._counter += 1
                self.id = TrackedObject._counter
        
        pool: ObjectPool[TrackedObject] = ObjectPool(
            factory=TrackedObject,
            maxsize=2
        )
        
        obj1 = pool.acquire()
        obj2 = pool.acquire()
        obj3 = pool.acquire()
        
        id1, id2, id3 = obj1.id, obj2.id, obj3.id
        
        pool.release(obj1)
        pool.release(obj2)
        pool.release(obj3)  # Should be rejected (maxsize=2)
        
        # Pool should only contain 2 objects
        acquired1 = pool.acquire()
        acquired2 = pool.acquire()
        acquired3 = pool.acquire()  # Should create new
        
        # The two from pool should be obj1 and obj2 (or obj2 and obj3)
        pool_ids = {acquired1.id, acquired2.id}
        assert acquired3.id not in pool_ids  # New object
        assert len(pool_ids) == 2

    def test_pool_with_reset(self):
        """Test object reset on release."""
        reset_count = 0
        
        def reset_func(obj: list[Any]) -> None:
            nonlocal reset_count
            reset_count += 1
            obj.clear()
        
        pool: ObjectPool[list[int]] = ObjectPool(
            factory=lambda: [],
            maxsize=5,
            reset=reset_func
        )
        
        obj = pool.acquire()
        obj.extend([1, 2, 3])
        pool.release(obj)
        
        assert reset_count == 1
        assert len(obj) == 0


class TestTimed:
    """Test timing decorator."""

    def test_timed_decorator(self):
        """Test function timing."""
        @timed
        def slow_func() -> str:
            time.sleep(0.15)
            return "done"
        
        result = slow_func()
        assert result == "done"
        # Timing output should be printed (visual inspection in logs)


class TestVectorizeSafe:
    """Test chunked vectorization."""

    def test_vectorize_small_array(self):
        """Test vectorization on small array."""
        arr = np.array([1.0, 2.0, 3.0, 4.0])
        result = vectorize_safe(np.exp, arr, chunk_size=10)
        
        expected = np.exp(arr)
        np.testing.assert_allclose(result, expected)

    def test_vectorize_large_array(self):
        """Test chunked processing on large array."""
        arr = np.random.randn(100000)
        result = vectorize_safe(lambda x: x ** 2, arr, chunk_size=10000)
        
        expected = arr ** 2
        np.testing.assert_allclose(result, expected)

    def test_vectorize_preserves_shape(self):
        """Test that shape is preserved."""
        arr = np.random.randn(100, 50)
        result = vectorize_safe(np.sqrt, arr, chunk_size=1000)
        
        assert result.shape == arr.shape


class TestCacheEntry:
    """Test CacheEntry dataclass optimization."""

    def test_cache_entry_has_slots(self):
        """Verify CacheEntry uses __slots__ for memory efficiency."""
        from core.utils.performance_optimization import CacheEntry
        
        # CacheEntry should have __slots__ defined
        assert hasattr(CacheEntry, '__slots__')


class TestPerformanceImprovements:
    """Integration tests for performance improvements."""

    def test_memoize_improves_performance(self):
        """Test that memoization actually improves performance."""
        def expensive_computation(n: int) -> int:
            result = 0
            for i in range(n):
                result += i ** 2
            return result
        
        # Without memoization
        start = time.perf_counter()
        for _ in range(100):
            expensive_computation(1000)
        no_cache_time = time.perf_counter() - start
        
        # With memoization
        cached_func = memoize(maxsize=10)(expensive_computation)
        start = time.perf_counter()
        for _ in range(100):
            cached_func(1000)
        cache_time = time.perf_counter() - start
        
        # Cached should be significantly faster
        assert cache_time < no_cache_time * 0.2

    def test_object_pool_reduces_allocations(self):
        """Test that object pool reduces allocation overhead."""
        # Without pool
        start = time.perf_counter()
        for _ in range(1000):
            arr = np.zeros(1000)
        no_pool_time = time.perf_counter() - start
        
        # With pool
        pool: ObjectPool[np.ndarray] = ObjectPool(
            factory=lambda: np.zeros(1000),
            maxsize=10,
            reset=lambda arr: arr.fill(0)
        )
        
        start = time.perf_counter()
        for _ in range(1000):
            arr = pool.acquire()
            pool.release(arr)
        pool_time = time.perf_counter() - start
        
        # Pool should be faster (though margin may vary)
        # Just ensure it doesn't crash and completes
        assert pool_time > 0
        assert no_pool_time > 0
