# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Automation Orchestrator

Central orchestration system that coordinates all 7 critical automation components:
1. Configuration Management
2. Data Pipeline
3. Strategy Scheduling
4. Monitoring & Observability
5. Security & Compliance
6. Infrastructure & Deployment
7. Testing & Quality Assurance

This orchestrator ensures autonomous operation across all systems.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .config_automation import ConfigAutomation
from .data_pipeline_automation import DataPipelineAutomation
from .infrastructure_automation import InfrastructureAutomation
from .monitoring_automation import MonitoringAutomation
from .security_automation import SecurityAutomation
from .strategy_automation import StrategyAutomation
from .testing_automation import TestingAutomation

logger = logging.getLogger(__name__)


class SystemComponent(str, Enum):
    """System component identifiers."""
    CONFIG = "config"
    DATA_PIPELINE = "data_pipeline"
    STRATEGY = "strategy"
    MONITORING = "monitoring"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    TESTING = "testing"


@dataclass
class SystemHealth:
    """Overall system health status."""
    
    overall_status: str  # 'healthy', 'degraded', 'critical'
    component_statuses: Dict[str, Dict[str, Any]]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_healthy(self) -> bool:
        """Check if system is in healthy state."""
        return self.overall_status == "healthy"
    
    @property
    def critical_components(self) -> List[str]:
        """Get list of components in critical state."""
        return [
            comp for comp, status in self.component_statuses.items()
            if status.get("status") == "critical"
        ]


@dataclass
class OrchestrationCycle:
    """Record of an orchestration cycle."""
    
    cycle_number: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    health_status: Optional[SystemHealth] = None


class AutomationOrchestrator:
    """
    Central orchestrator for all automation systems.
    
    Coordinates autonomous operations across:
    - Configuration management
    - Data pipeline quality
    - Strategy execution
    - Monitoring and observability
    - Security and compliance
    - Infrastructure scaling
    - Testing and QA
    """
    
    def __init__(
        self,
        orchestration_interval_seconds: int = 60,
        enable_auto_recovery: bool = True,
    ):
        """
        Initialize automation orchestrator.
        
        Args:
            orchestration_interval_seconds: Seconds between orchestration cycles
            enable_auto_recovery: Enable automatic recovery actions
        """
        self.orchestration_interval = timedelta(seconds=orchestration_interval_seconds)
        self.enable_auto_recovery = enable_auto_recovery
        
        # Initialize all automation components
        self.config_automation = ConfigAutomation()
        self.data_pipeline_automation = DataPipelineAutomation()
        self.strategy_automation = StrategyAutomation()
        self.monitoring_automation = MonitoringAutomation()
        self.security_automation = SecurityAutomation()
        self.infrastructure_automation = InfrastructureAutomation()
        self.testing_automation = TestingAutomation()
        
        self._orchestration_history: List[OrchestrationCycle] = []
        self._cycle_number = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the autonomous orchestration loop."""
        if self._running:
            logger.warning("Orchestrator is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._orchestration_loop())
        
        logger.info("Automation Orchestrator started")
    
    async def stop(self) -> None:
        """Stop the orchestration loop."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Automation Orchestrator stopped")
    
    async def _orchestration_loop(self) -> None:
        """Main orchestration loop."""
        while self._running:
            try:
                await self.run_orchestration_cycle()
                await asyncio.sleep(self.orchestration_interval.total_seconds())
            except Exception as e:
                logger.error(f"Orchestration cycle error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Brief pause before retry
    
    async def run_orchestration_cycle(self) -> OrchestrationCycle:
        """
        Run a complete orchestration cycle.
        
        Returns:
            Orchestration cycle record
        """
        self._cycle_number += 1
        cycle = OrchestrationCycle(
            cycle_number=self._cycle_number,
            started_at=datetime.now(timezone.utc),
        )
        
        logger.info(f"Starting orchestration cycle #{cycle.cycle_number}")
        
        try:
            # Phase 1: Configuration validation and healing
            await self._orchestrate_config(cycle)
            
            # Phase 2: Data pipeline health and DLQ processing
            await self._orchestrate_data_pipeline(cycle)
            
            # Phase 3: Strategy execution and rebalancing
            await self._orchestrate_strategies(cycle)
            
            # Phase 4: Monitoring and incident response
            await self._orchestrate_monitoring(cycle)
            
            # Phase 5: Security scanning and compliance
            await self._orchestrate_security(cycle)
            
            # Phase 6: Infrastructure scaling and healing
            await self._orchestrate_infrastructure(cycle)
            
            # Phase 7: Testing and quality assurance
            await self._orchestrate_testing(cycle)
            
            # Phase 8: System health assessment
            cycle.health_status = await self._assess_system_health()
            
            # Phase 9: Auto-recovery if needed
            if self.enable_auto_recovery and cycle.health_status:
                await self._apply_auto_recovery(cycle.health_status, cycle)
            
        except Exception as e:
            error_msg = f"Orchestration cycle failed: {e}"
            cycle.errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
        
        cycle.completed_at = datetime.now(timezone.utc)
        self._orchestration_history.append(cycle)
        
        # Log cycle summary
        duration = (cycle.completed_at - cycle.started_at).total_seconds()
        logger.info(
            f"Orchestration cycle #{cycle.cycle_number} completed in {duration:.2f}s, "
            f"{len(cycle.actions_taken)} actions, {len(cycle.errors)} errors"
        )
        
        return cycle
    
    async def _orchestrate_config(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate configuration management."""
        logger.debug("Orchestrating configuration management")
        
        # Validate all configs
        report = self.config_automation.validate_all_configs()
        
        if report.auto_fixes_applied > 0:
            cycle.actions_taken.append(
                f"Config: Applied {report.auto_fixes_applied} auto-fixes"
            )
        
        # Check for drift
        drift = self.config_automation.detect_config_drift()
        
        if drift:
            cycle.actions_taken.append(f"Config: Detected {len(drift)} drift issues")
    
    async def _orchestrate_data_pipeline(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate data pipeline."""
        logger.debug("Orchestrating data pipeline")
        
        # Process dead letter queue
        recovered = await self.data_pipeline_automation.process_dlq()
        
        if recovered > 0:
            cycle.actions_taken.append(f"Data: Recovered {recovered} records from DLQ")
    
    async def _orchestrate_strategies(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate strategy execution."""
        logger.debug("Orchestrating strategies")
        
        # Check all registered strategies
        for strategy_id in list(self.strategy_automation._strategies.keys()):
            try:
                # Execute strategy if due
                result = await self.strategy_automation.execute_strategy(strategy_id)
                
                if result is not None:
                    cycle.actions_taken.append(f"Strategy: Executed {strategy_id}")
                    
            except Exception as e:
                cycle.errors.append(f"Strategy {strategy_id} failed: {e}")
    
    async def _orchestrate_monitoring(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate monitoring and observability."""
        logger.debug("Orchestrating monitoring")
        
        # Run health checks
        health_checks = await self.monitoring_automation.run_health_checks()
        
        failed_checks = [hc for hc in health_checks if not hc.passed]
        
        if failed_checks:
            cycle.actions_taken.append(
                f"Monitoring: {len(failed_checks)} failed health checks"
            )
    
    async def _orchestrate_security(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate security and compliance."""
        logger.debug("Orchestrating security")
        
        # Check for expiring secrets
        expiring = await self.security_automation.check_secret_expiration()
        
        if expiring:
            cycle.actions_taken.append(f"Security: Rotated {len(expiring)} secrets")
        
        # Run security scan (less frequently)
        if cycle.cycle_number % 10 == 0:  # Every 10 cycles
            vulns = await self.security_automation.run_security_scan()
            if vulns:
                cycle.actions_taken.append(
                    f"Security: Detected {len(vulns)} vulnerabilities"
                )
        
        # Run compliance checks
        if cycle.cycle_number % 5 == 0:  # Every 5 cycles
            compliance = await self.security_automation.run_compliance_checks()
            failed = [c for c in compliance if not c.passed]
            if failed:
                cycle.actions_taken.append(
                    f"Security: {len(failed)} compliance checks failed"
                )
    
    async def _orchestrate_infrastructure(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate infrastructure management."""
        logger.debug("Orchestrating infrastructure")
        
        # Check and scale services
        for service_id in list(self.infrastructure_automation._services.keys()):
            try:
                # Check service health
                is_healthy = await self.infrastructure_automation.check_service_health(
                    service_id
                )
                
                if not is_healthy:
                    cycle.actions_taken.append(
                        f"Infrastructure: Healed service {service_id}"
                    )
                
                # Check scaling
                scaling_event = await self.infrastructure_automation.check_and_scale(
                    service_id
                )
                
                if scaling_event:
                    cycle.actions_taken.append(
                        f"Infrastructure: Scaled {service_id} "
                        f"{scaling_event.direction.value}"
                    )
                    
            except Exception as e:
                cycle.errors.append(f"Infrastructure {service_id} error: {e}")
    
    async def _orchestrate_testing(self, cycle: OrchestrationCycle) -> None:
        """Orchestrate testing and QA."""
        logger.debug("Orchestrating testing")
        
        # Run critical tests periodically
        if cycle.cycle_number % 15 == 0:  # Every 15 cycles
            results = await self.testing_automation.run_tests()
            
            failed = [r for r in results if r.status.value == "failed"]
            
            if failed:
                cycle.actions_taken.append(f"Testing: {len(failed)} tests failed")
            else:
                cycle.actions_taken.append(f"Testing: All {len(results)} tests passed")
    
    async def _assess_system_health(self) -> SystemHealth:
        """Assess overall system health across all components."""
        component_statuses = {
            SystemComponent.CONFIG.value: self.config_automation.get_health_status(),
            SystemComponent.DATA_PIPELINE.value: self.data_pipeline_automation.get_health_status(),
            SystemComponent.STRATEGY.value: self.strategy_automation.get_health_status(),
            SystemComponent.MONITORING.value: self.monitoring_automation.get_health_status(),
            SystemComponent.SECURITY.value: self.security_automation.get_health_status(),
            SystemComponent.INFRASTRUCTURE.value: self.infrastructure_automation.get_health_status(),
            SystemComponent.TESTING.value: self.testing_automation.get_health_status(),
        }
        
        # Determine overall status
        critical_count = sum(
            1 for status in component_statuses.values()
            if status.get("status") == "critical"
        )
        
        degraded_count = sum(
            1 for status in component_statuses.values()
            if status.get("status") == "degraded"
        )
        
        if critical_count > 0:
            overall_status = "critical"
        elif degraded_count > 2:
            overall_status = "degraded"
        elif degraded_count > 0:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        return SystemHealth(
            overall_status=overall_status,
            component_statuses=component_statuses,
        )
    
    async def _apply_auto_recovery(
        self,
        health: SystemHealth,
        cycle: OrchestrationCycle,
    ) -> None:
        """Apply automated recovery actions based on health status."""
        if health.is_healthy:
            return
        
        logger.warning(f"System health: {health.overall_status}, applying auto-recovery")
        
        for component in health.critical_components:
            try:
                action = await self._recover_component(component)
                if action:
                    cycle.actions_taken.append(f"Recovery: {component} - {action}")
            except Exception as e:
                cycle.errors.append(f"Recovery failed for {component}: {e}")
    
    async def _recover_component(self, component: str) -> Optional[str]:
        """Apply recovery actions for a specific component."""
        if component == SystemComponent.DATA_PIPELINE.value:
            # Force DLQ processing
            await self.data_pipeline_automation.process_dlq()
            return "Processed DLQ"
        
        elif component == SystemComponent.SECURITY.value:
            # Run emergency security scan
            await self.security_automation.run_security_scan()
            return "Emergency security scan"
        
        elif component == SystemComponent.INFRASTRUCTURE.value:
            # Scale up all services
            for service_id in self.infrastructure_automation._services:
                await self.infrastructure_automation.check_and_scale(service_id)
            return "Scaled infrastructure"
        
        return None
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get orchestrator status and statistics."""
        recent_cycles = self._orchestration_history[-10:]
        
        avg_duration = 0.0
        if recent_cycles:
            durations = [
                (c.completed_at - c.started_at).total_seconds()
                for c in recent_cycles
                if c.completed_at
            ]
            avg_duration = sum(durations) / len(durations) if durations else 0.0
        
        total_actions = sum(len(c.actions_taken) for c in recent_cycles)
        total_errors = sum(len(c.errors) for c in recent_cycles)
        
        return {
            "running": self._running,
            "cycle_number": self._cycle_number,
            "total_cycles": len(self._orchestration_history),
            "recent_avg_duration_seconds": avg_duration,
            "recent_actions": total_actions,
            "recent_errors": total_errors,
            "auto_recovery_enabled": self.enable_auto_recovery,
        }
    
    async def get_system_health(self) -> SystemHealth:
        """Get current system health across all components."""
        return await self._assess_system_health()


__all__ = [
    "AutomationOrchestrator",
    "SystemComponent",
    "SystemHealth",
    "OrchestrationCycle",
]
