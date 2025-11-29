"""Tests for mathematical_logic module."""

from __future__ import annotations

import numpy as np
import pytest

from core.validation.mathematical_logic import (
    DataIntegrityReport,
    MathematicalLogicValidator,
    ValidationLevel,
    ValidationResult,
    validate_correlation_matrix,
    validate_positive_definite,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_passed_result(self):
        """Test passed validation result."""
        result = ValidationResult(
            name="test_check",
            passed=True,
            level=ValidationLevel.INFO,
            message="Check passed",
        )
        assert result.passed
        assert "✓" in str(result)

    def test_failed_result(self):
        """Test failed validation result."""
        result = ValidationResult(
            name="test_check",
            passed=False,
            level=ValidationLevel.ERROR,
            message="Check failed",
        )
        assert not result.passed
        assert "✗" in str(result)

    def test_with_values(self):
        """Test result with value and expected."""
        result = ValidationResult(
            name="test_check",
            passed=True,
            level=ValidationLevel.INFO,
            message="Check passed",
            value=42,
            expected=42,
        )
        assert result.value == 42
        assert result.expected == 42


class TestDataIntegrityReport:
    """Tests for DataIntegrityReport."""

    def test_empty_report(self):
        """Test empty report is valid."""
        report = DataIntegrityReport()
        assert report.is_valid
        assert report.errors == 0
        assert report.warnings == 0

    def test_add_passed_check(self):
        """Test adding passed check."""
        report = DataIntegrityReport()
        result = ValidationResult(
            name="test", passed=True, level=ValidationLevel.INFO, message="OK"
        )
        report.add_check(result)
        assert report.is_valid
        assert len(report.checks) == 1

    def test_add_error_check(self):
        """Test adding error check invalidates report."""
        report = DataIntegrityReport()
        result = ValidationResult(
            name="test", passed=False, level=ValidationLevel.ERROR, message="Failed"
        )
        report.add_check(result)
        assert not report.is_valid
        assert report.errors == 1

    def test_add_warning_check(self):
        """Test adding warning doesn't invalidate report."""
        report = DataIntegrityReport()
        result = ValidationResult(
            name="test", passed=False, level=ValidationLevel.WARNING, message="Warning"
        )
        report.add_check(result)
        assert report.is_valid  # Still valid, just has warnings
        assert report.warnings == 1

    def test_get_failures(self):
        """Test getting failed checks."""
        report = DataIntegrityReport()
        report.add_check(
            ValidationResult(
                name="pass", passed=True, level=ValidationLevel.INFO, message="OK"
            )
        )
        report.add_check(
            ValidationResult(
                name="fail", passed=False, level=ValidationLevel.ERROR, message="Failed"
            )
        )
        failures = report.get_failures()
        assert len(failures) == 1
        assert failures[0].name == "fail"

    def test_summary(self):
        """Test summary generation."""
        report = DataIntegrityReport()
        report.add_check(
            ValidationResult(
                name="ok", passed=True, level=ValidationLevel.INFO, message="OK"
            )
        )
        summary = report.summary()
        assert "1" in summary
        assert "passed" in summary


class TestMathematicalLogicValidator:
    """Tests for MathematicalLogicValidator."""

    @pytest.fixture
    def validator(self):
        """Create default validator."""
        return MathematicalLogicValidator()

    def test_validate_finite_clean_data(self, validator):
        """Test finite check on clean data."""
        data = np.array([1.0, 2.0, 3.0, 4.0])
        results = validator.validate_finite(data, name="test")
        assert all(r.passed for r in results)

    def test_validate_finite_with_nan(self, validator):
        """Test finite check detects NaN."""
        data = np.array([1.0, float("nan"), 3.0])
        results = validator.validate_finite(data, name="test")
        nan_result = next(r for r in results if "nan" in r.name)
        assert not nan_result.passed

    def test_validate_finite_with_inf(self, validator):
        """Test finite check detects Inf."""
        data = np.array([1.0, float("inf"), 3.0])
        results = validator.validate_finite(data, name="test")
        inf_result = next(r for r in results if "inf" in r.name)
        assert not inf_result.passed

    def test_validate_finite_ignore_policy(self):
        """Test ignore policy for NaN."""
        validator = MathematicalLogicValidator(nan_policy="ignore")
        data = np.array([1.0, float("nan"), 3.0])
        results = validator.validate_finite(data, name="test")
        nan_result = next(r for r in results if "nan" in r.name)
        assert nan_result.passed  # NaN is ignored

    def test_validate_bounds_within(self, validator):
        """Test bounds check with data within bounds."""
        data = np.array([1.0, 2.0, 3.0])
        results = validator.validate_bounds(
            data, name="test", min_value=0.0, max_value=5.0
        )
        assert all(r.passed for r in results)

    def test_validate_bounds_below_min(self, validator):
        """Test bounds check with data below minimum."""
        data = np.array([-1.0, 2.0, 3.0])
        results = validator.validate_bounds(data, name="test", min_value=0.0)
        min_result = next(r for r in results if "min" in r.name)
        assert not min_result.passed

    def test_validate_bounds_above_max(self, validator):
        """Test bounds check with data above maximum."""
        data = np.array([1.0, 2.0, 10.0])
        results = validator.validate_bounds(data, name="test", max_value=5.0)
        max_result = next(r for r in results if "max" in r.name)
        assert not max_result.passed

    def test_validate_monotonic_increasing(self, validator):
        """Test monotonic check for increasing data."""
        data = np.array([1.0, 2.0, 3.0, 4.0])
        results = validator.validate_monotonic(
            data, name="test", direction="increasing"
        )
        assert results[0].passed

    def test_validate_monotonic_not_increasing(self, validator):
        """Test monotonic check for non-increasing data."""
        data = np.array([1.0, 3.0, 2.0, 4.0])
        results = validator.validate_monotonic(
            data, name="test", direction="increasing"
        )
        assert not results[0].passed

    def test_validate_monotonic_decreasing(self, validator):
        """Test monotonic check for decreasing data."""
        data = np.array([4.0, 3.0, 2.0, 1.0])
        results = validator.validate_monotonic(
            data, name="test", direction="decreasing"
        )
        assert results[0].passed

    def test_validate_monotonic_strict(self, validator):
        """Test strict monotonicity check."""
        data = np.array([1.0, 2.0, 2.0, 3.0])  # Not strictly increasing
        results = validator.validate_monotonic(
            data, name="test", direction="increasing", strict=True
        )
        assert not results[0].passed

    def test_validate_sum_conservation(self, validator):
        """Test sum conservation check."""
        before = np.array([1.0, 2.0, 3.0])
        after = np.array([2.0, 2.0, 2.0])  # Same sum (6)
        results = validator.validate_sum_conservation(before, after, name="test")
        assert results[0].passed

    def test_validate_sum_conservation_fail(self, validator):
        """Test sum conservation failure."""
        before = np.array([1.0, 2.0, 3.0])  # Sum = 6
        after = np.array([1.0, 1.0, 1.0])  # Sum = 3
        results = validator.validate_sum_conservation(
            before, after, name="test", tolerance=0.01
        )
        assert not results[0].passed

    def test_validate_probability_distribution(self, validator):
        """Test valid probability distribution."""
        probs = np.array([0.2, 0.3, 0.5])
        results = validator.validate_probability_distribution(probs, name="test")
        assert all(r.passed for r in results)

    def test_validate_probability_negative(self, validator):
        """Test probability with negative value."""
        probs = np.array([-0.1, 0.5, 0.6])
        results = validator.validate_probability_distribution(probs, name="test")
        non_neg_result = next(r for r in results if "non_negative" in r.name)
        assert not non_neg_result.passed

    def test_validate_probability_not_sum_to_one(self, validator):
        """Test probability not summing to one."""
        probs = np.array([0.2, 0.3, 0.3])  # Sum = 0.8
        results = validator.validate_probability_distribution(probs, name="test")
        sum_result = next(r for r in results if "sum_to_one" in r.name)
        assert not sum_result.passed

    def test_validate_statistical_moments(self, validator):
        """Test statistical moments validation."""
        data = np.random.normal(0.0, 1.0, 1000)
        results = validator.validate_statistical_moments(
            data, name="test", expected_mean=0.0, expected_std=1.0, mean_tolerance=0.2
        )
        # Should pass with reasonable tolerance for random data
        assert all(r.passed for r in results)

    def test_validate_array_comprehensive(self, validator):
        """Test comprehensive array validation."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        report = validator.validate_array(
            data, name="test", min_value=0.0, max_value=10.0
        )
        assert report.is_valid
        assert "min" in report.metrics
        assert "max" in report.metrics
        assert "mean" in report.metrics

    def test_validate_array_empty(self, validator):
        """Test empty array validation."""
        data = np.array([])
        report = validator.validate_array(data, name="test")
        assert len(report.checks) == 1  # Empty check
        assert any("empty" in c.message for c in report.checks)

    def test_validate_relationship_passes(self, validator):
        """Test custom relationship validation that passes."""
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 4.0, 6.0])
        result = validator.validate_relationship(
            x,
            y,
            relationship=lambda a, b: np.allclose(b, 2 * a),
            name="double_check",
            description="y = 2x",
        )
        assert result.passed

    def test_validate_relationship_fails(self, validator):
        """Test custom relationship validation that fails."""
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 5.0, 6.0])  # Not exactly 2x
        result = validator.validate_relationship(
            x,
            y,
            relationship=lambda a, b: np.allclose(b, 2 * a),
            name="double_check",
            description="y = 2x",
        )
        assert not result.passed


class TestValidatePositiveDefinite:
    """Tests for validate_positive_definite function."""

    def test_positive_definite_matrix(self):
        """Test positive definite matrix."""
        matrix = np.array([[2.0, 1.0], [1.0, 2.0]])
        result = validate_positive_definite(matrix, name="test")
        assert result.passed

    def test_not_positive_definite(self):
        """Test non-positive definite matrix."""
        matrix = np.array([[1.0, 2.0], [2.0, 1.0]])  # Has negative eigenvalue
        result = validate_positive_definite(matrix, name="test")
        assert not result.passed

    def test_non_square_matrix(self):
        """Test non-square matrix."""
        matrix = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        result = validate_positive_definite(matrix, name="test")
        assert not result.passed


class TestValidateCorrelationMatrix:
    """Tests for validate_correlation_matrix function."""

    def test_valid_correlation_matrix(self):
        """Test valid correlation matrix."""
        matrix = np.array(
            [
                [1.0, 0.5, 0.3],
                [0.5, 1.0, 0.4],
                [0.3, 0.4, 1.0],
            ]
        )
        results = validate_correlation_matrix(matrix, name="test")
        assert all(r.passed for r in results)

    def test_diagonal_not_ones(self):
        """Test correlation matrix with diagonal not all ones."""
        matrix = np.array(
            [
                [1.0, 0.5],
                [0.5, 0.8],  # Should be 1.0
            ]
        )
        results = validate_correlation_matrix(matrix, name="test")
        diag_result = next(r for r in results if "diagonal" in r.name)
        assert not diag_result.passed

    def test_not_symmetric(self):
        """Test non-symmetric matrix."""
        matrix = np.array(
            [
                [1.0, 0.5],
                [0.3, 1.0],  # Asymmetric
            ]
        )
        results = validate_correlation_matrix(matrix, name="test")
        sym_result = next(r for r in results if "symmetric" in r.name)
        assert not sym_result.passed

    def test_out_of_bounds(self):
        """Test correlation values outside [-1, 1]."""
        matrix = np.array(
            [
                [1.0, 1.5],  # Invalid correlation > 1
                [1.5, 1.0],
            ]
        )
        results = validate_correlation_matrix(matrix, name="test")
        bounds_result = next(r for r in results if "bounds" in r.name)
        assert not bounds_result.passed

    def test_non_square(self):
        """Test non-square matrix."""
        matrix = np.array([[1.0, 0.5, 0.3]])
        results = validate_correlation_matrix(matrix, name="test")
        assert not results[0].passed
        assert "square" in results[0].message
