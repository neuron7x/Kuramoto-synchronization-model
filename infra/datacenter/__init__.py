# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data center management module.

Provides abstractions for managing multiple data centers with:
- Geographic region and availability zone modeling
- Health monitoring and status tracking
- Failover management with latency-aware routing
- Multi-region replication coordination
"""

from infra.datacenter.health import DataCenterHealthMonitor
from infra.datacenter.manager import DataCenterManager
from infra.datacenter.models import (
    AvailabilityZone,
    DataCenter,
    DataCenterConfig,
    DataCenterHealth,
    DataCenterRegion,
    DataCenterStatus,
    FailoverPolicy,
    ReplicationConfig,
)

__all__ = [
    "AvailabilityZone",
    "DataCenter",
    "DataCenterConfig",
    "DataCenterHealth",
    "DataCenterHealthMonitor",
    "DataCenterManager",
    "DataCenterRegion",
    "DataCenterStatus",
    "FailoverPolicy",
    "ReplicationConfig",
]
