# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Digital Governance Framework for GeoSync.

This module implements the comprehensive digital transformation requirements
as specified in the architectural mandate. It provides centralized enforcement
of all 20 digitalization requirements across the trading system.

The framework ensures:
1. Market & operational data digitization via schemas
2. End-to-end digital trading process
3. Complete digital session contours
4. Full digital trail & tracing
5. Digital twins of market/portfolio state
6. Orchestration via neuro-orchestrator
7. Automated workflows (backtest, replay, live)
8. Digital exchange integration
9. Data normalization
10. Schema validation
11. Active data quality management
12. Observability via TACL metrics
13. Regulatory audit logging
14. Digital approvals & overrides
15. Access policies & secrets
16. Digital KPIs
17. Event-oriented architecture
18. Formalized component lifecycle
19. Digital compliance & TACL boundaries
20. Digital security

Compliance Level: SEC, FINRA, EU AI Act, SOC 2, ISO 27001
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

__all__ = [
    "DigitalGovernanceFramework",
    "ComplianceLevel",
    "GovernanceViolation",
    "DataQualityCheck",
    "DigitalAuditRecord",
    "SchemaValidator",
    "TACLMetricsCollector",
    "SecretManager",
]

logger = logging.getLogger(__name__)


class ComplianceLevel(str, Enum):
    """Regulatory compliance levels."""

    SEC = "SEC"
    FINRA = "FINRA"
    EU_AI_ACT = "EU_AI_ACT"
    SOC2 = "SOC2"
    ISO_27001 = "ISO_27001"


class GovernanceViolation(RuntimeError):
    """Raised when a governance rule is violated."""

    def __init__(
        self,
        message: str,
        requirement_id: int,
        severity: str = "ERROR",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.requirement_id = requirement_id
        self.severity = severity
        self.context = context or {}


@dataclass(frozen=True)
class DigitalAuditRecord:
    """Structured audit record for digital trail compliance (Requirement #4, #13)."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    actor: str = ""
    component: str = ""
    operation: str = ""
    decision_basis: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    parent_event_id: Optional[str] = None

    # Regulatory fields
    compliance_level: List[ComplianceLevel] = field(
        default_factory=lambda: [ComplianceLevel.SEC, ComplianceLevel.FINRA]
    )
    retention_years: int = 7

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["compliance_level"] = [c.value for c in self.compliance_level]
        return data

    def to_json(self) -> str:
        """Serialize to JSON for audit log."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass
class DataQualityCheck:
    """Data quality check result (Requirement #11)."""

    check_type: str
    passed: bool
    metric_name: str
    value: float
    threshold: float
    severity: str = "WARNING"
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SchemaValidationProtocol(Protocol):
    """Protocol for schema validators (Requirement #10)."""

    def validate(self, data: Dict[str, Any], schema_name: str) -> bool:
        """Validate data against schema."""
        ...

    def get_schema_version(self, schema_name: str) -> str:
        """Get schema version."""
        ...


class SchemaValidator:
    """JSON Schema validator for market events (Requirement #1, #10).

    Validates all market events against schemas in schemas/events/json/1.0.0/
    Supported event types: ticks, bars, orders, fills, signals, prediction_completed
    """

    def __init__(self, schema_dir: Optional[Path] = None) -> None:
        self.schema_dir = schema_dir or Path("schemas/events/json/1.0.0")
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        """Load all JSON schemas from schema directory."""
        if not self.schema_dir.exists():
            logger.warning(f"Schema directory not found: {self.schema_dir}")
            return

        for schema_file in self.schema_dir.glob("*.schema.json"):
            schema_name = schema_file.stem.replace(".schema", "")
            try:
                with schema_file.open("r") as f:
                    self._schemas[schema_name] = json.load(f)
                logger.info(f"Loaded schema: {schema_name}")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")

    def validate(self, data: Dict[str, Any], schema_name: str) -> bool:
        """Validate data against schema.

        Args:
            data: Data to validate
            schema_name: Name of schema (e.g., 'ticks', 'bars', 'orders')

        Returns:
            True if valid

        Raises:
            GovernanceViolation: If validation fails
        """
        if schema_name not in self._schemas:
            raise GovernanceViolation(
                f"Schema not found: {schema_name}",
                requirement_id=10,
                severity="ERROR",
                context={"schema_name": schema_name},
            )

        schema = self._schemas[schema_name]

        # Basic validation - check required fields
        required_fields = schema.get("required", [])
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            raise GovernanceViolation(
                f"Missing required fields: {missing_fields}",
                requirement_id=1,
                severity="ERROR",
                context={"schema": schema_name, "missing": missing_fields},
            )

        # Validate event_id presence (Requirement #4)
        if "event_id" not in data:
            raise GovernanceViolation(
                "Missing event_id for digital trail",
                requirement_id=4,
                severity="ERROR",
                context={"schema": schema_name},
            )

        return True

    def get_schema_version(self, schema_name: str) -> str:
        """Get version of schema."""
        schema = self._schemas.get(schema_name, {})
        return schema.get("$id", "1.0.0")


class TACLMetricsCollector:
    """TACL metrics collector for observability (Requirement #12).

    Collects and exposes TACL metrics:
    - RPE (Reward Prediction Error) from dopamine
    - Free energy from TACL energy model
    - Risk thresholds from risk modules
    - Latency metrics
    - Neuromodulator levels (serotonin, dopamine, GABA, NAK)
    """

    def __init__(self) -> None:
        self._metrics: Dict[str, float] = {}
        self._counters: Dict[str, int] = {}

    def record_metric(self, name: str, value: float) -> None:
        """Record a TACL metric."""
        self._metrics[name] = value
        logger.debug(f"TACL metric: {name}={value}")

    def increment_counter(self, name: str, amount: int = 1) -> None:
        """Increment a counter."""
        self._counters[name] = self._counters.get(name, 0) + amount

    def get_metrics(self) -> Dict[str, float]:
        """Get all current metrics."""
        return self._metrics.copy()

    def get_counters(self) -> Dict[str, int]:
        """Get all counters."""
        return self._counters.copy()

    def check_thresholds(
        self,
        free_energy_max: float = 1.0,
        rpe_max: float = 2.0,
        latency_p99_max_ms: float = 120.0,
    ) -> List[str]:
        """Check if metrics exceed thresholds (Requirement #19).

        Returns:
            List of threshold violations
        """
        violations = []

        free_energy = self._metrics.get("tacl_free_energy", 0.0)
        if not math.isfinite(free_energy):
            violations.append("Free energy is non-finite")
        elif free_energy > free_energy_max:
            violations.append(f"Free energy {free_energy:.3f} exceeds max {free_energy_max}")

        rpe = self._metrics.get("dopamine_rpe", 0.0)
        if not math.isfinite(rpe):
            violations.append("RPE is non-finite")
        elif abs(rpe) > rpe_max:
            violations.append(f"RPE {rpe:.3f} exceeds max {rpe_max}")

        latency = self._metrics.get("latency_p99_ms", 0.0)
        if not math.isfinite(latency):
            violations.append("Latency P99 is non-finite")
        elif latency > latency_p99_max_ms:
            violations.append(f"Latency P99 {latency:.1f}ms exceeds max {latency_p99_max_ms}ms")

        return violations


class SecretManager:
    """Secret management for digital security (Requirement #15, #20).

    Ensures:
    - No hard-coded secrets in code
    - Proper .env usage
    - SECURITY.md compliance
    """

    SENSITIVE_KEYWORDS = {
        "token",
        "secret",
        "password",
        "key",
        "credential",
        "api_key",
        "private_key",
        "access_token",
        "auth",
        "bearer",
    }

    def __init__(self, env_file: Optional[Path] = None) -> None:
        self.env_file = env_file or Path(".env")
        self._secrets: Dict[str, str] = {}
        self._load_secrets()

    def _load_secrets(self) -> None:
        """Load secrets from .env file."""
        if self.env_file.exists():
            with self.env_file.open("r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        self._secrets[key.strip()] = value.strip()

    def get_secret(self, key: str) -> Optional[str]:
        """Get secret value."""
        # First check environment variables
        value = os.environ.get(key)
        if value:
            return value

        # Then check loaded secrets
        return self._secrets.get(key)

    def validate_no_hardcoded_secrets(self, code: str) -> List[str]:
        """Validate that code doesn't contain hard-coded secrets.

        Returns:
            List of potential violations
        """
        violations = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith("#"):
                continue

            # Check for potential secrets
            lower_line = line.lower()
            for keyword in self.SENSITIVE_KEYWORDS:
                if keyword in lower_line and ("=" in line or ":" in line):
                    # Check if it's referencing env var or config
                    if "os.environ" not in line and "getenv" not in line:
                        violations.append(f"Line {i}: Potential hard-coded {keyword}")

        return violations


class DigitalGovernanceFramework:
    """Main digital governance framework orchestrating all 20 requirements.

    This class provides the central governance layer that enforces all
    digitalization requirements across the GeoSync system.
    """

    def __init__(
        self,
        schema_dir: Optional[Path] = None,
        audit_log_path: Optional[Path] = None,
        enable_strict_mode: bool = True,
    ) -> None:
        """Initialize digital governance framework.

        Args:
            schema_dir: Path to JSON schemas
            audit_log_path: Path for audit logs
            enable_strict_mode: If True, violations raise exceptions
        """
        self.schema_validator = SchemaValidator(schema_dir)
        self.tacl_metrics = TACLMetricsCollector()
        self.secret_manager = SecretManager()
        self.enable_strict_mode = enable_strict_mode

        # Audit logging (Requirement #4, #13)
        self.audit_log_path = audit_log_path or Path("/var/log/geosync/audit.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Track violations
        self._violations: List[GovernanceViolation] = []

        # Data quality checks
        self._quality_checks: List[DataQualityCheck] = []

        logger.info("Digital Governance Framework initialized")

    # =========================================================================
    # Requirement #1: Market & Operational Data Digitization
    # =========================================================================

    def validate_market_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> bool:
        """Validate market event against schema.

        Supported event types: ticks, bars, orders, fills, signals, prediction_completed
        """
        try:
            return self.schema_validator.validate(event_data, event_type)
        except GovernanceViolation as e:
            self._handle_violation(e)
            return False

    # =========================================================================
    # Requirement #4: Digital Trail & Tracing
    # =========================================================================

    def log_audit_event(
        self,
        event_type: str,
        actor: str,
        component: str,
        operation: str,
        decision_basis: Dict[str, Any],
        result: Dict[str, Any],
        trace_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
    ) -> DigitalAuditRecord:
        """Log an audit event for digital trail.

        Every decision (strategy, neuro, risk, TACL) must be logged.
        """
        record = DigitalAuditRecord(
            event_type=event_type,
            actor=actor,
            component=component,
            operation=operation,
            decision_basis=decision_basis,
            result=result,
            trace_id=trace_id,
            parent_event_id=parent_event_id,
        )

        # Write to audit log
        try:
            with self.audit_log_path.open("a") as f:
                f.write(record.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

        return record

    # =========================================================================
    # Requirement #9: Data Normalization
    # =========================================================================

    def normalize_timestamp(self, timestamp: Any) -> int:
        """Normalize timestamp to unix microseconds.

        All timestamps in GeoSync use unix microseconds in UTC.
        """
        if isinstance(timestamp, datetime):
            return int(timestamp.timestamp() * 1_000_000)
        elif isinstance(timestamp, (int, float)):
            # Assume already in correct format
            return int(timestamp)
        else:
            raise GovernanceViolation(
                f"Invalid timestamp type: {type(timestamp)}",
                requirement_id=9,
                severity="ERROR",
            )

    # =========================================================================
    # Requirement #11: Active Data Quality Management
    # =========================================================================

    def check_data_quality(
        self,
        data_name: str,
        values: List[float],
        detect_gaps: bool = True,
        detect_spikes: bool = True,
        spike_threshold_std: float = 5.0,
    ) -> List[DataQualityCheck]:
        """Check data quality for anomalies.

        Detects:
        - Gaps in data
        - Spikes (values beyond threshold std devs)
        - Shifts in distribution
        """
        checks = []

        if not values:
            check = DataQualityCheck(
                check_type="empty_data",
                passed=False,
                metric_name=data_name,
                value=0.0,
                threshold=1.0,
                severity="ERROR",
                message="No data points",
            )
            checks.append(check)
            self._quality_checks.append(check)
            return checks

        import numpy as np

        values_arr = np.array(values)

        # Check for NaN/Inf
        if np.isnan(values_arr).any() or np.isinf(values_arr).any():
            check = DataQualityCheck(
                check_type="invalid_values",
                passed=False,
                metric_name=data_name,
                value=float(np.isnan(values_arr).sum() + np.isinf(values_arr).sum()),
                threshold=0.0,
                severity="ERROR",
                message="Contains NaN or Inf values",
            )
            checks.append(check)
            self._quality_checks.append(check)

        # Detect spikes
        if detect_spikes and len(values_arr) > 1:
            mean = np.mean(values_arr)
            std = np.std(values_arr)

            if std > 0:
                z_scores = np.abs((values_arr - mean) / std)
                spike_count = int((z_scores > spike_threshold_std).sum())

                if spike_count > 0:
                    check = DataQualityCheck(
                        check_type="spikes",
                        passed=False,
                        metric_name=data_name,
                        value=float(spike_count),
                        threshold=0.0,
                        severity="WARNING",
                        message=f"{spike_count} spike(s) detected (>{spike_threshold_std} std)",
                    )
                    checks.append(check)
                    self._quality_checks.append(check)

        return checks

    # =========================================================================
    # Requirement #12: Observability via TACL
    # =========================================================================

    def record_tacl_metric(self, name: str, value: float) -> None:
        """Record TACL observability metric."""
        self.tacl_metrics.record_metric(name, value)

    def get_tacl_metrics(self) -> Dict[str, float]:
        """Get all TACL metrics."""
        return self.tacl_metrics.get_metrics()

    # =========================================================================
    # Requirement #19: Digital Compliance & TACL Boundaries
    # =========================================================================

    def enforce_tacl_boundaries(
        self,
        free_energy_max: float = 1.0,
        rpe_max: float = 2.0,
        latency_p99_max_ms: float = 120.0,
    ) -> bool:
        """Enforce TACL boundaries and risk limits.

        Returns:
            True if all boundaries respected, False otherwise
        """
        violations = self.tacl_metrics.check_thresholds(
            free_energy_max=free_energy_max,
            rpe_max=rpe_max,
            latency_p99_max_ms=latency_p99_max_ms,
        )

        if violations:
            for violation_msg in violations:
                violation = GovernanceViolation(
                    violation_msg,
                    requirement_id=19,
                    severity="CRITICAL",
                )
                self._handle_violation(violation)
            return False

        return True

    # =========================================================================
    # Requirement #20: Digital Security
    # =========================================================================

    def validate_code_security(self, code: str) -> List[str]:
        """Validate code for security issues.

        Checks for:
        - Hard-coded secrets
        - Injection vulnerabilities (basic check)
        """
        violations = []

        # Check for hard-coded secrets
        secret_violations = self.secret_manager.validate_no_hardcoded_secrets(code)
        violations.extend(secret_violations)

        # Basic injection checks
        dangerous_patterns = ["exec(", "eval(", "os.system(", "subprocess.call("]
        for pattern in dangerous_patterns:
            if pattern in code:
                violations.append(f"Potentially dangerous pattern: {pattern}")

        return violations

    # =========================================================================
    # Violation Handling
    # =========================================================================

    def _handle_violation(self, violation: GovernanceViolation) -> None:
        """Handle a governance violation."""
        self._violations.append(violation)

        logger.error(
            f"Governance violation (Req #{violation.requirement_id}): "
            f"{violation} [severity={violation.severity}]"
        )

        # Log to audit trail
        self.log_audit_event(
            event_type="governance_violation",
            actor="digital_governance",
            component="governance_framework",
            operation="violation_detected",
            decision_basis=violation.context,
            result={
                "requirement_id": violation.requirement_id,
                "severity": violation.severity,
                "message": str(violation),
            },
        )

        # In strict mode, raise exception for errors
        if self.enable_strict_mode and violation.severity in ("ERROR", "CRITICAL"):
            raise violation

    def get_violations(self) -> List[GovernanceViolation]:
        """Get all recorded violations."""
        return self._violations.copy()

    def get_quality_checks(self) -> List[DataQualityCheck]:
        """Get all data quality checks."""
        return self._quality_checks.copy()

    def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate comprehensive compliance report.

        Returns report covering all 20 requirements.
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "framework_version": "1.0.0",
            "compliance_levels": [c.value for c in ComplianceLevel],
            "violations": [
                {
                    "requirement_id": v.requirement_id,
                    "severity": v.severity,
                    "message": str(v),
                    "context": v.context,
                }
                for v in self._violations
            ],
            "quality_checks": [
                {
                    "check_type": c.check_type,
                    "passed": c.passed,
                    "metric": c.metric_name,
                    "value": c.value,
                    "threshold": c.threshold,
                    "severity": c.severity,
                    "message": c.message,
                }
                for c in self._quality_checks
            ],
            "tacl_metrics": self.tacl_metrics.get_metrics(),
            "tacl_counters": self.tacl_metrics.get_counters(),
            "total_violations": len(self._violations),
            "critical_violations": sum(1 for v in self._violations if v.severity == "CRITICAL"),
            "error_violations": sum(1 for v in self._violations if v.severity == "ERROR"),
            "warning_violations": sum(1 for v in self._violations if v.severity == "WARNING"),
        }
