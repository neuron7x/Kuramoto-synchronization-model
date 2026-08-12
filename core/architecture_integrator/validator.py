# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architecture validation and compliance checking.

This module provides validation utilities to ensure architectural constraints
and compliance requirements are met across the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from core.architecture_integrator.component import ComponentStatus
from core.architecture_integrator.registry import ComponentRegistry


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Represents a validation issue found during architecture checking."""

    severity: ValidationSeverity
    component: str
    category: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_blocking(self) -> bool:
        """Check if this issue should block system operations."""
        return self.severity in {ValidationSeverity.ERROR, ValidationSeverity.CRITICAL}


@dataclass
class ValidationResult:
    """Result of architecture validation."""

    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_blocking_issues(self) -> list[ValidationIssue]:
        """Return only blocking issues."""
        return [issue for issue in self.issues if issue.is_blocking()]

    def get_by_severity(self, severity: ValidationSeverity) -> list[ValidationIssue]:
        """Return issues of a specific severity."""
        return [issue for issue in self.issues if issue.severity == severity]

    def summary(self) -> dict[str, int]:
        """Get a summary count of issues by severity."""
        counts = {severity.value: 0 for severity in ValidationSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts


class ArchitectureValidator:
    """Validates architectural constraints and compliance requirements."""

    def __init__(self, registry: ComponentRegistry) -> None:
        """Initialize the validator.

        Args:
            registry: Component registry to validate
        """
        self._registry = registry
        self._custom_rules: list[Callable[[ComponentRegistry], list[ValidationIssue]]] = []

    def add_custom_rule(self, rule: Callable[[ComponentRegistry], list[ValidationIssue]]) -> None:
        """Add a custom validation rule.

        Args:
            rule: Function that takes registry and returns list of validation issues
        """
        self._custom_rules.append(rule)

    def validate_all(self) -> ValidationResult:
        """Run all validation checks.

        Returns:
            ValidationResult with all issues found
        """
        issues: list[ValidationIssue] = []

        # Run built-in validations
        issues.extend(self._validate_dependencies())
        issues.extend(self._validate_circular_dependencies())
        issues.extend(self._validate_component_health())
        issues.extend(self._validate_configuration())

        # Run custom rules
        for rule in self._custom_rules:
            try:
                issues.extend(rule(self._registry))
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        component="validator",
                        category="custom_rule",
                        message=f"Custom rule failed: {exc}",
                    )
                )

        # Determine overall pass/fail
        passed = not any(issue.is_blocking() for issue in issues)

        return ValidationResult(passed=passed, issues=issues)

    def _validate_dependencies(self) -> list[ValidationIssue]:
        """Validate that all component dependencies are satisfied."""
        issues: list[ValidationIssue] = []
        errors = self._registry.validate_dependencies()

        for error in errors:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    component="registry",
                    category="dependencies",
                    message=error,
                )
            )

        return issues

    def _validate_circular_dependencies(self) -> list[ValidationIssue]:
        """Check for circular dependencies in the component graph."""
        issues: list[ValidationIssue] = []

        try:
            self._registry.get_initialization_order()
        except ValueError as exc:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.CRITICAL,
                    component="registry",
                    category="circular_dependency",
                    message=str(exc),
                )
            )

        return issues

    def _validate_component_health(self) -> list[ValidationIssue]:
        """Check health status of all components."""
        issues: list[ValidationIssue] = []

        for component in self._registry.get_all():
            # Skip uninitialized components
            if component.status == ComponentStatus.UNINITIALIZED:
                continue

            try:
                health = component.check_health()

                if not health.healthy:
                    severity = (
                        ValidationSeverity.CRITICAL
                        if health.status == ComponentStatus.FAILED
                        else ValidationSeverity.WARNING
                    )
                    issues.append(
                        ValidationIssue(
                            severity=severity,
                            component=component.metadata.name,
                            category="health",
                            message=f"Component unhealthy: {health.message}",
                            metadata={"status": health.status.value},
                        )
                    )
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        component=component.metadata.name,
                        category="health",
                        message=f"Health check failed: {exc}",
                    )
                )

        return issues

    def _validate_configuration(self) -> list[ValidationIssue]:
        """Validate component configurations."""
        issues: list[ValidationIssue] = []

        for component in self._registry.get_all():
            config = component.metadata.configuration

            # Check for empty configurations on non-simple components
            if not config and component.get_dependencies():
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.INFO,
                        component=component.metadata.name,
                        category="configuration",
                        message="Component has dependencies but no configuration",
                    )
                )

        return issues

    def validate_component(self, name: str) -> ValidationResult:
        """Validate a specific component.

        Args:
            name: Component name

        Returns:
            ValidationResult for the component

        Raises:
            KeyError: If component not found
        """
        component = self._registry.get(name)
        issues: list[ValidationIssue] = []

        # Check dependencies
        for dep in component.get_dependencies():
            if not self._registry.has_component(dep) and not self._registry.has_capability(dep):
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        component=name,
                        category="dependencies",
                        message=f"Dependency '{dep}' not available",
                    )
                )

        # Check health
        try:
            health = component.check_health()
            if not health.healthy:
                severity = (
                    ValidationSeverity.CRITICAL
                    if health.status == ComponentStatus.FAILED
                    else ValidationSeverity.WARNING
                )
                issues.append(
                    ValidationIssue(
                        severity=severity,
                        component=name,
                        category="health",
                        message=f"Component unhealthy: {health.message}",
                    )
                )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    component=name,
                    category="health",
                    message=f"Health check failed: {exc}",
                )
            )

        passed = not any(issue.is_blocking() for issue in issues)
        return ValidationResult(passed=passed, issues=issues)
