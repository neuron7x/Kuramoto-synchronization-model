# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.architecture.system_principles module."""

from __future__ import annotations

import json

import pytest

try:
    from core.architecture.system_principles import (
        AutonomousPrinciple,
        AutonomyLevel,
        ComponentRole,
        ControlAction,
        ControllablePrinciple,
        IntegrationContract,
        IntegrativePrinciple,
        ModularPrinciple,
        ModuleCapability,
        NeuroOrientedPrinciple,
        PrincipleStatus,
        PrincipleViolation,
        ReproduciblePrinciple,
        RoleBasedPrinciple,
        StateSnapshot,
        SystemArchitecture,
        get_system_architecture,
    )
except ImportError:
    pytest.skip("system_principles not importable", allow_module_level=True)


class TestEnums:
    def test_principle_status(self):
        assert len(PrincipleStatus) == 4

    def test_component_role(self):
        assert ComponentRole.SENSOR.value == "sensor"

    def test_autonomy_ordering(self):
        assert AutonomyLevel.MANUAL.value < AutonomyLevel.AUTONOMOUS.value

    def test_module_capability(self):
        assert ModuleCapability.DATA_INGESTION.value == "data_ingestion"


class TestPrincipleViolation:
    def test_creation(self):
        v = PrincipleViolation(principle_name="t", component="c", description="d", severity="high")
        assert v.timestamp > 0

    def test_frozen(self):
        v = PrincipleViolation(principle_name="t", component="c", description="d", severity="low")
        with pytest.raises(AttributeError):
            v.principle_name = "x"


class TestIntegrationContract:
    def test_defaults(self):
        c = IntegrationContract(source="a", target="b", data_schema="json", protocol="async")
        assert c.version == "1.0.0"


class TestStateSnapshot:
    def test_checksum(self):
        s = StateSnapshot(
            component_states={"a": 1},
            random_seeds={"r": 42},
            configuration={},
            timestamp=1.0,
        )
        assert len(s.checksum) == 64

    def test_deterministic(self):
        s1 = StateSnapshot(component_states={}, random_seeds={}, configuration={}, timestamp=1.0)
        s2 = StateSnapshot(component_states={}, random_seeds={}, configuration={}, timestamp=1.0)
        assert s1.checksum == s2.checksum


class TestControlAction:
    def test_defaults(self):
        a = ControlAction(action_type="stop", target_component="e", parameters={})
        assert not a.requires_approval


class TestNeuroOrientedPrinciple:
    def test_props(self):
        p = NeuroOrientedPrinciple()
        assert p.name == "Neuro-Oriented"

    def test_compliant(self):
        p = NeuroOrientedPrinciple()
        ctx = {
            "neuromodulators": ["dopamine", "serotonin", "gaba", "na_ach"],
            "components": [
                "basal_ganglia_selector",
                "dopamine_learning_loop",
                "serotonin_risk_manager",
                "tacl_monitor",
            ],
            "learning_loop": {"algorithm": "td"},
        }
        assert p.validate(ctx) == []

    def test_missing(self):
        p = NeuroOrientedPrinciple()
        assert (
            len(
                p.validate(
                    {
                        "neuromodulators": ["dopamine"],
                        "components": [],
                        "learning_loop": {},
                    }
                )
            )
            > 0
        )

    def test_configure(self):
        p = NeuroOrientedPrinciple()
        p.configure({"required_neuromodulators": ["dopamine"]})
        vs = [
            v
            for v in p.validate(
                {
                    "neuromodulators": ["dopamine"],
                    "components": [],
                    "learning_loop": {"algorithm": "x"},
                }
            )
            if "neuromodulator" in v.description.lower()
        ]
        assert vs == []


class TestModularPrinciple:
    def test_compliant(self):
        assert ModularPrinciple().validate({"coupling_score": 0.1, "cohesion_score": 0.9}) == []

    def test_high_coupling(self):
        assert len(ModularPrinciple().validate({"coupling_score": 0.5, "cohesion_score": 0.9})) == 1

    def test_circular(self):
        vs = ModularPrinciple().validate({"circular_dependencies": ["a->b->a"]})
        assert any("circular" in v.description.lower() for v in vs)

    def test_configure(self):
        p = ModularPrinciple()
        p.configure({"max_coupling_score": 0.8})
        assert p.validate({"coupling_score": 0.5, "cohesion_score": 0.9}) == []


class TestRoleBasedPrinciple:
    def test_all_roles(self):
        p = RoleBasedPrinciple()
        roles = {
            ComponentRole.SENSOR,
            ComponentRole.PROCESSOR,
            ComponentRole.ACTUATOR,
            ComponentRole.COORDINATOR,
            ComponentRole.MONITOR,
            ComponentRole.GUARDIAN,
        }
        assert p.validate({"assigned_roles": roles}) == []

    def test_missing(self):
        assert len(RoleBasedPrinciple().validate({"assigned_roles": set()})) >= 1

    def test_permissions(self):
        assert "veto_actions" in RoleBasedPrinciple().get_permissions(ComponentRole.GUARDIAN)


class TestIntegrativePrinciple:
    def test_missing(self):
        assert len(IntegrativePrinciple().validate({})) >= 1

    def test_register(self):
        p = IntegrativePrinciple()
        p.register_contract(
            IntegrationContract(source="a", target="b", data_schema="j", protocol="sync")
        )
        assert len(p._integration_contracts) == 1


class TestReproduciblePrinciple:
    def test_missing_seed(self):
        vs = ReproduciblePrinciple().validate(
            {"stochastic_components": ["rng1"], "random_seeds": {}}
        )
        assert any("seed" in v.description.lower() for v in vs)

    def test_snapshot(self):
        p = ReproduciblePrinciple()
        s = p.create_snapshot({"a": 1}, {"r": 42}, {"k": "v"})
        assert len(s.checksum) == 64

    def test_trim(self):
        p = ReproduciblePrinciple()
        p.configure({"max_snapshots": 2})
        for _ in range(5):
            p.create_snapshot({}, {}, {})
        assert len(p._snapshots) == 2


class TestControllablePrinciple:
    def test_no_kill_switch(self):
        vs = ControllablePrinciple().validate({})
        assert any("kill switch" in v.description.lower() for v in vs)

    def test_action_approval(self):
        p = ControllablePrinciple()
        a = ControlAction(
            action_type="stop",
            target_component="x",
            parameters={},
            requires_approval=True,
            approval_level=2,
        )
        assert p.validate_action(a, 3) and not p.validate_action(a, 1)


class TestAutonomousPrinciple:
    def test_set_level(self):
        p = AutonomousPrinciple()
        assert p.set_autonomy_level(AutonomyLevel.SUPERVISED)

    def test_exceed_max(self):
        p = AutonomousPrinciple()
        p.configure({"max_autonomy_level": 1})
        assert not p.set_autonomy_level(AutonomyLevel.AUTONOMOUS)


class TestSystemArchitecture:
    def test_count(self):
        assert len(SystemArchitecture().principles) == 7

    def test_get(self):
        assert SystemArchitecture().get_principle("modular").name == "Modular"

    def test_missing(self):
        assert SystemArchitecture().get_principle("x") is None

    def test_validate_all(self):
        assert len(SystemArchitecture().validate_all({})) == 7

    def test_json(self):
        assert len(json.loads(SystemArchitecture().to_json())) == 7

    def test_configure_all(self):
        a = SystemArchitecture()
        a.configure_all({"modular": {"max_coupling_score": 0.9}})
        assert (
            a.get_principle("modular").validate({"coupling_score": 0.8, "cohesion_score": 0.9})
            == []
        )


class TestSingleton:
    def test_same(self):
        assert get_system_architecture() is get_system_architecture()
