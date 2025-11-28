"""Automated incident triage orchestration utilities.

This module provides a high-level orchestrator that automates the
operational workflow executed after a degradation is detected.  It
encapsulates the required steps – detection confirmation, automated
reproduction, log and traffic capture, ticket generation, owner routing,
resource linking, runbook surfacing, escalation planning, recovery
guidance, archival controls, and communication scaffolding – so that
systems can respond deterministically to production regressions.

The orchestrator favours composability over bespoke scripting.  Each
phase produces structured artefacts on disk to make subsequent manual or
automated follow-ups reproducible and auditable.
"""

from __future__ import annotations

import json
import shutil
import subprocess

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from .incidents import IncidentManager, IncidentRecord

__all__ = [
    "MetricThreshold",
    "DetectionResult",
    "TriageStepReport",
    "AutoTriageConfig",
    "AutoTriageReport",
    "AutoTriageOrchestrator",
]


Severity = str


@dataclass(slots=True, frozen=True)
class MetricThreshold:
    """Configuration describing when a metric should trigger triage."""

    name: str
    warning: float
    critical: float
    comparison: str = "ge"
    description: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - dataclass guard
        comparison = self.comparison
        if comparison not in {"ge", "le"}:
            msg = (
                "comparison must be 'ge' (greater-or-equal) or 'le' (less-or-equal), "
                f"got {comparison!r}"
            )
            raise ValueError(msg)


@dataclass(slots=True, frozen=True)
class DetectionResult:
    """Outcome of the degradation detection confirmation phase."""

    triggered: bool
    severity: Severity
    reason: str
    violations: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class TriageStepReport:
    """Structured record for each executed triage step."""

    name: str
    status: str
    details: Mapping[str, Any]
    artifacts: tuple[Path, ...]


@dataclass(slots=True)
class AutoTriageConfig:
    """User configurable options for :class:`AutoTriageOrchestrator`.

    Note: The ``incident_root``, ``log_paths``, and ``traffic_replay_sources``
    fields accept either ``Path`` or ``str`` values at initialization time,
    but are always converted to ``Path`` objects in ``__post_init__``.
    """

    thresholds: Sequence[MetricThreshold] = field(default_factory=tuple)
    incident_root: Path = field(default_factory=lambda: Path("reports/incidents"))
    reproduction_commands: Sequence[Sequence[str]] = field(default_factory=tuple)
    log_paths: Sequence[Path] = field(default_factory=tuple)
    traffic_replay_sources: Sequence[Path] = field(default_factory=tuple)
    runbook_links: Sequence[str] = field(default_factory=tuple)
    dashboard_links: Sequence[str] = field(default_factory=tuple)
    owner_routes: Mapping[str, str] = field(default_factory=dict)
    default_owner: str = "sre@tradepulse.io"
    ticket_project: str = "INC"
    ticket_template: str = "model-degradation-triage"
    severity_map: Mapping[str, str] = field(
        default_factory=lambda: {
            "critical": "critical",
            "major": "major",
            "minor": "minor",
        }
    )
    escalation_policy: Mapping[str, Sequence[str]] = field(default_factory=dict)
    communication_templates: Mapping[str, str] = field(default_factory=dict)
    recovery_actions: Sequence[str] = field(default_factory=tuple)
    training_schedule: Sequence[str] = field(default_factory=tuple)
    archive_history: int = 50

    def __post_init__(self) -> None:
        if self.archive_history < 0:
            raise ValueError("archive_history must be non-negative")

        # Normalize all path-like fields to Path objects (Path(path) is idempotent)
        object.__setattr__(self, "incident_root", Path(self.incident_root))

        log_paths = tuple(Path(p) for p in self.log_paths)
        object.__setattr__(self, "log_paths", log_paths)

        traffic_sources = tuple(Path(p) for p in self.traffic_replay_sources)
        object.__setattr__(self, "traffic_replay_sources", traffic_sources)

        commands: list[tuple[str, ...]] = []
        for command in self.reproduction_commands:
            commands.append(tuple(command))
        object.__setattr__(self, "reproduction_commands", tuple(commands))


@dataclass(slots=True, frozen=True)
class AutoTriageReport:
    """Summary of a full automated triage execution."""

    detection: DetectionResult
    incident: IncidentRecord | None
    owner: str | None
    ticket_path: Path | None
    summary_path: Path
    steps: tuple[TriageStepReport, ...]


class AutoTriageOrchestrator:
    """Automates the operational workflow triggered by degradations."""

    _SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1, "none": 0}

    def __init__(
        self,
        config: AutoTriageConfig,
        *,
        incident_manager: IncidentManager | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._incident_manager = incident_manager or IncidentManager(
            config.incident_root
        )
        self._now: Callable[[], datetime] = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute(
        self,
        metrics: Mapping[str, float],
        context: Mapping[str, Any] | None = None,
    ) -> AutoTriageReport:
        """Run the automated triage workflow.

        Parameters
        ----------
        metrics:
            Observed metric values that should be evaluated against the
            configured thresholds.
        context:
            Optional metadata describing the degraded system.  The
            orchestrator uses it to route owners, construct tickets, and
            enrich generated artefacts.
        """

        context = dict(context or {})
        start_timestamp = self._now()

        detection = self._confirm_degradation(metrics)
        incident: IncidentRecord | None = None
        owner: str | None = None
        ticket_path: Path | None = None
        steps: list[TriageStepReport] = []

        if not detection.triggered:
            # Persist a minimal summary for visibility even when no
            # incident was raised.  This doubles as proof that the
            # automation executed.
            summary_path = self._write_summary(
                start_timestamp,
                self._now(),
                detection,
                None,
                None,
                steps,
                context,
            )
            return AutoTriageReport(
                detection=detection,
                incident=None,
                owner=None,
                ticket_path=None,
                summary_path=summary_path,
                steps=tuple(steps),
            )

        incident = self._create_incident(detection, context)
        triage_dir = incident.directory / "triage"
        triage_dir.mkdir(exist_ok=True)

        owner = self._resolve_owner(context)
        self._write_owner(triage_dir, owner, context)

        steps.append(self._write_detection_report(triage_dir, detection))

        reproduction_steps = self._run_reproductions(triage_dir, context)
        steps.extend(reproduction_steps)

        steps.append(self._collect_logs(triage_dir))
        steps.append(self._collect_traffic(triage_dir))

        ticket_path = self._create_ticket(
            triage_dir, incident, detection, owner, context
        )
        steps.append(
            TriageStepReport(
                name="ticketing",
                status="completed",
                details={"ticket_path": str(ticket_path)},
                artifacts=(ticket_path,),
            )
        )

        resources_step = self._write_resources(triage_dir, context)
        steps.append(resources_step)

        steps.append(
            self._write_postmortem(triage_dir, incident, detection, owner, context)
        )

        steps.append(self._write_recovery_plan(triage_dir))

        end_timestamp = self._now()

        summary_path = self._write_summary(
            start_timestamp,
            end_timestamp,
            detection,
            incident,
            owner,
            steps,
            context,
        )

        self._enforce_archive_budget()

        return AutoTriageReport(
            detection=detection,
            incident=incident,
            owner=owner,
            ticket_path=ticket_path,
            summary_path=summary_path,
            steps=tuple(steps),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _confirm_degradation(self, metrics: Mapping[str, float]) -> DetectionResult:
        violations: list[dict[str, Any]] = []
        highest_severity = "none"
        reasons: list[str] = []

        for threshold in self._config.thresholds:
            value = metrics.get(threshold.name)
            if value is None:
                continue

            severity: Severity | None = None
            boundary: float | None = None

            if threshold.comparison == "ge":
                if value >= threshold.critical:
                    severity = "critical"
                    boundary = threshold.critical
                elif value >= threshold.warning:
                    severity = "major"
                    boundary = threshold.warning
            else:
                if value <= threshold.critical:
                    severity = "critical"
                    boundary = threshold.critical
                elif value <= threshold.warning:
                    severity = "major"
                    boundary = threshold.warning

            if severity is None:
                continue

            violation = {
                "metric": threshold.name,
                "observed": value,
                "boundary": boundary,
                "comparison": threshold.comparison,
                "severity": severity,
            }
            if threshold.description:
                violation["description"] = threshold.description
            violations.append(violation)

            if self._SEVERITY_ORDER[severity] > self._SEVERITY_ORDER[highest_severity]:
                highest_severity = severity

            reasons.append(
                f"{threshold.name} {value:.4g} vs {boundary:.4g} ({severity})"
            )

        if not violations:
            return DetectionResult(
                triggered=False,
                severity="none",
                reason="No thresholds breached",
                violations=tuple(),
            )

        return DetectionResult(
            triggered=True,
            severity=highest_severity,
            reason="; ".join(reasons),
            violations=tuple(violations),
        )

    def _create_incident(
        self,
        detection: DetectionResult,
        context: Mapping[str, Any],
    ) -> IncidentRecord:
        severity = self._config.severity_map.get(detection.severity, "major")
        title = (
            context.get("incident_title")
            or context.get("service")
            or "Automated degradation"
        )
        description_parts = [
            "Automated triage executed due to metric degradation.",
            f"Detected violations: {detection.reason}.",
        ]
        context_description = context.get("description")
        if context_description:
            description_parts.append(str(context_description))

        metadata: MutableMapping[str, Any] = {
            "violations": list(detection.violations),
            "context": dict(context),
            "severity": detection.severity,
        }

        return self._incident_manager.create(
            title=title,
            description="\n".join(description_parts),
            metadata=metadata,
            severity=severity,
        )

    def _resolve_owner(self, context: Mapping[str, Any]) -> str:
        service = (
            str(context.get("service")) if context.get("service") is not None else None
        )
        if service and service in self._config.owner_routes:
            return self._config.owner_routes[service]
        return self._config.default_owner

    def _write_detection_report(
        self,
        triage_dir: Path,
        detection: DetectionResult,
    ) -> TriageStepReport:
        report_path = triage_dir / "detection.json"
        report_path.write_text(
            json.dumps(
                {
                    "triggered": detection.triggered,
                    "severity": detection.severity,
                    "reason": detection.reason,
                    "violations": list(detection.violations),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        return TriageStepReport(
            name="detection",
            status="completed",
            details={"reason": detection.reason, "severity": detection.severity},
            artifacts=(report_path,),
        )

    def _run_reproductions(
        self,
        triage_dir: Path,
        context: Mapping[str, Any],
    ) -> list[TriageStepReport]:
        results: list[TriageStepReport] = []
        if not self._config.reproduction_commands:
            results.append(
                TriageStepReport(
                    name="reproduction",
                    status="skipped",
                    details={"reason": "no reproduction commands configured"},
                    artifacts=tuple(),
                )
            )
            return results

        reproduction_dir = triage_dir / "reproduction"
        reproduction_dir.mkdir(exist_ok=True)

        for index, command in enumerate(self._config.reproduction_commands, start=1):
            timestamp = self._now().isoformat()
            log_path = reproduction_dir / f"command_{index:02d}.json"
            serialized_command = [str(argument) for argument in command]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=None,
                )
            except (
                FileNotFoundError
            ) as exc:  # pragma: no cover - depends on environment
                error_payload: dict[str, Any] = {
                    "command": serialized_command,
                    "error": str(exc),
                    "timestamp": timestamp,
                    "context": dict(context),
                }
                log_path.write_text(
                    json.dumps(error_payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                results.append(
                    TriageStepReport(
                        name=f"reproduction:{index}",
                        status="failed",
                        details={"error": str(exc)},
                        artifacts=(log_path,),
                    )
                )
                continue

            success_payload: dict[str, Any] = {
                "command": serialized_command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "timestamp": timestamp,
                "context": dict(context),
            }
            log_path.write_text(
                json.dumps(success_payload, indent=2, sort_keys=True), encoding="utf-8"
            )

            status = "completed" if completed.returncode == 0 else "failed"
            results.append(
                TriageStepReport(
                    name=f"reproduction:{index}",
                    status=status,
                    details={"returncode": completed.returncode},
                    artifacts=(log_path,),
                )
            )

        return results

    def _collect_logs(self, triage_dir: Path) -> TriageStepReport:
        logs_dir = triage_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        copied: list[Path] = []
        missing: list[str] = []
        for log_path in self._config.log_paths:
            log_path_obj = Path(log_path)
            if log_path_obj.exists():
                destination = logs_dir / log_path_obj.name
                shutil.copy2(log_path_obj, destination)
                copied.append(destination)
            else:
                missing.append(str(log_path_obj))

        details: dict[str, Any] = {"copied": [str(path) for path in copied]}
        if missing:
            details["missing"] = missing

        status = "completed" if copied else "skipped"
        return TriageStepReport(
            name="log_collection",
            status=status,
            details=details,
            artifacts=tuple(copied),
        )

    def _collect_traffic(self, triage_dir: Path) -> TriageStepReport:
        traffic_dir = triage_dir / "traffic"
        traffic_dir.mkdir(exist_ok=True)
        captured: list[Path] = []
        missing: list[str] = []
        for source in self._config.traffic_replay_sources:
            if source.exists():
                destination = traffic_dir / source.name
                shutil.copy2(source, destination)
                captured.append(destination)
            else:
                missing.append(str(source))

        details: dict[str, Any] = {"captured": [str(path) for path in captured]}
        if missing:
            details["missing"] = missing

        status = "completed" if captured else "skipped"
        return TriageStepReport(
            name="traffic_capture",
            status=status,
            details=details,
            artifacts=tuple(captured),
        )

    def _create_ticket(
        self,
        triage_dir: Path,
        incident: IncidentRecord,
        detection: DetectionResult,
        owner: str,
        context: Mapping[str, Any],
    ) -> Path:
        ticket_dir = triage_dir / "tickets"
        ticket_dir.mkdir(exist_ok=True)
        ticket_id = f"{self._config.ticket_project}-{incident.identifier}"
        ticket_payload = {
            "ticket_id": ticket_id,
            "template": self._config.ticket_template,
            "incident_id": incident.identifier,
            "severity": detection.severity,
            "owner": owner,
            "context": dict(context),
            "created_at": self._now().isoformat(),
            "escalation_contacts": list(
                self._config.escalation_policy.get(detection.severity, ())
            ),
            "communication_template": self._config.communication_templates.get(
                detection.severity
            ),
        }
        ticket_path = ticket_dir / f"{ticket_id}.json"
        ticket_path.write_text(
            json.dumps(ticket_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return ticket_path

    def _write_resources(
        self,
        triage_dir: Path,
        context: Mapping[str, Any],
    ) -> TriageStepReport:
        resources = {
            "runbooks": list(self._config.runbook_links),
            "dashboards": list(self._config.dashboard_links),
            "contextual_links": list(context.get("links", [])),
            "training_schedule": list(self._config.training_schedule),
        }
        path = triage_dir / "resources.json"
        path.write_text(
            json.dumps(resources, indent=2, sort_keys=True), encoding="utf-8"
        )
        return TriageStepReport(
            name="knowledge",
            status="completed",
            details={
                "runbooks": len(self._config.runbook_links),
                "dashboards": len(self._config.dashboard_links),
            },
            artifacts=(path,),
        )

    def _write_postmortem(
        self,
        triage_dir: Path,
        incident: IncidentRecord,
        detection: DetectionResult,
        owner: str,
        context: Mapping[str, Any],
    ) -> TriageStepReport:
        template_path = triage_dir / "postmortem.md"
        timeline: list[str] = []
        timeline.append(f"- {self._now().isoformat()} – Automated triage initiated.")
        template_path.write_text(
            "\n".join(
                [
                    f"# Postmortem Draft for {incident.identifier}",
                    "",
                    "## Summary",
                    f"- Owner: {owner}",
                    f"- Severity: {detection.severity}",
                    f"- Detected: {detection.reason}",
                    "",
                    "## Timeline",
                    *timeline,
                    "",
                    "## Impact",
                    "- Describe the user, business, and regulatory impact with measurable indicators.",
                    "",
                    "## Detection",
                    "- Explain the signals, monitors, or reports that identified the incident and any detection gaps.",
                    "",
                    "## Root Cause",
                    "- Summarize the technical fault and contributing process gaps validated by the response team.",
                    "",
                    "## Mitigations",
                    "- Summarize containment steps taken, their effectiveness, and outstanding risks.",
                    "",
                    "## Follow-up Actions",
                    "- List remediation tasks with accountable owners, due dates, and validation checkpoints.",
                    "",
                    "## Lessons Learned",
                    "- Capture decisions, surprises, and improvements to tooling, process, or staffing.",
                    "",
                    "## Related Links",
                    *[f"- {link}" for link in self._config.runbook_links],
                    *[f"- {link}" for link in self._config.dashboard_links],
                    *[f"- {link}" for link in context.get("links", [])],
                ]
            ),
            encoding="utf-8",
        )

        return TriageStepReport(
            name="postmortem",
            status="completed",
            details={"template": str(template_path)},
            artifacts=(template_path,),
        )

    def _write_recovery_plan(self, triage_dir: Path) -> TriageStepReport:
        recovery_path = triage_dir / "recovery.json"
        recovery_payload = {
            "actions": list(self._config.recovery_actions),
            "generated_at": self._now().isoformat(),
        }
        recovery_path.write_text(
            json.dumps(recovery_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        status = "completed" if self._config.recovery_actions else "skipped"
        return TriageStepReport(
            name="recovery",
            status=status,
            details={"actions": len(self._config.recovery_actions)},
            artifacts=(recovery_path,),
        )

    def _write_owner(
        self,
        triage_dir: Path,
        owner: str,
        context: Mapping[str, Any],
    ) -> None:
        owner_path = triage_dir / "owner.json"
        payload = {
            "owner": owner,
            "context": dict(context),
            "assigned_at": self._now().isoformat(),
        }
        owner_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _write_summary(
        self,
        started_at: datetime,
        completed_at: datetime,
        detection: DetectionResult,
        incident: IncidentRecord | None,
        owner: str | None,
        steps: Iterable[TriageStepReport],
        context: Mapping[str, Any],
    ) -> Path:
        summary_root = self._config.incident_root / "automation_runs"
        summary_root.mkdir(parents=True, exist_ok=True)
        summary_path = (
            summary_root / f"auto_triage_{started_at.strftime('%Y%m%dT%H%M%S')}.json"
        )

        payload = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": max(0.0, (completed_at - started_at).total_seconds()),
            "detection": {
                "triggered": detection.triggered,
                "severity": detection.severity,
                "reason": detection.reason,
                "violations": list(detection.violations),
            },
            "incident": None,
            "owner": owner,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "details": dict(step.details),
                    "artifacts": [str(path) for path in step.artifacts],
                }
                for step in steps
            ],
            "context": dict(context),
        }

        if incident is not None:
            payload["incident"] = {
                "id": incident.identifier,
                "directory": str(incident.directory),
                "summary_path": str(incident.summary_path),
            }

        summary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        return summary_path

    def _enforce_archive_budget(self) -> None:
        if self._config.archive_history == 0:
            return

        root = self._config.incident_root
        if not root.exists():
            return

        incident_dirs: list[Path] = []
        for child in root.iterdir():
            if not child.is_dir() or child.name == "automation_runs":
                continue
            for path in child.iterdir():
                if path.is_dir() and path.name.startswith("INC-"):
                    incident_dirs.append(path)

        incident_dirs.sort(key=lambda path: path.stat().st_mtime)

        # In addition to the incident directories, the orchestrator stores
        # summaries under ``automation_runs``.  Those files should not be
        # counted towards the incident history budget.
        limit = self._config.archive_history
        excess = max(0, len(incident_dirs) - limit)
        if excess <= 0:
            return

        for path in incident_dirs[:excess]:
            shutil.rmtree(path, ignore_errors=True)


# End of module
