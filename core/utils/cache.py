# SPDX-License-Identifier: MIT
"""Multi-tier caching system with adaptive TTL, eviction and observability.

This module implements a production-grade caching subsystem tailored for
TradePulse's latency sensitive workloads.  The design goals are:

* Deterministic key normalisation to avoid duplicate entries caused by
  semantically equivalent keys that differ in formatting.
* Layered caches with independent eviction policies and adaptive TTL control.
* Support for heterogeneous artefacts: previous responses, prompts and
  arbitrary data samples, plus a vector index for semantic lookups.
* Built-in observability including hit-rate tracking and cold region
  detection so that cache warmup strategies can be adjusted dynamically.

The implementation embraces thread-safety and small, composable components to
keep the system maintainable.  All public types are fully typed to ease future
extension and static analysis.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, MutableMapping

import numpy as np

from .logging import StructuredLogger


logger = StructuredLogger(__name__)


# ---------------------------------------------------------------------------
# Key normalisation utilities


class CacheKeyNormalizer:
    """Canonicalises cache keys to avoid semantic duplication.

    The normaliser is purposely strict: whitespace is trimmed, dictionaries
    are serialised with sorted keys and non-JSONable types fall back to the
    repr() representation.  The output is always a string safe for use as a
    dictionary key.
    """

    @staticmethod
    def normalize(key: Any) -> str:
        if isinstance(key, str):
            return key.strip()
        if isinstance(key, (int, float, bytes)):
            return str(key)
        if isinstance(key, Mapping):
            normalized_items = {
                CacheKeyNormalizer.normalize(k): CacheKeyNormalizer.normalize(v)
                for k, v in sorted(key.items(), key=lambda item: CacheKeyNormalizer.normalize(item[0]))
            }
            return CacheKeyNormalizer.normalize(normalized_items.items())
        if isinstance(key, (set, frozenset, tuple, list)):
            normalized_sequence = [CacheKeyNormalizer.normalize(item) for item in key]
            return "|".join(normalized_sequence)
        if hasattr(key, "__dict__"):
            return CacheKeyNormalizer.normalize(vars(key))
        return repr(key)


# ---------------------------------------------------------------------------
# TTL strategies


class TTLStrategy(ABC):
    """Defines the interface for TTL computations."""

    @abstractmethod
    def compute_ttl(
        self,
        key: str,
        value: Any,
        *,
        layer_name: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> float | None:
        """Return TTL in seconds or ``None`` for infinite retention."""


@dataclass(slots=True)
class AdaptiveTTLStrategy(TTLStrategy):
    """Adaptive TTL that extends lifetimes for hot entries.

    Parameters
    ----------
    base_ttl: float
        Baseline TTL that will be applied to new entries.
    max_ttl: float
        Maximum TTL after adaptions.
    hot_hit_threshold: int
        Number of hits after which the TTL is doubled, up to ``max_ttl``.
    cooldown_factor: float
        Multiplicative factor applied when the cache entry is considered cold.
    """

    base_ttl: float
    max_ttl: float
    hot_hit_threshold: int = 5
    cooldown_factor: float = 0.5

    def compute_ttl(
        self,
        key: str,
        value: Any,
        *,
        layer_name: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> float:
        metadata = metadata or {}
        hits = int(metadata.get("hits", 0))
        last_access_delta = float(metadata.get("seconds_since_last_access", 0.0))

        ttl = self.base_ttl
        if hits >= self.hot_hit_threshold:
            ttl = min(self.max_ttl, ttl * 2)
        elif last_access_delta > self.base_ttl:
            ttl = max(self.base_ttl * self.cooldown_factor, ttl * self.cooldown_factor)

        logger.debug(
            "Computed TTL",
            key=key,
            layer=layer_name,
            hits=hits,
            ttl=ttl,
        )
        return ttl


# ---------------------------------------------------------------------------
# Eviction policies


class EvictionPolicy(ABC):
    """Base contract for eviction policies."""

    @abstractmethod
    def on_insert(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def on_access(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def choose_eviction_candidates(self, limit: int) -> list[str]:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def on_remove(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def compact(self, valid_keys: Iterable[str]) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class LRUEvictionPolicy(EvictionPolicy):
    """Least-Recently-Used eviction strategy."""

    def __init__(self) -> None:
        self._order: "OrderedDict[str, None]" = OrderedDict()
        self._lock = RLock()

    def on_insert(self, key: str) -> None:
        with self._lock:
            self._order[key] = None
            self._order.move_to_end(key)

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._order:
                self._order.move_to_end(key)

    def choose_eviction_candidates(self, limit: int) -> list[str]:
        with self._lock:
            victims = []
            for _ in range(min(limit, len(self._order))):
                victim_key, _ = self._order.popitem(last=False)
                victims.append(victim_key)
            return victims

    def on_remove(self, key: str) -> None:
        with self._lock:
            self._order.pop(key, None)

    def compact(self, valid_keys: Iterable[str]) -> None:
        with self._lock:
            valid_key_set = set(valid_keys)
            for key in list(self._order.keys()):
                if key not in valid_key_set:
                    self._order.pop(key, None)


class LFUEvictionPolicy(EvictionPolicy):
    """Least-Frequently-Used eviction strategy."""

    def __init__(self) -> None:
        self._frequency: MutableMapping[str, int] = defaultdict(int)
        self._lock = RLock()

    def on_insert(self, key: str) -> None:
        with self._lock:
            self._frequency[key] = 1

    def on_access(self, key: str) -> None:
        with self._lock:
            if key in self._frequency:
                self._frequency[key] += 1

    def choose_eviction_candidates(self, limit: int) -> list[str]:
        with self._lock:
            sorted_items = sorted(self._frequency.items(), key=lambda item: item[1])
            victims = [key for key, _ in sorted_items[:limit]]
            for victim in victims:
                self._frequency.pop(victim, None)
            return victims

    def on_remove(self, key: str) -> None:
        with self._lock:
            self._frequency.pop(key, None)

    def compact(self, valid_keys: Iterable[str]) -> None:
        with self._lock:
            valid_keys_set = set(valid_keys)
            for key in list(self._frequency.keys()):
                if key not in valid_keys_set:
                    self._frequency.pop(key, None)


# ---------------------------------------------------------------------------
# Cache entry and metrics


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float | None
    created_at: float = field(default_factory=monotonic)
    hits: int = 0
    last_access_at: float = field(default_factory=monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = monotonic() if now is None else now
        return now >= self.expires_at

    def touch(self) -> None:
        self.hits += 1
        self.last_access_at = monotonic()


@dataclass(slots=True)
class CacheMetrics:
    """Observability for cache performance."""

    hits: Counter = field(default_factory=Counter)
    misses: Counter = field(default_factory=Counter)

    def record_hit(self, layer: str, region: str) -> None:
        self.hits[(layer, region)] += 1

    def record_miss(self, layer: str, region: str) -> None:
        self.misses[(layer, region)] += 1

    def region_hit_rate(self, region: str) -> float:
        hits = sum(count for (layer, reg), count in self.hits.items() if reg == region)
        misses = sum(count for (layer, reg), count in self.misses.items() if reg == region)
        total = hits + misses
        return hits / total if total else 1.0

    def layer_stats(self) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for (layer, region), count in self.hits.items():
            stats[layer][f"{region}_hits"] = count
        for (layer, region), count in self.misses.items():
            stats[layer][f"{region}_misses"] = count
        for layer, region_data in stats.items():
            for region in list(region_data.keys()):
                if region.endswith("_hits"):
                    region_name = region[:-5]
                    hits = region_data[region]
                    misses = region_data.get(f"{region_name}_misses", 0.0)
                    total = hits + misses
                    region_data[f"{region_name}_hit_rate"] = hits / total if total else 1.0
        return stats

    def identify_cold_regions(self, *, threshold: float, min_requests: int) -> list[str]:
        cold_regions: list[str] = []
        regions = {
            region for (_, region) in {**self.hits, **self.misses}
        }
        for region in regions:
            hits = sum(count for (layer, reg), count in self.hits.items() if reg == region)
            misses = sum(count for (layer, reg), count in self.misses.items() if reg == region)
            total = hits + misses
            if total < min_requests:
                continue
            hit_rate = hits / total if total else 1.0
            if hit_rate < threshold:
                cold_regions.append(region)
        return cold_regions


# ---------------------------------------------------------------------------
# Cache layers


class CacheLayer(ABC):
    """Base class for cache layers."""

    def __init__(
        self,
        name: str,
        *,
        max_entries: int,
        ttl_strategy: TTLStrategy,
        eviction_policy: EvictionPolicy,
        region: str,
        metrics: CacheMetrics,
    ) -> None:
        self.name = name
        self.max_entries = max_entries
        self.ttl_strategy = ttl_strategy
        self.eviction_policy = eviction_policy
        self.region = region
        self.metrics = metrics

    @abstractmethod
    def get(self, key: Any) -> Any | None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def set(self, key: Any, value: Any, *, metadata: Mapping[str, Any] | None = None) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def invalidate(self, key: Any) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def compact(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def warmup(self, data: Iterable[tuple[Any, Any]]) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryCacheLayer(CacheLayer):
    """Thread-safe in-memory cache layer."""

    def __init__(
        self,
        name: str,
        *,
        max_entries: int,
        ttl_strategy: TTLStrategy,
        eviction_policy: EvictionPolicy,
        region: str,
        metrics: CacheMetrics,
    ) -> None:
        super().__init__(
            name,
            max_entries=max_entries,
            ttl_strategy=ttl_strategy,
            eviction_policy=eviction_policy,
            region=region,
            metrics=metrics,
        )
        self._store: Dict[str, CacheEntry] = {}
        self._lock = RLock()

    def _ensure_capacity(self) -> None:
        over_capacity = max(len(self._store) - self.max_entries + 1, 0)
        if over_capacity <= 0:
            return
        victims = self.eviction_policy.choose_eviction_candidates(over_capacity)
        for victim_key in victims:
            self._store.pop(victim_key, None)
            logger.debug("Evicted key", layer=self.name, key=victim_key)

    def get(self, key: Any) -> Any | None:
        normalized_key = CacheKeyNormalizer.normalize(key)
        with self._lock:
            entry = self._store.get(normalized_key)
            if entry is None:
                self.metrics.record_miss(self.name, self.region)
                return None
            if entry.is_expired():
                self.metrics.record_miss(self.name, self.region)
                self.invalidate(normalized_key)
                return None
            entry.touch()
            self.eviction_policy.on_access(normalized_key)
            self.metrics.record_hit(self.name, self.region)
            return entry.value

    def set(self, key: Any, value: Any, *, metadata: Mapping[str, Any] | None = None) -> None:
        normalized_key = CacheKeyNormalizer.normalize(key)
        with self._lock:
            existing_entry = self._store.get(normalized_key)
            context_metadata = {
                "hits": existing_entry.hits if existing_entry else 0,
                "seconds_since_last_access": (
                    monotonic() - existing_entry.last_access_at if existing_entry else 0.0
                ),
            }
            if metadata:
                context_metadata.update(metadata)
            ttl = self.ttl_strategy.compute_ttl(
                normalized_key,
                value,
                layer_name=self.name,
                metadata=context_metadata,
            )
            expires_at = monotonic() + ttl if ttl is not None else None
            entry = CacheEntry(value=value, expires_at=expires_at, metadata=dict(context_metadata))
            self._ensure_capacity()
            self._store[normalized_key] = entry
            self.eviction_policy.on_insert(normalized_key)

    def invalidate(self, key: Any) -> None:
        normalized_key = CacheKeyNormalizer.normalize(key)
        with self._lock:
            if normalized_key in self._store:
                self._store.pop(normalized_key, None)
                self.eviction_policy.on_remove(normalized_key)

    def compact(self) -> None:
        with self._lock:
            now = monotonic()
            expired_keys = [key for key, entry in self._store.items() if entry.is_expired(now)]
            for key in expired_keys:
                self._store.pop(key, None)
                self.eviction_policy.on_remove(key)
            self.eviction_policy.compact(self._store.keys())

    def warmup(self, data: Iterable[tuple[Any, Any]]) -> None:
        for key, value in data:
            self.set(key, value)


# ---------------------------------------------------------------------------
# Vector index layer


@dataclass(slots=True)
class VectorRecord:
    key: str
    vector: np.ndarray
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorIndexLayer:
    """Lightweight semantic index for prompts or responses."""

    def __init__(self, *, region: str, metrics: CacheMetrics, similarity: str = "cosine") -> None:
        self.region = region
        self.metrics = metrics
        self.similarity = similarity
        self._records: list[VectorRecord] = []
        self._lock = RLock()

    def add(self, key: Any, vector: np.ndarray, value: Any, *, metadata: Mapping[str, Any] | None = None) -> None:
        normalized_key = CacheKeyNormalizer.normalize(key)
        record = VectorRecord(
            key=normalized_key,
            vector=vector.astype(np.float32),
            value=value,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._records.append(record)

    def query(
        self,
        vector: np.ndarray,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[tuple[Any, float, dict[str, Any]]]:
        vector = vector.astype(np.float32)
        with self._lock:
            if not self._records:
                self.metrics.record_miss("vector_index", self.region)
                return []
            vectors = np.stack([record.vector for record in self._records])
            if self.similarity == "cosine":
                norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(vector)
                norms[norms == 0] = 1e-12
                scores = vectors @ vector / norms
            else:
                diff = vectors - vector
                scores = -np.linalg.norm(diff, axis=1)
            best_indices = np.argsort(scores)[::-1][:top_k]
            results: list[tuple[Any, float, dict[str, Any]]] = []
            for idx in best_indices:
                score = float(scores[idx])
                if score < min_score:
                    continue
                record = self._records[idx]
                self.metrics.record_hit("vector_index", self.region)
                results.append((record.value, score, dict(record.metadata)))
            if not results:
                self.metrics.record_miss("vector_index", self.region)
            return results

    def compact(self, *, max_records: int | None = None) -> None:
        with self._lock:
            if max_records is None or len(self._records) <= max_records:
                return
            self._records = self._records[-max_records:]

    def warmup(self, records: Iterable[tuple[Any, np.ndarray, Any, Mapping[str, Any] | None]]) -> None:
        for key, vector, value, metadata in records:
            self.add(key, vector, value, metadata=metadata)


# ---------------------------------------------------------------------------
# Cache orchestrator


WarmupSource = Callable[[], Iterable[tuple[Any, Any]]]


@dataclass(slots=True)
class CacheRegionConfig:
    name: str
    layers: list[InMemoryCacheLayer]
    warmup_source: WarmupSource | None = None


class MultiTierCache:
    """Co-ordinates cache layers for different artefact types."""

    def __init__(
        self,
        *,
        metrics: CacheMetrics | None = None,
    ) -> None:
        self.metrics = metrics or CacheMetrics()
        self._regions: dict[str, CacheRegionConfig] = {}
        self.vector_index = VectorIndexLayer(region="semantic", metrics=self.metrics)
        self._lock = RLock()

    def register_region(
        self,
        name: str,
        *,
        layers: list[InMemoryCacheLayer],
        warmup_source: WarmupSource | None = None,
    ) -> None:
        for layer in layers:
            if layer.region != name:
                raise ValueError("Layer region mismatch")
        config = CacheRegionConfig(name=name, layers=layers, warmup_source=warmup_source)
        with self._lock:
            self._regions[name] = config
        if warmup_source is not None:
            self.warmup_region(name)

    def warmup_region(self, region: str) -> None:
        config = self._regions.get(region)
        if config is None or config.warmup_source is None:
            return
        payload = list(config.warmup_source())
        logger.info("Warmup region", region=region, entries=len(payload))
        for layer in config.layers:
            layer.warmup(payload)

    def get(self, key: Any, *, region: str) -> Any | None:
        config = self._regions.get(region)
        if config is None:
            raise KeyError(f"Unknown cache region: {region}")
        for layer in config.layers:
            value = layer.get(key)
            if value is not None:
                # propagate to hotter layers if hit on colder layer
                for previous_layer in config.layers:
                    if previous_layer is layer:
                        break
                    previous_layer.set(key, value)
                return value
        return None

    def set(
        self,
        key: Any,
        value: Any,
        *,
        region: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        config = self._regions.get(region)
        if config is None:
            raise KeyError(f"Unknown cache region: {region}")
        for layer in config.layers:
            layer.set(key, value, metadata=metadata)

    def invalidate(self, key: Any, *, region: str) -> None:
        config = self._regions.get(region)
        if config is None:
            return
        for layer in config.layers:
            layer.invalidate(key)

    def compact(self) -> None:
        for config in self._regions.values():
            for layer in config.layers:
                layer.compact()
        self.vector_index.compact()

    def control_cold_regions(
        self,
        *,
        threshold: float,
        min_requests: int,
        remediate: Callable[[str], None] | None = None,
    ) -> list[str]:
        cold_regions = self.metrics.identify_cold_regions(
            threshold=threshold,
            min_requests=min_requests,
        )
        for region in cold_regions:
            logger.warning("Cold cache region detected", region=region)
            if remediate:
                remediate(region)
        return cold_regions

    def region_hit_rate(self, region: str) -> float:
        return self.metrics.region_hit_rate(region)

    def observe(self) -> dict[str, dict[str, float]]:
        return self.metrics.layer_stats()


def build_default_cache_system() -> MultiTierCache:
    """Create a ready-to-use multi-tier cache with sensible defaults."""

    metrics = CacheMetrics()

    def _mk_layers(region: str) -> list[InMemoryCacheLayer]:
        hot_layer = InMemoryCacheLayer(
            f"{region}_hot",
            max_entries=256,
            ttl_strategy=AdaptiveTTLStrategy(base_ttl=30.0, max_ttl=300.0),
            eviction_policy=LRUEvictionPolicy(),
            region=region,
            metrics=metrics,
        )
        warm_layer = InMemoryCacheLayer(
            f"{region}_warm",
            max_entries=2048,
            ttl_strategy=AdaptiveTTLStrategy(base_ttl=300.0, max_ttl=3600.0),
            eviction_policy=LFUEvictionPolicy(),
            region=region,
            metrics=metrics,
        )
        return [hot_layer, warm_layer]

    cache = MultiTierCache(metrics=metrics)

    cache.register_region("responses", layers=_mk_layers("responses"))
    cache.register_region("prompts", layers=_mk_layers("prompts"))
    cache.register_region("samples", layers=_mk_layers("samples"))

    return cache


__all__ = [
    "AdaptiveTTLStrategy",
    "CacheEntry",
    "CacheKeyNormalizer",
    "CacheLayer",
    "CacheMetrics",
    "CacheRegionConfig",
    "InMemoryCacheLayer",
    "LFUEvictionPolicy",
    "LRUEvictionPolicy",
    "MultiTierCache",
    "TTLStrategy",
    "VectorIndexLayer",
    "VectorRecord",
    "build_default_cache_system",
]

