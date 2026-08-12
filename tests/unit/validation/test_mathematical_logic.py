# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for core.validation.mathematical_logic module."""

from __future__ import annotations

import numpy as np

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

    def test_validation_result_passed_str(self) -> None:
        result = ValidationResult(
            name="test",
            passed=True,
            level=ValidationLevel.INFO,
            message="All good",
        )
        assert "✓" in str(result)
        assert "test" in str(result)

    def test_validation_result_failed_str(self) -> None:
        result = ValidationResult(
            name="test",
            passed=False,
            level=ValidationLevel.ERROR,
            message="Failed",
        )
        assert "✗" in str(result)

    def test_validation_result_with_value_and_expected(self) -> None:
        result = ValidationResult(
            name="bounds_check",
            passed=False,
            level=ValidationLevel.ERROR,
            message="Value out of bounds",
            value=100,
            expected="< 50",
        )
        assert result.value == 100
        assert result.expected == "< 50"


class TestDataIntegrityReport:
    """Tests for DataIntegrityReport dataclass."""

    def test_empty_report_is_valid(self) -> None:
        report = DataIntegrityReport()
        assert report.is_valid
        assert report.errors == 0
        assert report.warnings == 0
        assert report.checks == []

    def test_add_check_with_error(self) -> None:
        report = DataIntegrityReport()
        error_result = ValidationResult(
            name="error_check",
            passed=False,
            level=ValidationLevel.ERROR,
            message="Error occurred",
        )
        report.add_check(error_result)
        assert not report.is_valid
        assert report.errors == 1
        assert len(report.checks) == 1

    def test_add_check_with_warning(self) -> None:
        report = DataIntegrityReport()
        warning_result = ValidationResult(
            name="warning_check",
            passed=False,
            level=ValidationLevel.WARNING,
            message="Warning",
        )
        report.add_check(warning_result)
        # Warnings don't affect is_valid
        assert report.is_valid
        assert report.warnings == 1

    def test_add_check_with_passing_result(self) -> None:
        report = DataIntegrityReport()
        passing_result = ValidationResult(
            name="pass_check",
            passed=True,
            level=ValidationLevel.INFO,
            message="Passed",
        )
        report.add_check(passing_result)
        assert report.is_valid
        assert report.errors == 0
        assert report.warnings == 0

    def test_get_failures(self) -> None:
        report = DataIntegrityReport()
        passed = ValidationResult("p", True, ValidationLevel.INFO, "ok")
        failed = ValidationResult("f", False, ValidationLevel.ERROR, "fail")
        report.add_check(passed)
        report.add_check(failed)
        failures = report.get_failures()
        assert len(failures) == 1
        assert failures[0].name == "f"

    def test_summary(self) -> None:
        report = DataIntegrityReport()
        report.add_check(ValidationResult("a", True, ValidationLevel.INFO, "ok"))
        report.add_check(ValidationResult("b", False, ValidationLevel.ERROR, "fail"))
        report.add_check(ValidationResult("c", False, ValidationLevel.WARNING, "warn"))
        summary = report.summary()
        assert "1/3 passed" in summary
        assert "1 errors" in summary
        assert "1 warnings" in summary


class TestMathematicalLogicValidator:
    """Tests for MathematicalLogicValidator class."""

    def test_default_initialization(self) -> None:
        validator = MathematicalLogicValidator()
        assert validator.nan_policy == "error"
        assert validator.inf_policy == "error"
        assert validator.epsilon == 1e-12

    def test_custom_initialization(self) -> None:
        validator = MathematicalLogicValidator(
            nan_policy="warning",
            inf_policy="ignore",
            epsilon=1e-6,
        )
        assert validator.nan_policy == "warning"
        assert validator.inf_policy == "ignore"
        assert validator.epsilon == 1e-6

    def test_policy_to_level_error(self) -> None:
        validator = MathematicalLogicValidator()
        assert validator._policy_to_level("error") == ValidationLevel.ERROR

    def test_policy_to_level_warning(self) -> None:
        validator = MathematicalLogicValidator()
        assert validator._policy_to_level("warning") == ValidationLevel.WARNING

    def test_policy_to_level_ignore(self) -> None:
        validator = MathematicalLogicValidator()
        assert validator._policy_to_level("ignore") is None


class TestValidateFinite:
    """Tests for validate_finite method."""

    def test_clean_data_passes(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        results = validator.validate_finite(data, name="prices")
        assert all(r.passed for r in results)

    def test_nan_values_detected(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, np.nan, 3.0])
        results = validator.validate_finite(data, name="data")
        nan_result = next(r for r in results if "nan_check" in r.name)
        assert not nan_result.passed
        assert nan_result.level == ValidationLevel.ERROR
        assert nan_result.value == 1

    def test_inf_values_detected(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, np.inf, -np.inf])
        results = validator.validate_finite(data, name="data")
        inf_result = next(r for r in results if "inf_check" in r.name)
        assert not inf_result.passed
        assert inf_result.value == 2

    def test_nan_warning_policy(self) -> None:
        validator = MathematicalLogicValidator(nan_policy="warning")
        data = np.array([1.0, np.nan])
        results = validator.validate_finite(data, name="data")
        nan_result = next(r for r in results if "nan_check" in r.name)
        assert nan_result.level == ValidationLevel.WARNING

    def test_inf_ignore_policy(self) -> None:
        validator = MathematicalLogicValidator(inf_policy="ignore")
        data = np.array([1.0, np.inf])
        results = validator.validate_finite(data, name="data")
        inf_result = next(r for r in results if "inf_check" in r.name)
        # When ignored, still passes
        assert inf_result.passed


class TestValidateBounds:
    """Tests for validate_bounds method."""

    def test_within_bounds(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([5.0, 10.0, 15.0])
        results = validator.validate_bounds(data, name="data", min_value=0, max_value=20)
        assert all(r.passed for r in results)

    def test_below_min_bound(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([5.0, 10.0, 15.0])
        results = validator.validate_bounds(data, name="data", min_value=6)
        min_result = next(r for r in results if "min_bound" in r.name)
        assert not min_result.passed

    def test_above_max_bound(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([5.0, 10.0, 15.0])
        results = validator.validate_bounds(data, name="data", max_value=12)
        max_result = next(r for r in results if "max_bound" in r.name)
        assert not max_result.passed

    def test_strict_bounds_min(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([5.0, 10.0])
        results = validator.validate_bounds(data, name="data", min_value=5.0, strict=True)
        min_result = next(r for r in results if "min_bound" in r.name)
        # Strict: 5.0 > 5.0 is False
        assert not min_result.passed

    def test_strict_bounds_max(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([5.0, 10.0])
        results = validator.validate_bounds(data, name="data", max_value=10.0, strict=True)
        max_result = next(r for r in results if "max_bound" in r.name)
        # Strict: 10.0 < 10.0 is False
        assert not max_result.passed

    def test_no_finite_values(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([np.nan, np.inf])
        results = validator.validate_bounds(data, name="data", min_value=0)
        assert any("No finite values" in r.message for r in results)


class TestValidateMonotonic:
    """Tests for validate_monotonic method."""

    def test_strictly_increasing_passes(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 3.0, 4.0])
        results = validator.validate_monotonic(data, direction="increasing", strict=True)
        assert results[0].passed

    def test_non_decreasing_passes(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 2.0, 3.0])
        results = validator.validate_monotonic(data, direction="increasing", strict=False)
        assert results[0].passed

    def test_strictly_increasing_fails(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 2.0, 3.0])  # Has equal values
        results = validator.validate_monotonic(data, direction="increasing", strict=True)
        assert not results[0].passed
        assert results[0].value == 1  # One violation

    def test_strictly_decreasing_passes(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([4.0, 3.0, 2.0, 1.0])
        results = validator.validate_monotonic(data, direction="decreasing", strict=True)
        assert results[0].passed

    def test_non_increasing_passes(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([4.0, 3.0, 3.0, 2.0])
        results = validator.validate_monotonic(data, direction="decreasing", strict=False)
        assert results[0].passed

    def test_decreasing_fails(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([4.0, 3.0, 5.0, 2.0])  # 3->5 is increase
        results = validator.validate_monotonic(data, direction="decreasing", strict=False)
        assert not results[0].passed

    def test_single_element(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0])
        results = validator.validate_monotonic(data)
        assert results[0].passed
        assert "trivially monotonic" in results[0].message


class TestValidateSumConservation:
    """Tests for validate_sum_conservation method."""

    def test_sum_conserved(self) -> None:
        validator = MathematicalLogicValidator()
        before = np.array([1.0, 2.0, 3.0])
        after = np.array([2.0, 2.0, 2.0])
        results = validator.validate_sum_conservation(before, after)
        assert results[0].passed

    def test_sum_not_conserved(self) -> None:
        validator = MathematicalLogicValidator()
        before = np.array([1.0, 2.0, 3.0])
        after = np.array([1.0, 1.0, 1.0])
        results = validator.validate_sum_conservation(before, after)
        assert not results[0].passed

    def test_custom_tolerance(self) -> None:
        validator = MathematicalLogicValidator()
        before = np.array([1.0, 2.0, 3.0])  # sum=6
        after = np.array([2.1, 2.0, 2.0])  # sum=6.1 (rel_diff ~0.017)
        results = validator.validate_sum_conservation(before, after, tolerance=0.02)
        assert results[0].passed

    def test_near_zero_sum(self) -> None:
        validator = MathematicalLogicValidator()
        before = np.array([0.0, 0.0])
        after = np.array([1e-13, -1e-13])
        results = validator.validate_sum_conservation(before, after)
        assert results[0].passed


class TestValidateProbabilityDistribution:
    """Tests for validate_probability_distribution method."""

    def test_valid_probability(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([0.2, 0.3, 0.5])
        results = validator.validate_probability_distribution(data)
        assert all(r.passed for r in results)

    def test_negative_probability(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([-0.1, 0.5, 0.6])
        results = validator.validate_probability_distribution(data)
        non_neg = next(r for r in results if "non_negative" in r.name)
        assert not non_neg.passed

    def test_sum_not_one(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([0.2, 0.3, 0.4])  # Sum = 0.9
        results = validator.validate_probability_distribution(data)
        sum_check = next(r for r in results if "sum_to_one" in r.name)
        assert not sum_check.passed

    def test_probability_exceeds_one(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([0.0, 1.2, -0.2])  # max > 1
        results = validator.validate_probability_distribution(data)
        max_check = next(r for r in results if "max_one" in r.name)
        assert not max_check.passed


class TestValidateStatisticalMoments:
    """Tests for validate_statistical_moments method."""

    def test_mean_within_tolerance(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([9.0, 10.0, 11.0])  # mean=10
        results = validator.validate_statistical_moments(data, expected_mean=10.0)
        mean_result = next(r for r in results if "mean" in r.name)
        assert mean_result.passed

    def test_mean_outside_tolerance(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([9.0, 10.0, 11.0])  # mean=10
        results = validator.validate_statistical_moments(
            data, expected_mean=5.0, mean_tolerance=0.01
        )
        mean_result = next(r for r in results if "mean" in r.name)
        assert not mean_result.passed

    def test_std_within_tolerance(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([0.0, 1.0, 2.0])  # std ~ 0.816
        results = validator.validate_statistical_moments(
            data, expected_std=0.816, std_tolerance=0.01
        )
        std_result = next(r for r in results if "std" in r.name)
        assert std_result.passed

    def test_std_outside_tolerance(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([0.0, 1.0, 2.0])
        results = validator.validate_statistical_moments(data, expected_std=0.5, std_tolerance=0.01)
        std_result = next(r for r in results if "std" in r.name)
        assert not std_result.passed

    def test_no_finite_values(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([np.nan, np.nan])
        results = validator.validate_statistical_moments(data, expected_mean=0.0)
        assert any("No finite values" in r.message for r in results)

    def test_near_zero_expected_mean(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1e-14, 0.0, -1e-14])
        results = validator.validate_statistical_moments(
            data, expected_mean=0.0, mean_tolerance=1e-10
        )
        mean_result = next(r for r in results if "mean" in r.name)
        assert mean_result.passed

    def test_near_zero_expected_std(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 1.0, 1.0])  # std=0
        results = validator.validate_statistical_moments(
            data, expected_std=0.0, std_tolerance=1e-10
        )
        std_result = next(r for r in results if "std" in r.name)
        assert std_result.passed


class TestValidateArray:
    """Tests for validate_array method."""

    def test_basic_validation(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 3.0])
        report = validator.validate_array(data, name="test")
        assert report.is_valid
        assert "size" in report.metrics
        assert report.metrics["size"] == 3

    def test_empty_array(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([])
        report = validator.validate_array(data, name="empty")
        assert any("empty" in str(c.message) for c in report.checks)

    def test_with_bounds(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 5.0, 10.0])
        report = validator.validate_array(data, name="data", min_value=0, max_value=15)
        assert report.is_valid

    def test_metrics_populated(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        report = validator.validate_array(data, name="data")
        assert "min" in report.metrics
        assert "max" in report.metrics
        assert "mean" in report.metrics
        assert "std" in report.metrics
        assert report.metrics["min"] == 1.0
        assert report.metrics["max"] == 5.0

    def test_skip_finite_check(self) -> None:
        validator = MathematicalLogicValidator()
        data = np.array([1.0, np.nan, 3.0])
        report = validator.validate_array(data, name="data", check_finite=False)
        # Should not have NaN check failures
        nan_checks = [c for c in report.checks if "nan" in c.name]
        assert len(nan_checks) == 0


class TestValidateRelationship:
    """Tests for validate_relationship method."""

    def test_relationship_holds(self) -> None:
        validator = MathematicalLogicValidator()
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 4.0, 6.0])
        result = validator.validate_relationship(
            x, y, relationship=lambda a, b: np.allclose(b, 2 * a), name="double"
        )
        assert result.passed

    def test_relationship_fails(self) -> None:
        validator = MathematicalLogicValidator()
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 4.0, 5.0])  # Not double
        result = validator.validate_relationship(
            x, y, relationship=lambda a, b: np.allclose(b, 2 * a), name="double"
        )
        assert not result.passed

    def test_relationship_with_exception(self) -> None:
        validator = MathematicalLogicValidator()
        x = np.array([1.0])
        y = np.array([2.0])

        def bad_relationship(a: np.ndarray, b: np.ndarray) -> bool:
            raise ValueError("Test error")

        result = validator.validate_relationship(x, y, relationship=bad_relationship, name="bad")
        assert not result.passed
        assert "Error" in result.message


class TestValidatePositiveDefinite:
    """Tests for validate_positive_definite function."""

    def test_positive_definite_matrix(self) -> None:
        # Identity matrix is positive definite
        matrix = np.eye(3)
        result = validate_positive_definite(matrix, name="identity")
        assert result.passed

    def test_negative_definite_matrix(self) -> None:
        # -I is not positive definite
        matrix = -np.eye(3)
        result = validate_positive_definite(matrix, name="neg_identity")
        assert not result.passed

    def test_non_square_matrix(self) -> None:
        matrix = np.array([[1, 2, 3], [4, 5, 6]])
        result = validate_positive_definite(matrix, name="rect")
        assert not result.passed
        assert "not a square matrix" in result.message

    def test_singular_matrix(self) -> None:
        # Singular matrix has zero eigenvalue
        matrix = np.array([[1, 2], [2, 4]])
        result = validate_positive_definite(matrix, name="singular")
        assert not result.passed


class TestValidateCorrelationMatrix:
    """Tests for validate_correlation_matrix function."""

    def test_valid_correlation_matrix(self) -> None:
        matrix = np.array([[1.0, 0.5], [0.5, 1.0]])
        results = validate_correlation_matrix(matrix, name="corr")
        assert all(r.passed for r in results)

    def test_non_square_matrix(self) -> None:
        matrix = np.array([[1, 2, 3], [4, 5, 6]])
        results = validate_correlation_matrix(matrix, name="rect")
        assert any(not r.passed for r in results)
        # Should return early with square check failure
        assert len(results) == 1

    def test_diagonal_not_ones(self) -> None:
        matrix = np.array([[0.9, 0.5], [0.5, 1.0]])
        results = validate_correlation_matrix(matrix, name="corr")
        diag_result = next(r for r in results if "diagonal_ones" in r.name)
        assert not diag_result.passed

    def test_not_symmetric(self) -> None:
        matrix = np.array([[1.0, 0.5], [0.3, 1.0]])
        results = validate_correlation_matrix(matrix, name="corr")
        sym_result = next(r for r in results if "symmetric" in r.name)
        assert not sym_result.passed

    def test_values_out_of_bounds(self) -> None:
        matrix = np.array([[1.0, 1.5], [1.5, 1.0]])
        results = validate_correlation_matrix(matrix, name="corr")
        bounds_result = next(r for r in results if "bounds" in r.name)
        assert not bounds_result.passed

    def test_not_positive_semidefinite(self) -> None:
        # This matrix is symmetric with 1s on diagonal but not PSD
        matrix = np.array([[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]])
        results = validate_correlation_matrix(matrix, name="corr")
        psd_result = next(r for r in results if "positive_definite" in r.name)
        assert not psd_result.passed
