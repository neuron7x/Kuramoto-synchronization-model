# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for MultiLevelSynapticMemory numerical contracts.

These tests verify the numerical correctness and robustness of the
MultiLevelSynapticMemory class, including:
- NaN/Inf vector rejection in strict mode
- Lambda hierarchy validation
- Dimension mismatch handling
- Sanitization in non-strict mode
"""

from __future__ import annotations

import numpy as np
import pytest

try:
    from tradepulse.sdk.mlsdm.memory.multi_level_memory import (
        LambdaHierarchyError,
        MultiLevelSynapticMemory,
    )
    from tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError
except ImportError:
    from src.tradepulse.sdk.mlsdm.memory.multi_level_memory import (
        LambdaHierarchyError,
        MultiLevelSynapticMemory,
    )
    from src.tradepulse.sdk.mlsdm.utils.input_validator import NumericalContractError


class TestMultiLevelSynapticMemoryInit:
    """Tests for MultiLevelSynapticMemory initialization."""

    def test_valid_initialization(self) -> None:
        """Memory initializes with valid parameters."""
        memory = MultiLevelSynapticMemory(dim=128)
        assert memory.dim == 128
        state = memory.get_state()
        assert state.l1.shape == (128,)
        assert state.l2.shape == (128,)
        assert state.l3.shape == (128,)
        assert state.update_count == 0

    def test_rejects_invalid_lambda_hierarchy(self) -> None:
        """Memory rejects λ hierarchy violation: λ3 > λ2."""
        with pytest.raises(LambdaHierarchyError) as exc_info:
            MultiLevelSynapticMemory(
                dim=64,
                lambda_l1=0.95,
                lambda_l2=0.90,
                lambda_l3=0.98,  # Violates: λ3 > λ1 (0.98 > 0.95)
            )
        assert "λ hierarchy violation" in str(exc_info.value)

    def test_rejects_invalid_lambda_hierarchy_l2_gt_l1(self) -> None:
        """Memory rejects λ hierarchy violation: λ2 > λ1."""
        with pytest.raises(LambdaHierarchyError):
            MultiLevelSynapticMemory(
                dim=64,
                lambda_l1=0.90,
                lambda_l2=0.95,  # Violates: λ2 > λ1
                lambda_l3=0.85,
            )

    def test_rejects_invalid_lambda_range(self) -> None:
        """Memory rejects λ values outside (0, 1]."""
        with pytest.raises(ValueError, match="must be in \\(0, 1\\]"):
            MultiLevelSynapticMemory(dim=64, lambda_l1=0.0)  # 0 not allowed

        with pytest.raises(ValueError, match="must be in \\(0, 1\\]"):
            MultiLevelSynapticMemory(dim=64, lambda_l1=1.5)  # > 1 not allowed

        with pytest.raises(ValueError, match="must be in \\(0, 1\\]"):
            MultiLevelSynapticMemory(dim=64, lambda_l2=-0.1)  # Negative not allowed

    def test_rejects_invalid_dimension(self) -> None:
        """Memory rejects non-positive dimensions."""
        with pytest.raises(ValueError, match="dim must be positive"):
            MultiLevelSynapticMemory(dim=0)

        with pytest.raises(ValueError, match="dim must be positive"):
            MultiLevelSynapticMemory(dim=-5)


class TestMultiLevelSynapticMemoryUpdate:
    """Tests for update() method numerical contracts."""

    def test_rejects_nan_vector_strict_mode(self) -> None:
        """Memory rejects NaN vector in strict mode."""
        memory = MultiLevelSynapticMemory(dim=4, strict_mode=True)
        nan_event = np.array([1.0, np.nan, 2.0, 3.0])

        with pytest.raises(NumericalContractError) as exc_info:
            memory.update(nan_event)

        assert "event" in str(exc_info.value)
        assert "NaN" in str(exc_info.value)

    def test_rejects_inf_vector_strict_mode(self) -> None:
        """Memory rejects Inf vector in strict mode."""
        memory = MultiLevelSynapticMemory(dim=4, strict_mode=True)
        inf_event = np.array([1.0, np.inf, 2.0, 3.0])

        with pytest.raises(NumericalContractError) as exc_info:
            memory.update(inf_event)

        assert "event" in str(exc_info.value)
        assert "Inf" in str(exc_info.value)

    def test_rejects_negative_inf_strict_mode(self) -> None:
        """Memory rejects -Inf vector in strict mode."""
        memory = MultiLevelSynapticMemory(dim=4, strict_mode=True)
        neg_inf_event = np.array([1.0, -np.inf, 2.0, 3.0])

        with pytest.raises(NumericalContractError):
            memory.update(neg_inf_event)

    def test_sanitizes_nan_vector_non_strict_mode(self) -> None:
        """Memory sanitizes NaN vector in non-strict mode."""
        memory = MultiLevelSynapticMemory(dim=4, strict_mode=False)
        nan_event = np.array([1.0, np.nan, 2.0, 3.0])

        # Should not raise
        memory.update(nan_event)

        state = memory.get_state()
        assert state.update_count == 1
        # L1 should have received sanitized event (NaN -> 0)
        # With λ=0.99, L1 = 0.99*0 + 0.01*[1,0,2,3] = [0.01, 0, 0.02, 0.03]
        assert np.all(np.isfinite(state.l1))

    def test_sanitizes_inf_vector_non_strict_mode(self) -> None:
        """Memory sanitizes Inf vector in non-strict mode."""
        memory = MultiLevelSynapticMemory(dim=4, strict_mode=False)
        inf_event = np.array([1.0, np.inf, 2.0, -np.inf])

        # Should not raise
        memory.update(inf_event)

        state = memory.get_state()
        assert state.update_count == 1
        assert np.all(np.isfinite(state.l1))
        assert np.all(np.isfinite(state.l2))
        assert np.all(np.isfinite(state.l3))

    def test_rejects_dimension_mismatch(self) -> None:
        """Memory rejects events with wrong dimension."""
        memory = MultiLevelSynapticMemory(dim=4)
        wrong_dim_event = np.array([1.0, 2.0, 3.0])  # 3 instead of 4

        with pytest.raises(ValueError, match="dimension mismatch"):
            memory.update(wrong_dim_event)

    def test_valid_update_updates_state(self) -> None:
        """Memory correctly updates state with valid event."""
        memory = MultiLevelSynapticMemory(
            dim=3,
            lambda_l1=0.9,
            lambda_l2=0.8,
            lambda_l3=0.7,
        )
        event = np.array([10.0, 20.0, 30.0])

        memory.update(event)

        state = memory.get_state()
        assert state.update_count == 1

        # L1 = 0.9 * 0 + 0.1 * event = 0.1 * event
        expected_l1 = 0.1 * event
        np.testing.assert_allclose(state.l1, expected_l1)

        # L2 = 0.8 * 0 + 0.2 * event = 0.2 * event
        expected_l2 = 0.2 * event
        np.testing.assert_allclose(state.l2, expected_l2)

        # L3 = 0.7 * 0 + 0.3 * event = 0.3 * event
        expected_l3 = 0.3 * event
        np.testing.assert_allclose(state.l3, expected_l3)


class TestMultiLevelSynapticMemoryReset:
    """Tests for reset() method."""

    def test_reset_clears_state(self) -> None:
        """Reset clears all memory levels to zeros."""
        memory = MultiLevelSynapticMemory(dim=4)
        event = np.array([1.0, 2.0, 3.0, 4.0])

        memory.update(event)
        memory.update(event)
        assert memory.get_state().update_count == 2

        memory.reset()

        state = memory.get_state()
        assert state.update_count == 0
        np.testing.assert_array_equal(state.l1, np.zeros(4))
        np.testing.assert_array_equal(state.l2, np.zeros(4))
        np.testing.assert_array_equal(state.l3, np.zeros(4))


class TestMultiLevelSynapticMemoryFromConfig:
    """Tests for from_config() factory method."""

    def test_from_config_with_all_params(self) -> None:
        """Memory can be created from full config dict."""
        config = {
            "dim": 64,
            "lambda_l1": 0.98,
            "lambda_l2": 0.92,
            "lambda_l3": 0.85,
            "strict_mode": False,
        }
        memory = MultiLevelSynapticMemory.from_config(config)

        assert memory.dim == 64
        assert memory.lambda_l1 == 0.98
        assert memory.lambda_l2 == 0.92
        assert memory.lambda_l3 == 0.85
        assert memory.strict_mode is False

    def test_from_config_with_defaults(self) -> None:
        """Memory uses defaults for missing config keys."""
        config = {"dim": 32}
        memory = MultiLevelSynapticMemory.from_config(config)

        assert memory.dim == 32
        assert memory.lambda_l1 == 0.99  # default
        assert memory.lambda_l2 == 0.95  # default
        assert memory.lambda_l3 == 0.90  # default
        assert memory.strict_mode is True  # default

    def test_from_config_rejects_invalid_hierarchy(self) -> None:
        """from_config still validates λ hierarchy."""
        config = {
            "dim": 32,
            "lambda_l1": 0.80,
            "lambda_l2": 0.90,  # Invalid: λ2 > λ1
            "lambda_l3": 0.70,
        }
        with pytest.raises(LambdaHierarchyError):
            MultiLevelSynapticMemory.from_config(config)


class TestMultiLevelSynapticMemoryGetCombined:
    """Tests for get_combined() method."""

    def test_get_combined_default_weights(self) -> None:
        """get_combined with default weights returns sum."""
        memory = MultiLevelSynapticMemory(dim=2, lambda_l1=0.5, lambda_l2=0.4, lambda_l3=0.3)
        event = np.array([10.0, 20.0])
        memory.update(event)

        combined = memory.get_combined()
        state = memory.get_state()

        expected = state.l1 + state.l2 + state.l3
        np.testing.assert_allclose(combined, expected)

    def test_get_combined_custom_weights(self) -> None:
        """get_combined with custom weights applies them."""
        memory = MultiLevelSynapticMemory(dim=2, lambda_l1=0.5, lambda_l2=0.4, lambda_l3=0.3)
        event = np.array([10.0, 20.0])
        memory.update(event)

        combined = memory.get_combined(weights=(2.0, 0.0, 0.0))
        state = memory.get_state()

        expected = 2.0 * state.l1
        np.testing.assert_allclose(combined, expected)
