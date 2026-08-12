# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for memory validation utilities.

This module contains comprehensive tests for the memory validation layer,
covering invariant checking, checksum verification, and recovery modes.
"""

from __future__ import annotations

import time
import warnings
from typing import Any, Dict

import numpy as np
import pytest

from core.utils.memory_validation import (
    STATE_VERSION,
    CorruptedStateError,
    InvariantError,
    ValidationContext,
    ValidationResult,
    assert_finite_array,
    assert_finite_float,
    compute_state_checksum,
    recover_pelm_state,
    recover_strategy_memory_state,
    validate_decay_invariant,
    validate_pelm_state,
    validate_strategy_memory_state,
    verify_state_checksum,
)

# SHA-256 produces 256 bits = 32 bytes = 64 hex characters
SHA256_HEX_LENGTH = 64


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_strategy_state() -> Dict[str, Any]:
    """Create a valid StrategyMemory state."""
    return {
        "decay_lambda": 1e-6,
        "max_records": 256,
        "records": [
            {
                "name": "momentum",
                "signature": {
                    "R": 0.95,
                    "delta_H": 0.05,
                    "kappa_mean": 0.3,
                    "entropy": 2.1,
                    "instability": 0.1,
                },
                "score": 0.85,
                "ts": time.time() - 100,
            },
            {
                "name": "mean_reversion",
                "signature": {
                    "R": 0.7,
                    "delta_H": -0.02,
                    "kappa_mean": 0.5,
                    "entropy": 1.8,
                    "instability": 0.2,
                },
                "score": 0.72,
                "ts": time.time() - 50,
            },
        ],
    }


@pytest.fixture
def valid_pelm_state() -> Dict[str, Any]:
    """Create a valid FractalPELMGPU state."""
    np.random.seed(42)
    return {
        "dimension": 64,
        "capacity": 1000,
        "fractal_weight": 0.3,
        "entries": [
            {
                "vector": np.random.randn(64).tolist(),
                "phase": float(i) * 0.1,
                "metadata": {"id": i},
            }
            for i in range(5)
        ],
    }


# =============================================================================
# Test assert_finite_float
# =============================================================================


class TestAssertFiniteFloat:
    """Tests for assert_finite_float function."""

    def test_accepts_normal_float(self) -> None:
        """Normal float values should pass."""
        assert_finite_float(0.5, "test")
        assert_finite_float(-100.0, "test")
        assert_finite_float(1e-10, "test")

    def test_rejects_nan(self) -> None:
        """NaN should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be finite"):
            assert_finite_float(float("nan"), "test")

    def test_rejects_positive_inf(self) -> None:
        """Positive infinity should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be finite"):
            assert_finite_float(float("inf"), "test")

    def test_rejects_negative_inf(self) -> None:
        """Negative infinity should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be finite"):
            assert_finite_float(float("-inf"), "test")

    def test_enforces_min_value(self) -> None:
        """Values below min should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be >="):
            assert_finite_float(-1.0, "test", min_value=0.0)

    def test_enforces_max_value(self) -> None:
        """Values above max should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be <="):
            assert_finite_float(2.0, "test", max_value=1.0)


# =============================================================================
# Test assert_finite_array
# =============================================================================


class TestAssertFiniteArray:
    """Tests for assert_finite_array function."""

    def test_accepts_normal_array(self) -> None:
        """Normal arrays should pass."""
        arr = np.array([1.0, 2.0, 3.0])
        assert_finite_array(arr, "test")

    def test_accepts_empty_array_by_default(self) -> None:
        """Empty arrays should pass by default."""
        arr = np.array([])
        assert_finite_array(arr, "test")

    def test_rejects_empty_when_not_allowed(self) -> None:
        """Empty arrays should fail when allow_empty=False."""
        arr = np.array([])
        with pytest.raises(InvariantError, match="must not be empty"):
            assert_finite_array(arr, "test", allow_empty=False)

    def test_rejects_array_with_nan(self) -> None:
        """Arrays with NaN should raise InvariantError."""
        arr = np.array([1.0, float("nan"), 3.0])
        with pytest.raises(InvariantError, match="non-finite values"):
            assert_finite_array(arr, "test")

    def test_rejects_array_with_inf(self) -> None:
        """Arrays with Inf should raise InvariantError."""
        arr = np.array([1.0, float("inf"), 3.0])
        with pytest.raises(InvariantError, match="non-finite values"):
            assert_finite_array(arr, "test")

    def test_rejects_non_array(self) -> None:
        """Non-array inputs should raise InvariantError."""
        with pytest.raises(InvariantError, match="must be a numpy array"):
            assert_finite_array([1.0, 2.0], "test")  # type: ignore

    def test_checks_dtype_when_specified(self) -> None:
        """Dtype mismatch should raise InvariantError."""
        arr = np.array([1.0, 2.0], dtype=np.float64)
        with pytest.raises(InvariantError, match="must have dtype"):
            assert_finite_array(arr, "test", expected_dtype=np.float32)


# =============================================================================
# Test compute_state_checksum and verify_state_checksum
# =============================================================================


class TestChecksum:
    """Tests for checksum computation and verification."""

    def test_checksum_is_deterministic(self) -> None:
        """Same data should produce same checksum."""
        data = {"a": 1, "b": [1, 2, 3], "c": {"nested": "value"}}
        checksum1 = compute_state_checksum(data)
        checksum2 = compute_state_checksum(data)
        assert checksum1 == checksum2

    def test_checksum_changes_on_data_mutation(self) -> None:
        """Modified data should produce different checksum."""
        data1 = {"a": 1, "b": 2}
        data2 = {"a": 1, "b": 3}  # Changed b value
        checksum1 = compute_state_checksum(data1)
        checksum2 = compute_state_checksum(data2)
        assert checksum1 != checksum2

    def test_checksum_handles_numpy_arrays(self) -> None:
        """Numpy arrays should be checksummed correctly."""
        data = {"arr": np.array([1.0, 2.0, 3.0])}
        checksum = compute_state_checksum(data)
        assert len(checksum) == SHA256_HEX_LENGTH

    def test_checksum_excludes_specified_keys(self) -> None:
        """Excluded keys should not affect checksum."""
        data1 = {"a": 1, "_checksum": "abc"}
        data2 = {"a": 1, "_checksum": "xyz"}
        checksum1 = compute_state_checksum(data1)
        checksum2 = compute_state_checksum(data2)
        assert checksum1 == checksum2

    def test_verify_checksum_passes_for_valid(self) -> None:
        """Valid checksum should pass verification."""
        data = {"a": 1, "b": 2}
        checksum = compute_state_checksum(data)
        assert verify_state_checksum(data, checksum, strict=True) is True

    def test_verify_checksum_strict_raises_on_mismatch(self) -> None:
        """Strict mode should raise on checksum mismatch."""
        data = {"a": 1, "b": 2}
        with pytest.raises(CorruptedStateError, match="checksum mismatch"):
            verify_state_checksum(data, "wrong_checksum", strict=True)

    def test_verify_checksum_nonstrict_returns_false(self) -> None:
        """Non-strict mode should return False on mismatch."""
        data = {"a": 1, "b": 2}
        result = verify_state_checksum(data, "wrong_checksum", strict=False)
        assert result is False


# =============================================================================
# Test validate_strategy_memory_state
# =============================================================================


class TestValidateStrategyMemoryState:
    """Tests for StrategyMemory state validation."""

    def test_accepts_valid_state(self, valid_strategy_state: Dict[str, Any]) -> None:
        """Valid state should pass validation."""
        result = validate_strategy_memory_state(valid_strategy_state)
        assert result.is_valid
        assert len(result.violations) == 0

    def test_rejects_negative_decay_lambda(self, valid_strategy_state: Dict[str, Any]) -> None:
        """Negative decay_lambda should be rejected."""
        valid_strategy_state["decay_lambda"] = -1.0
        with pytest.raises(InvariantError, match="decay_lambda must be >= 0"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_nan_decay_lambda(self, valid_strategy_state: Dict[str, Any]) -> None:
        """NaN decay_lambda should be rejected."""
        valid_strategy_state["decay_lambda"] = float("nan")
        with pytest.raises(InvariantError, match="decay_lambda must be finite"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_zero_max_records(self, valid_strategy_state: Dict[str, Any]) -> None:
        """Zero max_records should be rejected."""
        valid_strategy_state["max_records"] = 0
        with pytest.raises(InvariantError, match="max_records must be > 0"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_capacity_overflow(self, valid_strategy_state: Dict[str, Any]) -> None:
        """More records than max_records should be rejected."""
        valid_strategy_state["max_records"] = 1  # Only 1 allowed but we have 2
        with pytest.raises(InvariantError, match="exceeds max_records"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_nan_score(self, valid_strategy_state: Dict[str, Any]) -> None:
        """NaN score in record should be rejected."""
        valid_strategy_state["records"][0]["score"] = float("nan")
        with pytest.raises(InvariantError, match="score must be finite"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_negative_timestamp(self, valid_strategy_state: Dict[str, Any]) -> None:
        """Negative timestamp should be rejected."""
        valid_strategy_state["records"][0]["ts"] = -100.0
        with pytest.raises(InvariantError, match="ts must be non-negative"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_rejects_nan_in_signature(self, valid_strategy_state: Dict[str, Any]) -> None:
        """NaN in signature should be rejected."""
        valid_strategy_state["records"][0]["signature"]["R"] = float("nan")
        with pytest.raises(InvariantError, match="signature.R must be finite"):
            validate_strategy_memory_state(valid_strategy_state, strict=True)

    def test_recovery_mode_quarantines_bad_records(
        self, valid_strategy_state: Dict[str, Any]
    ) -> None:
        """Non-strict mode should quarantine bad records."""
        valid_strategy_state["records"][0]["score"] = float("nan")
        result = validate_strategy_memory_state(valid_strategy_state, strict=False)
        assert not result.is_valid
        assert 0 in result.quarantined_indices


# =============================================================================
# Test validate_pelm_state
# =============================================================================


class TestValidatePelmState:
    """Tests for FractalPELMGPU state validation."""

    def test_accepts_valid_state(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Valid state should pass validation."""
        result = validate_pelm_state(valid_pelm_state)
        assert result.is_valid
        assert len(result.violations) == 0

    def test_rejects_zero_dimension(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Zero dimension should be rejected."""
        valid_pelm_state["dimension"] = 0
        with pytest.raises(InvariantError, match="dimension must be > 0"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_negative_capacity(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Negative capacity should be rejected."""
        valid_pelm_state["capacity"] = -10
        with pytest.raises(InvariantError, match="capacity must be > 0"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_fractal_weight_out_of_range(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Fractal weight outside [0,1] should be rejected."""
        valid_pelm_state["fractal_weight"] = 1.5
        with pytest.raises(InvariantError, match="fractal_weight must be in"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_capacity_overflow(self, valid_pelm_state: Dict[str, Any]) -> None:
        """More entries than capacity should be rejected."""
        valid_pelm_state["capacity"] = 2  # Only 2 allowed but we have 5
        with pytest.raises(InvariantError, match="exceeds capacity"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_nan_in_vector(self, valid_pelm_state: Dict[str, Any]) -> None:
        """NaN in vector should be rejected."""
        valid_pelm_state["entries"][0]["vector"][0] = float("nan")
        with pytest.raises(InvariantError, match="vector contains NaN"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_wrong_dimension_vector(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Vector with wrong dimension should be rejected."""
        valid_pelm_state["entries"][0]["vector"] = [1.0] * 32  # Wrong dimension
        with pytest.raises(InvariantError, match="vector dimension"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_rejects_nan_phase(self, valid_pelm_state: Dict[str, Any]) -> None:
        """NaN phase should be rejected."""
        valid_pelm_state["entries"][0]["phase"] = float("nan")
        with pytest.raises(InvariantError, match="phase must be finite"):
            validate_pelm_state(valid_pelm_state, strict=True)

    def test_recovery_mode_quarantines_bad_entries(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Non-strict mode should quarantine bad entries."""
        valid_pelm_state["entries"][0]["vector"][0] = float("nan")
        result = validate_pelm_state(valid_pelm_state, strict=False)
        assert not result.is_valid
        assert 0 in result.quarantined_indices


# =============================================================================
# Test validate_decay_invariant
# =============================================================================


class TestValidateDecayInvariant:
    """Tests for decay invariant validation."""

    def test_accepts_decay_reduction(self) -> None:
        """Decay that reduces score should pass."""
        validate_decay_invariant(1.0, 0.9)  # Should not raise

    def test_accepts_no_change(self) -> None:
        """No change in score should pass."""
        validate_decay_invariant(1.0, 1.0)  # Should not raise

    def test_rejects_decay_increase(self) -> None:
        """Decay that increases score should fail."""
        with pytest.raises(InvariantError, match="Decay invariant violated"):
            validate_decay_invariant(0.8, 0.9)  # Increased!

    def test_allows_small_floating_point_error(self) -> None:
        """Small floating-point errors within tolerance should pass."""
        validate_decay_invariant(1.0, 1.0 + 1e-12)  # Within default tolerance

    def test_rejects_nan_original(self) -> None:
        """NaN original score should fail."""
        with pytest.raises(InvariantError, match="must be finite"):
            validate_decay_invariant(float("nan"), 0.9)

    def test_rejects_nan_decayed(self) -> None:
        """NaN decayed score should fail."""
        with pytest.raises(InvariantError, match="must be finite"):
            validate_decay_invariant(1.0, float("nan"))


# =============================================================================
# Test Recovery Functions
# =============================================================================


class TestRecoveryFunctions:
    """Tests for state recovery functions."""

    def test_recover_strategy_memory_removes_quarantined(
        self, valid_strategy_state: Dict[str, Any]
    ) -> None:
        """Recovery should remove quarantined records."""
        result = ValidationResult(
            is_valid=False,
            violations=("test",),
            quarantined_indices=(0,),  # Quarantine first record
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            recovered = recover_strategy_memory_state(valid_strategy_state, result)
            assert len(w) == 1
            assert "quarantining" in str(w[0].message).lower()

        assert len(recovered["records"]) == 1  # One record removed
        assert recovered["_recovered"] is True
        assert recovered["_quarantined_count"] == 1

    def test_recover_pelm_removes_quarantined(self, valid_pelm_state: Dict[str, Any]) -> None:
        """Recovery should remove quarantined entries."""
        result = ValidationResult(
            is_valid=False,
            violations=("test",),
            quarantined_indices=(0, 2),  # Quarantine entries 0 and 2
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            recovered = recover_pelm_state(valid_pelm_state, result)
            assert len(w) == 1

        assert len(recovered["entries"]) == 3  # Two entries removed
        assert recovered["_recovered"] is True
        assert recovered["_quarantined_count"] == 2


# =============================================================================
# Test ValidationContext and ValidationResult
# =============================================================================


class TestValidationTypes:
    """Tests for validation type classes."""

    def test_validation_context_accumulates_violations(self) -> None:
        """ValidationContext should accumulate violations."""
        ctx = ValidationContext()
        ctx.add_violation("Error 1")
        ctx.add_violation("Error 2")
        result = ctx.to_result()
        assert not result.is_valid
        assert len(result.violations) == 2

    def test_validation_context_accumulates_warnings(self) -> None:
        """ValidationContext should accumulate warnings."""
        ctx = ValidationContext()
        ctx.add_warning("Warning 1")
        result = ctx.to_result()
        assert result.is_valid  # Warnings don't invalidate
        assert len(result.warnings) == 1

    def test_validation_context_tracks_quarantine(self) -> None:
        """ValidationContext should track quarantined indices."""
        ctx = ValidationContext()
        ctx.quarantine(0)
        ctx.quarantine(5)
        result = ctx.to_result()
        assert result.quarantined_indices == (0, 5)

    def test_validation_result_raise_if_invalid(self) -> None:
        """ValidationResult.raise_if_invalid should raise on invalid."""
        result = ValidationResult(is_valid=False, violations=("test error",))
        with pytest.raises(InvariantError, match="test error"):
            result.raise_if_invalid()

    def test_validation_result_raise_if_invalid_passes_when_valid(self) -> None:
        """ValidationResult.raise_if_invalid should not raise when valid."""
        result = ValidationResult(is_valid=True)
        result.raise_if_invalid()  # Should not raise


# =============================================================================
# Test STATE_VERSION
# =============================================================================


def test_state_version_format() -> None:
    """STATE_VERSION should be a semver-like string."""
    assert isinstance(STATE_VERSION, str)
    parts = STATE_VERSION.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()
