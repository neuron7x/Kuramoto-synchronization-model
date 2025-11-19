# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Performance optimization utilities for TradePulse system.

This module provides reusable optimization patterns and utilities to improve
system efficiency and productivity:

* Memory optimization through object pooling and caching
* Lazy module loading for faster startup
* Function memoization with configurable TTL
* Vectorized computation helpers
* Performance profiling decorators

The utilities focus on maximizing efficiency through:
- Reduced memory allocations via __slots__ and object pools
- Deferred imports for faster module initialization
- Intelligent caching strategies with LRU eviction
- Optimized NumPy operations with proper broadcasting
- Zero-copy operations where possible

Example:
    >>> from core.utils.performance_optimization import memoize, lazy_import
    >>> 
    >>> @memoize(maxsize=128)
    >>> def expensive_computation(x):
    ...     return x ** 2
    >>> 
    >>> # Lazy load heavy dependencies
    >>> scipy = lazy_import('scipy')
"""

from __future__ import annotations

import functools
import importlib
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

import numpy as np

__all__ = [
    "memoize",
    "lazy_import",
    "ObjectPool",
    "timed",
    "vectorize_safe",
    "LRUCache",
]

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    """Cache entry with value and expiration."""
    
    value: T
    timestamp: float
    access_count: int = 0


class LRUCache(Generic[T]):
    """Thread-safe LRU cache with TTL support and performance monitoring.
    
    This cache provides:
    - O(1) get/set operations using OrderedDict
    - Thread-safe access with RLock
    - Optional TTL-based expiration
    - Hit rate tracking for performance tuning
    - Automatic eviction on maxsize
    
    Args:
        maxsize: Maximum number of entries (default 128)
        ttl: Time-to-live in seconds (None = no expiration)
    
    Example:
        >>> cache = LRUCache[int](maxsize=100, ttl=60.0)
        >>> cache.set("key", 42)
        >>> value = cache.get("key")  # Returns 42
        >>> stats = cache.get_stats()  # {'hits': 1, 'misses': 0, ...}
    """
    
    def __init__(self, maxsize: int = 128, ttl: Optional[float] = None):
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive when provided")
        
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[T]:
        """Retrieve value from cache if present and not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            # Check TTL expiration
            if self.ttl is not None:
                age = time.time() - entry.timestamp
                if age > self.ttl:
                    del self._cache[key]
                    self._misses += 1
                    return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.access_count += 1
            self._hits += 1
            return entry.value
    
    def set(self, key: str, value: T) -> None:
        """Store value in cache, evicting LRU entry if at capacity."""
        with self._lock:
            # Update existing entry
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.timestamp = time.time()
                self._cache.move_to_end(key)
                return
            
            # Evict LRU entry if at capacity
            if len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
            
            # Add new entry
            self._cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                access_count=0
            )
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics for performance monitoring."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "maxsize": self.maxsize,
            }


def memoize(
    maxsize: int = 128,
    ttl: Optional[float] = None,
    typed: bool = False
) -> Callable[[F], F]:
    """Memoization decorator with LRU eviction and optional TTL.
    
    Caches function results based on arguments. More efficient than
    functools.lru_cache for our use cases due to:
    - Better integration with our monitoring
    - Optional TTL support
    - Thread-safe by default
    
    Args:
        maxsize: Maximum cache size
        ttl: Time-to-live in seconds
        typed: If True, arguments of different types are cached separately
    
    Example:
        >>> @memoize(maxsize=100, ttl=60.0)
        >>> def fibonacci(n):
        ...     if n < 2:
        ...         return n
        ...     return fibonacci(n-1) + fibonacci(n-2)
    """
    def decorator(func: F) -> F:
        cache: LRUCache[Any] = LRUCache(maxsize=maxsize, ttl=ttl)
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Create cache key from arguments
            key_parts = [str(args)]
            if kwargs:
                key_parts.append(str(sorted(kwargs.items())))
            if typed:
                key_parts.append(str([type(arg) for arg in args]))
            cache_key = "|".join(key_parts)
            
            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        # Expose cache for introspection
        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = cache.get_stats  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore
        
        return wrapper  # type: ignore
    
    return decorator


class LazyModule:
    """Proxy for lazy module loading.
    
    Defers import until first attribute access, reducing startup time
    for modules with heavy dependencies.
    
    Example:
        >>> scipy = LazyModule('scipy')
        >>> # scipy not imported yet
        >>> result = scipy.stats.norm()  # imports scipy now
    """
    
    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module: Optional[Any] = None
    
    def _load(self) -> Any:
        """Load the module if not already loaded."""
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module
    
    def __getattr__(self, name: str) -> Any:
        """Load module on first attribute access."""
        return getattr(self._load(), name)
    
    def __dir__(self) -> list[str]:
        """Return module attributes."""
        return dir(self._load())


def lazy_import(module_name: str) -> Any:
    """Create a lazy-loading module proxy.
    
    Use this to defer expensive imports until they're actually needed,
    improving module initialization time.
    
    Args:
        module_name: Fully qualified module name
    
    Returns:
        LazyModule proxy that loads on first use
    
    Example:
        >>> # In module imports section
        >>> if TYPE_CHECKING:
        >>>     import scipy
        >>> else:
        >>>     scipy = lazy_import('scipy')
    """
    return LazyModule(module_name)


class ObjectPool(Generic[T]):
    """Thread-safe object pool for reducing allocation overhead.
    
    Maintains a pool of reusable objects to minimize allocation/deallocation
    overhead for frequently created objects. Useful for:
    - NumPy arrays with fixed shapes
    - Protocol buffers / dataclasses
    - Connection objects
    
    Args:
        factory: Callable that creates new objects
        maxsize: Maximum pool size
        reset: Optional callable to reset object state before reuse
    
    Example:
        >>> pool = ObjectPool(
        ...     factory=lambda: np.zeros(1000),
        ...     maxsize=10
        ... )
        >>> arr = pool.acquire()
        >>> # use array
        >>> pool.release(arr)  # returns to pool
    """
    
    def __init__(
        self,
        factory: Callable[[], T],
        maxsize: int = 10,
        reset: Optional[Callable[[T], None]] = None
    ):
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        
        self.factory = factory
        self.maxsize = maxsize
        self.reset = reset
        self._pool: list[T] = []
        self._lock = RLock()
    
    def acquire(self) -> T:
        """Get an object from pool or create a new one."""
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self.factory()
    
    def release(self, obj: T) -> None:
        """Return an object to the pool."""
        with self._lock:
            if len(self._pool) < self.maxsize:
                if self.reset is not None:
                    self.reset(obj)
                self._pool.append(obj)
    
    def clear(self) -> None:
        """Clear the pool."""
        with self._lock:
            self._pool.clear()


def timed(func: F) -> F:
    """Decorator to measure function execution time.
    
    Logs execution time at DEBUG level. Useful for identifying
    performance bottlenecks during development.
    
    Example:
        >>> @timed
        >>> def slow_operation():
        ...     time.sleep(1)
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        
        # Use print instead of logging to avoid circular imports
        if elapsed > 0.1:  # Only log slow operations
            print(f"[PERF] {func.__name__} took {elapsed:.4f}s")
        
        return result
    
    return wrapper  # type: ignore


def vectorize_safe(
    func: Callable[[float], float],
    arr: np.ndarray,
    *,
    chunk_size: int = 10000
) -> np.ndarray:
    """Apply function to array with chunking for memory efficiency.
    
    Processes large arrays in chunks to avoid memory spikes while
    maintaining vectorization benefits.
    
    Args:
        func: Function to apply element-wise
        arr: Input array
        chunk_size: Process this many elements at a time
    
    Returns:
        Result array with same shape as input
    
    Example:
        >>> arr = np.random.randn(1000000)
        >>> result = vectorize_safe(np.exp, arr, chunk_size=10000)
    """
    if arr.size <= chunk_size:
        return np.vectorize(func)(arr)
    
    # Process in chunks
    flat = arr.ravel()
    result = np.empty_like(flat)
    
    for i in range(0, flat.size, chunk_size):
        end = min(i + chunk_size, flat.size)
        result[i:end] = np.vectorize(func)(flat[i:end])
    
    return result.reshape(arr.shape)
