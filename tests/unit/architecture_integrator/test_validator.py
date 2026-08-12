# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core/architecture_integrator/validator.py module."""

from __future__ import annotations

import pytest

from core.architecture_integrator.component import (
    Component,
    ComponentHealth,
    ComponentMetadata,
    ComponentStatus,
)
from core.architecture_integrator.registry import ComponentRegistry
from core.architecture_integrator.validator import (
    ArchitectureValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)


class TestValidationSeverity:
    """Tests for ValidationSeverity enum."""

    def test_all_severities_defined(self) -> None:
        """Test all expected severities are defined."""
        expected = {"INFO", "WARNING", "ERROR", "CRITICAL"}
        actual = {s.name for s in ValidationSeverity}
        assert actual == expected

    def test_severity_values(self) -> None:
        """Test severity string values."""
        assert ValidationSeverity.INFO.value == "info"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.CRITICAL.value == "critical"


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic issue creation."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            component="test-component",
            category="dependencies",
            message="Missing dependency",
        )
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.component == "test-component"
        assert issue.category == "dependencies"
        assert issue.message == "Missing dependency"
        assert issue.metadata == {}

    def test_with_metadata(self) -> None:
        """Test issue with metadata."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            component="test",
            category="health",
            message="High load",
            metadata={"cpu": 95.0, "memory": 80.0},
        )
        assert issue.metadata["cpu"] == 95.0
        assert issue.metadata["memory"] == 80.0

    def test_is_blocking_error(self) -> None:
        """Test is_blocking returns True for ERROR."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            component="test",
            category="test",
            message="test",
        )
        assert issue.is_blocking() is True

    def test_is_blocking_critical(self) -> None:
        """Test is_blocking returns True for CRITICAL."""
        issue = ValidationIssue(
            severity=ValidationSeverity.CRITICAL,
            component="test",
            category="test",
            message="test",
        )
        assert issue.is_blocking() is True

    def test_is_blocking_warning(self) -> None:
        """Test is_blocking returns False for WARNING."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            component="test",
            category="test",
            message="test",
        )
        assert issue.is_blocking() is False

    def test_is_blocking_info(self) -> None:
        """Test is_blocking returns False for INFO."""
        issue = ValidationIssue(
            severity=ValidationSeverity.INFO,
            component="test",
            category="test",
            message="test",
        )
        assert issue.is_blocking() is False


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_passed_result(self) -> None:
        """Test passed validation result."""
        result = ValidationResult(passed=True)
        assert result.passed is True
        assert result.issues == []

    def test_failed_result(self) -> None:
        """Test failed validation result."""
        issues = [
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                component="test",
                category="test",
                message="error",
            )
        ]
        result = ValidationResult(passed=False, issues=issues)
        assert result.passed is False
        assert len(result.issues) == 1

    def test_get_blocking_issues(self) -> None:
        """Test get_blocking_issues method."""
        issues = [
            ValidationIssue(
                severity=ValidationSeverity.INFO,
                component="test",
                category="test",
                message="info",
            ),
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                component="test",
                category="test",
                message="error",
            ),
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                component="test",
                category="test",
                message="warning",
            ),
        ]
        result = ValidationResult(passed=False, issues=issues)
        blocking = result.get_blocking_issues()

        assert len(blocking) == 1
        assert blocking[0].severity == ValidationSeverity.ERROR

    def test_get_by_severity(self) -> None:
        """Test get_by_severity method."""
        issues = [
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                component="test",
                category="test",
                message="warning1",
            ),
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                component="test",
                category="test",
                message="warning2",
            ),
            ValidationIssue(
                severity=ValidationSeverity.INFO,
                component="test",
                category="test",
                message="info",
            ),
        ]
        result = ValidationResult(passed=True, issues=issues)

        warnings = result.get_by_severity(ValidationSeverity.WARNING)
        assert len(warnings) == 2

        infos = result.get_by_severity(ValidationSeverity.INFO)
        assert len(infos) == 1

    def test_summary(self) -> None:
        """Test summary method."""
        issues = [
            ValidationIssue(
                severity=ValidationSeverity.INFO,
                component="test",
                category="test",
                message="info",
            ),
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                component="test",
                category="test",
                message="warning",
            ),
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                component="test",
                category="test",
                message="warning2",
            ),
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                component="test",
                category="test",
                message="error",
            ),
        ]
        result = ValidationResult(passed=False, issues=issues)
        summary = result.summary()

        assert summary["info"] == 1
        assert summary["warning"] == 2
        assert summary["error"] == 1
        assert summary["critical"] == 0


class TestArchitectureValidator:
    """Tests for ArchitectureValidator class."""

    def test_initialization(self) -> None:
        """Test validator initialization."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        assert validator._registry == registry
        assert validator._custom_rules == []

    def test_add_custom_rule(self) -> None:
        """Test adding custom rule."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)

        def custom_rule(reg: ComponentRegistry) -> list[ValidationIssue]:
            return []

        validator.add_custom_rule(custom_rule)
        assert len(validator._custom_rules) == 1

    def test_validate_all_empty_registry(self) -> None:
        """Test validate_all with empty registry."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)

        result = validator.validate_all()

        assert result.passed is True
        assert result.issues == []

    def test_validate_all_healthy_components(self) -> None:
        """Test validate_all with healthy components."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        assert result.passed is True

    def test_validate_all_detects_missing_dependencies(self) -> None:
        """Test validate_all detects missing dependencies."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test", dependencies=["missing"])
        component = Component(metadata=metadata, instance=object())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        assert result.passed is False
        assert any("missing" in issue.message.lower() for issue in result.issues)

    def test_validate_all_detects_circular_dependencies(self) -> None:
        """Test validate_all detects circular dependencies."""
        registry = ComponentRegistry()
        metadata_a = ComponentMetadata(name="a", dependencies=["b"])
        metadata_b = ComponentMetadata(name="b", dependencies=["a"])

        registry.register(Component(metadata=metadata_a, instance=object()))
        registry.register(Component(metadata=metadata_b, instance=object()))

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        assert result.passed is False
        assert any(issue.category == "circular_dependency" for issue in result.issues)

    def test_validate_all_checks_component_health(self) -> None:
        """Test validate_all checks component health."""

        class UnhealthyComponent:
            def health_check(self) -> ComponentHealth:
                return ComponentHealth(
                    status=ComponentStatus.DEGRADED,
                    healthy=False,
                    message="High load",
                )

        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=UnhealthyComponent())
        component.status = ComponentStatus.RUNNING
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        assert any(
            issue.category == "health" and "unhealthy" in issue.message.lower()
            for issue in result.issues
        )

    def test_validate_all_handles_health_check_failure(self) -> None:
        """Test validate_all handles health check failures."""

        class FailingComponent:
            def health_check(self) -> ComponentHealth:
                raise ValueError("Health check error")

        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())
        component.status = ComponentStatus.RUNNING
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        assert any(
            issue.category == "health" and "failed" in issue.message.lower()
            for issue in result.issues
        )

    def test_validate_all_configuration_info(self) -> None:
        """Test validate_all reports configuration info."""
        registry = ComponentRegistry()
        # Component with dependencies but no config
        metadata = ComponentMetadata(name="test", dependencies=["db"])
        metadata_db = ComponentMetadata(name="db", provides=["db"])

        registry.register(Component(metadata=metadata, instance=object()))
        registry.register(Component(metadata=metadata_db, instance=object()))

        validator = ArchitectureValidator(registry)
        result = validator.validate_all()

        info_issues = result.get_by_severity(ValidationSeverity.INFO)
        assert any("configuration" in issue.category for issue in info_issues)

    def test_validate_all_runs_custom_rules(self) -> None:
        """Test validate_all runs custom rules."""
        registry = ComponentRegistry()

        def custom_rule(reg: ComponentRegistry) -> list[ValidationIssue]:
            return [
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    component="custom",
                    category="custom_check",
                    message="Custom validation",
                )
            ]

        validator = ArchitectureValidator(registry)
        validator.add_custom_rule(custom_rule)

        result = validator.validate_all()

        assert any(issue.category == "custom_check" for issue in result.issues)

    def test_validate_all_handles_custom_rule_failure(self) -> None:
        """Test validate_all handles custom rule failures."""
        registry = ComponentRegistry()

        def failing_rule(reg: ComponentRegistry) -> list[ValidationIssue]:
            raise ValueError("Rule failed")

        validator = ArchitectureValidator(registry)
        validator.add_custom_rule(failing_rule)

        result = validator.validate_all()

        assert any(
            issue.category == "custom_rule" and "failed" in issue.message.lower()
            for issue in result.issues
        )

    def test_validate_component(self) -> None:
        """Test validate_component."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=object())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_component("test")

        assert result.passed is True

    def test_validate_component_missing_dependency(self) -> None:
        """Test validate_component with missing dependency."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test", dependencies=["missing"])
        component = Component(metadata=metadata, instance=object())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_component("test")

        assert result.passed is False
        assert any("missing" in issue.message for issue in result.issues)

    def test_validate_component_unhealthy(self) -> None:
        """Test validate_component with unhealthy component."""

        class UnhealthyComponent:
            def health_check(self) -> ComponentHealth:
                return ComponentHealth(
                    status=ComponentStatus.FAILED,
                    healthy=False,
                    message="Component failed",
                )

        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=UnhealthyComponent())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_component("test")

        assert result.passed is False
        assert any(issue.severity == ValidationSeverity.CRITICAL for issue in result.issues)

    def test_validate_component_health_check_failure(self) -> None:
        """Test validate_component handles health check failure."""

        class FailingComponent:
            def health_check(self) -> ComponentHealth:
                raise ValueError("Health check error")

        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="test")
        component = Component(metadata=metadata, instance=FailingComponent())
        registry.register(component)

        validator = ArchitectureValidator(registry)
        result = validator.validate_component("test")

        assert result.passed is False
        assert any("health check failed" in issue.message.lower() for issue in result.issues)

    def test_validate_component_not_found(self) -> None:
        """Test validate_component with nonexistent component."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)

        with pytest.raises(KeyError):
            validator.validate_component("nonexistent")


class TestValidatorGuardBranches:
    """Pin the three surviving validation guards: severity dispatch, empty-config, dep resolution."""

    def _registered(self, registry: "ComponentRegistry", **meta: object) -> "Component":
        component = Component(metadata=ComponentMetadata(**meta), instance=object())
        registry.register(component)
        return component

    def test_failed_health_is_critical_other_unhealthy_is_warning(self) -> None:
        """`... if health.status == ComponentStatus.FAILED else WARNING` -- FAILED is CRITICAL.

        Under `Eq -> NotEq` a FAILED component is downgraded to WARNING and a merely DEGRADED
        one is escalated to CRITICAL -- the severity map inverts on the safety-relevant edge.
        """
        registry = ComponentRegistry()
        failed = self._registered(registry, name="failed")
        failed.status = ComponentStatus.RUNNING
        failed.health_hook = lambda: ComponentHealth(status=ComponentStatus.FAILED, healthy=False)
        degraded = self._registered(registry, name="degraded")
        degraded.status = ComponentStatus.RUNNING
        degraded.health_hook = lambda: ComponentHealth(status=ComponentStatus.DEGRADED, healthy=False)

        result = ArchitectureValidator(registry).validate_all()
        by_component = {i.component: i.severity for i in result.issues if i.category == "health"}
        assert by_component["failed"] == ValidationSeverity.CRITICAL
        assert by_component["degraded"] == ValidationSeverity.WARNING

    def test_dependency_satisfied_by_capability_is_not_flagged(self) -> None:
        """`not has_component(dep) and not has_capability(dep)` -- a dep is missing only if
        NEITHER a component nor a capability provides it.

        Under `And -> Or` a dependency resolved purely through a provided capability is wrongly
        reported missing.
        """
        registry = ComponentRegistry()
        self._registered(registry, name="provider", provides=["telemetry"])
        self._registered(registry, name="consumer", dependencies=["telemetry"])

        # validate_component() is the per-component path that resolves deps via component OR
        # capability; validate_all uses a separate dependency pass.
        result = ArchitectureValidator(registry).validate_component("consumer")
        dep_issues = [i for i in result.issues if i.category == "dependencies"]
        assert not any("telemetry" in i.message.lower() for i in dep_issues), (
            "a capability-resolved dependency was reported as missing"
        )

    def test_empty_config_note_only_for_configless_components(self) -> None:
        """`if not config and component.get_dependencies()` -- the empty-config note is for
        dependency-carrying components that have NO configuration.

        Under `And -> Or` a fully-configured component with dependencies also gets the note.
        """
        registry = ComponentRegistry()
        self._registered(
            registry, name="configured", dependencies=["dep"], configuration={"k": "v"}
        )
        self._registered(registry, name="dep")

        result = ArchitectureValidator(registry).validate_all()
        info = [i for i in result.issues if i.component == "configured" and "config" in i.message.lower()]
        assert not info, "a configured component was flagged for empty configuration"
