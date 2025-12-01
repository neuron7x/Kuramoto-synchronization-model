# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data center manager.

Provides centralized management of multiple data centers with:
- Registration and lifecycle management
- Failover orchestration
- Latency-aware routing
- Replication coordination
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, List, Optional

from infra.datacenter.health import DataCenterHealthMonitor
from infra.datacenter.models import (
    DataCenter,
    DataCenterConfig,
    DataCenterHealth,
    DataCenterRegion,
    DataCenterStatus,
    FailoverPolicy,
)

logger = logging.getLogger(__name__)


class DataCenterManager:
    """Manages multiple data centers.

    Provides central coordination for data center operations including
    registration, health monitoring, failover, and routing.
    """

    def __init__(
        self,
        health_monitor: Optional[DataCenterHealthMonitor] = None,
        failover_callback: Optional[Callable[[DataCenter, DataCenter], None]] = None,
    ):
        """Initialize the data center manager.

        Args:
            health_monitor: Optional custom health monitor
            failover_callback: Callback invoked on failover (old_dc, new_dc)
        """
        self._lock = RLock()
        self._data_centers: Dict[str, DataCenter] = {}
        self._health_monitor = health_monitor or DataCenterHealthMonitor()
        self._failover_callback = failover_callback
        self._primary_dc_id: Optional[str] = None
        self._failover_history: List[Dict] = []

    def register_data_center(self, config: DataCenterConfig) -> DataCenter:
        """Register a new data center.

        Args:
            config: Data center configuration

        Returns:
            The registered data center

        Raises:
            ValueError: If data center with same ID already exists
        """
        with self._lock:
            if config.id in self._data_centers:
                raise ValueError(f"Data center {config.id} already registered")

            dc = DataCenter(
                config=config,
                status=(
                    DataCenterStatus.ACTIVE
                    if config.is_primary
                    else DataCenterStatus.STANDBY
                ),
            )

            self._data_centers[config.id] = dc

            if config.is_primary:
                if self._primary_dc_id is not None:
                    # Demote existing primary
                    old_primary = self._data_centers.get(self._primary_dc_id)
                    if old_primary:
                        old_primary.status = DataCenterStatus.STANDBY
                        old_primary.config = old_primary.config.with_primary_status(
                            False
                        )
                self._primary_dc_id = config.id

            logger.info(
                f"Registered data center {config.id} ({config.name}) "
                f"in region {config.region.value}"
            )
            return dc

    def unregister_data_center(self, dc_id: str) -> bool:
        """Unregister a data center.

        Args:
            dc_id: ID of the data center to unregister

        Returns:
            True if successfully unregistered, False if not found
        """
        with self._lock:
            if dc_id not in self._data_centers:
                return False

            self._data_centers.pop(dc_id)

            if self._primary_dc_id == dc_id:
                # Need to elect a new primary
                self._primary_dc_id = None
                for other_dc in self._data_centers.values():
                    if other_dc.status in (
                        DataCenterStatus.ACTIVE,
                        DataCenterStatus.STANDBY,
                    ):
                        self._promote_to_primary(other_dc)
                        break

            logger.info(f"Unregistered data center {dc_id}")
            return True

    def get_data_center(self, dc_id: str) -> Optional[DataCenter]:
        """Get a data center by ID.

        Args:
            dc_id: Data center ID

        Returns:
            Data center if found, None otherwise
        """
        with self._lock:
            return self._data_centers.get(dc_id)

    def get_all_data_centers(self) -> List[DataCenter]:
        """Get all registered data centers.

        Returns:
            List of all data centers
        """
        with self._lock:
            return list(self._data_centers.values())

    def get_primary_data_center(self) -> Optional[DataCenter]:
        """Get the primary data center.

        Returns:
            Primary data center if one is set
        """
        with self._lock:
            if self._primary_dc_id:
                return self._data_centers.get(self._primary_dc_id)
            return None

    def get_data_centers_by_region(self, region: DataCenterRegion) -> List[DataCenter]:
        """Get all data centers in a specific region.

        Args:
            region: Region to filter by

        Returns:
            List of data centers in the region
        """
        with self._lock:
            return [dc for dc in self._data_centers.values() if dc.region == region]

    def get_available_data_centers(self) -> List[DataCenter]:
        """Get all available data centers.

        Returns:
            List of data centers that can serve traffic
        """
        with self._lock:
            return [dc for dc in self._data_centers.values() if dc.is_available]

    def update_health(
        self, dc_id: str, health: DataCenterHealth
    ) -> Optional[DataCenter]:
        """Update health metrics for a data center.

        Args:
            dc_id: Data center ID
            health: New health metrics

        Returns:
            Updated data center, or None if not found
        """
        with self._lock:
            dc = self._data_centers.get(dc_id)
            if dc is None:
                return None

            dc.health = health

            # Check if failover is needed
            if dc.is_primary and dc.should_failover():
                if dc.config.failover_policy == FailoverPolicy.AUTOMATIC:
                    self._trigger_failover(dc)

            return dc

    def perform_health_checks(self) -> Dict[str, Dict]:
        """Perform health checks on all data centers.

        Returns:
            Dictionary of health check results by DC ID
        """
        results = {}
        with self._lock:
            for dc in self._data_centers.values():
                if self._health_monitor.is_check_due(dc):
                    check_result = self._health_monitor.check_health(dc)
                    results[dc.id] = {
                        "success": check_result.success,
                        "latency_ms": check_result.latency_ms,
                        "health_score": dc.get_health_score(),
                        "status": dc.status.value,
                    }

                    # Check for failover
                    if dc.is_primary and dc.should_failover():
                        if dc.config.failover_policy == FailoverPolicy.AUTOMATIC:
                            self._trigger_failover(dc)

        return results

    def _trigger_failover(self, failing_dc: DataCenter) -> Optional[DataCenter]:
        """Trigger failover from a failing data center.

        Args:
            failing_dc: The data center that is failing

        Returns:
            New primary data center, or None if failover failed
        """
        # Find best candidate for failover
        candidates = [
            dc
            for dc in self._data_centers.values()
            if dc.id != failing_dc.id
            and dc.status in (DataCenterStatus.STANDBY, DataCenterStatus.ACTIVE)
            and dc.health.is_healthy
        ]

        if not candidates:
            logger.error(f"No available candidates for failover from {failing_dc.id}")
            return None

        # Select candidate with best health score
        best_candidate = max(candidates, key=lambda dc: dc.get_health_score())

        return self.execute_failover(failing_dc.id, best_candidate.id)

    def execute_failover(
        self, source_dc_id: str, target_dc_id: str, reason: str = "automatic"
    ) -> Optional[DataCenter]:
        """Execute a failover from source to target data center.

        Args:
            source_dc_id: ID of data center to failover from
            target_dc_id: ID of data center to failover to
            reason: Reason for failover

        Returns:
            New primary data center, or None if failover failed
        """
        with self._lock:
            source_dc = self._data_centers.get(source_dc_id)
            target_dc = self._data_centers.get(target_dc_id)

            if source_dc is None:
                logger.error(f"Source data center {source_dc_id} not found")
                return None

            if target_dc is None:
                logger.error(f"Target data center {target_dc_id} not found")
                return None

            if not target_dc.health.is_healthy:
                logger.error(f"Target data center {target_dc_id} is not healthy")
                return None

            # Record failover
            now = datetime.now(timezone.utc)
            failover_record = {
                "timestamp": now.isoformat(),
                "source_dc": source_dc_id,
                "target_dc": target_dc_id,
                "reason": reason,
                "source_health_score": source_dc.get_health_score(),
                "target_health_score": target_dc.get_health_score(),
            }
            self._failover_history.append(failover_record)

            # Update source DC
            source_dc.status = DataCenterStatus.FAILOVER
            source_dc.last_failover_at = now
            source_dc.failover_count += 1

            # Demote source from primary
            if source_dc.is_primary:
                source_dc.config = source_dc.config.with_primary_status(False)

            # Promote target DC
            self._promote_to_primary(target_dc)

            logger.warning(
                f"Failover executed: {source_dc_id} -> {target_dc_id} "
                f"(reason: {reason})"
            )

            # Invoke callback
            if self._failover_callback:
                self._failover_callback(source_dc, target_dc)

            return target_dc

    def _promote_to_primary(self, dc: DataCenter) -> None:
        """Promote a data center to primary.

        Args:
            dc: Data center to promote
        """
        dc.config = dc.config.with_primary_status(True)
        dc.status = DataCenterStatus.ACTIVE
        self._primary_dc_id = dc.id

        logger.info(f"Data center {dc.id} promoted to primary")

    def set_data_center_status(
        self, dc_id: str, status: DataCenterStatus
    ) -> Optional[DataCenter]:
        """Manually set data center status.

        Args:
            dc_id: Data center ID
            status: New status

        Returns:
            Updated data center, or None if not found
        """
        with self._lock:
            dc = self._data_centers.get(dc_id)
            if dc is None:
                return None

            dc.status = status
            logger.info(f"Data center {dc_id} status set to {status.value}")
            return dc

    def get_best_data_center(
        self, client_region: Optional[DataCenterRegion] = None
    ) -> Optional[DataCenter]:
        """Get the best available data center for a client.

        Uses latency-aware routing to select the optimal data center.

        Args:
            client_region: Client's region for proximity-based routing

        Returns:
            Best available data center, or None if none available
        """
        with self._lock:
            available = self.get_available_data_centers()
            if not available:
                return None

            # If client region specified, prefer same-region DCs
            if client_region:
                same_region = [dc for dc in available if dc.region == client_region]
                if same_region:
                    # Return the healthiest DC in the same region
                    return max(same_region, key=lambda dc: dc.get_health_score())

            # Otherwise return the primary if available, else healthiest
            primary = self.get_primary_data_center()
            if primary and primary.is_available:
                return primary

            return max(available, key=lambda dc: dc.get_health_score())

    def get_routing_table(self) -> Dict[str, Dict]:
        """Get routing table for all regions.

        Returns:
            Dictionary mapping regions to recommended data centers
        """
        with self._lock:
            routing_table = {}

            for region in DataCenterRegion:
                best_dc = self.get_best_data_center(region)
                if best_dc:
                    routing_table[region.value] = {
                        "primary_dc": best_dc.id,
                        "dc_name": best_dc.name,
                        "dc_region": best_dc.region.value,
                        "health_score": best_dc.get_health_score(),
                        "latency_ms": best_dc.health.latency_ms,
                    }

            return routing_table

    def get_failover_history(self, limit: int = 10) -> List[Dict]:
        """Get recent failover history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of failover records
        """
        with self._lock:
            return list(self._failover_history[-limit:])

    def get_system_status(self) -> Dict:
        """Get overall system status.

        Returns:
            Dictionary with system status information
        """
        with self._lock:
            total_dcs = len(self._data_centers)
            active_dcs = sum(
                1
                for dc in self._data_centers.values()
                if dc.status == DataCenterStatus.ACTIVE
            )
            degraded_dcs = sum(
                1
                for dc in self._data_centers.values()
                if dc.status == DataCenterStatus.DEGRADED
            )
            offline_dcs = sum(
                1
                for dc in self._data_centers.values()
                if dc.status == DataCenterStatus.OFFLINE
            )

            primary = self.get_primary_data_center()

            return {
                "total_data_centers": total_dcs,
                "active": active_dcs,
                "degraded": degraded_dcs,
                "offline": offline_dcs,
                "standby": total_dcs - active_dcs - degraded_dcs - offline_dcs,
                "primary_dc": primary.id if primary else None,
                "primary_dc_healthy": primary.health.is_healthy if primary else False,
                "total_failovers": len(self._failover_history),
                "regions_covered": list(
                    set(dc.region.value for dc in self._data_centers.values())
                ),
            }

    def get_data_center_summary(self) -> List[Dict]:
        """Get summary of all data centers.

        Returns:
            List of data center summaries
        """
        with self._lock:
            return [dc.to_dict() for dc in self._data_centers.values()]
