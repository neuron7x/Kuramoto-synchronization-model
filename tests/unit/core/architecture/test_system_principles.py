# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the core architecture system principles module."""

from __future__ import annotations

import json
import time
from typing import Any, Dict

import pytest

from core.architecture.system_principles import (
    AutonomousPrinciple,
    AutonomyLevel,
    ComponentRole,
    ControlAction,
    ControllablePrinciple,
    IntegrationContract,
    IntegrativePrinciple,
    ModularPrinciple,
    NeuroOrientedPrinciple,
    PrincipleStatus,
    PrincipleViolation,
    ReproduciblePrinciple,
    RoleBasedPrinciple,
    StateSnapshot,
    SystemArchitecture,
    get_system_architecture,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def full_context() -> Dict[str, Any]:
    """Create a full valid context for testing."""
    return {
        # Neuro-oriented
        "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
        "components": [
            "basal_ganglia_selector",
            "dopamine_learning_loop",
            "serotonin_risk_manager",
            "tacl_monitor",
        ],
        "learning_loop": {"algorithm": "TD(0)", "learning_rate": 0.01},
        # Modular
        "coupling_score": 0.2,
        "cohesion_score": 0.8,
        "circular_dependencies": [],
        # Role-based
        "assigned_roles": [
            ComponentRole.SENSOR,
            ComponentRole.PROCESSOR,
            ComponentRole.ACTUATOR,
            ComponentRole.COORDINATOR,
            ComponentRole.MONITOR,
            ComponentRole.GUARDIAN,
        ],
        "permission_violations": [],
        # Integrative
        "integration_contracts": [
            {"source": "data_ingestion", "target": "feature_extraction"},
            {"source": "feature_extraction", "target": "risk_assessment"},
            {"source": "risk_assessment", "target": "action_selector"},
            {"source": "action_selector", "target": "execution"},
            {"source": "execution", "target": "monitoring"},
        ],
        "schema_mismatches": [],
        # Reproducible
        "random_seeds": {"rng": 42, "strategy": 123},
        "stochastic_components": ["rng", "strategy"],
        "snapshot_enabled": True,
        "config_versioned": True,
        # Controllable
        "kill_switch_available": True,
        "circuit_breakers": {"risk": True, "latency": True},
        "monitoring_enabled": True,
        # Autonomous
        "self_healing_available": True,
        "adaptation_available": True,
        "current_autonomy_level": AutonomyLevel.SUPERVISED,
    }


@pytest.fixture
def system_architecture() -> SystemArchitecture:
    """Create a fresh SystemArchitecture instance."""
    return SystemArchitecture()


# =============================================================================
# DATA CLASSES TESTS
# =============================================================================


class TestPrincipleViolation:
    """Tests for PrincipleViolation dataclass."""

    def test_creation_with_all_fields(self) -> None:
        violation = PrincipleViolation(
            principle_name="TestPrinciple",
            component="test_component",
            description="Test violation description",
            severity="high",
            timestamp=1234567890.0,
        )
        assert violation.principle_name == "TestPrinciple"
        assert violation.component == "test_component"
        assert violation.description == "Test violation description"
        assert violation.severity == "high"
        assert violation.timestamp == 1234567890.0

    def test_default_timestamp(self) -> None:
        before = time.time()
        violation = PrincipleViolation(
            principle_name="Test",
            component="comp",
            description="desc",
            severity="low",
        )
        after = time.time()
        assert before <= violation.timestamp <= after

    def test_immutability(self) -> None:
        violation = PrincipleViolation(
            principle_name="Test",
            component="comp",
            description="desc",
            severity="medium",
        )
        with pytest.raises(AttributeError):
            violation.severity = "high"  # type: ignore


class TestIntegrationContract:
    """Tests for IntegrationContract dataclass."""

    def test_creation(self) -> None:
        contract = IntegrationContract(
            source="source_module",
            target="target_module",
            data_schema="schema_v1",
            protocol="async",
        )
        assert contract.source == "source_module"
        assert contract.target == "target_module"
        assert contract.data_schema == "schema_v1"
        assert contract.protocol == "async"
        assert contract.version == "1.0.0"

    def test_custom_version(self) -> None:
        contract = IntegrationContract(
            source="a",
            target="b",
            data_schema="s",
            protocol="sync",
            version="2.1.0",
        )
        assert contract.version == "2.1.0"


class TestStateSnapshot:
    """Tests for StateSnapshot dataclass."""

    def test_creation_and_checksum(self) -> None:
        snapshot = StateSnapshot(
            component_states={"strategy": {"position": 100}},
            random_seeds={"rng": 42},
            configuration={"risk_limit": 0.02},
            timestamp=1234567890.0,
        )
        assert snapshot.component_states == {"strategy": {"position": 100}}
        assert snapshot.random_seeds == {"rng": 42}
        assert snapshot.configuration == {"risk_limit": 0.02}
        assert snapshot.timestamp == 1234567890.0
        assert len(snapshot.checksum) == 64  # SHA-256 hex

    def test_deterministic_checksum(self) -> None:
        snapshot1 = StateSnapshot(
            component_states={"a": 1},
            random_seeds={"rng": 42},
            configuration={"x": "y"},
            timestamp=1000.0,
        )
        snapshot2 = StateSnapshot(
            component_states={"a": 1},
            random_seeds={"rng": 42},
            configuration={"x": "y"},
            timestamp=1000.0,
        )
        assert snapshot1.checksum == snapshot2.checksum

    def test_different_data_different_checksum(self) -> None:
        snapshot1 = StateSnapshot(
            component_states={"a": 1},
            random_seeds={"rng": 42},
            configuration={},
            timestamp=1000.0,
        )
        snapshot2 = StateSnapshot(
            component_states={"a": 2},
            random_seeds={"rng": 42},
            configuration={},
            timestamp=1000.0,
        )
        assert snapshot1.checksum != snapshot2.checksum


class TestControlAction:
    """Tests for ControlAction dataclass."""

    def test_creation(self) -> None:
        action = ControlAction(
            action_type="start",
            target_component="strategy_engine",
            parameters={"mode": "aggressive"},
        )
        assert action.action_type == "start"
        assert action.target_component == "strategy_engine"
        assert action.parameters == {"mode": "aggressive"}
        assert action.requires_approval is False
        assert action.approval_level == 0

    def test_with_approval_required(self) -> None:
        action = ControlAction(
            action_type="override",
            target_component="risk_manager",
            parameters={},
            requires_approval=True,
            approval_level=2,
        )
        assert action.requires_approval is True
        assert action.approval_level == 2


# =============================================================================
# NEURO-ORIENTED PRINCIPLE TESTS
# =============================================================================


class TestNeuroOrientedPrinciple:
    """Tests for NeuroOrientedPrinciple."""

    def test_properties(self) -> None:
        principle = NeuroOrientedPrinciple()
        assert principle.name == "Neuro-Oriented"
        assert principle.name_ua == "Нейроорієнтована"
        assert "Brain-inspired" in principle.description
        assert principle.status == PrincipleStatus.IMPLEMENTED

    def test_validate_full_context(self, full_context: Dict[str, Any]) -> None:
        principle = NeuroOrientedPrinciple()
        violations = principle.validate(full_context)
        assert len(violations) == 0

    def test_validate_missing_neuromodulators(self) -> None:
        principle = NeuroOrientedPrinciple()
        context = {
            "neuromodulators": ["dopamine"],  # Missing others
            "components": [
                "basal_ganglia_selector",
                "dopamine_learning_loop",
                "serotonin_risk_manager",
                "tacl_monitor",
            ],
            "learning_loop": {"algorithm": "TD(0)"},
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("neuromodulator" in v.description.lower() for v in violations)

    def test_validate_missing_components(self) -> None:
        principle = NeuroOrientedPrinciple()
        context = {
            "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
            "components": [],  # Missing all required components
            "learning_loop": {"algorithm": "TD(0)"},
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("component" in v.description.lower() for v in violations)

    def test_validate_missing_learning_algorithm(self) -> None:
        principle = NeuroOrientedPrinciple()
        context = {
            "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
            "components": [
                "basal_ganglia_selector",
                "dopamine_learning_loop",
                "serotonin_risk_manager",
                "tacl_monitor",
            ],
            "learning_loop": {},  # Missing algorithm
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("learning" in v.description.lower() for v in violations)

    def test_configure(self) -> None:
        principle = NeuroOrientedPrinciple()
        principle.configure(
            {
                "required_neuromodulators": ["dopamine", "serotonin"],
                "required_components": ["custom_component"],
            }
        )
        # After configuration, validation should use new requirements
        context = {
            "neuromodulators": ["dopamine", "serotonin"],
            "components": ["custom_component"],
            "learning_loop": {"algorithm": "TD(0)"},
        }
        violations = principle.validate(context)
        assert len(violations) == 0


# =============================================================================
# MODULAR PRINCIPLE TESTS
# =============================================================================


class TestModularPrinciple:
    """Tests for ModularPrinciple."""

    def test_properties(self) -> None:
        principle = ModularPrinciple()
        assert principle.name == "Modular"
        assert principle.name_ua == "Модульна"
        assert "Loosely coupled" in principle.description

    def test_validate_good_metrics(self) -> None:
        principle = ModularPrinciple()
        context = {
            "coupling_score": 0.2,
            "cohesion_score": 0.8,
            "circular_dependencies": [],
        }
        violations = principle.validate(context)
        assert len(violations) == 0

    def test_validate_high_coupling(self) -> None:
        principle = ModularPrinciple()
        context = {
            "coupling_score": 0.5,  # Exceeds 0.3
            "cohesion_score": 0.8,
            "circular_dependencies": [],
        }
        violations = principle.validate(context)
        assert len(violations) == 1
        assert "coupling" in violations[0].description.lower()

    def test_validate_low_cohesion(self) -> None:
        principle = ModularPrinciple()
        context = {
            "coupling_score": 0.2,
            "cohesion_score": 0.5,  # Below 0.7
            "circular_dependencies": [],
        }
        violations = principle.validate(context)
        assert len(violations) == 1
        assert "cohesion" in violations[0].description.lower()

    def test_validate_circular_dependencies(self) -> None:
        principle = ModularPrinciple()
        context = {
            "coupling_score": 0.2,
            "cohesion_score": 0.8,
            "circular_dependencies": ["A->B->A"],
        }
        violations = principle.validate(context)
        assert len(violations) == 1
        assert "circular" in violations[0].description.lower()

    def test_configure(self) -> None:
        principle = ModularPrinciple()
        principle.configure(
            {
                "max_coupling_score": 0.5,
                "min_cohesion_score": 0.5,
            }
        )
        context = {
            "coupling_score": 0.4,
            "cohesion_score": 0.6,
            "circular_dependencies": [],
        }
        violations = principle.validate(context)
        assert len(violations) == 0


# =============================================================================
# ROLE-BASED PRINCIPLE TESTS
# =============================================================================


class TestRoleBasedPrinciple:
    """Tests for RoleBasedPrinciple."""

    def test_properties(self) -> None:
        principle = RoleBasedPrinciple()
        assert principle.name == "Role-Based"
        assert principle.name_ua == "Рольова"
        assert "separation" in principle.description.lower()

    def test_validate_all_roles_assigned(self, full_context: Dict[str, Any]) -> None:
        principle = RoleBasedPrinciple()
        violations = principle.validate(full_context)
        # Filter to only role-related violations
        role_violations = [v for v in violations if "role" in v.description.lower()]
        assert len(role_violations) == 0

    def test_validate_missing_roles(self) -> None:
        principle = RoleBasedPrinciple()
        context = {
            "assigned_roles": [ComponentRole.SENSOR],  # Missing others
            "permission_violations": [],
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("missing" in v.description.lower() for v in violations)

    def test_validate_permission_violations(self) -> None:
        principle = RoleBasedPrinciple()
        context = {
            "assigned_roles": list(ComponentRole),
            "permission_violations": [
                {"component": "bad_actor", "action": "execute_orders", "role": "sensor"}
            ],
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("unauthorized" in v.description.lower() for v in violations)

    def test_get_permissions(self) -> None:
        principle = RoleBasedPrinciple()
        perms = principle.get_permissions(ComponentRole.GUARDIAN)
        assert "halt_system" in perms
        assert "veto_actions" in perms


# =============================================================================
# INTEGRATIVE PRINCIPLE TESTS
# =============================================================================


class TestIntegrativePrinciple:
    """Tests for IntegrativePrinciple."""

    def test_properties(self) -> None:
        principle = IntegrativePrinciple()
        assert principle.name == "Integrative"
        assert principle.name_ua == "Інтегративна"

    def test_validate_all_integrations(self, full_context: Dict[str, Any]) -> None:
        principle = IntegrativePrinciple()
        violations = principle.validate(full_context)
        integration_violations = [v for v in violations if "integration" in v.description.lower()]
        assert len(integration_violations) == 0

    def test_validate_missing_integrations(self) -> None:
        principle = IntegrativePrinciple()
        context = {
            "integration_contracts": [],
            "schema_mismatches": [],
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("missing" in v.description.lower() for v in violations)

    def test_validate_schema_mismatch(self) -> None:
        principle = IntegrativePrinciple()
        context = {
            "integration_contracts": [
                {"source": "data_ingestion", "target": "feature_extraction"},
            ],
            "schema_mismatches": [
                {"source": "a", "target": "b", "description": "Version mismatch"}
            ],
        }
        violations = principle.validate(context)
        assert any("schema" in v.description.lower() for v in violations)

    def test_register_contract(self) -> None:
        principle = IntegrativePrinciple()
        contract = IntegrationContract(
            source="custom_source",
            target="custom_target",
            data_schema="custom_schema",
            protocol="event",
        )
        principle.register_contract(contract)
        # Contract should be registered (internal state)
        assert len(principle._integration_contracts) == 1


# =============================================================================
# REPRODUCIBLE PRINCIPLE TESTS
# =============================================================================


class TestReproduciblePrinciple:
    """Tests for ReproduciblePrinciple."""

    def test_properties(self) -> None:
        principle = ReproduciblePrinciple()
        assert principle.name == "Reproducible"
        assert principle.name_ua == "Відтворювана"

    def test_validate_full_context(self, full_context: Dict[str, Any]) -> None:
        principle = ReproduciblePrinciple()
        violations = principle.validate(full_context)
        assert len(violations) == 0

    def test_validate_missing_random_seed(self) -> None:
        principle = ReproduciblePrinciple()
        context = {
            "random_seeds": {},
            "stochastic_components": ["component_a"],
            "snapshot_enabled": True,
            "config_versioned": True,
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("random seed" in v.description.lower() for v in violations)

    def test_validate_snapshot_disabled(self) -> None:
        principle = ReproduciblePrinciple()
        context = {
            "random_seeds": {},
            "stochastic_components": [],
            "snapshot_enabled": False,
            "config_versioned": True,
        }
        violations = principle.validate(context)
        assert any("snapshot" in v.description.lower() for v in violations)

    def test_create_snapshot(self) -> None:
        principle = ReproduciblePrinciple()
        snapshot = principle.create_snapshot(
            component_states={"a": 1},
            random_seeds={"rng": 42},
            configuration={"x": "y"},
        )
        assert snapshot.component_states == {"a": 1}
        assert len(snapshot.checksum) == 64

    def test_snapshot_limit(self) -> None:
        principle = ReproduciblePrinciple()
        principle.configure({"max_snapshots": 5})
        for i in range(10):
            principle.create_snapshot(
                component_states={"i": i},
                random_seeds={"rng": i},
                configuration={},
            )
        assert len(principle._snapshots) == 5


# =============================================================================
# CONTROLLABLE PRINCIPLE TESTS
# =============================================================================


class TestControllablePrinciple:
    """Tests for ControllablePrinciple."""

    def test_properties(self) -> None:
        principle = ControllablePrinciple()
        assert principle.name == "Controllable"
        assert principle.name_ua == "Контрольована"

    def test_validate_full_context(self, full_context: Dict[str, Any]) -> None:
        principle = ControllablePrinciple()
        violations = principle.validate(full_context)
        assert len(violations) == 0

    def test_validate_missing_kill_switch(self) -> None:
        principle = ControllablePrinciple()
        context = {
            "kill_switch_available": False,
            "circuit_breakers": {"risk": True},
            "monitoring_enabled": True,
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("kill switch" in v.description.lower() for v in violations)
        assert violations[0].severity == "critical"

    def test_validate_missing_circuit_breakers(self) -> None:
        principle = ControllablePrinciple()
        context = {
            "kill_switch_available": True,
            "circuit_breakers": {},
            "monitoring_enabled": True,
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("circuit breaker" in v.description.lower() for v in violations)

    def test_validate_action_with_approval(self) -> None:
        principle = ControllablePrinciple()
        action = ControlAction(
            action_type="override",
            target_component="risk_manager",
            parameters={},
            requires_approval=True,
            approval_level=2,
        )
        # Operator level 1 cannot perform level 2 action
        assert principle.validate_action(action, operator_level=1) is False
        # Operator level 2 can perform level 2 action
        assert principle.validate_action(action, operator_level=2) is True


# =============================================================================
# AUTONOMOUS PRINCIPLE TESTS
# =============================================================================


class TestAutonomousPrinciple:
    """Tests for AutonomousPrinciple."""

    def test_properties(self) -> None:
        principle = AutonomousPrinciple()
        assert principle.name == "Autonomous"
        assert principle.name_ua == "Автономна"

    def test_validate_full_context(self, full_context: Dict[str, Any]) -> None:
        principle = AutonomousPrinciple()
        violations = principle.validate(full_context)
        assert len(violations) == 0

    def test_validate_missing_self_healing(self) -> None:
        principle = AutonomousPrinciple()
        context = {
            "self_healing_available": False,
            "adaptation_available": True,
            "current_autonomy_level": AutonomyLevel.SUPERVISED,
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("self-healing" in v.description.lower() for v in violations)

    def test_validate_autonomy_level_exceeded(self) -> None:
        principle = AutonomousPrinciple()
        principle.configure({"max_autonomy_level": AutonomyLevel.ASSISTED.value})
        context = {
            "self_healing_available": True,
            "adaptation_available": True,
            "current_autonomy_level": AutonomyLevel.AUTONOMOUS,
        }
        violations = principle.validate(context)
        assert len(violations) >= 1
        assert any("autonomy level" in v.description.lower() for v in violations)

    def test_set_autonomy_level(self) -> None:
        principle = AutonomousPrinciple()
        # Default max is AUTONOMOUS
        assert principle.set_autonomy_level(AutonomyLevel.SUPERVISED) is True
        assert principle.autonomy_level == AutonomyLevel.SUPERVISED

    def test_set_autonomy_level_exceeds_max(self) -> None:
        principle = AutonomousPrinciple()
        principle.configure({"max_autonomy_level": AutonomyLevel.ASSISTED.value})
        assert principle.set_autonomy_level(AutonomyLevel.AUTONOMOUS) is False


# =============================================================================
# SYSTEM ARCHITECTURE TESTS
# =============================================================================


class TestSystemArchitecture:
    """Tests for SystemArchitecture container."""

    def test_all_principles_present(self, system_architecture: SystemArchitecture) -> None:
        principles = system_architecture.principles
        assert len(principles) == 7
        assert "neuro_oriented" in principles
        assert "modular" in principles
        assert "role_based" in principles
        assert "integrative" in principles
        assert "reproducible" in principles
        assert "controllable" in principles
        assert "autonomous" in principles

    def test_get_principle(self, system_architecture: SystemArchitecture) -> None:
        neuro = system_architecture.get_principle("neuro_oriented")
        assert neuro is not None
        assert isinstance(neuro, NeuroOrientedPrinciple)

        nonexistent = system_architecture.get_principle("nonexistent")
        assert nonexistent is None

    def test_validate_all(
        self, system_architecture: SystemArchitecture, full_context: Dict[str, Any]
    ) -> None:
        results = system_architecture.validate_all(full_context)
        assert len(results) == 7
        # With full context, most should have no violations
        total_violations = sum(len(v) for v in results.values())
        assert total_violations == 0

    def test_validate_all_with_violations(self, system_architecture: SystemArchitecture) -> None:
        empty_context: Dict[str, Any] = {}
        results = system_architecture.validate_all(empty_context)
        # Empty context should produce violations in most principles
        total_violations = sum(len(v) for v in results.values())
        assert total_violations > 0

    def test_configure_all(self, system_architecture: SystemArchitecture) -> None:
        settings = {
            "modular": {"max_coupling_score": 0.5},
            "reproducible": {"max_snapshots": 50},
        }
        system_architecture.configure_all(settings)
        # Verify settings were applied (indirectly through validation)
        modular = system_architecture.get_principle("modular")
        assert modular is not None
        assert modular._max_coupling_score == 0.5

    def test_get_summary(self, system_architecture: SystemArchitecture) -> None:
        summary = system_architecture.get_summary()
        assert len(summary) == 7
        for name, info in summary.items():
            assert "name" in info
            assert "name_ua" in info
            assert "description" in info
            assert "status" in info

    def test_to_json(self, system_architecture: SystemArchitecture) -> None:
        json_str = system_architecture.to_json()
        data = json.loads(json_str)
        assert len(data) == 7
        # Verify Ukrainian names are preserved
        assert data["neuro_oriented"]["name_ua"] == "Нейроорієнтована"


class TestGetSystemArchitecture:
    """Tests for the singleton getter function."""

    def test_returns_instance(self) -> None:
        arch = get_system_architecture()
        assert isinstance(arch, SystemArchitecture)

    def test_returns_singleton(self) -> None:
        arch1 = get_system_architecture()
        arch2 = get_system_architecture()
        assert arch1 is arch2


# =============================================================================
# ENUMS TESTS
# =============================================================================


class TestEnums:
    """Tests for enum types."""

    def test_principle_status_values(self) -> None:
        # Test status enum members exist and are distinct
        assert PrincipleStatus.NOT_IMPLEMENTED != PrincipleStatus.IMPLEMENTED
        assert PrincipleStatus.NOT_IMPLEMENTED != PrincipleStatus.VALIDATED
        assert len(PrincipleStatus) == 4  # NOT_IMPLEMENTED, PARTIAL, IMPLEMENTED, VALIDATED

    def test_component_role_values(self) -> None:
        assert ComponentRole.SENSOR.value == "sensor"
        assert ComponentRole.GUARDIAN.value == "guardian"

    def test_autonomy_level_ordering(self) -> None:
        assert AutonomyLevel.MANUAL.value < AutonomyLevel.ASSISTED.value
        assert AutonomyLevel.ASSISTED.value < AutonomyLevel.SUPERVISED.value
        assert AutonomyLevel.SUPERVISED.value < AutonomyLevel.AUTONOMOUS.value

    def test_module_capability_values(self) -> None:
        from core.architecture.system_principles import ModuleCapability

        assert ModuleCapability.DATA_INGESTION.value == "data_ingestion"
        assert ModuleCapability.TRADE_EXECUTION.value == "trade_execution"
