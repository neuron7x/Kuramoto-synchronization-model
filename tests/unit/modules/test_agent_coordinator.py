# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Tests for Agent Coordinator Module.

The suite covers — in addition to the original registration / scheduling /
decision paths — the full fail-closed halt contract, the ``SubjectiveState``
state-class partition, the halt/reset audit schema (with reproducible
``state_hash``), the UTC timestamp contract, and an exhaustive sweep of
every mutating operation gated by ``_assert_not_halted``.
"""

from __future__ import annotations

import pytest

from modules.agent_coordinator import (
    _HALT_ALLOWED_OPS,
    _HALT_GATED_OPS,
    AgentCoordinator,
    AgentMetadata,
    AgentStatus,
    AgentType,
    CoherenceAxes,
    ContradictionHaltError,
    Priority,
    SubjectiveState,
)


class MockAgentHandler:
    """Mock agent handler for testing"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.call_count = 0

    def process(self, task: object) -> dict[str, str]:
        self.call_count += 1
        return {"status": "success", "handler": self.name}


def _healthy_state() -> SubjectiveState:
    return SubjectiveState(
        axes=CoherenceAxes(1.0, 1.0, 1.0, 1.0, 1.0),
        coherence_score=1.0,
        entropy=0.0,
    )


def _degraded_state() -> SubjectiveState:
    return SubjectiveState(
        axes=CoherenceAxes(0.95, 0.91, 0.89, 0.92, 0.86),
        coherence_score=0.9,
        entropy=0.1,
    )


def _impossible_state_entropy_drift() -> SubjectiveState:
    # coherence=0.9 demands entropy=0.1 under Variant A; 0.3 breaks the
    # equation → sanity guard fires.
    return SubjectiveState(
        axes=CoherenceAxes(0.95, 0.91, 0.89, 0.92, 0.86),
        coherence_score=0.9,
        entropy=0.3,
    )


class TestAgentCoordinator:
    """Test suite for AgentCoordinator"""

    def test_initialization(self) -> None:
        """Test coordinator initialization"""
        coordinator = AgentCoordinator(max_concurrent_tasks=10)

        assert coordinator.max_concurrent_tasks == 10
        assert len(coordinator._agents) == 0
        assert len(coordinator._task_queue) == 0
        assert coordinator._halted_due_to_contradiction is False
        assert coordinator._halt_history == []

    def test_register_agent(self) -> None:
        """Test agent registration"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        metadata = coordinator.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.TRADING,
            name="Test Agent",
            description="Test trading agent",
            handler=handler,
            capabilities={"trade", "analyze"},
            priority=Priority.HIGH,
        )

        assert isinstance(metadata, AgentMetadata)
        assert metadata.agent_id == "agent_1"
        assert metadata.agent_type == AgentType.TRADING
        assert metadata.priority == Priority.HIGH
        assert "trade" in metadata.capabilities

    def test_register_duplicate_agent(self) -> None:
        """Test duplicate agent registration fails"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)

        with pytest.raises(ValueError):
            coordinator.register_agent(
                "agent_1", AgentType.TRADING, "Agent 1 Duplicate", "Desc", handler
            )

    def test_unregister_agent(self) -> None:
        """Test agent unregistration"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)
        assert "agent_1" in coordinator._agents

        coordinator.unregister_agent("agent_1")
        assert "agent_1" not in coordinator._agents

    def test_submit_task(self) -> None:
        """Test task submission"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)

        task_id = coordinator.submit_task(
            agent_id="agent_1",
            task_type="analyze",
            payload={"symbol": "BTCUSD"},
            priority=Priority.HIGH,
        )

        assert task_id.startswith("task_")
        assert len(coordinator._task_queue) == 1

    def test_submit_task_unregistered_agent(self) -> None:
        """Test task submission for unregistered agent fails"""
        coordinator = AgentCoordinator()

        with pytest.raises(ValueError):
            coordinator.submit_task(agent_id="nonexistent", task_type="test", payload={})

    def test_task_priority_ordering(self) -> None:
        """Test tasks are ordered by priority"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)

        coordinator.submit_task("agent_1", "task_low", {}, Priority.LOW)
        coordinator.submit_task("agent_1", "task_high", {}, Priority.HIGH)
        coordinator.submit_task("agent_1", "task_normal", {}, Priority.NORMAL)

        assert coordinator._task_queue[0].priority == Priority.HIGH

    def test_make_decision_resource_allocation(self) -> None:
        """Test resource allocation decision"""
        coordinator = AgentCoordinator()
        handler1 = MockAgentHandler("agent1")
        handler2 = MockAgentHandler("agent2")

        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Agent 1",
            "Desc",
            handler1,
            priority=Priority.HIGH,
        )
        coordinator.register_agent(
            "agent_2",
            AgentType.RISK_MANAGER,
            "Agent 2",
            "Desc",
            handler2,
            priority=Priority.NORMAL,
        )

        decision = coordinator.make_decision(decision_type="resource_allocation", context={})

        assert decision.decision_type == "resource_allocation"
        assert len(decision.affected_agents) == 2
        assert sum(coordinator._resource_allocation.values()) > 0

    def test_make_decision_emergency_stop(self) -> None:
        """Test emergency stop decision"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)

        decision = coordinator.make_decision(
            decision_type="emergency_stop", context={"reason": "critical_error"}
        )

        assert decision.priority == Priority.EMERGENCY
        assert decision.action == "stop_all"
        assert coordinator._agents["agent_1"].status == AgentStatus.STOPPED

    def test_update_agent_status(self) -> None:
        """Test agent status update"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Description", handler)

        coordinator.update_agent_status("agent_1", AgentStatus.ACTIVE)
        assert coordinator._agents["agent_1"].status == AgentStatus.ACTIVE

    def test_get_agent_info(self) -> None:
        """Test getting agent information"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Agent 1",
            "Description",
            handler,
            capabilities={"trade", "analyze"},
        )

        info = coordinator.get_agent_info("agent_1")

        assert info is not None
        assert info["agent_id"] == "agent_1"
        assert info["type"] == AgentType.TRADING.value
        assert "trade" in info["capabilities"]

    def test_get_agent_info_nonexistent(self) -> None:
        """Test getting info for nonexistent agent"""
        coordinator = AgentCoordinator()

        info = coordinator.get_agent_info("nonexistent")
        assert info is None

    def test_get_system_health(self) -> None:
        """Test system health calculation"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Desc", handler)
        coordinator.register_agent("agent_2", AgentType.RISK_MANAGER, "Agent 2", "Desc", handler)

        health = coordinator.get_system_health()

        assert "health_score" in health
        assert "total_agents" in health
        assert health["total_agents"] == 2

    def test_get_coordination_summary(self) -> None:
        """Test coordination summary"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Desc", handler)

        summary = coordinator.get_coordination_summary()

        assert "registered_agents" in summary
        assert "system_health" in summary
        assert summary["registered_agents"] == 1
        assert summary["halted"] is False

    def test_process_task_uses_handler_process_method(self) -> None:
        """Task processing should call handler.process when available."""
        coordinator = AgentCoordinator(max_concurrent_tasks=1)
        handler = MockAgentHandler("exec_agent")

        coordinator.register_agent("agent_1", AgentType.TRADING, "Agent 1", "Desc", handler)
        coordinator.submit_task("agent_1", "execute", {"symbol": "ETHUSD"})

        processed = coordinator.process_tasks()

        assert len(processed) == 1
        assert handler.call_count == 1
        result = coordinator._completed_tasks[0].result
        assert isinstance(result, dict)
        assert result["handler"] == "exec_agent"

    def test_protocol_inversion_of_control(self) -> None:
        """Registered protocol should execute instead of direct handler invocation."""
        coordinator = AgentCoordinator(max_concurrent_tasks=1)
        handler = MockAgentHandler("fallback_agent")
        coordinator.register_agent("agent_1", AgentType.STRATEGY, "Strategy Agent", "Desc", handler)

        coordinator.register_protocol(
            "shared_protocol",
            lambda payload: {"status": "protocol_ok", "payload": payload["value"]},
        )
        coordinator.submit_task(
            "agent_1",
            "sync",
            {"protocol": "shared_protocol", "value": 42},
            Priority.HIGH,
        )

        coordinator.process_tasks()
        result = coordinator._completed_tasks[0].result
        assert isinstance(result, dict)
        assert result["status"] == "protocol_ok"
        assert result["payload"] == 42
        assert handler.call_count == 0

    def test_deterministic_synthesis_cycle_detects_and_recovers(self) -> None:
        """Deterministic synthesis cycle should isolate conflicts and recover errored agents."""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "dependency_agent",
            AgentType.RISK_MANAGER,
            "Dependency",
            "Desc",
            handler,
        )
        coordinator.update_agent_status("dependency_agent", AgentStatus.ERROR)
        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Trading Agent",
            "Desc",
            handler,
            dependencies={"dependency_agent"},
        )
        coordinator.update_agent_status("agent_1", AgentStatus.ERROR)

        report = coordinator.run_deterministic_synthesis_cycle()

        assert report.cycle_id.startswith("cycle_")
        assert any(
            conflict.conflict_type == "error_dependency" for conflict in report.decomposed_conflicts
        )
        assert "agent_1" in report.recovered_agents
        assert coordinator._agents["agent_1"].status == AgentStatus.PAUSED
        assert 0.0 <= report.coherence_score <= 1.0
        assert report.hidden_contradiction_detected is False
        assert report.halted is False
        assert report.subjective_state.truth in {False, True}
        assert report.subjective_state.axes.recovery_readiness >= 0.0


class TestSubjectiveStateContract:
    """Variant-A entropy contract: derived in production; sanity-only on injection."""

    def test_healthy_state_class(self) -> None:
        s = _healthy_state()
        assert s.state_class == "healthy"
        assert s.hidden_contradiction is False
        assert s.truth is True

    def test_degraded_state_class(self) -> None:
        s = _degraded_state()
        assert s.state_class == "degraded_valid"
        assert s.hidden_contradiction is False
        assert s.truth is True  # axes ≥ 0.8, coherence ≥ 0.8, entropy consistent

    def test_impossible_state_entropy_drift(self) -> None:
        s = _impossible_state_entropy_drift()
        assert s.state_class == "impossible"
        assert s.hidden_contradiction is True
        assert s.truth is False

    def test_impossible_state_out_of_range_coherence(self) -> None:
        """Externally-injected invalid state (sanity guard test)."""
        s = SubjectiveState(
            axes=CoherenceAxes(1.0, 1.0, 1.0, 1.0, 1.0),
            coherence_score=1.5,
            entropy=-0.5,
        )
        assert s.hidden_contradiction is True
        assert s.state_class == "impossible"

    def test_impossible_state_out_of_range_axis(self) -> None:
        """Axis outside [0,1] must trip the sanity guard."""
        s = SubjectiveState(
            axes=CoherenceAxes(1.0, 1.0, 1.0, 1.0, 1.5),
            coherence_score=1.0,
            entropy=0.0,
        )
        assert s.hidden_contradiction is True
        assert s.state_class == "impossible"

    def test_state_class_partition_is_exhaustive(self) -> None:
        """The classifier only emits one of three canonical labels."""
        labels = {
            _healthy_state().state_class,
            _degraded_state().state_class,
            _impossible_state_entropy_drift().state_class,
        }
        assert labels <= {"healthy", "degraded_valid", "impossible"}
        assert labels == {"healthy", "degraded_valid", "impossible"}


class TestHaltContract:
    """System-wide fail-closed halt contract."""

    def test_healthy_state_no_halt(self) -> None:
        coordinator = AgentCoordinator()
        assert coordinator._detect_hidden_contradiction(_healthy_state()) is False

    def test_degraded_state_no_halt(self) -> None:
        coordinator = AgentCoordinator()
        assert coordinator._detect_hidden_contradiction(_degraded_state()) is False

    def test_impossible_state_triggers_halt(self) -> None:
        coordinator = AgentCoordinator()
        s = _impossible_state_entropy_drift()
        coordinator._halted_due_to_contradiction = coordinator._detect_hidden_contradiction(s)
        assert coordinator._halted_due_to_contradiction is True

    def test_fail_closed_blocks_next_cycle_until_explicit_reset(self) -> None:
        coordinator = AgentCoordinator()
        coordinator._halted_due_to_contradiction = True
        with pytest.raises(ContradictionHaltError):
            coordinator.run_deterministic_synthesis_cycle()

    def test_reset_allows_reentry_after_halt(self) -> None:
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)
        coordinator._halted_due_to_contradiction = True
        coordinator._halted_state_snapshot = _impossible_state_entropy_drift()

        coordinator.reset_halt("manual clear", "ops")

        report = coordinator.run_deterministic_synthesis_cycle()
        assert report.halted is False
        assert coordinator._halted_state_snapshot is None

    def test_halt_blocks_submit_and_process_paths(self) -> None:
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)
        coordinator._halted_due_to_contradiction = True

        with pytest.raises(ContradictionHaltError):
            coordinator.submit_task("agent_1", "sync", {})
        with pytest.raises(ContradictionHaltError):
            coordinator.process_tasks()

    def test_halt_blocks_every_gated_mutating_operation(self) -> None:
        """Exhaustive coverage of every op inside ``_HALT_GATED_OPS``."""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)
        # Go halted only after initial setup so the probes below can assume
        # the registered agent exists.
        coordinator._halted_due_to_contradiction = True

        def _probe(op: str) -> None:
            if op == "register_agent":
                coordinator.register_agent("new_agent", AgentType.TRADING, "N", "D", handler)
            elif op == "unregister_agent":
                coordinator.unregister_agent("agent_1")
            elif op == "submit_task":
                coordinator.submit_task("agent_1", "t", {})
            elif op == "register_protocol":
                coordinator.register_protocol("p", lambda _p: None)
            elif op == "register_validator":
                coordinator.register_validator("v", lambda _c: True)
            elif op == "process_tasks":
                coordinator.process_tasks()
            elif op == "make_decision":
                coordinator.make_decision("agent_coordination", {})
            elif op == "update_agent_status":
                coordinator.update_agent_status("agent_1", AgentStatus.ACTIVE)
            elif op == "run_deterministic_synthesis_cycle":
                coordinator.run_deterministic_synthesis_cycle()
            else:
                raise AssertionError(f"unmapped gated op: {op}")

        for op in _HALT_GATED_OPS:
            with pytest.raises(ContradictionHaltError) as exc:
                _probe(op)
            assert op in str(exc.value)

    def test_halt_permits_every_allowed_readonly_operation(self) -> None:
        """Read-only introspection + reset_halt remain callable under halt."""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)
        coordinator._halted_due_to_contradiction = True
        coordinator._halted_state_snapshot = _impossible_state_entropy_drift()

        # get_agent_info
        assert coordinator.get_agent_info("agent_1") is not None
        # get_system_health
        assert "health_score" in coordinator.get_system_health()
        # get_coordination_summary
        summary = coordinator.get_coordination_summary()
        assert summary["halted"] is True
        # reset_halt (explicit recovery)
        coordinator.reset_halt("ok", "ops")
        assert coordinator._halted_due_to_contradiction is False

    def test_allowed_and_gated_op_sets_are_disjoint(self) -> None:
        """Contract invariant: no op appears in both sets."""
        assert _HALT_GATED_OPS.isdisjoint(_HALT_ALLOWED_OPS)

    def test_last_subjective_state_matches_report_state(self) -> None:
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)

        report = coordinator.run_deterministic_synthesis_cycle()
        assert coordinator._last_subjective_state == report.subjective_state
        assert coordinator._halted_state_snapshot is None


class TestAuditTrail:
    """Halt/reset audit schema, reproducible state_hash."""

    def test_halt_event_schema_and_cycle_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Production path through halt records the full event schema."""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)

        # Force the production path to emit an impossible state without
        # editing its mathematics: monkey-patch the evaluator.
        monkeypatch.setattr(
            AgentCoordinator,
            "_evaluate_subjective_state",
            lambda _self, **_kw: _impossible_state_entropy_drift(),
        )

        report = coordinator.run_deterministic_synthesis_cycle()
        assert report.hidden_contradiction_detected is True
        assert report.halted is True
        assert coordinator._halted_due_to_contradiction is True

        # Event schema
        assert len(coordinator._halt_history) == 1
        event = coordinator._halt_history[0]
        assert event["event_type"] == "halt"
        assert event["reason"] == "hidden_contradiction_detected"
        assert event["cycle_id"] == report.cycle_id
        assert event["state_hash"] is not None
        assert event["subjective_state"] is not None
        assert event["halt_at"].tzinfo is not None

    def test_reset_halt_schema_and_authorized_by(self) -> None:
        coordinator = AgentCoordinator()
        coordinator._halted_due_to_contradiction = True
        coordinator._halted_state_snapshot = _impossible_state_entropy_drift()

        coordinator.reset_halt(reason="manual review", authorized_by="chief_risk")

        assert coordinator._halted_due_to_contradiction is False
        assert len(coordinator._halt_history) == 1
        event = coordinator._halt_history[0]
        assert event["event_type"] == "reset"
        assert event["reason"] == "manual review"
        assert event["authorized_by"] == "chief_risk"
        assert event["state_hash"] is not None
        assert event["cycle_id"] is None
        assert event["reset_at"].tzinfo is not None
        assert coordinator._halted_state_snapshot is None

    def test_reset_without_halt_is_noop(self) -> None:
        coordinator = AgentCoordinator()
        assert coordinator._halt_history == []
        coordinator.reset_halt(reason="noop", authorized_by="ops")
        assert coordinator._halt_history == []
        assert coordinator._halted_due_to_contradiction is False

    def test_state_hash_is_deterministic_for_same_payload(self) -> None:
        """Identical SubjectiveState → identical state_hash."""
        from dataclasses import asdict

        coordinator = AgentCoordinator()
        s = _impossible_state_entropy_drift()
        h1 = coordinator._state_payload_hash(asdict(s))
        h2 = coordinator._state_payload_hash(asdict(s))
        assert h1 is not None
        assert h1 == h2

    def test_state_hash_diverges_when_any_axis_changes(self) -> None:
        """Changing any axis must perturb the hash."""
        from dataclasses import asdict

        coordinator = AgentCoordinator()
        s = _impossible_state_entropy_drift()
        s_perturbed = SubjectiveState(
            axes=CoherenceAxes(
                structural_integrity=s.axes.structural_integrity + 0.01,
                temporal_stability=s.axes.temporal_stability,
                verification_honesty=s.axes.verification_honesty,
                dependency_coherence=s.axes.dependency_coherence,
                recovery_readiness=s.axes.recovery_readiness,
            ),
            coherence_score=s.coherence_score,
            entropy=s.entropy,
        )
        h1 = coordinator._state_payload_hash(asdict(s))
        h2 = coordinator._state_payload_hash(asdict(s_perturbed))
        assert h1 != h2

    def test_state_hash_of_none_is_none(self) -> None:
        coordinator = AgentCoordinator()
        assert coordinator._state_payload_hash(None) is None


class TestUTCContract:
    """Every coordinator-produced timestamp must be timezone-aware UTC."""

    def test_utc_aware_timestamps_on_all_surfaces(self) -> None:
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("agent")
        metadata = coordinator.register_agent("agent_1", AgentType.TRADING, "A", "D", handler)
        coordinator.submit_task("agent_1", "t", {})
        coordinator.process_tasks()
        report = coordinator.run_deterministic_synthesis_cycle()
        decision = coordinator.make_decision("agent_coordination", {"agents": ["agent_1"]})

        assert metadata.registered_at.tzinfo is not None
        assert metadata.last_active.tzinfo is not None
        assert report.started_at.tzinfo is not None
        assert report.completed_at.tzinfo is not None
        assert decision.timestamp.tzinfo is not None
        task = coordinator._completed_tasks[0]
        assert task.created_at.tzinfo is not None
        assert task.started_at is not None and task.started_at.tzinfo is not None
        assert task.completed_at is not None and task.completed_at.tzinfo is not None

    def test_halt_and_reset_events_are_utc_aware(self) -> None:
        coordinator = AgentCoordinator()
        coordinator._halted_due_to_contradiction = True
        coordinator._halted_state_snapshot = _impossible_state_entropy_drift()
        # Seed a halt event to exercise halt_at path.
        coordinator._record_halt_event(
            cycle_id="cycle_test",
            reason="hidden_contradiction_detected",
            subjective_state=_impossible_state_entropy_drift(),
        )
        coordinator.reset_halt("ok", "ops")

        halt_event, reset_event = coordinator._halt_history
        assert halt_event["halt_at"].tzinfo is not None
        assert reset_event["reset_at"].tzinfo is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
