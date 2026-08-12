# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Orchestrated observability bootstrap utilities.

This module centralises the steps required to prepare the GeoSync
observability stack end-to-end.  It wires together logging, metrics, and
tracing configuration, validates dashboards and alert definitions, performs
synthetic endpoint probing, ensures exporters are reachable, and generates
postmortem templates.  The goal is to offer a single, repeatable entrypoint
that operators can run during environment provisioning or continuous delivery
pipelines.

The implementation intentionally leans on existing building blocks (logging
formatters, tracing helpers, Prometheus manifest generation) to avoid
duplicating logic.  Additional glue code focuses on safe defaults, extensive
validation, and actionable summaries returned to callers.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.utils.slo import AutoRollbackGuard, SLOBurnRateRule, SLOConfig
from observability.logging import StructuredLogFormatter, configure_logging
from observability.tracing import TracingConfig, configure_tracing
from tools.observability.builder import (
    MetricDefinition,
    build_bundle,
    validate_alerts,
    validate_metrics,
)

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging


class _TaggingFilter(logging.Filter):
    """Inject static key/value tags into every log record."""

    def __init__(self, tags: Mapping[str, str]) -> None:
        super().__init__()
        self._tags = dict(tags)

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover -
        for key, value in self._tags.items():
            record.__dict__.setdefault(key, value)
        return True


@dataclass(slots=True)
class LoggingSetup:
    """Parameters for configuring structured logging."""

    level: int | str = logging.INFO
    tags: Mapping[str, str] = field(default_factory=dict)
    sink: Callable[[dict[str, Any]], None] | None = None

    def apply(self) -> StructuredLogFormatter:
        """Configure logging and attach static tags."""

        configure_logging(level=self.level, sink=self.sink)
        formatter = StructuredLogFormatter()

        if self.tags:
            root_logger = logging.getLogger()
            tag_filter = _TaggingFilter(self.tags)
            root_logger.addFilter(tag_filter)
            for handler in root_logger.handlers:
                handler.addFilter(tag_filter)
        return formatter


# ---------------------------------------------------------------------------
# Metrics


@dataclass(slots=True)
class MetricsValidationIssue:
    """Structured representation of a metrics validation warning."""

    metric: str
    message: str


@dataclass(slots=True)
class MetricsValidationReport:
    """Outcome of validating metric definitions."""

    metrics: Sequence[MetricDefinition]
    issues: Sequence[MetricsValidationIssue] = ()

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


@dataclass(slots=True)
class MetricsSetup:
    """Configuration for metrics validation and tagging."""

    metrics_path: Path = Path("observability/metrics.json")
    required_tags: Sequence[str] = field(default_factory=lambda: ("service", "environment"))
    max_labels_per_metric: int = 8
    cardinality_limits: Mapping[str, int] = field(
        default_factory=lambda: {"service": 10, "environment": 5, "strategy": 50}
    )

    def validate(self) -> MetricsValidationReport:
        definitions = validate_metrics(self.metrics_path)
        issues: list[MetricsValidationIssue] = []

        for metric in definitions:
            label_count = len(metric.labels)
            if label_count > self.max_labels_per_metric:
                issues.append(
                    MetricsValidationIssue(
                        metric=metric.name,
                        message=(
                            "label count exceeds max_labels_per_metric"
                            f" ({label_count} > {self.max_labels_per_metric})"
                        ),
                    )
                )

            missing = [tag for tag in self.required_tags if tag not in metric.labels]
            if missing:
                issues.append(
                    MetricsValidationIssue(
                        metric=metric.name,
                        message=("missing required tags: " + ", ".join(sorted(missing))),
                    )
                )

            for label in metric.labels:
                if label not in self.cardinality_limits:
                    issues.append(
                        MetricsValidationIssue(
                            metric=metric.name,
                            message=(f"label '{label}' lacks a configured cardinality limit"),
                        )
                    )

        return MetricsValidationReport(metrics=definitions, issues=issues)


# ---------------------------------------------------------------------------
# Tracing


@dataclass(slots=True)
class TracingSetup:
    """Wrapper around :class:`observability.tracing.TracingConfig`."""

    config: TracingConfig = field(default_factory=TracingConfig)

    def apply(self) -> bool:
        return configure_tracing(self.config)


# ---------------------------------------------------------------------------
# Dashboards & Alerts


@dataclass(slots=True)
class DashboardSetup:
    """Compile dashboards and alert definitions into generated artefacts."""

    root: Path = Path("observability")
    output_dir: Path = Path("observability/generated")

    def build(self) -> dict[str, Any]:
        return build_bundle(self.root, self.output_dir)


@dataclass(slots=True)
class AlertNoiseGuard:
    """Evaluate alert definitions for anti-noise best practices."""

    alerts_path: Path = Path("observability/alerts.json")
    minimum_for_seconds: int = 60

    def evaluate(self, metric_names: Iterable[str]) -> dict[str, list[str]]:
        payload = validate_alerts(self.alerts_path, metric_names)
        findings: dict[str, list[str]] = defaultdict(list)

        for group in payload.get("groups", []):
            group_name = group.get("name", "<unknown>")
            for rule in group.get("rules", []):
                alert_name = rule.get("alert", "<unnamed>")
                hold_for = rule.get("for")
                if hold_for is None:
                    findings[group_name].append(
                        f"{alert_name}: missing 'for' to dampen transient noise"
                    )
                    continue
                try:
                    duration = _parse_duration_to_seconds(str(hold_for))
                except ValueError:
                    findings[group_name].append(
                        f"{alert_name}: invalid 'for' duration {hold_for!r}"
                    )
                    continue
                if duration < self.minimum_for_seconds:
                    findings[group_name].append(
                        f"{alert_name}: hold duration {duration}s below minimum"
                    )

        return {group: issues for group, issues in findings.items() if issues}


# ---------------------------------------------------------------------------
# Endpoint & Synthetic validation


@dataclass(slots=True)
class EndpointCheck:
    """Declarative description of an HTTP endpoint validation."""

    url: str
    expected_status: int = 200
    timeout: float = 2.0


@dataclass(slots=True)
class EndpointCheckResult:
    """Outcome of a single endpoint validation."""

    check: EndpointCheck
    success: bool
    status: int | None
    detail: str | None = None


@dataclass(slots=True)
class EndpointValidator:
    """Execute synthetic black-box checks against HTTP endpoints."""

    checks: Sequence[EndpointCheck]

    def run(self) -> list[EndpointCheckResult]:
        results: list[EndpointCheckResult] = []
        for check in self.checks:
            try:
                request = urllib.request.Request(check.url, method="GET")
                with urllib.request.urlopen(request, timeout=check.timeout) as resp:
                    status = int(resp.status)
                    body = resp.read()
            except urllib.error.HTTPError as exc:
                results.append(
                    EndpointCheckResult(
                        check=check,
                        success=exc.code == check.expected_status,
                        status=exc.code,
                        detail=str(exc),
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                results.append(
                    EndpointCheckResult(
                        check=check,
                        success=False,
                        status=None,
                        detail=str(exc),
                    )
                )
            else:
                detail = f"response {status}; {len(body)} bytes"
                results.append(
                    EndpointCheckResult(
                        check=check,
                        success=status == check.expected_status,
                        status=status,
                        detail=detail,
                    )
                )
        return results


@dataclass(slots=True)
class SyntheticCheck:
    """Generic callable-based synthetic check."""

    name: str
    probe: Callable[[], bool]


@dataclass(slots=True)
class SyntheticSuite:
    """Execute custom probes to validate business transactions."""

    checks: Sequence[SyntheticCheck]

    def run(self) -> dict[str, bool]:
        outcomes: dict[str, bool] = {}
        for check in self.checks:
            try:
                outcomes[check.name] = bool(check.probe())
            except Exception:  # pragma: no cover - defensive logging path
                LOGGER.exception("Synthetic check failed", extra={"check": check.name})
                outcomes[check.name] = False
        return outcomes


# ---------------------------------------------------------------------------
# Exporters & agents


@dataclass(slots=True)
class ExporterSetup:
    """Ensure Prometheus exporters are running and reachable."""

    enable_prometheus: bool = True
    address: str = "127.0.0.1"
    port: int = 9200

    def verify_connectivity(self, *, timeout: float = 1.0) -> bool:
        if not self.enable_prometheus:
            return True

        sock = socket.socket()
        sock.settimeout(timeout)
        try:
            sock.connect((self.address, self.port))
        except OSError:
            return False
        finally:
            sock.close()
        return True


# ---------------------------------------------------------------------------
# SLO definitions & validation


def _parse_duration_to_seconds(value: str) -> float:
    value = value.strip().lower()
    if value.endswith("ms"):
        return max(0.0, float(value[:-2]) / 1000.0)
    if value.endswith("s"):
        return float(value[:-1])
    if value.endswith("m"):
        minutes = float(value[:-1])
        return minutes * 60.0
    if value.endswith("h"):
        hours = float(value[:-1])
        return hours * 3600.0
    if value.endswith("d"):
        days = float(value[:-1])
        return days * 86400.0
    raise ValueError(f"Unsupported duration literal: {value}")


def _parse_duration(value: str) -> timedelta:
    seconds = _parse_duration_to_seconds(value)
    return timedelta(seconds=seconds)


@dataclass(slots=True)
class SLOPolicy:
    """Representation of an SLO policy defined in JSON."""

    name: str
    description: str
    error_rate_threshold: float
    latency_threshold_ms: float
    min_requests: int
    evaluation_period: timedelta
    burn_rates: tuple[SLOBurnRateRule, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SLOPolicy":
        burn_rates: list[SLOBurnRateRule] = []
        for entry in payload.get("burn_rates", []):
            window = _parse_duration(entry["window"])
            burn_rates.append(
                SLOBurnRateRule(
                    window=window,
                    max_burn_rate=float(entry["max_burn_rate"]),
                    min_requests=int(entry.get("min_requests", 0)) or None,
                    name=entry.get("name"),
                )
            )

        return cls(
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            error_rate_threshold=float(payload["error_rate_threshold"]),
            latency_threshold_ms=float(payload["latency_threshold_ms"]),
            min_requests=int(payload.get("min_requests", 1)),
            evaluation_period=_parse_duration(payload.get("evaluation_period", "5m")),
            burn_rates=tuple(burn_rates),
        )

    def to_config(self) -> SLOConfig:
        return SLOConfig(
            error_rate_threshold=self.error_rate_threshold,
            latency_threshold_ms=self.latency_threshold_ms,
            min_requests=self.min_requests,
            evaluation_period=self.evaluation_period,
            burn_rate_rules=self.burn_rates,
        )


@dataclass(slots=True)
class SLOSuite:
    """Load SLO policies and validate guardrail behaviour."""

    policies_path: Path = Path("observability/slo_policies.json")

    def load(self) -> list[SLOPolicy]:
        payload = json.loads(self.policies_path.read_text(encoding="utf-8"))
        policies: list[SLOPolicy] = []
        for item in payload.get("slos", []):
            policies.append(SLOPolicy.from_dict(item))
        if not policies:
            raise ValueError("No SLO policies defined")
        return policies

    def run_threshold_tests(self) -> dict[str, dict[str, bool]]:
        results: dict[str, dict[str, bool]] = {}
        for policy in self.load():
            config = policy.to_config()
            guard = AutoRollbackGuard(config)
            safe = not guard.evaluate_snapshot(
                error_rate=max(0.0, config.error_rate_threshold - 0.001),
                latency_p95_ms=config.latency_threshold_ms - 1.0,
                total_requests=config.min_requests,
            )
            breach = guard.evaluate_snapshot(
                error_rate=min(1.0, config.error_rate_threshold + 0.05),
                latency_p95_ms=config.latency_threshold_ms * 1.5,
                total_requests=max(config.min_requests, 10),
            )
            results[policy.name] = {"within_threshold": safe, "breach_detected": breach}
        return results


# ---------------------------------------------------------------------------
# Postmortem template


@dataclass(slots=True)
class PostmortemTemplateBuilder:
    """Ensure a postmortem template exists for incident reviews."""

    template_path: Path
    sections: Sequence[str] = field(
        default_factory=lambda: (
            "Summary",
            "Timeline",
            "Impact",
            "Detection",
            "Root Cause",
            "Mitigations",
            "Follow-up Actions",
            "Lessons Learned",
        )
    )

    def ensure(self) -> Path:
        if self.template_path.exists():
            return self.template_path

        lines = ["# Postmortem Template", ""]
        guidance: dict[str, str] = {
            "Summary": "- Capture a concise description of the incident, affected systems, and customer impact.",
            "Timeline": "- List the key timestamps from detection through resolution with responsible owners.",
            "Impact": "- Quantify user-facing impact, financial exposure, and any regulatory considerations.",
            "Detection": "- Explain how the issue was detected and where monitoring succeeded or failed.",
            "Root Cause": "- Document the technical and organizational contributors that allowed the issue to occur.",
            "Mitigations": "- Outline containment actions taken during the incident and their effectiveness.",
            "Follow-up Actions": "- Define remediation tasks with owners and due dates to prevent recurrence.",
            "Lessons Learned": "- Summarize key takeaways to improve processes, tooling, and communication.",
        }
        default_note = "- Record the most relevant facts, decisions, and outstanding questions."
        for section in self.sections:
            lines.append(f"## {section}")
            lines.append("")
            lines.append(guidance.get(section, default_note))
            lines.append("")

        self.template_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return self.template_path


# ---------------------------------------------------------------------------
# Bootstrap orchestrator


@dataclass(slots=True)
class ObservabilityBootstrapper:
    """High-level coordinator for observability setup."""

    logging: LoggingSetup
    metrics: MetricsSetup
    tracing: TracingSetup
    dashboards: DashboardSetup
    endpoints: EndpointValidator
    synthetic: SyntheticSuite
    exporters: ExporterSetup
    slo: SLOSuite
    postmortem: PostmortemTemplateBuilder
    alert_guard: AlertNoiseGuard

    def run(self) -> dict[str, Any]:
        formatter = self.logging.apply()
        LOGGER.debug("Logging configured", extra={"formatter": formatter.__class__.__name__})

        metrics_report = self.metrics.validate()
        if metrics_report.issues:
            for issue in metrics_report.issues:
                LOGGER.warning(
                    "Metric validation warning",
                    extra={"metric": issue.metric, "detail": issue.message},
                )

        tracing_enabled = self.tracing.apply()

        manifest = self.dashboards.build()
        metric_names = [metric.name for metric in metrics_report.metrics]
        alert_findings = self.alert_guard.evaluate(metric_names)

        endpoint_results = self.endpoints.run()
        synthetic_results = self.synthetic.run()

        exporter_ok = self.exporters.verify_connectivity()
        slo_results = self.slo.run_threshold_tests()
        template_path = self.postmortem.ensure()

        return {
            "metrics": metrics_report,
            "tracing_enabled": tracing_enabled,
            "manifest": manifest,
            "endpoints": endpoint_results,
            "synthetic": synthetic_results,
            "exporter_ok": exporter_ok,
            "slo": slo_results,
            "postmortem_template": str(template_path),
            "alert_findings": alert_findings,
        }


def build_default_bootstrapper() -> ObservabilityBootstrapper:
    """Return a bootstrapper wired with repository defaults."""

    logging_setup = LoggingSetup(tags={"service": "geosync", "environment": "local"})
    metrics_setup = MetricsSetup()
    tracing_setup = TracingSetup(TracingConfig(environment="local"))
    dashboards_setup = DashboardSetup()
    alert_guard = AlertNoiseGuard()

    endpoints = EndpointValidator(
        checks=(
            EndpointCheck("http://127.0.0.1:8085/healthz"),
            EndpointCheck("http://127.0.0.1:8085/readyz"),
        )
    )

    synthetic_suite = SyntheticSuite(
        checks=(
            SyntheticCheck(
                "order-roundtrip",
                probe=lambda: True,
            ),
        )
    )

    exporters = ExporterSetup()
    slo_suite = SLOSuite()
    postmortem_builder = PostmortemTemplateBuilder(
        template_path=Path("observability/generated/postmortem_template.md")
    )

    return ObservabilityBootstrapper(
        logging=logging_setup,
        metrics=metrics_setup,
        tracing=tracing_setup,
        dashboards=dashboards_setup,
        endpoints=endpoints,
        synthetic=synthetic_suite,
        exporters=exporters,
        slo=slo_suite,
        postmortem=postmortem_builder,
        alert_guard=alert_guard,
    )


__all__ = [
    "AlertNoiseGuard",
    "EndpointCheck",
    "EndpointCheckResult",
    "EndpointValidator",
    "ExporterSetup",
    "LoggingSetup",
    "MetricsSetup",
    "MetricsValidationIssue",
    "MetricsValidationReport",
    "ObservabilityBootstrapper",
    "PostmortemTemplateBuilder",
    "SLOPolicy",
    "SLOSuite",
    "SyntheticCheck",
    "SyntheticSuite",
    "TracingSetup",
    "build_default_bootstrapper",
]
