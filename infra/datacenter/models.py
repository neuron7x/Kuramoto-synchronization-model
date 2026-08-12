# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data center models and configuration.

Defines the core data structures for representing data centers, their
configuration, health status, and failover policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Sequence


class DataCenterRegion(str, Enum):
    """Geographic regions for data center placement."""

    US_EAST = "us-east"
    US_WEST = "us-west"
    EU_WEST = "eu-west"
    EU_CENTRAL = "eu-central"
    APAC_NORTHEAST = "apac-northeast"
    APAC_SOUTHEAST = "apac-southeast"
    SA_EAST = "sa-east"


class DataCenterStatus(str, Enum):
    """Operational status of a data center."""

    ACTIVE = "active"
    STANDBY = "standby"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    FAILOVER = "failover"


class FailoverPolicy(str, Enum):
    """Failover policy strategies."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    SEMI_AUTOMATIC = "semi_automatic"


@dataclass(frozen=True)
class AvailabilityZone:
    """Represents an availability zone within a data center region.

    Attributes:
        name: Zone identifier (e.g., "us-east-1a")
        region: Parent region
        is_primary: Whether this is the primary zone for the region
    """

    name: str
    region: DataCenterRegion
    is_primary: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Availability zone name cannot be empty")


@dataclass
class DataCenterHealth:
    """Health metrics for a data center.

    Attributes:
        latency_ms: Current average latency in milliseconds
        packet_loss_rate: Packet loss rate (0.0 to 1.0)
        cpu_utilization: CPU utilization percentage (0.0 to 100.0)
        memory_utilization: Memory utilization percentage (0.0 to 100.0)
        disk_utilization: Disk utilization percentage (0.0 to 100.0)
        active_connections: Number of active connections
        error_rate: Request error rate (0.0 to 1.0)
        last_check: Timestamp of last health check
        is_healthy: Overall health status
    """

    latency_ms: float = 0.0
    packet_loss_rate: float = 0.0
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    disk_utilization: float = 0.0
    active_connections: int = 0
    error_rate: float = 0.0
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_healthy: bool = True

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative")
        if not 0.0 <= self.packet_loss_rate <= 1.0:
            raise ValueError("Packet loss rate must be between 0 and 1")
        if not 0.0 <= self.error_rate <= 1.0:
            raise ValueError("Error rate must be between 0 and 1")

    def calculate_health_score(self) -> float:
        """Calculate an overall health score from 0 to 100.

        Returns:
            Health score where 100 is perfect health
        """
        score = 100.0

        # Latency impact (up to -30 points)
        if self.latency_ms > 100:
            score -= min(30.0, (self.latency_ms - 100) / 10)

        # Packet loss impact (up to -20 points)
        score -= self.packet_loss_rate * 20

        # Resource utilization impact (up to -20 points)
        # Use max utilization to ensure high usage in any resource is penalized
        max_utilization = max(self.cpu_utilization, self.memory_utilization, self.disk_utilization)
        if max_utilization > 70:
            score -= min(20.0, (max_utilization - 70) / 1.0)

        # Error rate impact (up to -30 points)
        score -= self.error_rate * 30

        return max(0.0, score)


@dataclass
class ReplicationConfig:
    """Configuration for data replication between data centers.

    Attributes:
        target_dc_id: ID of the target data center
        mode: Replication mode ("sync" or "async")
        lag_threshold_ms: Maximum acceptable replication lag
        enabled: Whether replication is enabled
    """

    target_dc_id: str
    mode: str = "async"
    lag_threshold_ms: float = 1000.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.mode not in ("sync", "async"):
            raise ValueError("Replication mode must be 'sync' or 'async'")
        if self.lag_threshold_ms < 0:
            raise ValueError("Lag threshold cannot be negative")


@dataclass
class DataCenterConfig:
    """Configuration for a data center.

    Attributes:
        id: Unique identifier for the data center
        name: Human-readable name
        region: Geographic region
        availability_zones: List of availability zones
        is_primary: Whether this is the primary data center
        failover_policy: Policy for handling failovers
        replication_configs: Replication configurations to other DCs
        max_connections: Maximum allowed connections
        health_check_interval_seconds: Interval between health checks
        failover_threshold_score: Health score below which failover is triggered
    """

    id: str
    name: str
    region: DataCenterRegion
    availability_zones: Sequence[AvailabilityZone] = field(default_factory=list)
    is_primary: bool = False
    failover_policy: FailoverPolicy = FailoverPolicy.AUTOMATIC
    replication_configs: Sequence[ReplicationConfig] = field(default_factory=list)
    max_connections: int = 10000
    health_check_interval_seconds: int = 30
    failover_threshold_score: float = 50.0

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Data center ID cannot be empty")
        if not self.name:
            raise ValueError("Data center name cannot be empty")
        if self.max_connections < 1:
            raise ValueError("Max connections must be at least 1")
        if self.health_check_interval_seconds < 1:
            raise ValueError("Health check interval must be at least 1 second")
        if not 0.0 <= self.failover_threshold_score <= 100.0:
            raise ValueError("Failover threshold score must be between 0 and 100")

    def with_primary_status(self, is_primary: bool) -> "DataCenterConfig":
        """Create a new config with updated primary status.

        Args:
            is_primary: New primary status

        Returns:
            New DataCenterConfig with updated is_primary field
        """
        return DataCenterConfig(
            id=self.id,
            name=self.name,
            region=self.region,
            availability_zones=self.availability_zones,
            is_primary=is_primary,
            failover_policy=self.failover_policy,
            replication_configs=self.replication_configs,
            max_connections=self.max_connections,
            health_check_interval_seconds=self.health_check_interval_seconds,
            failover_threshold_score=self.failover_threshold_score,
        )


@dataclass
class DataCenter:
    """Represents a complete data center instance.

    Combines configuration with runtime state including health metrics
    and operational status.

    Attributes:
        config: Data center configuration
        status: Current operational status
        health: Current health metrics
        created_at: When the DC was registered
        last_failover_at: Timestamp of last failover event
        failover_count: Total number of failovers
    """

    config: DataCenterConfig
    status: DataCenterStatus = DataCenterStatus.STANDBY
    health: DataCenterHealth = field(default_factory=DataCenterHealth)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_failover_at: Optional[datetime] = None
    failover_count: int = 0

    @property
    def id(self) -> str:
        """Return the data center ID."""
        return self.config.id

    @property
    def name(self) -> str:
        """Return the data center name."""
        return self.config.name

    @property
    def region(self) -> DataCenterRegion:
        """Return the data center region."""
        return self.config.region

    @property
    def is_primary(self) -> bool:
        """Return whether this is the primary data center."""
        return self.config.is_primary

    @property
    def is_available(self) -> bool:
        """Check if the data center is available for traffic."""
        return self.status in (DataCenterStatus.ACTIVE, DataCenterStatus.DEGRADED)

    def get_health_score(self) -> float:
        """Get the current health score."""
        return self.health.calculate_health_score()

    def should_failover(self) -> bool:
        """Determine if failover should be triggered.

        Returns:
            True if health score is below threshold
        """
        return self.get_health_score() < self.config.failover_threshold_score

    def to_dict(self) -> Dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with data center information
        """
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region.value,
            "status": self.status.value,
            "is_primary": self.is_primary,
            "health_score": self.get_health_score(),
            "is_healthy": self.health.is_healthy,
            "latency_ms": self.health.latency_ms,
            "error_rate": self.health.error_rate,
            "failover_count": self.failover_count,
            "availability_zones": [az.name for az in self.config.availability_zones],
        }


def create_default_availability_zones(
    region: DataCenterRegion,
) -> List[AvailabilityZone]:
    """Create default availability zones for a region.

    Args:
        region: The region to create zones for

    Returns:
        List of availability zones
    """
    region_prefixes = {
        DataCenterRegion.US_EAST: "us-east-1",
        DataCenterRegion.US_WEST: "us-west-2",
        DataCenterRegion.EU_WEST: "eu-west-1",
        DataCenterRegion.EU_CENTRAL: "eu-central-1",
        DataCenterRegion.APAC_NORTHEAST: "ap-northeast-1",
        DataCenterRegion.APAC_SOUTHEAST: "ap-southeast-1",
        DataCenterRegion.SA_EAST: "sa-east-1",
    }

    prefix = region_prefixes.get(region, region.value)
    zones = []

    for i, suffix in enumerate(["a", "b", "c"]):
        zones.append(
            AvailabilityZone(
                name=f"{prefix}{suffix}",
                region=region,
                is_primary=(i == 0),
            )
        )

    return zones
