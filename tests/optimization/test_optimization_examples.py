"""Tests for optimization examples.

Validates that optimization code examples work correctly.
"""

from unittest.mock import Mock

import numpy as np
import pytest

from examples.optimization_examples import (
    AdaptivePoller,
    AdaptivePollingConfig,
    IndicatorCache,
    StreamingEventReplayer,
)


class TestStreamingEventReplayer:
    """Tests for StreamingEventReplayer optimization."""

    def test_streaming_replay_returns_iterator(self):
        """Streaming replay should return an iterator of batches."""
        replayer = StreamingEventReplayer(batch_size=10)
        replayer._fetch_batch = Mock(return_value=[])

        result = replayer.replay_events_streaming("test-id", "TestType")
        assert hasattr(result, "__iter__")


class TestAdaptivePoller:
    """Tests for AdaptivePoller optimization."""

    def test_starts_with_min_interval(self):
        """Should start with minimum interval."""
        config = AdaptivePollingConfig(min_interval=0.1, max_interval=2.0)
        poller = AdaptivePoller(config)
        assert poller._current_interval == 0.1


class TestIndicatorCache:
    """Tests for IndicatorCache optimization."""

    def test_cache_miss_computes_value(self):
        """Cache miss should compute value."""
        cache = IndicatorCache(max_size=10, ttl_seconds=60.0)

        data = np.random.randn(1000)
        compute_fn = Mock(return_value=42.0)

        result = cache.get_or_compute("test", data, compute_fn)
        assert result == 42.0
        compute_fn.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
