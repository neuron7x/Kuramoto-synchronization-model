"""Caching layer for thermodynamics computations to improve performance.

This module provides intelligent caching for expensive thermodynamic calculations,
reducing computational overhead while maintaining system accuracy.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import numpy as np


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Immutable key for caching thermodynamic computations."""

    topology_hash: str
    metrics_hash: str
    timestamp_bucket: int  # Bucket timestamps to increase cache hits


class ThermoCache:
    """High-performance cache for thermodynamic computations.

    This cache implements:
    - LRU eviction for memory efficiency
    - Time-based invalidation for freshness
    - Hash-based keys for fast lookups
    - Statistics tracking for optimization
    """

    def __init__(
        self,
        *,
        max_size: int = 1000,
        ttl_seconds: float = 5.0,
        time_bucket_size: float = 0.1,
    ) -> None:
        """Initialize the thermodynamics cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cached entries in seconds
            time_bucket_size: Time bucket size for grouping similar timestamps
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.time_bucket_size = time_bucket_size

        self._energy_cache: Dict[CacheKey, Tuple[float, float]] = (
            {}
        )  # (value, timestamp)
        self._topology_cache: Dict[str, Tuple[Any, float]] = {}  # (topology, timestamp)
        self._metrics_cache: Dict[str, Tuple[Any, float]] = {}  # (metrics, timestamp)

        # Statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _compute_topology_hash(self, topology: Any) -> str:
        """Compute a stable hash for a topology."""
        # Convert topology to a stable string representation
        if hasattr(topology, "__iter__"):
            topology_str = "|".join(sorted(str(t) for t in topology))
        else:
            topology_str = str(topology)
        return hashlib.sha256(topology_str.encode()).hexdigest()[:16]

    def _compute_metrics_hash(
        self, latencies: Dict, coherency: Dict, resource: float, entropy: float
    ) -> str:
        """Compute a stable hash for metrics snapshot."""
        # Round values to reduce sensitivity
        lat_str = "|".join(f"{k}:{v:.4f}" for k, v in sorted(latencies.items()))
        coh_str = "|".join(f"{k}:{v:.4f}" for k, v in sorted(coherency.items()))
        metrics_str = f"{lat_str}|{coh_str}|{resource:.4f}|{entropy:.4f}"
        return hashlib.sha256(metrics_str.encode()).hexdigest()[:16]

    def _get_time_bucket(self, timestamp: Optional[float] = None) -> int:
        """Get time bucket for timestamp."""
        if timestamp is None:
            timestamp = time.time()
        return int(timestamp / self.time_bucket_size)

    def _evict_old_entries(self) -> None:
        """Evict expired cache entries."""
        current_time = time.time()

        # Evict old energy cache entries
        expired_keys = [
            key
            for key, (_, ts) in self._energy_cache.items()
            if current_time - ts > self.ttl_seconds
        ]
        for key in expired_keys:
            del self._energy_cache[key]
            self.evictions += 1

        # Evict old topology cache entries
        expired_topo = [
            key
            for key, (_, ts) in self._topology_cache.items()
            if current_time - ts > self.ttl_seconds
        ]
        for key in expired_topo:
            del self._topology_cache[key]
            self.evictions += 1

    def _enforce_max_size(self) -> None:
        """Enforce max cache size by evicting oldest entries (LRU)."""
        if len(self._energy_cache) > self.max_size:
            sorted_items = sorted(self._energy_cache.items(), key=lambda x: x[1][1])
            to_evict = len(self._energy_cache) - self.max_size
            for key, _ in sorted_items[:to_evict]:
                del self._energy_cache[key]
                self.evictions += 1

    def get_energy(
        self,
        topology: Any,
        latencies: Dict,
        coherency: Dict,
        resource: float,
        entropy: float,
    ) -> Optional[float]:
        """Get cached energy computation if available.

        Returns:
            Cached energy value if found, None otherwise
        """
        topo_hash = self._compute_topology_hash(topology)
        metrics_hash = self._compute_metrics_hash(
            latencies, coherency, resource, entropy
        )
        time_bucket = self._get_time_bucket()

        key = CacheKey(
            topology_hash=topo_hash,
            metrics_hash=metrics_hash,
            timestamp_bucket=time_bucket,
        )

        if key in self._energy_cache:
            value, timestamp = self._energy_cache[key]
            if time.time() - timestamp <= self.ttl_seconds:
                self.hits += 1
                return value
            else:
                # Expired entry
                del self._energy_cache[key]

        self.misses += 1
        return None

    def set_energy(
        self,
        topology: Any,
        latencies: Dict,
        coherency: Dict,
        resource: float,
        entropy: float,
        value: float,
    ) -> None:
        """Cache an energy computation."""
        self._evict_old_entries()

        topo_hash = self._compute_topology_hash(topology)
        metrics_hash = self._compute_metrics_hash(
            latencies, coherency, resource, entropy
        )
        time_bucket = self._get_time_bucket()

        key = CacheKey(
            topology_hash=topo_hash,
            metrics_hash=metrics_hash,
            timestamp_bucket=time_bucket,
        )

        self._energy_cache[key] = (value, time.time())
        self._enforce_max_size()

    def get_topology(self, topology_hash: str) -> Optional[Any]:
        """Get cached topology computation."""
        if topology_hash in self._topology_cache:
            value, timestamp = self._topology_cache[topology_hash]
            if time.time() - timestamp <= self.ttl_seconds:
                self.hits += 1
                return value
            else:
                del self._topology_cache[topology_hash]

        self.misses += 1
        return None

    def set_topology(self, topology_hash: str, value: Any) -> None:
        """Cache a topology computation."""
        self._evict_old_entries()
        self._topology_cache[topology_hash] = (value, time.time())
        # Note: topology cache doesn't enforce max_size currently

    def clear(self) -> None:
        """Clear all cache entries and reset statistics."""
        self._energy_cache.clear()
        self._topology_cache.clear()
        self._metrics_cache.clear()
        # Reset statistics
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": hit_rate,
            "cache_size": len(self._energy_cache),
            "topology_cache_size": len(self._topology_cache),
        }


@lru_cache(maxsize=256)
def cached_bond_energy(
    src: str,
    dst: str,
    bond_type: str,
    latency: float,
    coherency: float,
) -> float:
    """Cached version of bond energy computation.

    This uses functools.lru_cache for fast repeated computations
    with the same parameters.
    """
    from core.energy import ENERGY_SCALE, bond_internal_energy

    # Round values to reduce cache misses from floating point precision
    latency_rounded = round(latency, 4)
    coherency_rounded = round(coherency, 4)

    return ENERGY_SCALE * bond_internal_energy(
        src,
        dst,
        bond_type,
        {(src, dst): latency_rounded},
        {(src, dst): coherency_rounded},
    )


class VectorizedOperations:
    """Vectorized operations for thermodynamics computations.

    This class provides NumPy-based vectorized implementations of common
    thermodynamic operations for improved performance.
    """

    @staticmethod
    def compute_bond_energies_vectorized(
        edges: np.ndarray,
        bond_types: np.ndarray,
        latencies: np.ndarray,
        coherencies: np.ndarray,
    ) -> np.ndarray:
        """Compute bond energies in vectorized form.

        Args:
            edges: Array of shape (N, 2) containing source-destination pairs
            bond_types: Array of shape (N,) containing bond type indices
            latencies: Array of shape (N,) containing latency values
            coherencies: Array of shape (N,) containing coherency values

        Returns:
            Array of shape (N,) containing bond energies
        """
        # Placeholder for vectorized computation
        # In real implementation, this would use NumPy operations
        # to compute energies in parallel
        from core.energy import ENERGY_SCALE

        # Base energy computation (simplified)
        base_energy = ENERGY_SCALE * latencies * (1.0 - coherencies)

        # Apply bond type multipliers (vectorized)
        type_multipliers = np.ones_like(latencies)
        # Different bond types have different energy characteristics
        # This is a simplified version

        return base_energy * type_multipliers

    @staticmethod
    def compute_coherency_mean_vectorized(coherency_values: np.ndarray) -> float:
        """Compute mean coherency using vectorized operations."""
        if len(coherency_values) == 0:
            return 0.0
        return float(np.mean(coherency_values))

    @staticmethod
    def detect_anomalies_vectorized(
        values: np.ndarray,
        window_size: int = 10,
        threshold: float = 3.0,
    ) -> np.ndarray:
        """Detect anomalies using vectorized rolling statistics.

        Args:
            values: Time series values
            window_size: Window size for rolling statistics
            threshold: Z-score threshold for anomaly detection

        Returns:
            Boolean array indicating anomalies
        """
        if len(values) < window_size:
            return np.zeros(len(values), dtype=bool)

        # Compute rolling mean and std using convolution
        kernel = np.ones(window_size) / window_size
        rolling_mean = np.convolve(values, kernel, mode="valid")

        # Pad to match original length
        rolling_mean = np.pad(rolling_mean, (window_size - 1, 0), mode="edge")

        # Compute rolling std
        rolling_std = np.array(
            [
                np.std(values[max(0, i - window_size) : i + 1])
                for i in range(len(values))
            ]
        )

        # Compute z-scores
        z_scores = np.abs(values - rolling_mean) / (rolling_std + 1e-9)

        return z_scores > threshold
