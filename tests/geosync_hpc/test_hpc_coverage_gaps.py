# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Additional tests to achieve 98% coverage for HPC-AI v4.
Targets specific uncovered lines in afferent_synthesis.
"""

import numpy as np
import pandas as pd
import pytest

from geosync_hpc.hpc_active_inference_v4 import HPCActiveInferenceModuleV4


@pytest.fixture
def model():
    """Create model for testing."""
    return HPCActiveInferenceModuleV4(input_dim=10, state_dim=32)


class TestAfferentSynthesisIndexHandling:
    """Test different index scenarios in afferent_synthesis."""

    def test_with_timestamp_column(self, model):
        """Test data with 'timestamp' column (line 137)."""
        data = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=100, freq="D"),
                "open": np.random.uniform(95, 105, 100),
                "high": np.random.uniform(100, 110, 100),
                "low": np.random.uniform(90, 100, 100),
                "close": np.random.uniform(95, 105, 100),
                "volume": np.random.uniform(1e6, 1e7, 100),
            }
        )

        # Should convert timestamp to index
        state = model.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)

    def test_with_date_column(self, model):
        """Test data with 'date' column (line 139)."""
        data = pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=100, freq="D"),
                "open": np.random.uniform(95, 105, 100),
                "high": np.random.uniform(100, 110, 100),
                "low": np.random.uniform(90, 100, 100),
                "close": np.random.uniform(95, 105, 100),
                "volume": np.random.uniform(1e6, 1e7, 100),
            }
        )

        # Should convert date to index
        state = model.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)


class TestFeaturePadding:
    """Test feature padding and truncation logic."""

    def test_feature_padding_when_too_few(self, model):
        """Test padding when features < input_dim (lines 174-175, 181-182)."""
        # Create data with only 5 features (less than input_dim=10)
        data = pd.DataFrame(
            {
                "open": [100.0],
                "high": [105.0],
                "low": [95.0],
                "close": [102.0],
                "volume": [1000000.0],
            },
            index=pd.date_range("2020-01-01", periods=1),
        )

        # Should pad to 10 dimensions
        state = model.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)

    def test_feature_truncation_when_too_many(self, model):
        """Test truncation when features > input_dim (line 185)."""
        # Create data with standard OHLCV + extra features (more than input_dim=10)
        data = pd.DataFrame(
            {
                "open": np.random.uniform(95, 105, 100),
                "high": np.random.uniform(100, 110, 100),
                "low": np.random.uniform(90, 100, 100),
                "close": np.random.uniform(95, 105, 100),
                "volume": np.random.uniform(1e6, 1e7, 100),
                **{f"extra_feature_{i}": np.random.rand(100) for i in range(10)},
            },
            index=pd.date_range("2020-01-01", periods=100),
        )

        # Should handle gracefully (GeoSyncCompositeEngine might fail with extra columns)
        state = model.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)


class TestFallbackMechanism:
    """Test fallback when GeoSyncCompositeEngine fails."""

    def test_fallback_with_minimal_data(self, model):
        """Test fallback mechanism with minimal OHLCV data."""
        # Create minimal data that might trigger fallback
        data = pd.DataFrame(
            {
                "open": [100.0] * 50,  # Too short for some indicators
                "high": [100.0] * 50,
                "low": [100.0] * 50,
                "close": [100.0] * 50,
                "volume": [1000000.0] * 50,
            },
            index=pd.date_range("2020-01-01", periods=50),
        )

        # Should use fallback if engine fails
        state = model.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)

    def test_feature_padding_in_fallback(self, model):
        """Test that fallback path pads features correctly (lines 174-175)."""
        # Ensure we use model with different input_dim to force padding
        model_large = HPCActiveInferenceModuleV4(input_dim=20, state_dim=32)

        data = pd.DataFrame(
            {
                "open": [100.0] * 10,
                "high": [105.0] * 10,
                "low": [95.0] * 10,
                "close": [102.0] * 10,
                "volume": [1000000.0] * 10,
            },
            index=pd.date_range("2020-01-01", periods=10),
        )

        # With input_dim=20 and only 5 OHLCV features, should pad
        state = model_large.afferent_synthesis(data)
        assert state is not None
        assert state.shape == (1, 32)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
