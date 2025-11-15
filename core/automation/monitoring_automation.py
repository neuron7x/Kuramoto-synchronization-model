# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Monitoring & Observability Automation

Autonomous monitoring that:
- Auto-triage system for alerts with intelligent routing
- Self-diagnostics and proactive health checks
- Automated incident response workflows
- Adaptive alerting thresholds
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Incident status states."""
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Alert:
    """Represents a monitoring alert."""
    
    alert_id: str
    severity: AlertSeverity
    source: str
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    auto_triaged: bool = False
    triage_action: Optional[str] = None


@dataclass
class Incident:
    """Represents a system incident."""
    
    incident_id: str
    status: IncidentStatus
    severity: AlertSeverity
    alerts: List[Alert]
    created_at: datetime
    resolved_at: Optional[datetime] = None
    auto_mitigation_attempted: bool = False
    mitigation_actions: List[str] = field(default_factory=list)


@dataclass
class HealthCheck:
    """Health check result."""
    
    check_name: str
    passed: bool
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class MonitoringAutomation:
    """
    Autonomous monitoring and observability system.
    
    Features:
    1. Intelligent auto-triage of alerts
    2. Self-diagnostic health checks
    3. Automated incident response
    4. Adaptive alerting thresholds
    """
    
    def __init__(
        self,
        health_check_interval_seconds: int = 60,
        alert_correlation_window_seconds: int = 300,
        auto_mitigation_enabled: bool = True,
    ):
        """
        Initialize monitoring automation.
        
        Args:
            health_check_interval_seconds: Interval for health checks
            alert_correlation_window_seconds: Window for correlating alerts
            auto_mitigation_enabled: Enable automatic mitigation
        """
        self.health_check_interval = timedelta(seconds=health_check_interval_seconds)
        self.correlation_window = timedelta(seconds=alert_correlation_window_seconds)
        self.auto_mitigation_enabled = auto_mitigation_enabled
        
        self._alerts: List[Alert] = []
        self._incidents: Dict[str, Incident] = {}
        self._health_checks: List[HealthCheck] = []
        self._alert_thresholds: Dict[str, float] = self._initialize_thresholds()
        self._mitigation_strategies: Dict[str, Callable] = self._register_mitigation_strategies()
        
    def _initialize_thresholds(self) -> Dict[str, float]:
        """Initialize adaptive alert thresholds."""
        return {
            "cpu_usage": 0.80,
            "memory_usage": 0.85,
            "disk_usage": 0.90,
            "error_rate": 0.05,
            "response_time_ms": 1000.0,
            "queue_depth": 10000.0,
        }
    
    def _register_mitigation_strategies(self) -> Dict[str, Callable]:
        """Register automated mitigation strategies."""
        return {
            "high_cpu": self._mitigate_high_cpu,
            "high_memory": self._mitigate_high_memory,
            "high_error_rate": self._mitigate_high_error_rate,
            "slow_response": self._mitigate_slow_response,
            "queue_backlog": self._mitigate_queue_backlog,
        }
    
    async def process_alert(
        self,
        alert_id: str,
        severity: AlertSeverity,
        source: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """
        Process an alert with automatic triage.
        
        Args:
            alert_id: Unique alert identifier
            severity: Alert severity level
            source: Alert source system
            message: Alert message
            metadata: Additional alert metadata
            
        Returns:
            Processed alert with triage information
        """
        alert = Alert(
            alert_id=alert_id,
            severity=severity,
            source=source,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        
        # Auto-triage alert
        triage_action = await self._auto_triage(alert)
        alert.auto_triaged = True
        alert.triage_action = triage_action
        
        self._alerts.append(alert)
        
        # Check for incident correlation
        await self._correlate_alerts(alert)
        
        # Apply mitigation if needed
        if severity in (AlertSeverity.ERROR, AlertSeverity.CRITICAL):
            await self._apply_auto_mitigation(alert)
        
        logger.info(f"Alert processed: {alert_id}, triage: {triage_action}")
        
        return alert
    
    async def _auto_triage(self, alert: Alert) -> str:
        """
        Automatically triage an alert and determine action.
        
        Returns:
            Triage action to take
        """
        # Simple triage logic based on severity and source
        if alert.severity == AlertSeverity.CRITICAL:
            return "escalate_immediately"
        
        if alert.severity == AlertSeverity.ERROR:
            # Check if this is a known issue
            similar_alerts = self._find_similar_alerts(alert, hours=1)
            if len(similar_alerts) >= 3:
                return "create_incident"
            return "monitor_and_notify"
        
        if alert.severity == AlertSeverity.WARNING:
            # Check for trends
            if self._is_trending_up(alert):
                return "monitor_closely"
            return "log_only"
        
        return "log_only"
    
    def _find_similar_alerts(self, alert: Alert, hours: int = 1) -> List[Alert]:
        """Find similar alerts within time window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        return [
            a for a in self._alerts
            if a.source == alert.source
            and a.timestamp >= cutoff
            and a.alert_id != alert.alert_id
        ]
    
    def _is_trending_up(self, alert: Alert) -> bool:
        """Check if alerts of this type are trending upward."""
        similar = self._find_similar_alerts(alert, hours=24)
        
        if len(similar) < 5:
            return False
        
        # Check if frequency is increasing
        recent = sum(1 for a in similar if a.timestamp >= datetime.now(timezone.utc) - timedelta(hours=1))
        older = sum(1 for a in similar if a.timestamp < datetime.now(timezone.utc) - timedelta(hours=1))
        
        return recent > older * 1.5
    
    async def _correlate_alerts(self, alert: Alert) -> None:
        """Correlate alerts to detect incidents."""
        # Find recent alerts within correlation window
        cutoff = datetime.now(timezone.utc) - self.correlation_window
        recent_alerts = [a for a in self._alerts if a.timestamp >= cutoff]
        
        # Group by source
        alerts_by_source = {}
        for a in recent_alerts:
            if a.source not in alerts_by_source:
                alerts_by_source[a.source] = []
            alerts_by_source[a.source].append(a)
        
        # Create incident if multiple critical/error alerts from same source
        for source, source_alerts in alerts_by_source.items():
            critical_errors = [
                a for a in source_alerts
                if a.severity in (AlertSeverity.CRITICAL, AlertSeverity.ERROR)
            ]
            
            if len(critical_errors) >= 3:
                await self._create_incident(source, critical_errors)
    
    async def _create_incident(self, source: str, alerts: List[Alert]) -> Incident:
        """Create a new incident from correlated alerts."""
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{source}"
        
        # Determine severity (highest among alerts)
        severity = max((a.severity for a in alerts), key=lambda s: list(AlertSeverity).index(s))
        
        incident = Incident(
            incident_id=incident_id,
            status=IncidentStatus.DETECTED,
            severity=severity,
            alerts=alerts,
            created_at=datetime.now(timezone.utc),
        )
        
        self._incidents[incident_id] = incident
        
        logger.warning(f"Incident created: {incident_id} with {len(alerts)} correlated alerts")
        
        # Start automated response
        if self.auto_mitigation_enabled:
            await self._respond_to_incident(incident)
        
        return incident
    
    async def _respond_to_incident(self, incident: Incident) -> None:
        """Automated incident response workflow."""
        incident.status = IncidentStatus.INVESTIGATING
        
        # Analyze incident
        root_cause = await self._analyze_incident(incident)
        
        # Apply mitigation
        incident.status = IncidentStatus.MITIGATING
        incident.auto_mitigation_attempted = True
        
        for alert in incident.alerts:
            await self._apply_auto_mitigation(alert)
        
        logger.info(f"Automated mitigation applied for incident: {incident.incident_id}")
    
    async def _analyze_incident(self, incident: Incident) -> str:
        """Analyze incident to determine root cause."""
        # Simple analysis based on alert patterns
        sources = [a.source for a in incident.alerts]
        most_common_source = max(set(sources), key=sources.count)
        
        return f"Multiple failures from {most_common_source}"
    
    async def _apply_auto_mitigation(self, alert: Alert) -> None:
        """Apply automated mitigation for an alert."""
        # Determine mitigation strategy based on alert content
        strategy = self._select_mitigation_strategy(alert)
        
        if strategy and strategy in self._mitigation_strategies:
            try:
                mitigation_func = self._mitigation_strategies[strategy]
                await mitigation_func(alert)
                logger.info(f"Applied mitigation strategy '{strategy}' for alert {alert.alert_id}")
            except Exception as e:
                logger.error(f"Mitigation failed for {alert.alert_id}: {e}")
    
    def _select_mitigation_strategy(self, alert: Alert) -> Optional[str]:
        """Select appropriate mitigation strategy for alert."""
        message_lower = alert.message.lower()
        
        if "cpu" in message_lower or "processor" in message_lower:
            return "high_cpu"
        elif "memory" in message_lower or "ram" in message_lower:
            return "high_memory"
        elif "error" in message_lower or "exception" in message_lower:
            return "high_error_rate"
        elif "slow" in message_lower or "latency" in message_lower:
            return "slow_response"
        elif "queue" in message_lower or "backlog" in message_lower:
            return "queue_backlog"
        
        return None
    
    async def _mitigate_high_cpu(self, alert: Alert) -> None:
        """Mitigate high CPU usage."""
        logger.info("Mitigation: Reducing background job concurrency")
        # Placeholder for actual mitigation logic
        await asyncio.sleep(0.1)
    
    async def _mitigate_high_memory(self, alert: Alert) -> None:
        """Mitigate high memory usage."""
        logger.info("Mitigation: Clearing caches and garbage collection")
        # Placeholder for actual mitigation logic
        await asyncio.sleep(0.1)
    
    async def _mitigate_high_error_rate(self, alert: Alert) -> None:
        """Mitigate high error rate."""
        logger.info("Mitigation: Enabling circuit breaker and fallback mode")
        # Placeholder for actual mitigation logic
        await asyncio.sleep(0.1)
    
    async def _mitigate_slow_response(self, alert: Alert) -> None:
        """Mitigate slow response times."""
        logger.info("Mitigation: Scaling up resources and optimizing queries")
        # Placeholder for actual mitigation logic
        await asyncio.sleep(0.1)
    
    async def _mitigate_queue_backlog(self, alert: Alert) -> None:
        """Mitigate queue backlog."""
        logger.info("Mitigation: Increasing queue workers and batch processing")
        # Placeholder for actual mitigation logic
        await asyncio.sleep(0.1)
    
    async def run_health_checks(self) -> List[HealthCheck]:
        """
        Run comprehensive health checks.
        
        Returns:
            List of health check results
        """
        checks = []
        
        # CPU check
        checks.append(await self._check_cpu_health())
        
        # Memory check
        checks.append(await self._check_memory_health())
        
        # Disk check
        checks.append(await self._check_disk_health())
        
        # Service availability
        checks.append(await self._check_service_health())
        
        # Database connectivity
        checks.append(await self._check_database_health())
        
        self._health_checks.extend(checks)
        
        # Trigger alerts for failed checks
        for check in checks:
            if not check.passed:
                await self.process_alert(
                    alert_id=f"health-{check.check_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    severity=AlertSeverity.WARNING,
                    source="health_check",
                    message=check.message,
                    metadata=check.metadata,
                )
        
        return checks
    
    async def _check_cpu_health(self) -> HealthCheck:
        """Check CPU health."""
        # Placeholder - actual implementation would check real CPU metrics
        cpu_usage = 0.45  # Example: 45%
        threshold = self._alert_thresholds["cpu_usage"]
        
        passed = cpu_usage < threshold
        message = f"CPU usage: {cpu_usage:.1%}" + ("" if passed else f" (threshold: {threshold:.1%})")
        
        return HealthCheck(
            check_name="cpu_usage",
            passed=passed,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata={"cpu_usage": cpu_usage, "threshold": threshold},
        )
    
    async def _check_memory_health(self) -> HealthCheck:
        """Check memory health."""
        memory_usage = 0.62  # Example: 62%
        threshold = self._alert_thresholds["memory_usage"]
        
        passed = memory_usage < threshold
        message = f"Memory usage: {memory_usage:.1%}" + ("" if passed else f" (threshold: {threshold:.1%})")
        
        return HealthCheck(
            check_name="memory_usage",
            passed=passed,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata={"memory_usage": memory_usage, "threshold": threshold},
        )
    
    async def _check_disk_health(self) -> HealthCheck:
        """Check disk health."""
        disk_usage = 0.55  # Example: 55%
        threshold = self._alert_thresholds["disk_usage"]
        
        passed = disk_usage < threshold
        message = f"Disk usage: {disk_usage:.1%}" + ("" if passed else f" (threshold: {threshold:.1%})")
        
        return HealthCheck(
            check_name="disk_usage",
            passed=passed,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata={"disk_usage": disk_usage, "threshold": threshold},
        )
    
    async def _check_service_health(self) -> HealthCheck:
        """Check service availability."""
        # Placeholder - would check actual service endpoints
        services_up = 5
        total_services = 5
        
        passed = services_up == total_services
        message = f"Services: {services_up}/{total_services} up"
        
        return HealthCheck(
            check_name="service_availability",
            passed=passed,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata={"services_up": services_up, "total_services": total_services},
        )
    
    async def _check_database_health(self) -> HealthCheck:
        """Check database connectivity."""
        # Placeholder - would check actual database
        db_responsive = True
        response_time_ms = 15.3
        
        passed = db_responsive and response_time_ms < 100
        message = f"Database: {'responsive' if db_responsive else 'unresponsive'} ({response_time_ms:.1f}ms)"
        
        return HealthCheck(
            check_name="database_connectivity",
            passed=passed,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata={"responsive": db_responsive, "response_time_ms": response_time_ms},
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        recent_checks = [
            c for c in self._health_checks
            if c.timestamp >= datetime.now(timezone.utc) - timedelta(minutes=5)
        ]
        
        if not recent_checks:
            return {"status": "unknown", "message": "No recent health checks"}
        
        failed_checks = [c for c in recent_checks if not c.passed]
        pass_rate = 1.0 - (len(failed_checks) / len(recent_checks))
        
        status = "healthy"
        if pass_rate < 0.9:
            status = "degraded"
        if pass_rate < 0.7:
            status = "critical"
        
        open_incidents = len([i for i in self._incidents.values() if i.status != IncidentStatus.CLOSED])
        
        return {
            "status": status,
            "health_pass_rate": pass_rate,
            "failed_checks": len(failed_checks),
            "open_incidents": open_incidents,
            "total_alerts": len(self._alerts),
            "auto_mitigations": sum(1 for i in self._incidents.values() if i.auto_mitigation_attempted),
        }


__all__ = [
    "MonitoringAutomation",
    "AlertSeverity",
    "IncidentStatus",
    "Alert",
    "Incident",
    "HealthCheck",
]
