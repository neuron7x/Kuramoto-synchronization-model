# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for coordination / monitoring modules.

Targets: agent_coordinator, strategy_scheduler, system_health_dashboard,
alert_manager, data_quality_monitor. Pins duplicate-id rejection, invalid-interval
handling, failed-task -> failed verdict, alert dedup + severity ordering, stale /
missing-column feed rejection, secret hiding in the dashboard payload, deterministic
health aggregation, and unknown-id fail-closed behaviour.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import pytest

from modules.agent_coordinator import (
    AgentCoordinator,
    AgentStatus,
    AgentType,
    ContradictionHaltError,
)
from modules.alert_manager import (
    AlertCategory,
    AlertManager,
    AlertRule,
    AlertSeverity,
    NotificationChannel,
    NotificationConfig,
)
from modules.data_quality_monitor import DataQualityMonitor, MonitorConfig
from modules.strategy_scheduler import ScheduleConfig, ScheduleType, StrategyScheduler, TaskStatus
from modules.system_health_dashboard import (
    ComponentStatus,
    ComponentType,
    SystemHealthDashboard,
)


# --------------------------------------------------------------------------- #
# agent_coordinator
# --------------------------------------------------------------------------- #
def test_duplicate_agent_registration_is_rejected() -> None:
    coordinator = AgentCoordinator()
    coordinator.register_agent("a1", AgentType.TRADING, "n", "d", handler=object())
    with pytest.raises(ValueError, match="already registered"):
        coordinator.register_agent("a1", AgentType.TRADING, "n", "d", handler=object())


def test_submit_task_for_unknown_agent_fails_closed() -> None:
    coordinator = AgentCoordinator()
    with pytest.raises(ValueError, match="not registered"):
        coordinator.submit_task("ghost", "t", {})
    assert coordinator.get_agent_info("ghost") is None


def test_failing_task_marks_agent_error() -> None:
    coordinator = AgentCoordinator()

    class Boom:
        def process(self, task: object) -> object:
            raise RuntimeError("boom")

    coordinator.register_agent("b", AgentType.TRADING, "n", "d", handler=Boom())
    coordinator.submit_task("b", "t", {})
    coordinator.process_tasks()
    agent = coordinator.get_agent_info("b")
    assert agent is not None
    assert agent["status"] == AgentStatus.ERROR.value
    assert agent["error_count"] == 1


def test_halted_coordinator_blocks_mutation_but_allows_read() -> None:
    coordinator = AgentCoordinator()
    coordinator.register_agent("a1", AgentType.TRADING, "n", "d", handler=object())
    # Enter the fail-closed halt state (production dead-branch, forced here).
    coordinator._halted_due_to_contradiction = True
    with pytest.raises(ContradictionHaltError):
        coordinator.register_agent("a2", AgentType.TRADING, "n", "d", handler=object())
    # Read-only introspection must still work while halted.
    assert coordinator.get_system_health()["total_agents"] == 1


def test_system_health_is_deterministic_from_agent_states() -> None:
    coordinator = AgentCoordinator()
    h1 = coordinator.get_system_health()
    h2 = coordinator.get_system_health()
    assert h1 == h2


# --------------------------------------------------------------------------- #
# strategy_scheduler
# --------------------------------------------------------------------------- #
def test_run_now_unknown_task_returns_none() -> None:
    assert StrategyScheduler().run_now("ghost") is None


def test_failing_handler_yields_failed_execution() -> None:
    scheduler = StrategyScheduler()

    def boom() -> None:
        raise RuntimeError("x")

    task_id = scheduler.schedule("n", "s", boom, ScheduleConfig(ScheduleType.ONCE))
    execution = scheduler.run_now(task_id)
    assert execution is not None
    assert execution.status == TaskStatus.FAILED
    assert execution.error is not None


def test_interval_schedule_without_interval_is_not_scheduled() -> None:
    scheduler = StrategyScheduler()
    # An INTERVAL schedule with no interval is degenerate -> no next run time.
    assert scheduler._calculate_next_run(ScheduleConfig(ScheduleType.INTERVAL)) is None
    # A valid interval produces a strictly future run time.
    valid = scheduler._calculate_next_run(
        ScheduleConfig(ScheduleType.INTERVAL, interval_seconds=30.0)
    )
    assert valid is not None and valid > datetime.now()


# --------------------------------------------------------------------------- #
# alert_manager
# --------------------------------------------------------------------------- #
def test_alert_deduplication_increments_occurrence() -> None:
    manager = AlertManager()
    first = manager.create_alert("t", "m", AlertSeverity.WARNING, AlertCategory.RISK, "src")
    second = manager.create_alert("t", "m", AlertSeverity.WARNING, AlertCategory.RISK, "src")
    assert first is second
    assert first.occurrence_count == 2


def test_duplicate_rule_id_is_rejected() -> None:
    manager = AlertManager()
    rule = AlertRule(
        "r1", "n", lambda ctx: True, "t", "m", AlertSeverity.INFO, AlertCategory.SYSTEM
    )
    assert manager.add_rule(rule) is True
    assert manager.add_rule(rule) is False


def test_severity_ordering_gates_notifications() -> None:
    manager = AlertManager()
    delivered: list[str] = []
    manager.register_notification_handler(
        NotificationChannel.CONSOLE, lambda alert: bool(delivered.append(alert.alert_id))
    )
    manager.configure_notification_channel(
        NotificationConfig(
            NotificationChannel.CONSOLE, enabled=True, min_severity=AlertSeverity.ERROR
        )
    )
    manager.create_alert("a", "m", AlertSeverity.INFO, AlertCategory.SYSTEM, "s1")
    assert delivered == []  # below min_severity -> suppressed
    manager.create_alert("b", "m", AlertSeverity.CRITICAL, AlertCategory.SYSTEM, "s2")
    assert len(delivered) == 1  # at/above min_severity -> delivered


def test_acknowledge_and_resolve_unknown_alert_fail_closed() -> None:
    manager = AlertManager()
    assert manager.acknowledge_alert("ghost", "me") is False
    assert manager.resolve_alert("ghost") is False


# --------------------------------------------------------------------------- #
# data_quality_monitor
# --------------------------------------------------------------------------- #
def test_empty_and_missing_column_feeds_are_rejected() -> None:
    monitor = DataQualityMonitor()
    metrics, issues = monitor.check_dataframe("S", pd.DataFrame())
    assert metrics.overall_score == 0.0
    assert issues[0].issue_type.value == "missing_data"
    assert issues[0].severity.value == "critical"

    _, missing_issues = monitor.check_dataframe("S", pd.DataFrame({"open": [1.0], "close": [1.0]}))
    assert any("Missing columns" in i.description for i in missing_issues)


def test_negative_price_and_zero_volume_are_flagged() -> None:
    monitor = DataQualityMonitor()
    issues = monitor.check_data_point("S", datetime.now(), -1.0, 1.0, 1.0, 1.0, 0.0)
    kinds = {i.issue_type.value for i in issues}
    assert "negative_price" in kinds
    assert "zero_volume" in kinds


def test_stale_symbol_is_reported() -> None:
    monitor = DataQualityMonitor(MonitorConfig(stale_data_seconds=1.0))
    old = datetime.now() - timedelta(seconds=3600)
    monitor.check_data_point("STALE", old, 1.0, 1.0, 1.0, 1.0, 100.0)
    assert "STALE" in monitor.get_stale_symbols()


# --------------------------------------------------------------------------- #
# system_health_dashboard
# --------------------------------------------------------------------------- #
def test_duplicate_component_and_unknown_update_fail_closed() -> None:
    dashboard = SystemHealthDashboard()
    assert dashboard.register_component("c1", "N", ComponentType.DATABASE) is True
    assert dashboard.register_component("c1", "N", ComponentType.DATABASE) is False
    assert dashboard.update_component_status("ghost", ComponentStatus.HEALTHY) is False
    assert dashboard.get_component_health("ghost") is None


def test_dashboard_payload_hides_component_metadata() -> None:
    dashboard = SystemHealthDashboard()
    # A sensitive marker stored in component metadata must never surface in the
    # dashboard payload, which only exposes id/name/status/error_count/timestamp.
    hidden_marker = "do-not-leak-marker-4711"
    dashboard.register_component(
        "c1", "DB", ComponentType.DATABASE, metadata={"internal_note": hidden_marker}
    )
    payload = json.dumps(dashboard.get_dashboard_data())
    assert hidden_marker not in payload


def test_overall_status_is_deterministic_and_unknown_when_empty() -> None:
    dashboard = SystemHealthDashboard()
    # No components -> fail closed to UNKNOWN, never a green HEALTHY.
    assert dashboard.get_system_summary().overall_status == ComponentStatus.UNKNOWN
    dashboard.register_component("c1", "N", ComponentType.DATABASE)
    dashboard.update_component_status("c1", ComponentStatus.UNHEALTHY)
    # A single unhealthy component dominates the aggregate verdict.
    assert dashboard.get_system_summary().overall_status == ComponentStatus.UNHEALTHY
