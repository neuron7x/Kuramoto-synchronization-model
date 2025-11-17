"""Tests for the automated incident triage orchestrator."""

from __future__ import annotations

import itertools
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from observability.auto_triage import (
    AutoTriageConfig,
    AutoTriageOrchestrator,
    MetricThreshold,
)


def _incremental_clock(start: datetime):
    counter = itertools.count()

    def _now() -> datetime:
        return start + timedelta(seconds=next(counter))

    return _now


def test_auto_triage_full_workflow_creates_artifacts(tmp_path: Path) -> None:
    base_time = datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = _incremental_clock(base_time)

    incident_root = tmp_path / "incidents"
    old_year = incident_root / "2023"
    old_incident = old_year / "INC-20230101-001"
    old_incident.mkdir(parents=True)
    (old_incident / "summary.json").write_text("{}", encoding="utf-8")
    os.utime(
        old_incident, (base_time.timestamp() - 10_000, base_time.timestamp() - 10_000)
    )

    service_log = tmp_path / "service.log"
    service_log.write_text("error: something happened\n", encoding="utf-8")

    traffic_dump = tmp_path / "traffic.jsonl"
    traffic_dump.write_text("{}\n", encoding="utf-8")

    config = AutoTriageConfig(
        thresholds=[
            MetricThreshold(
                name="latency_ms",
                warning=120.0,
                critical=200.0,
                description="p95 latency budget",
            )
        ],
        incident_root=incident_root,
        reproduction_commands=[
            (sys.executable, "-c", "print('reproduction-ok')"),
        ],
        log_paths=[service_log],
        traffic_replay_sources=[traffic_dump],
        owner_routes={"order-matching": "order-matching@sre.tradepulse"},
        runbook_links=["https://runbooks.tradepulse/order-latency"],
        dashboard_links=["https://grafana.tradepulse/d/latency"],
        communication_templates={"critical": "pagerduty-blast"},
        escalation_policy={"critical": ["vp-eng@tradepulse"]},
        recovery_actions=["rollback deployment", "scale out cluster"],
        training_schedule=["First Monday of the month"],
        archive_history=1,
    )

    orchestrator = AutoTriageOrchestrator(config, now=now)
    report = orchestrator.execute(
        metrics={"latency_ms": 240.0},
        context={
            "service": "order-matching",
            "incident_title": "Order latency regression",
            "links": ["https://status.tradepulse/incidents/123"],
        },
    )

    assert report.detection.triggered is True
    assert report.detection.severity == "critical"
    assert report.incident is not None
    assert report.owner == "order-matching@sre.tradepulse"
    assert report.ticket_path is not None and report.ticket_path.exists()
    assert report.summary_path.exists()

    triage_dir = report.incident.directory / "triage"
    assert (triage_dir / "detection.json").exists()
    assert (triage_dir / "reproduction" / "command_01.json").exists()
    assert (triage_dir / "logs" / service_log.name).exists()
    assert (triage_dir / "traffic" / traffic_dump.name).exists()
    assert (triage_dir / "tickets").is_dir()
    assert (triage_dir / "resources.json").exists()
    assert (triage_dir / "postmortem.md").exists()
    assert (triage_dir / "recovery.json").exists()

    with report.ticket_path.open(encoding="utf-8") as fp:
        ticket = json.load(fp)
    assert ticket["escalation_contacts"] == ["vp-eng@tradepulse"]
    assert ticket["communication_template"] == "pagerduty-blast"

    with (triage_dir / "resources.json").open(encoding="utf-8") as fp:
        resources = json.load(fp)
    assert resources["training_schedule"] == ["First Monday of the month"]

    with (triage_dir / "postmortem.md").open(encoding="utf-8") as fp:
        postmortem_contents = fp.read()
    assert report.incident.identifier in postmortem_contents
    assert "## Summary" in postmortem_contents
    assert "https://runbooks.tradepulse/order-latency" in postmortem_contents

    with report.summary_path.open(encoding="utf-8") as fp:
        summary = json.load(fp)
    assert summary["detection"]["triggered"] is True
    assert summary["incident"]["id"] == report.incident.identifier
    step_names = {step["name"] for step in summary["steps"]}
    assert {"detection", "traffic_capture", "log_collection", "postmortem"}.issubset(
        step_names
    )

    assert not old_incident.exists(), "archive pruning should remove oldest incident"


def test_auto_triage_skips_when_no_thresholds_breached(tmp_path: Path) -> None:
    base_time = datetime(2024, 6, 1, tzinfo=timezone.utc)
    now = _incremental_clock(base_time)

    incident_root = tmp_path / "incidents"
    config = AutoTriageConfig(
        thresholds=[MetricThreshold(name="error_rate", warning=0.2, critical=0.4)],
        incident_root=incident_root,
    )

    orchestrator = AutoTriageOrchestrator(config, now=now)
    report = orchestrator.execute(
        metrics={"error_rate": 0.05}, context={"service": "pricing"}
    )

    assert report.detection.triggered is False
    assert report.incident is None
    assert report.summary_path.exists()
    assert report.summary_path.parent == incident_root / "automation_runs"

    with report.summary_path.open(encoding="utf-8") as fp:
        summary = json.load(fp)

    assert summary["detection"]["triggered"] is False
    assert summary["steps"] == []
