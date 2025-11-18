# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Comprehensive test suite for architecture_integrator/validator.py

Tests architecture validation and compliance checking.
Following 2025 best practices with comprehensive coverage.
"""
import pytest
from unittest.mock import Mock

from core.architecture_integrator.component import (
    Component,
    ComponentMetadata,
    ComponentHealth,
    ComponentStatus,
)
from core.architecture_integrator.registry import ComponentRegistry
from core.architecture_integrator.validator import (
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
    ArchitectureValidator,
)


class TestValidationSeverity:
    """Test ValidationSeverity enum."""

    def test_all_severities_defined(self):
        """Test all severity levels are defined."""
        expected = {"INFO", "WARNING", "ERROR", "CRITICAL"}
        actual = {s.name for s in ValidationSeverity}
        assert actual == expected


class TestValidationIssue:
    """Test ValidationIssue dataclass."""

    def test_issue_creation(self):
        """Test creating validation issue."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            component="TestComponent",
            category="health",
            message="Component failed",
        )
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.component == "TestComponent"
        assert issue.category == "health"
        assert issue.message == "Component failed"

    def test_is_blocking_error(self):
        """Test ERROR severity is blocking."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            component="Test",
            category="test",
            message="Error",
        )
        assert issue.is_blocking() is True

    def test_is_blocking_critical(self):
        """Test CRITICAL severity is blocking."""
        issue = ValidationIssue(
            severity=ValidationSeverity.CRITICAL,
            component="Test",
            category="test",
            message="Critical",
        )
        assert issue.is_blocking() is True

    def test_is_not_blocking_warning(self):
        """Test WARNING severity is not blocking."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            component="Test",
            category="test",
            message="Warning",
        )
        assert issue.is_blocking() is False

    def test_is_not_blocking_info(self):
        """Test INFO severity is not blocking."""
        issue = ValidationIssue(
            severity=ValidationSeverity.INFO,
            component="Test",
            category="test",
            message="Info",
        )
        assert issue.is_blocking() is False


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_result_creation(self):
        """Test creating validation result."""
        result = ValidationResult(passed=True, issues=[])
        assert result.passed is True
        assert result.issues == []

    def test_get_blocking_issues(self):
        """Test filtering blocking issues."""
        issues = [
            ValidationIssue(ValidationSeverity.INFO, "A", "test", "Info"),
            ValidationIssue(ValidationSeverity.ERROR, "B", "test", "Error"),
            ValidationIssue(ValidationSeverity.WARNING, "C", "test", "Warning"),
            ValidationIssue(ValidationSeverity.CRITICAL, "D", "test", "Critical"),
        ]
        result = ValidationResult(passed=False, issues=issues)
        
        blocking = result.get_blocking_issues()
        assert len(blocking) == 2
        assert blocking[0].severity == ValidationSeverity.ERROR
        assert blocking[1].severity == ValidationSeverity.CRITICAL

    def test_get_by_severity(self):
        """Test filtering issues by severity."""
        issues = [
            ValidationIssue(ValidationSeverity.INFO, "A", "test", "Info"),
            ValidationIssue(ValidationSeverity.ERROR, "B", "test", "Error1"),
            ValidationIssue(ValidationSeverity.ERROR, "C", "test", "Error2"),
        ]
        result = ValidationResult(passed=False, issues=issues)
        
        errors = result.get_by_severity(ValidationSeverity.ERROR)
        assert len(errors) == 2

    def test_summary(self):
        """Test getting summary of issues."""
        issues = [
            ValidationIssue(ValidationSeverity.INFO, "A", "test", "Info"),
            ValidationIssue(ValidationSeverity.ERROR, "B", "test", "Error"),
            ValidationIssue(ValidationSeverity.ERROR, "C", "test", "Error2"),
            ValidationIssue(ValidationSeverity.CRITICAL, "D", "test", "Critical"),
        ]
        result = ValidationResult(passed=False, issues=issues)
        
        summary = result.summary()
        assert summary["info"] == 1
        assert summary["error"] == 2
        assert summary["warning"] == 0
        assert summary["critical"] == 1


class TestArchitectureValidator:
    """Test ArchitectureValidator class."""

    def test_validator_creation(self):
        """Test creating validator."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        assert validator._registry == registry

    def test_add_custom_rule(self):
        """Test adding custom validation rule."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        
        def custom_rule(reg):
            return []
        
        validator.add_custom_rule(custom_rule)
        assert custom_rule in validator._custom_rules

    def test_validate_all_empty_registry(self):
        """Test validation with empty registry."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        
        result = validator.validate_all()
        assert result.passed is True
        assert result.issues == []

    def test_validate_dependencies_missing(self):
        """Test validation detects missing dependencies."""
        registry = ComponentRegistry()
        metadata = ComponentMetadata(name="Consumer", dependencies=["Provider"])
        registry.register(Component(metadata=metadata, instance=Mock()))
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is False
        assert len(result.issues) > 0
        assert any("depends on" in issue.message for issue in result.issues)

    def test_validate_dependencies_satisfied(self):
        """Test validation passes with satisfied dependencies."""
        registry = ComponentRegistry()
        
        provider_meta = ComponentMetadata(name="Provider")
        consumer_meta = ComponentMetadata(name="Consumer", dependencies=["Provider"])
        
        registry.register(Component(metadata=provider_meta, instance=Mock()))
        registry.register(Component(metadata=consumer_meta, instance=Mock()))
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is True

    def test_validate_circular_dependencies(self):
        """Test validation detects circular dependencies."""
        registry = ComponentRegistry()
        
        meta_a = ComponentMetadata(name="A", dependencies=["B"])
        meta_b = ComponentMetadata(name="B", dependencies=["A"])
        
        registry.register(Component(metadata=meta_a, instance=Mock()))
        registry.register(Component(metadata=meta_b, instance=Mock()))
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is False
        critical_issues = result.get_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0
        assert any("Circular dependency" in issue.message for issue in critical_issues)

    def test_validate_component_health_healthy(self):
        """Test validation of healthy components."""
        registry = ComponentRegistry()
        
        instance = Mock()
        instance.health_check = Mock(
            return_value=ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
            )
        )
        
        metadata = ComponentMetadata(name="HealthyComponent")
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.RUNNING
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is True

    def test_validate_component_health_unhealthy(self):
        """Test validation detects unhealthy components."""
        registry = ComponentRegistry()
        
        instance = Mock()
        instance.health_check = Mock(
            return_value=ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message="Service degraded",
            )
        )
        
        metadata = ComponentMetadata(name="UnhealthyComponent")
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.DEGRADED
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is True  # WARNING is not blocking
        warning_issues = result.get_by_severity(ValidationSeverity.WARNING)
        assert len(warning_issues) > 0

    def test_validate_component_health_failed(self):
        """Test validation detects failed components."""
        registry = ComponentRegistry()
        
        instance = Mock()
        instance.health_check = Mock(
            return_value=ComponentHealth(
                status=ComponentStatus.FAILED,
                healthy=False,
                message="Component failed",
            )
        )
        
        metadata = ComponentMetadata(name="FailedComponent")
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.FAILED
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is False
        critical_issues = result.get_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0

    def test_validate_component_health_check_exception(self):
        """Test validation handles health check exceptions."""
        registry = ComponentRegistry()
        
        instance = Mock()
        instance.health_check = Mock(side_effect=RuntimeError("Health check error"))
        
        metadata = ComponentMetadata(name="BrokenComponent")
        component = Component(metadata=metadata, instance=instance)
        component.status = ComponentStatus.RUNNING
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        assert result.passed is False
        # Health check exceptions result in CRITICAL severity (FAILED status)
        critical_issues = result.get_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0

    def test_validate_configuration(self):
        """Test configuration validation."""
        registry = ComponentRegistry()
        
        # Component with dependencies but no config
        metadata = ComponentMetadata(
            name="Consumer",
            dependencies=["Provider"],
            configuration={},
        )
        
        registry.register(Component(metadata=metadata, instance=Mock()))
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        # Should have INFO issue about missing config
        info_issues = result.get_by_severity(ValidationSeverity.INFO)
        assert len(info_issues) > 0

    def test_custom_rule_execution(self):
        """Test that custom rules are executed."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        
        executed = []
        
        def custom_rule(reg):
            executed.append(True)
            return [
                ValidationIssue(
                    ValidationSeverity.INFO,
                    "custom",
                    "test",
                    "Custom rule ran",
                )
            ]
        
        validator.add_custom_rule(custom_rule)
        result = validator.validate_all()
        
        assert executed == [True]
        assert any("Custom rule ran" in issue.message for issue in result.issues)

    def test_custom_rule_exception(self):
        """Test handling of custom rule exceptions."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        
        def failing_rule(reg):
            raise RuntimeError("Rule failed")
        
        validator.add_custom_rule(failing_rule)
        result = validator.validate_all()
        
        assert result.passed is False
        assert any("Custom rule failed" in issue.message for issue in result.issues)

    def test_validate_component_specific(self):
        """Test validating a specific component."""
        registry = ComponentRegistry()
        
        provider_meta = ComponentMetadata(name="Provider")
        consumer_meta = ComponentMetadata(name="Consumer", dependencies=["Provider"])
        
        provider = Component(metadata=provider_meta, instance=Mock())
        consumer = Component(metadata=consumer_meta, instance=Mock())
        
        registry.register(provider)
        registry.register(consumer)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_component("Consumer")
        
        assert result.passed is True

    def test_validate_component_missing_dependency(self):
        """Test validating component with missing dependency."""
        registry = ComponentRegistry()
        
        metadata = ComponentMetadata(name="Consumer", dependencies=["Missing"])
        component = Component(metadata=metadata, instance=Mock())
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_component("Consumer")
        
        assert result.passed is False
        assert any("not available" in issue.message for issue in result.issues)

    def test_validate_component_not_found(self):
        """Test validating non-existent component raises error."""
        registry = ComponentRegistry()
        validator = ArchitectureValidator(registry)
        
        with pytest.raises(KeyError):
            validator.validate_component("NonExistent")

    def test_skips_uninitialized_components(self):
        """Test that uninitialized components are skipped in health validation."""
        registry = ComponentRegistry()
        
        metadata = ComponentMetadata(name="Uninitialized")
        component = Component(metadata=metadata, instance=Mock())
        # Component is UNINITIALIZED by default
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        # Should pass since uninitialized components are skipped
        assert result.passed is True

    def test_validate_component_health_exception_in_validate_component(self):
        """Test exception handling in validate_component method."""
        registry = ComponentRegistry()
        
        # Create a component that will raise an exception when check_health is called
        # but we need to intercept before Component.check_health catches it
        metadata = ComponentMetadata(name="ExceptionComponent")
        instance = Mock()
        
        # Make check_health raise but set up component
        def raise_error():
            raise RuntimeError("Direct exception")
        
        component = Component(metadata=metadata, instance=instance)
        component.check_health = raise_error  # Override the method
        component.status = ComponentStatus.RUNNING
        
        registry.register(component)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_component("ExceptionComponent")
        
        # Should have ERROR issue
        assert result.passed is False
        error_issues = result.get_by_severity(ValidationSeverity.ERROR)
        assert len(error_issues) > 0
        assert "Health check failed" in error_issues[0].message


class TestArchitectureValidatorIntegration:
    """Integration tests combining multiple validation aspects."""

    def test_complex_validation_scenario(self):
        """Test complex scenario with multiple components and issues."""
        registry = ComponentRegistry()
        
        # Healthy provider
        provider_instance = Mock()
        provider_instance.health_check = Mock(
            return_value=ComponentHealth(
                status=ComponentStatus.RUNNING,
                healthy=True,
            )
        )
        provider = Component(
            metadata=ComponentMetadata(name="Provider", provides=["service"]),
            instance=provider_instance,
        )
        provider.status = ComponentStatus.RUNNING
        
        # Degraded consumer
        consumer_instance = Mock()
        consumer_instance.health_check = Mock(
            return_value=ComponentHealth(
                status=ComponentStatus.DEGRADED,
                healthy=False,
                message="Slow performance",
            )
        )
        consumer = Component(
            metadata=ComponentMetadata(
                name="Consumer",
                dependencies=["service"],
            ),
            instance=consumer_instance,
        )
        consumer.status = ComponentStatus.DEGRADED
        
        # Component with missing dependency
        broken = Component(
            metadata=ComponentMetadata(
                name="Broken",
                dependencies=["MissingService"],
            ),
            instance=Mock(),
        )
        
        registry.register(provider)
        registry.register(consumer)
        registry.register(broken)
        
        validator = ArchitectureValidator(registry)
        result = validator.validate_all()
        
        # Should fail due to missing dependency
        assert result.passed is False
        
        # Should have WARNING for degraded and ERROR for missing dependency
        summary = result.summary()
        assert summary["warning"] >= 1
        assert summary["error"] >= 1
