# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Additional unit tests for indicator cache module to improve coverage."""
from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.indicators.cache import (
    FileSystemIndicatorCache,
    hash_input_data,
    make_fingerprint,
)


class TestHashInputData:
    """Test hash_input_data function with various data types."""

    def test_hash_numpy_array(self):
        """Test hashing of NumPy arrays."""
        arr1 = np.array([1.0, 2.0, 3.0])
        arr2 = np.array([1.0, 2.0, 3.0])
        arr3 = np.array([1.0, 2.0, 4.0])

        hash1 = hash_input_data(arr1)
        hash2 = hash_input_data(arr2)
        hash3 = hash_input_data(arr3)

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA256 hex digest

    def test_hash_pandas_dataframe(self):
        """Test hashing of pandas DataFrames."""
        df1 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df2 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df3 = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 7]})

        hash1 = hash_input_data(df1)
        hash2 = hash_input_data(df2)
        hash3 = hash_input_data(df3)

        assert hash1 == hash2
        assert hash1 != hash3

    def test_hash_pandas_series(self):
        """Test hashing of pandas Series."""
        s1 = pd.Series([1.0, 2.0, 3.0])
        s2 = pd.Series([1.0, 2.0, 3.0])
        s3 = pd.Series([1.0, 2.0, 4.0])

        hash1 = hash_input_data(s1)
        hash2 = hash_input_data(s2)
        hash3 = hash_input_data(s3)

        assert hash1 == hash2
        assert hash1 != hash3

    def test_hash_mapping(self):
        """Test hashing of dictionary/mapping data."""
        d1 = {"x": 1, "y": 2, "z": 3}
        d2 = {"z": 3, "y": 2, "x": 1}  # Different order, same content
        d3 = {"x": 1, "y": 2, "z": 4}

        hash1 = hash_input_data(d1)
        hash2 = hash_input_data(d2)
        hash3 = hash_input_data(d3)

        assert hash1 == hash2  # Order shouldn't matter
        assert hash1 != hash3

    def test_hash_sequence(self):
        """Test hashing of list/sequence data."""
        list1 = [1.0, 2.0, 3.0]
        list2 = [1.0, 2.0, 3.0]
        list3 = [1.0, 2.0, 4.0]

        hash1 = hash_input_data(list1)
        hash2 = hash_input_data(list2)
        hash3 = hash_input_data(list3)

        assert hash1 == hash2
        assert hash1 != hash3


class TestMakeFingerprint:
    """Test fingerprint generation for cache keys."""

    def test_fingerprint_deterministic(self):
        """Test that fingerprints are deterministic."""
        fp1 = make_fingerprint(
            "test_indicator",
            {"param1": 10, "param2": "value"},
            "data_hash_123",
            "v1.0.0",
        )
        fp2 = make_fingerprint(
            "test_indicator",
            {"param1": 10, "param2": "value"},
            "data_hash_123",
            "v1.0.0",
        )

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256

    def test_fingerprint_changes_with_params(self):
        """Test that fingerprints change when parameters change."""
        fp1 = make_fingerprint(
            "test_indicator", {"param": 10}, "data_hash", "v1.0.0"
        )
        fp2 = make_fingerprint(
            "test_indicator", {"param": 20}, "data_hash", "v1.0.0"
        )

        assert fp1 != fp2

    def test_fingerprint_changes_with_data_hash(self):
        """Test that fingerprints change when data hash changes."""
        fp1 = make_fingerprint(
            "test_indicator", {"param": 10}, "hash1", "v1.0.0"
        )
        fp2 = make_fingerprint(
            "test_indicator", {"param": 10}, "hash2", "v1.0.0"
        )

        assert fp1 != fp2

    def test_fingerprint_changes_with_version(self):
        """Test that fingerprints change when code version changes."""
        fp1 = make_fingerprint(
            "test_indicator", {"param": 10}, "hash", "v1.0.0"
        )
        fp2 = make_fingerprint(
            "test_indicator", {"param": 10}, "hash", "v2.0.0"
        )

        assert fp1 != fp2


class TestFileSystemIndicatorCache:
    """Test FileSystemIndicatorCache with various scenarios."""

    @pytest.fixture
    def cache_dir(self):
        """Create temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, cache_dir):
        """Create cache instance."""
        return FileSystemIndicatorCache(cache_dir, code_version="test-v1.0")

    def test_cache_initialization(self, cache):
        """Test cache initialization."""
        assert cache.root.exists()
        assert cache.code_version == "test-v1.0"

    def test_store_and_load_numpy_array(self, cache):
        """Test storing and loading NumPy arrays."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        data_hash = hash_input_data(data)

        # Store
        fingerprint = cache.store(
            indicator_name="test_indicator",
            params={"window": 5},
            data_hash=data_hash,
            value=data,
        )

        # Load
        record = cache.load(
            indicator_name="test_indicator",
            params={"window": 5},
            data_hash=data_hash,
        )

        assert record is not None
        assert record.fingerprint == fingerprint
        np.testing.assert_array_equal(record.value, data)

    def test_store_and_load_dataframe(self, cache):
        """Test storing and loading pandas DataFrames."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        data_hash = hash_input_data(df)

        cache.store(
            indicator_name="test_df",
            params={},
            data_hash=data_hash,
            value=df,
        )

        record = cache.load(
            indicator_name="test_df",
            params={},
            data_hash=data_hash,
        )

        assert record is not None
        pd.testing.assert_frame_equal(record.value, df)

    def test_store_and_load_with_metadata(self, cache):
        """Test storing and loading with metadata."""
        data = np.array([1.0, 2.0, 3.0])
        data_hash = hash_input_data(data)

        metadata = {"computation_time": 0.5, "parameters_used": True}
        coverage_start = datetime(2024, 1, 1, tzinfo=UTC)
        coverage_end = datetime(2024, 12, 31, tzinfo=UTC)

        cache.store(
            indicator_name="test_meta",
            params={"window": 10},
            data_hash=data_hash,
            value=data,
            metadata=metadata,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

        record = cache.load(
            indicator_name="test_meta",
            params={"window": 10},
            data_hash=data_hash,
        )

        assert record is not None
        assert record.metadata["computation_time"] == 0.5
        assert record.coverage_start == coverage_start
        assert record.coverage_end == coverage_end

    def test_load_nonexistent_returns_none(self, cache):
        """Test that loading non-existent cache returns None."""
        record = cache.load(
            indicator_name="nonexistent",
            params={},
            data_hash="fake_hash",
        )

        assert record is None

    def test_cache_miss_and_hit(self, cache):
        """Test cache miss followed by cache hit."""
        data = np.array([1.0, 2.0, 3.0])
        data_hash = hash_input_data(data)

        # First load - cache miss
        record1 = cache.load(
            indicator_name="test",
            params={"p": 1},
            data_hash=data_hash,
        )
        assert record1 is None

        # Store
        cache.store(
            indicator_name="test",
            params={"p": 1},
            data_hash=data_hash,
            value=data,
        )

        # Second load - cache hit
        record2 = cache.load(
            indicator_name="test",
            params={"p": 1},
            data_hash=data_hash,
        )
        assert record2 is not None
        np.testing.assert_array_equal(record2.value, data)

    def test_backfill_state_operations(self, cache):
        """Test backfill state storage and retrieval."""
        timeframe = "1h"

        # Initially no state
        state = cache.get_backfill_state(timeframe)
        assert state is None

        # Update state
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        cache.update_backfill_state(
            timeframe,
            last_timestamp=timestamp,
            fingerprint="fp123",
            extras={"count": 100},
        )

        # Retrieve state
        state = cache.get_backfill_state(timeframe)
        assert state is not None
        assert state.timeframe == "1h"
        assert state.last_timestamp == timestamp
        assert state.fingerprint == "fp123"
        assert state.extras["count"] == 100

    def test_cache_with_different_code_versions(self, cache):
        """Test that different code versions produce different cache entries."""
        data = np.array([1.0, 2.0, 3.0])
        data_hash = hash_input_data(data)

        # Store with version 1
        cache.store(
            indicator_name="test",
            params={},
            data_hash=data_hash,
            value=data,
            code_version="v1.0",
        )

        # Try to load with version 2 - should be cache miss
        record = cache.load(
            indicator_name="test",
            params={},
            data_hash=data_hash,
            code_version="v2.0",
        )
        assert record is None

        # Load with version 1 - should be cache hit
        record = cache.load(
            indicator_name="test",
            params={},
            data_hash=data_hash,
            code_version="v1.0",
        )
        assert record is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
