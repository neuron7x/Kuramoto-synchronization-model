# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Progressive rollout and canary deployment management.

This module implements controlled deployment mechanisms including canary releases,
progressive rollouts, and automatic rollback on failure.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeploymentPhase(Enum):
    """Deployment phase stages."""

    VALIDATION = "validation"
    CANARY = "canary"
    PROGRESSIVE = "progressive"
    COMPLETE = "complete"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RolloutStrategy(Enum):
    """Rollout strategy types."""

    IMMEDIATE = "immediate"
    GRADUAL = "gradual"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"


@dataclass
class DeploymentConfig:
    """Configuration for a deployment."""

    version: str
    rollout_strategy: RolloutStrategy
    canary_percentage: float = 5.0
    rollout_stages: List[int] = field(default_factory=lambda: [5, 25, 50, 100])
    stage_duration_minutes: int = 10
    health_check_interval_seconds: int = 30
    rollback_on_error_rate: float = 0.05
    rollback_on_latency_ms: float = 1000.0


@dataclass
class DeploymentMetrics:
    """Metrics for a deployment."""

    timestamp: float
    version: str
    traffic_percentage: float
    request_count: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    p99_latency_ms: float
    health_check_passed: bool


@dataclass
class DeploymentState:
    """Current state of a deployment."""

    version: str
    phase: DeploymentPhase
    current_traffic_percentage: float
    start_time: float
    metrics: List[DeploymentMetrics] = field(default_factory=list)
    rollback_triggered: bool = False
    rollback_reason: Optional[str] = None


class ProgressiveRolloutManager:
    """Manager for progressive deployment rollouts."""

    def __init__(self, config: DeploymentConfig):
        """Initialize rollout manager.

        Args:
            config: Deployment configuration
        """
        self.config = config
        self.current_state: Optional[DeploymentState] = None
        self.stable_version: str = "v1.0.0"  # Default
        self.deployment_history: List[DeploymentState] = []
        self._traffic_router: Optional[Callable] = None
        self._health_checker: Optional[Callable] = None

    def register_traffic_router(self, router: Callable[[str, float], bool]) -> None:
        """Register traffic routing handler.

        Args:
            router: Function to route traffic to version with percentage
        """
        self._traffic_router = router

    def register_health_checker(self, checker: Callable[[str], bool]) -> None:
        """Register health check handler.

        Args:
            checker: Function to check health of a version
        """
        self._health_checker = checker

    def start_deployment(self, version: str) -> bool:
        """Start a new deployment.

        Args:
            version: Version to deploy

        Returns:
            True if deployment started successfully
        """
        if self.current_state and self.current_state.phase not in [
            DeploymentPhase.COMPLETE,
            DeploymentPhase.FAILED,
            DeploymentPhase.ROLLED_BACK,
        ]:
            logger.warning(f"Deployment already in progress: {self.current_state.version}")
            return False

        # Pre-deployment validation
        if not self._validate_deployment(version):
            logger.error(f"Pre-deployment validation failed for {version}")
            return False

        self.current_state = DeploymentState(
            version=version,
            phase=DeploymentPhase.CANARY,
            current_traffic_percentage=self.config.canary_percentage,
            start_time=time.time(),
        )

        # Start canary
        if self._traffic_router:
            self._traffic_router(version, self.config.canary_percentage)

        logger.info(f"Started canary deployment of {version} at {self.config.canary_percentage}%")
        return True

    def _validate_deployment(self, version: str) -> bool:
        """Validate deployment before starting.

        Args:
            version: Version to validate

        Returns:
            True if validation passed
        """
        # Check if version is valid
        if not version or version == self.stable_version:
            return False

        # Run health checks if available
        if self._health_checker:
            return self._health_checker(version)

        return True

    def record_metrics(
        self,
        version: str,
        request_count: int,
        error_count: int,
        avg_latency_ms: float,
        p99_latency_ms: float,
    ) -> None:
        """Record deployment metrics.

        Args:
            version: Deployment version
            request_count: Number of requests
            error_count: Number of errors
            avg_latency_ms: Average latency
            p99_latency_ms: 99th percentile latency
        """
        if not self.current_state or self.current_state.version != version:
            return

        error_rate = error_count / request_count if request_count > 0 else 0.0
        health_check = self._check_health(error_rate, p99_latency_ms)

        metrics = DeploymentMetrics(
            timestamp=time.time(),
            version=version,
            traffic_percentage=self.current_state.current_traffic_percentage,
            request_count=request_count,
            error_count=error_count,
            error_rate=error_rate,
            avg_latency_ms=avg_latency_ms,
            p99_latency_ms=p99_latency_ms,
            health_check_passed=health_check,
        )

        self.current_state.metrics.append(metrics)

        # Check if rollback needed
        if not health_check:
            self._trigger_rollback(
                f"Health check failed: error_rate={error_rate:.2%}, latency={p99_latency_ms:.0f}ms"
            )

    def _check_health(self, error_rate: float, latency_ms: float) -> bool:
        """Check if metrics are healthy.

        Args:
            error_rate: Current error rate
            latency_ms: Current latency

        Returns:
            True if healthy
        """
        if error_rate > self.config.rollback_on_error_rate:
            logger.warning(f"Error rate {error_rate:.2%} exceeds threshold")
            return False

        if latency_ms > self.config.rollback_on_latency_ms:
            logger.warning(f"Latency {latency_ms:.0f}ms exceeds threshold")
            return False

        return True

    def advance_rollout(self) -> bool:
        """Advance to next rollout stage.

        Returns:
            True if advanced successfully
        """
        if not self.current_state:
            return False

        if self.current_state.phase == DeploymentPhase.COMPLETE:
            return False

        if self.current_state.rollback_triggered:
            return False

        # Check if enough time has passed
        elapsed = time.time() - self.current_state.start_time
        stage_duration = self.config.stage_duration_minutes * 60

        if elapsed < stage_duration:
            logger.info("Not enough time elapsed for stage, waiting...")
            return False

        # Find next stage
        current_pct = self.current_state.current_traffic_percentage
        next_stage = None

        for stage in self.config.rollout_stages:
            if stage > current_pct:
                next_stage = stage
                break

        if next_stage is None:
            # Already at final stage
            self._complete_deployment()
            return True

        # Advance to next stage
        self.current_state.current_traffic_percentage = next_stage
        self.current_state.phase = DeploymentPhase.PROGRESSIVE

        if self._traffic_router:
            self._traffic_router(self.current_state.version, next_stage)

        logger.info(f"Advanced rollout to {next_stage}%")
        return True

    def _complete_deployment(self) -> None:
        """Complete the deployment."""
        if not self.current_state:
            return

        self.current_state.phase = DeploymentPhase.COMPLETE
        self.stable_version = self.current_state.version

        self.deployment_history.append(self.current_state)

        logger.info(f"Deployment of {self.current_state.version} completed successfully")

    def _trigger_rollback(self, reason: str) -> bool:
        """Trigger automatic rollback.

        Args:
            reason: Reason for rollback

        Returns:
            True if rollback initiated
        """
        if not self.current_state:
            return False

        if self.current_state.rollback_triggered:
            return False

        self.current_state.rollback_triggered = True
        self.current_state.rollback_reason = reason
        self.current_state.phase = DeploymentPhase.ROLLED_BACK

        # Route traffic back to stable version
        if self._traffic_router:
            self._traffic_router(self.stable_version, 100.0)

        self.deployment_history.append(self.current_state)

        logger.error(f"Rolled back deployment: {reason}")
        return True

    def manual_rollback(self, reason: str = "Manual intervention") -> bool:
        """Manually trigger rollback.

        Args:
            reason: Reason for rollback

        Returns:
            True if rollback successful
        """
        return self._trigger_rollback(reason)

    def get_deployment_status(self) -> Dict:
        """Get current deployment status.

        Returns:
            Dictionary with deployment status
        """
        if not self.current_state:
            return {"status": "no_deployment", "stable_version": self.stable_version}

        recent_metrics = self.current_state.metrics[-10:] if self.current_state.metrics else []

        return {
            "version": self.current_state.version,
            "phase": self.current_state.phase.value,
            "traffic_percentage": self.current_state.current_traffic_percentage,
            "elapsed_seconds": time.time() - self.current_state.start_time,
            "rollback_triggered": self.current_state.rollback_triggered,
            "rollback_reason": self.current_state.rollback_reason,
            "metrics_count": len(self.current_state.metrics),
            "recent_metrics": [
                {
                    "error_rate": m.error_rate,
                    "latency_ms": m.p99_latency_ms,
                    "health": m.health_check_passed,
                }
                for m in recent_metrics
            ],
        }

    def get_deployment_history(self, limit: int = 10) -> List[Dict]:
        """Get deployment history.

        Args:
            limit: Maximum number of deployments to return

        Returns:
            List of deployment summaries
        """
        return [
            {
                "version": d.version,
                "phase": d.phase.value,
                "final_traffic": d.current_traffic_percentage,
                "duration_seconds": time.time() - d.start_time,
                "rollback_triggered": d.rollback_triggered,
                "rollback_reason": d.rollback_reason,
            }
            for d in self.deployment_history[-limit:]
        ]


class CanaryValidator:
    """Validator for canary deployments."""

    def __init__(
        self,
        baseline_error_rate: float = 0.01,
        baseline_latency_ms: float = 100.0,
        threshold_multiplier: float = 2.0,
    ):
        """Initialize canary validator.

        Args:
            baseline_error_rate: Expected baseline error rate
            baseline_latency_ms: Expected baseline latency
            threshold_multiplier: Multiplier for acceptable deviation
        """
        self.baseline_error_rate = baseline_error_rate
        self.baseline_latency_ms = baseline_latency_ms
        self.threshold_multiplier = threshold_multiplier

    def validate(
        self,
        canary_error_rate: float,
        canary_latency_ms: float,
        stable_error_rate: float,
        stable_latency_ms: float,
    ) -> tuple[bool, List[str]]:
        """Validate canary against stable version.

        Args:
            canary_error_rate: Canary error rate
            canary_latency_ms: Canary latency
            stable_error_rate: Stable version error rate
            stable_latency_ms: Stable version latency

        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues = []

        # Compare error rates
        if canary_error_rate > stable_error_rate * self.threshold_multiplier:
            issues.append(
                f"Error rate {canary_error_rate:.2%} exceeds stable "
                f"{stable_error_rate:.2%} by {self.threshold_multiplier}x"
            )

        # Compare latencies
        if canary_latency_ms > stable_latency_ms * self.threshold_multiplier:
            issues.append(
                f"Latency {canary_latency_ms:.0f}ms exceeds stable "
                f"{stable_latency_ms:.0f}ms by {self.threshold_multiplier}x"
            )

        return len(issues) == 0, issues
