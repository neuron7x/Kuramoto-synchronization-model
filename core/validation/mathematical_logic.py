# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical logic validation for data integrity and formal constraints.

This module provides validators that enforce mathematical constraints on trading
data transformations. The mathematical foundation ensures that all computations
maintain formal correctness, numerical stability, and logical consistency.

Key Components:
    ValidationResult: Result of a single validation check
    DataIntegrityReport: Comprehensive validation report
    MathematicalLogicValidator: Main validator with formal constraint checks

The validator implements:
    - Numerical stability: NaN/Inf detection and bounds checking
    - Monotonicity: Enforcing order relationships where required
    - Conservation laws: Sum/product invariants
    - Statistical constraints: Distribution bounds and moments
    - Logical consistency: Cross-field relationship validation

Example:
    >>> validator = MathematicalLogicValidator()
    >>> data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    >>> report = validator.validate_array(data, name="prices")
    >>> print(f"Valid: {report.is_valid}, Checks: {len(report.checks)}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import numpy as np


class ValidationLevel(Enum):
    """Severity level of validation results."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a single validation check.

    Attributes:
        name: Name of the validation check
        passed: Whether the check passed
        level: Severity level if failed
        message: Descriptive message
        value: The value that was checked
        expected: Expected value or range (optional)
    """

    name: str
    passed: bool
    level: ValidationLevel
    message: str
    value: Any = None
    expected: Any = None

    def __str__(self) -> str:
        status = "✓" if self.passed else "✗"
        return f"[{status}] {self.name}: {self.message}"


@dataclass(slots=True)
class DataIntegrityReport:
    """Comprehensive report of data integrity validation.

    Attributes:
        is_valid: True if all critical checks passed
        checks: List of all validation results
        errors: Count of error-level failures
        warnings: Count of warning-level issues
        metrics: Additional diagnostic metrics
    """

    is_valid: bool = True
    checks: list[ValidationResult] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    def add_check(self, result: ValidationResult) -> None:
        """Add a validation check result."""
        self.checks.append(result)
        if not result.passed:
            if result.level == ValidationLevel.ERROR:
                self.errors += 1
                self.is_valid = False
            elif result.level == ValidationLevel.WARNING:
                self.warnings += 1

    def get_failures(self) -> list[ValidationResult]:
        """Get all failed checks."""
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        """Generate summary string."""
        total = len(self.checks)
        passed = total - self.errors - self.warnings
        return (
            f"Validation: {passed}/{total} passed, {self.errors} errors, {self.warnings} warnings"
        )


class MathematicalLogicValidator:
    """Validator enforcing mathematical constraints and data integrity.

    The validator provides comprehensive checks for:

    1. Numerical Stability: Detection of NaN, Inf, and overflow conditions
    2. Bounds Checking: Ensuring values within specified ranges
    3. Monotonicity: Verifying order relationships
    4. Conservation: Checking sum/product invariants
    5. Statistical Properties: Moments, distribution bounds
    6. Logical Consistency: Cross-field relationships

    Example:
        >>> validator = MathematicalLogicValidator()
        >>> data = np.array([1.0, 2.0, 3.0])
        >>> report = validator.validate_array(data, name="test")
        >>> assert report.is_valid
    """

    def __init__(
        self,
        *,
        nan_policy: str = "error",
        inf_policy: str = "error",
        epsilon: float = 1e-12,
    ) -> None:
        """Initialize validator with configuration.

        Args:
            nan_policy: How to handle NaN values ("error", "warning", "ignore")
            inf_policy: How to handle Inf values ("error", "warning", "ignore")
            epsilon: Small value for numerical comparisons
        """
        self.nan_policy = nan_policy
        self.inf_policy = inf_policy
        self.epsilon = epsilon

    def _policy_to_level(self, policy: str) -> ValidationLevel | None:
        """Convert policy string to validation level."""
        if policy == "error":
            return ValidationLevel.ERROR
        elif policy == "warning":
            return ValidationLevel.WARNING
        return None

    def validate_finite(
        self,
        data: np.ndarray,
        name: str = "data",
    ) -> list[ValidationResult]:
        """Check that all values are finite (no NaN or Inf).

        Args:
            data: Array to validate.
            name: Name for error messages.

        Returns:
            List of validation results.
        """
        results = []
        data = np.asarray(data)

        # Check NaN
        nan_count = int(np.sum(np.isnan(data)))
        nan_level = self._policy_to_level(self.nan_policy)
        if nan_count > 0 and nan_level:
            results.append(
                ValidationResult(
                    name=f"{name}_nan_check",
                    passed=False,
                    level=nan_level,
                    message=f"Found {nan_count} NaN values in {name}",
                    value=nan_count,
                    expected=0,
                )
            )
        else:
            results.append(
                ValidationResult(
                    name=f"{name}_nan_check",
                    passed=True,
                    level=ValidationLevel.INFO,
                    message=f"No NaN values in {name}",
                )
            )

        # Check Inf
        inf_count = int(np.sum(np.isinf(data)))
        inf_level = self._policy_to_level(self.inf_policy)
        if inf_count > 0 and inf_level:
            results.append(
                ValidationResult(
                    name=f"{name}_inf_check",
                    passed=False,
                    level=inf_level,
                    message=f"Found {inf_count} Inf values in {name}",
                    value=inf_count,
                    expected=0,
                )
            )
        else:
            results.append(
                ValidationResult(
                    name=f"{name}_inf_check",
                    passed=True,
                    level=ValidationLevel.INFO,
                    message=f"No Inf values in {name}",
                )
            )

        return results

    def validate_bounds(
        self,
        data: np.ndarray,
        name: str = "data",
        min_value: float | None = None,
        max_value: float | None = None,
        strict: bool = False,
    ) -> list[ValidationResult]:
        """Check that values are within specified bounds.

        Args:
            data: Array to validate.
            name: Name for error messages.
            min_value: Minimum allowed value (inclusive unless strict).
            max_value: Maximum allowed value (inclusive unless strict).
            strict: If True, use strict inequalities.

        Returns:
            List of validation results.
        """
        results = []
        data = np.asarray(data)
        finite_data = data[np.isfinite(data)]

        if len(finite_data) == 0:
            results.append(
                ValidationResult(
                    name=f"{name}_bounds_check",
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message=f"No finite values to check bounds in {name}",
                )
            )
            return results

        data_min = float(np.min(finite_data))
        data_max = float(np.max(finite_data))

        # Check minimum bound
        if min_value is not None:
            if strict:
                passed = data_min > min_value
                op = ">"
            else:
                passed = data_min >= min_value
                op = ">="
            results.append(
                ValidationResult(
                    name=f"{name}_min_bound",
                    passed=passed,
                    level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
                    message=f"min({name})={data_min:.6g} {op} {min_value:.6g}: {'OK' if passed else 'FAIL'}",
                    value=data_min,
                    expected=f"{op} {min_value}",
                )
            )

        # Check maximum bound
        if max_value is not None:
            if strict:
                passed = data_max < max_value
                op = "<"
            else:
                passed = data_max <= max_value
                op = "<="
            results.append(
                ValidationResult(
                    name=f"{name}_max_bound",
                    passed=passed,
                    level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
                    message=f"max({name})={data_max:.6g} {op} {max_value:.6g}: {'OK' if passed else 'FAIL'}",
                    value=data_max,
                    expected=f"{op} {max_value}",
                )
            )

        return results

    def validate_monotonic(
        self,
        data: np.ndarray,
        name: str = "data",
        direction: str = "increasing",
        strict: bool = False,
    ) -> list[ValidationResult]:
        """Check that values maintain monotonic order.

        Args:
            data: Array to validate.
            name: Name for error messages.
            direction: "increasing" or "decreasing".
            strict: If True, require strict monotonicity.

        Returns:
            List of validation results.
        """
        results = []
        data = np.asarray(data)

        if len(data) < 2:
            results.append(
                ValidationResult(
                    name=f"{name}_monotonic",
                    passed=True,
                    level=ValidationLevel.INFO,
                    message=f"{name} has fewer than 2 elements, trivially monotonic",
                )
            )
            return results

        diff = np.diff(data)

        if direction == "increasing":
            if strict:
                violations = np.sum(diff <= 0)
                check_desc = "strictly increasing"
            else:
                violations = np.sum(diff < 0)
                check_desc = "non-decreasing"
        else:  # decreasing
            if strict:
                violations = np.sum(diff >= 0)
                check_desc = "strictly decreasing"
            else:
                violations = np.sum(diff > 0)
                check_desc = "non-increasing"

        passed = violations == 0
        results.append(
            ValidationResult(
                name=f"{name}_monotonic",
                passed=passed,
                level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
                message=f"{name} is {check_desc}: {violations} violations",
                value=int(violations),
                expected=0,
            )
        )

        return results

    def validate_sum_conservation(
        self,
        before: np.ndarray,
        after: np.ndarray,
        name: str = "data",
        tolerance: float | None = None,
    ) -> list[ValidationResult]:
        """Check that sum is conserved between two arrays.

        Args:
            before: Array before transformation.
            after: Array after transformation.
            name: Name for error messages.
            tolerance: Relative tolerance for sum comparison.

        Returns:
            List of validation results.
        """
        results = []
        tolerance = tolerance or self.epsilon

        sum_before = float(np.nansum(before))
        sum_after = float(np.nansum(after))

        if abs(sum_before) < self.epsilon:
            rel_diff = abs(sum_after - sum_before)
        else:
            rel_diff = abs(sum_after - sum_before) / abs(sum_before)

        passed = rel_diff <= tolerance
        results.append(
            ValidationResult(
                name=f"{name}_sum_conservation",
                passed=passed,
                level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
                message=f"Sum conservation: before={sum_before:.6g}, after={sum_after:.6g}, "
                f"rel_diff={rel_diff:.6g} (tol={tolerance:.6g})",
                value=rel_diff,
                expected=f"<= {tolerance}",
            )
        )

        return results

    def validate_probability_distribution(
        self,
        data: np.ndarray,
        name: str = "probabilities",
        tolerance: float = 1e-6,
    ) -> list[ValidationResult]:
        """Validate that array represents a valid probability distribution.

        Args:
            data: Array of probabilities.
            name: Name for error messages.
            tolerance: Tolerance for sum-to-one check.

        Returns:
            List of validation results.
        """
        results = []
        data = np.asarray(data)

        # Check non-negative
        min_val = float(np.min(data))
        non_neg_passed = min_val >= -tolerance
        results.append(
            ValidationResult(
                name=f"{name}_non_negative",
                passed=non_neg_passed,
                level=(ValidationLevel.ERROR if not non_neg_passed else ValidationLevel.INFO),
                message=f"Probabilities non-negative: min={min_val:.6g}",
                value=min_val,
                expected=">= 0",
            )
        )

        # Check sum to one
        total = float(np.sum(data))
        sum_passed = abs(total - 1.0) <= tolerance
        results.append(
            ValidationResult(
                name=f"{name}_sum_to_one",
                passed=sum_passed,
                level=ValidationLevel.ERROR if not sum_passed else ValidationLevel.INFO,
                message=f"Probabilities sum to 1: sum={total:.6g} (tol={tolerance:.6g})",
                value=total,
                expected=f"1.0 ± {tolerance}",
            )
        )

        # Check max <= 1
        max_val = float(np.max(data))
        max_passed = max_val <= 1.0 + tolerance
        results.append(
            ValidationResult(
                name=f"{name}_max_one",
                passed=max_passed,
                level=ValidationLevel.ERROR if not max_passed else ValidationLevel.INFO,
                message=f"Probabilities max <= 1: max={max_val:.6g}",
                value=max_val,
                expected="<= 1.0",
            )
        )

        return results

    def validate_statistical_moments(
        self,
        data: np.ndarray,
        name: str = "data",
        expected_mean: float | None = None,
        expected_std: float | None = None,
        mean_tolerance: float = 0.1,
        std_tolerance: float = 0.1,
    ) -> list[ValidationResult]:
        """Validate statistical moments of data.

        Args:
            data: Array to validate.
            name: Name for error messages.
            expected_mean: Expected mean value.
            expected_std: Expected standard deviation.
            mean_tolerance: Tolerance for mean comparison (relative).
            std_tolerance: Tolerance for std comparison (relative).

        Returns:
            List of validation results.
        """
        results = []
        data = np.asarray(data)
        finite_data = data[np.isfinite(data)]

        if len(finite_data) == 0:
            results.append(
                ValidationResult(
                    name=f"{name}_moments",
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message=f"No finite values for moment calculation in {name}",
                )
            )
            return results

        actual_mean = float(np.mean(finite_data))
        actual_std = float(np.std(finite_data))

        # Check mean if specified
        if expected_mean is not None:
            if abs(expected_mean) < self.epsilon:
                mean_diff = abs(actual_mean - expected_mean)
            else:
                mean_diff = abs(actual_mean - expected_mean) / abs(expected_mean)
            mean_passed = mean_diff <= mean_tolerance
            results.append(
                ValidationResult(
                    name=f"{name}_mean",
                    passed=mean_passed,
                    level=(ValidationLevel.WARNING if not mean_passed else ValidationLevel.INFO),
                    message=f"Mean: actual={actual_mean:.6g}, expected={expected_mean:.6g}, "
                    f"rel_diff={mean_diff:.6g}",
                    value=actual_mean,
                    expected=expected_mean,
                )
            )

        # Check std if specified
        if expected_std is not None:
            if abs(expected_std) < self.epsilon:
                std_diff = abs(actual_std - expected_std)
            else:
                std_diff = abs(actual_std - expected_std) / abs(expected_std)
            std_passed = std_diff <= std_tolerance
            results.append(
                ValidationResult(
                    name=f"{name}_std",
                    passed=std_passed,
                    level=(ValidationLevel.WARNING if not std_passed else ValidationLevel.INFO),
                    message=f"Std: actual={actual_std:.6g}, expected={expected_std:.6g}, "
                    f"rel_diff={std_diff:.6g}",
                    value=actual_std,
                    expected=expected_std,
                )
            )

        return results

    def validate_array(
        self,
        data: np.ndarray,
        name: str = "data",
        min_value: float | None = None,
        max_value: float | None = None,
        check_finite: bool = True,
    ) -> DataIntegrityReport:
        """Comprehensive validation of a data array.

        Args:
            data: Array to validate.
            name: Name for error messages.
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
            check_finite: Whether to check for NaN/Inf.

        Returns:
            DataIntegrityReport with all check results.
        """
        report = DataIntegrityReport()
        data = np.asarray(data)

        # Basic shape info
        report.metrics["size"] = data.size
        report.metrics["ndim"] = data.ndim

        if data.size == 0:
            report.add_check(
                ValidationResult(
                    name=f"{name}_empty",
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message=f"{name} is empty",
                )
            )
            return report

        # Finite checks
        if check_finite:
            for result in self.validate_finite(data, name):
                report.add_check(result)

        # Bounds checks
        if min_value is not None or max_value is not None:
            for result in self.validate_bounds(data, name, min_value, max_value):
                report.add_check(result)

        # Add metrics
        finite_data = data[np.isfinite(data)]
        if len(finite_data) > 0:
            report.metrics["min"] = float(np.min(finite_data))
            report.metrics["max"] = float(np.max(finite_data))
            report.metrics["mean"] = float(np.mean(finite_data))
            report.metrics["std"] = float(np.std(finite_data))
            report.metrics["finite_count"] = len(finite_data)

        return report

    def validate_relationship(
        self,
        x: np.ndarray,
        y: np.ndarray,
        relationship: Callable[[np.ndarray, np.ndarray], bool],
        name: str = "relationship",
        description: str = "",
    ) -> ValidationResult:
        """Validate a custom relationship between two arrays.

        Args:
            x: First array.
            y: Second array.
            relationship: Function that returns True if relationship holds.
            name: Name of the relationship check.
            description: Description of what's being checked.

        Returns:
            ValidationResult for the relationship check.
        """
        try:
            passed = relationship(x, y)
            return ValidationResult(
                name=name,
                passed=passed,
                level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
                message=f"{description}: {'OK' if passed else 'FAIL'}",
            )
        except Exception as e:
            return ValidationResult(
                name=name,
                passed=False,
                level=ValidationLevel.ERROR,
                message=f"{description}: Error - {e}",
            )


def validate_positive_definite(matrix: np.ndarray, name: str = "matrix") -> ValidationResult:
    """Check if a matrix is positive definite.

    Args:
        matrix: Square matrix to check.
        name: Name for error messages.

    Returns:
        ValidationResult indicating if matrix is positive definite.
    """
    matrix = np.asarray(matrix)

    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        return ValidationResult(
            name=f"{name}_positive_definite",
            passed=False,
            level=ValidationLevel.ERROR,
            message=f"{name} is not a square matrix",
        )

    try:
        eigenvalues = np.linalg.eigvalsh(matrix)
        min_eigenvalue = float(np.min(eigenvalues))
        passed = min_eigenvalue > 0
        return ValidationResult(
            name=f"{name}_positive_definite",
            passed=passed,
            level=ValidationLevel.ERROR if not passed else ValidationLevel.INFO,
            message=f"{name} positive definite: min_eigenvalue={min_eigenvalue:.6g}",
            value=min_eigenvalue,
            expected="> 0",
        )
    except np.linalg.LinAlgError as e:
        return ValidationResult(
            name=f"{name}_positive_definite",
            passed=False,
            level=ValidationLevel.ERROR,
            message=f"{name} eigenvalue computation failed: {e}",
        )


def validate_correlation_matrix(
    matrix: np.ndarray, name: str = "correlation"
) -> list[ValidationResult]:
    """Validate that a matrix is a valid correlation matrix.

    Args:
        matrix: Matrix to validate as correlation matrix.
        name: Name for error messages.

    Returns:
        List of validation results.
    """
    results = []
    matrix = np.asarray(matrix)

    # Check square
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        results.append(
            ValidationResult(
                name=f"{name}_square",
                passed=False,
                level=ValidationLevel.ERROR,
                message=f"{name} must be square, got shape {matrix.shape}",
            )
        )
        return results

    n = matrix.shape[0]

    # Check diagonal is 1
    diag = np.diag(matrix)
    diag_passed = np.allclose(diag, 1.0, atol=1e-6)
    results.append(
        ValidationResult(
            name=f"{name}_diagonal_ones",
            passed=diag_passed,
            level=ValidationLevel.ERROR if not diag_passed else ValidationLevel.INFO,
            message=f"{name} diagonal all 1s: {diag_passed}",
        )
    )

    # Check symmetric
    sym_diff = float(np.max(np.abs(matrix - matrix.T)))
    sym_passed = sym_diff < 1e-6
    results.append(
        ValidationResult(
            name=f"{name}_symmetric",
            passed=sym_passed,
            level=ValidationLevel.ERROR if not sym_passed else ValidationLevel.INFO,
            message=f"{name} symmetric: max_diff={sym_diff:.6g}",
        )
    )

    # Check bounds [-1, 1]
    off_diag = matrix[~np.eye(n, dtype=bool)]
    if len(off_diag) > 0:
        min_val = float(np.min(off_diag))
        max_val = float(np.max(off_diag))
        bounds_passed = min_val >= -1.0 - 1e-6 and max_val <= 1.0 + 1e-6
        results.append(
            ValidationResult(
                name=f"{name}_bounds",
                passed=bounds_passed,
                level=(ValidationLevel.ERROR if not bounds_passed else ValidationLevel.INFO),
                message=f"{name} in [-1,1]: min={min_val:.6g}, max={max_val:.6g}",
            )
        )

    # Check positive semi-definite
    results.append(validate_positive_definite(matrix, name))

    return results


__all__ = [
    "ValidationLevel",
    "ValidationResult",
    "DataIntegrityReport",
    "MathematicalLogicValidator",
    "validate_positive_definite",
    "validate_correlation_matrix",
]
