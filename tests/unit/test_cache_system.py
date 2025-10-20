from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from core.utils.cache import (
    AdaptiveTTLStrategy,
    CacheKeyNormalizer,
    CacheMetrics,
    InMemoryCacheLayer,
    LRUEvictionPolicy,
    MultiTierCache,
    build_default_cache_system,
)


class _ConstantTTLStrategy(AdaptiveTTLStrategy):
    """Deterministic TTL strategy for tests."""

    def compute_ttl(self, key, value, *, layer_name, metadata=None):  # type: ignore[override]
        return self.base_ttl


def test_key_normalizer_handles_nested_collections() -> None:
    key_a = {"b": 1, "a": [2, 3]}
    key_b = {"a": (2, 3), "b": 1}

    assert CacheKeyNormalizer.normalize(key_a) == CacheKeyNormalizer.normalize(key_b)


def test_in_memory_cache_promotes_hot_entries() -> None:
    metrics = CacheMetrics()
    ttl = _ConstantTTLStrategy(base_ttl=10.0, max_ttl=10.0)
    hot_layer = InMemoryCacheLayer(
        "hot",
        max_entries=2,
        ttl_strategy=ttl,
        eviction_policy=LRUEvictionPolicy(),
        region="responses",
        metrics=metrics,
    )
    warm_layer = InMemoryCacheLayer(
        "warm",
        max_entries=2,
        ttl_strategy=ttl,
        eviction_policy=LRUEvictionPolicy(),
        region="responses",
        metrics=metrics,
    )

    cache = MultiTierCache(metrics=metrics)
    cache.register_region("responses", layers=[hot_layer, warm_layer])

    # Seed only the warm layer to simulate a colder tier hit.
    warm_layer.set("foo", "bar")

    assert cache.get("foo", region="responses") == "bar"
    assert hot_layer.get("foo") == "bar"


def test_adaptive_ttl_increases_for_hot_keys() -> None:
    metrics = CacheMetrics()
    ttl_strategy = AdaptiveTTLStrategy(base_ttl=10.0, max_ttl=100.0, hot_hit_threshold=2)
    layer = InMemoryCacheLayer(
        "layer",
        max_entries=5,
        ttl_strategy=ttl_strategy,
        eviction_policy=LRUEvictionPolicy(),
        region="samples",
        metrics=metrics,
    )

    layer.set("alpha", 1)
    for _ in range(3):
        assert layer.get("alpha") == 1
    layer.set("alpha", 2)

    entry = layer._store[CacheKeyNormalizer.normalize("alpha")]  # type: ignore[attr-defined]
    assert entry.expires_at is not None
    ttl_seconds = entry.expires_at - entry.created_at
    assert ttl_seconds > 10.0


def test_vector_index_returns_ranked_matches() -> None:
    cache = build_default_cache_system()
    vector = np.array([1.0, 0.0], dtype=np.float32)
    cache.vector_index.add("prompt:1", vector, {"prompt": "alpha"})
    cache.vector_index.add("prompt:2", np.array([0.0, 1.0], dtype=np.float32), {"prompt": "beta"})

    results = cache.vector_index.query(np.array([0.9, 0.1], dtype=np.float32), top_k=1)
    assert results
    value, score, metadata = results[0]
    assert value["prompt"] == "alpha"
    assert score > 0.5
    assert metadata == {}


def test_control_cold_regions_flags_low_hit_rate() -> None:
    metrics = CacheMetrics()
    ttl = _ConstantTTLStrategy(base_ttl=10.0, max_ttl=10.0)
    layer = InMemoryCacheLayer(
        "layer",
        max_entries=5,
        ttl_strategy=ttl,
        eviction_policy=LRUEvictionPolicy(),
        region="prompts",
        metrics=metrics,
    )
    cache = MultiTierCache(metrics=metrics)
    cache.register_region("prompts", layers=[layer])

    for _ in range(3):
        cache.get("missing", region="prompts")

    cold_regions: list[str] = []

    def remediation(region: str) -> None:
        cold_regions.append(region)

    flagged = cache.control_cold_regions(threshold=0.5, min_requests=2, remediate=remediation)
    assert flagged == ["prompts"]
    assert cold_regions == ["prompts"]


def test_warmup_populates_region(tmp_path) -> None:
    metrics = CacheMetrics()
    ttl = _ConstantTTLStrategy(base_ttl=10.0, max_ttl=10.0)

    def warmup_source() -> Iterable[tuple[str, str]]:
        return [("hello", "world")]

    layer = InMemoryCacheLayer(
        "layer",
        max_entries=5,
        ttl_strategy=ttl,
        eviction_policy=LRUEvictionPolicy(),
        region="samples",
        metrics=metrics,
    )

    cache = MultiTierCache(metrics=metrics)
    cache.register_region("samples", layers=[layer], warmup_source=warmup_source)

    assert cache.get("hello", region="samples") == "world"

