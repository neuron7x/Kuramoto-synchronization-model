# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Infrastructure & Deployment Automation

Autonomous infrastructure that:
- Auto-scaling based on load and predictions
- Self-healing services with automatic restart
- Automated rollback on deployment failures
- Resource optimization and cost management
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Service status states."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RESTARTING = "restarting"
    FAILED = "failed"


class ScalingDirection(str, Enum):
    """Scaling direction."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class Service:
    """Represents a service instance."""
    
    service_id: str
    name: str
    status: ServiceStatus
    instances: int
    cpu_usage: float
    memory_usage: float
    request_rate: float
    error_rate: float
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ScalingEvent:
    """Represents a scaling event."""
    
    service_id: str
    direction: ScalingDirection
    old_instances: int
    new_instances: int
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DeploymentEvent:
    """Represents a deployment event."""
    
    deployment_id: str
    service_id: str
    version: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    rolled_back: bool = False


class InfrastructureAutomation:
    """
    Autonomous infrastructure management system.
    
    Features:
    1. Predictive auto-scaling
    2. Self-healing services
    3. Automatic deployment rollback
    4. Resource optimization
    """
    
    def __init__(
        self,
        min_instances: int = 2,
        max_instances: int = 20,
        target_cpu_utilization: float = 0.70,
        scale_up_threshold: float = 0.80,
        scale_down_threshold: float = 0.40,
        enable_auto_healing: bool = True,
    ):
        """
        Initialize infrastructure automation.
        
        Args:
            min_instances: Minimum service instances
            max_instances: Maximum service instances
            target_cpu_utilization: Target CPU utilization
            scale_up_threshold: CPU threshold for scaling up
            scale_down_threshold: CPU threshold for scaling down
            enable_auto_healing: Enable automatic service healing
        """
        self.min_instances = min_instances
        self.max_instances = max_instances
        self.target_cpu_utilization = target_cpu_utilization
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.enable_auto_healing = enable_auto_healing
        
        self._services: Dict[str, Service] = {}
        self._scaling_history: List[ScalingEvent] = []
        self._deployment_history: List[DeploymentEvent] = []
        self._healing_count: int = 0
        
    def register_service(
        self,
        service_id: str,
        name: str,
        initial_instances: int = 2,
    ) -> Service:
        """Register a service for autonomous management."""
        service = Service(
            service_id=service_id,
            name=name,
            status=ServiceStatus.HEALTHY,
            instances=initial_instances,
            cpu_usage=0.0,
            memory_usage=0.0,
            request_rate=0.0,
            error_rate=0.0,
        )
        
        self._services[service_id] = service
        logger.info(f"Registered service: {name} with {initial_instances} instances")
        
        return service
    
    async def check_and_scale(self, service_id: str) -> Optional[ScalingEvent]:
        """
        Check service metrics and scale if needed.
        
        Args:
            service_id: Service to check
            
        Returns:
            Scaling event if scaling occurred, None otherwise
        """
        if service_id not in self._services:
            logger.error(f"Service not found: {service_id}")
            return None
        
        service = self._services[service_id]
        
        # Update metrics (in production, fetch from monitoring system)
        await self._update_service_metrics(service)
        
        # Determine scaling direction
        scaling_direction = self._determine_scaling_direction(service)
        
        if scaling_direction == ScalingDirection.STABLE:
            return None
        
        # Calculate new instance count
        new_instances = self._calculate_target_instances(service, scaling_direction)
        
        if new_instances == service.instances:
            return None
        
        # Perform scaling
        scaling_event = await self._scale_service(
            service,
            new_instances,
            scaling_direction,
        )
        
        return scaling_event
    
    async def _update_service_metrics(self, service: Service) -> None:
        """Update service metrics."""
        # Placeholder - would fetch from actual monitoring
        # For now, simulate varying metrics
        import random
        service.cpu_usage = max(0.1, min(0.95, service.cpu_usage + random.uniform(-0.1, 0.1)))
        service.memory_usage = max(0.1, min(0.9, service.memory_usage + random.uniform(-0.05, 0.05)))
        service.request_rate = max(0, service.request_rate + random.uniform(-100, 150))
        service.error_rate = max(0, min(0.1, service.error_rate + random.uniform(-0.01, 0.01)))
        service.last_check = datetime.now(timezone.utc)
    
    def _determine_scaling_direction(self, service: Service) -> ScalingDirection:
        """Determine if scaling is needed."""
        # Scale up conditions
        if service.cpu_usage > self.scale_up_threshold:
            return ScalingDirection.UP
        if service.error_rate > 0.05:  # High error rate
            return ScalingDirection.UP
        if service.instances < self.min_instances:
            return ScalingDirection.UP
        
        # Scale down conditions
        if service.cpu_usage < self.scale_down_threshold and service.instances > self.min_instances:
            return ScalingDirection.DOWN
        
        return ScalingDirection.STABLE
    
    def _calculate_target_instances(
        self,
        service: Service,
        direction: ScalingDirection,
    ) -> int:
        """Calculate target instance count."""
        if direction == ScalingDirection.UP:
            # Scale up by 50% or add at least 1 instance
            new_instances = max(
                service.instances + 1,
                int(service.instances * 1.5),
            )
        else:  # DOWN
            # Scale down by 25% or remove at least 1 instance
            new_instances = min(
                service.instances - 1,
                int(service.instances * 0.75),
            )
        
        # Enforce limits
        return max(self.min_instances, min(self.max_instances, new_instances))
    
    async def _scale_service(
        self,
        service: Service,
        new_instances: int,
        direction: ScalingDirection,
    ) -> ScalingEvent:
        """Perform service scaling."""
        old_instances = service.instances
        
        # Determine reason
        if service.cpu_usage > self.scale_up_threshold:
            reason = f"High CPU usage: {service.cpu_usage:.1%}"
        elif service.error_rate > 0.05:
            reason = f"High error rate: {service.error_rate:.1%}"
        elif service.cpu_usage < self.scale_down_threshold:
            reason = f"Low CPU usage: {service.cpu_usage:.1%}"
        else:
            reason = "Predictive scaling"
        
        # Create scaling event
        scaling_event = ScalingEvent(
            service_id=service.service_id,
            direction=direction,
            old_instances=old_instances,
            new_instances=new_instances,
            reason=reason,
        )
        
        # Simulate scaling operation
        await asyncio.sleep(0.5)  # Simulate scaling delay
        
        service.instances = new_instances
        self._scaling_history.append(scaling_event)
        
        logger.info(
            f"Scaled {service.name} {direction.value}: "
            f"{old_instances} -> {new_instances} ({reason})"
        )
        
        return scaling_event
    
    async def check_service_health(self, service_id: str) -> bool:
        """
        Check service health and apply self-healing if needed.
        
        Args:
            service_id: Service to check
            
        Returns:
            True if service is healthy or was healed, False otherwise
        """
        if service_id not in self._services:
            return False
        
        service = self._services[service_id]
        
        # Update status based on metrics
        service.status = self._assess_service_health(service)
        
        # Apply self-healing if unhealthy
        if service.status in (ServiceStatus.UNHEALTHY, ServiceStatus.FAILED):
            if self.enable_auto_healing:
                await self._heal_service(service)
                return service.status == ServiceStatus.HEALTHY
            return False
        
        return service.status in (ServiceStatus.HEALTHY, ServiceStatus.DEGRADED)
    
    def _assess_service_health(self, service: Service) -> ServiceStatus:
        """Assess service health based on metrics."""
        if service.error_rate > 0.5:
            return ServiceStatus.FAILED
        if service.error_rate > 0.2 or service.cpu_usage > 0.95:
            return ServiceStatus.UNHEALTHY
        if service.error_rate > 0.05 or service.cpu_usage > 0.85:
            return ServiceStatus.DEGRADED
        return ServiceStatus.HEALTHY
    
    async def _heal_service(self, service: Service) -> None:
        """Apply self-healing to unhealthy service."""
        logger.warning(f"Healing unhealthy service: {service.name}")
        
        service.status = ServiceStatus.RESTARTING
        
        # Simulate restart
        await asyncio.sleep(1.0)
        
        # Reset metrics after restart
        service.cpu_usage = 0.3
        service.memory_usage = 0.4
        service.error_rate = 0.0
        service.status = ServiceStatus.HEALTHY
        
        self._healing_count += 1
        
        logger.info(f"Successfully healed service: {service.name}")
    
    async def deploy_with_rollback(
        self,
        service_id: str,
        version: str,
        health_check_attempts: int = 3,
    ) -> DeploymentEvent:
        """
        Deploy service with automatic rollback on failure.
        
        Args:
            service_id: Service to deploy
            version: Version to deploy
            health_check_attempts: Number of health checks before rollback
            
        Returns:
            Deployment event
        """
        if service_id not in self._services:
            raise ValueError(f"Service not found: {service_id}")
        
        service = self._services[service_id]
        deployment_id = f"deploy-{service_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        deployment = DeploymentEvent(
            deployment_id=deployment_id,
            service_id=service_id,
            version=version,
            started_at=datetime.now(timezone.utc),
        )
        
        logger.info(f"Starting deployment: {service.name} v{version}")
        
        try:
            # Simulate deployment
            await asyncio.sleep(2.0)
            
            # Health checks
            for attempt in range(health_check_attempts):
                await asyncio.sleep(1.0)
                
                # Update metrics
                await self._update_service_metrics(service)
                
                # Check health
                is_healthy = await self.check_service_health(service_id)
                
                if not is_healthy:
                    logger.error(f"Deployment health check failed (attempt {attempt + 1}/{health_check_attempts})")
                    
                    if attempt == health_check_attempts - 1:
                        # Rollback
                        await self._rollback_deployment(service, deployment)
                        deployment.rolled_back = True
                        deployment.success = False
                        break
                else:
                    logger.info(f"Deployment health check passed (attempt {attempt + 1}/{health_check_attempts})")
                    if attempt == health_check_attempts - 1:
                        deployment.success = True
            
            deployment.completed_at = datetime.now(timezone.utc)
            self._deployment_history.append(deployment)
            
            return deployment
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            await self._rollback_deployment(service, deployment)
            deployment.rolled_back = True
            deployment.success = False
            deployment.completed_at = datetime.now(timezone.utc)
            self._deployment_history.append(deployment)
            return deployment
    
    async def _rollback_deployment(
        self,
        service: Service,
        deployment: DeploymentEvent,
    ) -> None:
        """Rollback a failed deployment."""
        logger.warning(f"Rolling back deployment: {deployment.deployment_id}")
        
        # Simulate rollback
        await asyncio.sleep(1.0)
        
        # Restore service health
        service.status = ServiceStatus.HEALTHY
        service.error_rate = 0.01
        
        logger.info(f"Rollback completed for: {service.name}")
    
    def get_infrastructure_stats(self) -> Dict[str, Any]:
        """Get infrastructure statistics."""
        total_instances = sum(s.instances for s in self._services.values())
        avg_cpu = sum(s.cpu_usage for s in self._services.values()) / len(self._services) if self._services else 0
        avg_memory = sum(s.memory_usage for s in self._services.values()) / len(self._services) if self._services else 0
        
        successful_deployments = sum(1 for d in self._deployment_history if d.success)
        rollbacks = sum(1 for d in self._deployment_history if d.rolled_back)
        
        return {
            "total_services": len(self._services),
            "total_instances": total_instances,
            "avg_cpu_usage": avg_cpu,
            "avg_memory_usage": avg_memory,
            "scaling_events": len(self._scaling_history),
            "healing_events": self._healing_count,
            "deployments": len(self._deployment_history),
            "successful_deployments": successful_deployments,
            "rollbacks": rollbacks,
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get infrastructure health status."""
        if not self._services:
            return {"status": "unknown", "message": "No services registered"}
        
        healthy_services = sum(
            1 for s in self._services.values()
            if s.status == ServiceStatus.HEALTHY
        )
        
        health_rate = healthy_services / len(self._services)
        
        status = "healthy"
        if health_rate < 0.9:
            status = "degraded"
        if health_rate < 0.7:
            status = "critical"
        
        return {
            "status": status,
            "healthy_services": healthy_services,
            "total_services": len(self._services),
            "health_rate": health_rate,
            "auto_healing_enabled": self.enable_auto_healing,
            "healing_count": self._healing_count,
        }


__all__ = [
    "InfrastructureAutomation",
    "ServiceStatus",
    "ScalingDirection",
    "Service",
    "ScalingEvent",
    "DeploymentEvent",
]
