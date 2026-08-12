# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for data center manager."""

from __future__ import annotations

import pytest

from infra.datacenter.manager import DataCenterManager
from infra.datacenter.models import (
    DataCenter,
    DataCenterConfig,
    DataCenterHealth,
    DataCenterRegion,
    DataCenterStatus,
)


class TestDataCenterManager:
    """Tests for DataCenterManager."""

    def test_register_data_center(self) -> None:
        """Test registering a data center."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        dc = manager.register_data_center(config)

        assert dc.id == "dc-test"
        assert dc.name == "Test DC"
        assert manager.get_data_center("dc-test") is dc

    def test_register_primary_data_center(self) -> None:
        """Test registering a primary data center."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-primary",
            name="Primary DC",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        dc = manager.register_data_center(config)

        assert dc.is_primary is True
        assert dc.status == DataCenterStatus.ACTIVE
        assert manager.get_primary_data_center() is dc

    def test_register_secondary_data_center(self) -> None:
        """Test registering a secondary data center."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-secondary",
            name="Secondary DC",
            region=DataCenterRegion.US_WEST,
            is_primary=False,
        )
        dc = manager.register_data_center(config)

        assert dc.is_primary is False
        assert dc.status == DataCenterStatus.STANDBY

    def test_register_duplicate_fails(self) -> None:
        """Test that registering duplicate DC raises ValueError."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        manager.register_data_center(config)

        with pytest.raises(ValueError, match="already registered"):
            manager.register_data_center(config)

    def test_unregister_data_center(self) -> None:
        """Test unregistering a data center."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        manager.register_data_center(config)

        result = manager.unregister_data_center("dc-test")
        assert result is True
        assert manager.get_data_center("dc-test") is None

    def test_unregister_nonexistent_returns_false(self) -> None:
        """Test unregistering nonexistent DC returns False."""
        manager = DataCenterManager()
        result = manager.unregister_data_center("dc-nonexistent")
        assert result is False

    def test_get_all_data_centers(self) -> None:
        """Test getting all data centers."""
        manager = DataCenterManager()
        config1 = DataCenterConfig(
            id="dc-1",
            name="DC 1",
            region=DataCenterRegion.US_EAST,
        )
        config2 = DataCenterConfig(
            id="dc-2",
            name="DC 2",
            region=DataCenterRegion.US_WEST,
        )
        manager.register_data_center(config1)
        manager.register_data_center(config2)

        all_dcs = manager.get_all_data_centers()
        assert len(all_dcs) == 2
        ids = {dc.id for dc in all_dcs}
        assert ids == {"dc-1", "dc-2"}

    def test_get_data_centers_by_region(self) -> None:
        """Test getting data centers by region."""
        manager = DataCenterManager()
        config1 = DataCenterConfig(
            id="dc-east-1",
            name="East 1",
            region=DataCenterRegion.US_EAST,
        )
        config2 = DataCenterConfig(
            id="dc-east-2",
            name="East 2",
            region=DataCenterRegion.US_EAST,
        )
        config3 = DataCenterConfig(
            id="dc-west",
            name="West",
            region=DataCenterRegion.US_WEST,
        )
        manager.register_data_center(config1)
        manager.register_data_center(config2)
        manager.register_data_center(config3)

        east_dcs = manager.get_data_centers_by_region(DataCenterRegion.US_EAST)
        assert len(east_dcs) == 2

        west_dcs = manager.get_data_centers_by_region(DataCenterRegion.US_WEST)
        assert len(west_dcs) == 1

    def test_get_available_data_centers(self) -> None:
        """Test getting available data centers."""
        manager = DataCenterManager()
        config1 = DataCenterConfig(
            id="dc-active",
            name="Active",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-standby",
            name="Standby",
            region=DataCenterRegion.US_WEST,
        )
        manager.register_data_center(config1)
        manager.register_data_center(config2)

        available = manager.get_available_data_centers()
        assert len(available) == 1
        assert available[0].id == "dc-active"

    def test_update_health(self) -> None:
        """Test updating data center health."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        manager.register_data_center(config)

        new_health = DataCenterHealth(
            latency_ms=50.0,
            cpu_utilization=30.0,
        )
        dc = manager.update_health("dc-test", new_health)

        assert dc is not None
        assert dc.health.latency_ms == 50.0
        assert dc.health.cpu_utilization == 30.0

    def test_update_health_nonexistent(self) -> None:
        """Test updating health for nonexistent DC."""
        manager = DataCenterManager()
        new_health = DataCenterHealth(latency_ms=50.0)
        dc = manager.update_health("dc-nonexistent", new_health)
        assert dc is None

    def test_execute_failover(self) -> None:
        """Test executing failover."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        dc1 = manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)

        # Activate secondary for failover
        dc2.status = DataCenterStatus.STANDBY
        dc2.health.is_healthy = True

        new_primary = manager.execute_failover("dc-primary", "dc-secondary", "test")

        assert new_primary is not None
        assert new_primary.id == "dc-secondary"
        assert new_primary.is_primary is True
        assert dc1.status == DataCenterStatus.FAILOVER
        assert dc1.is_primary is False
        assert dc1.failover_count == 1

    def test_execute_failover_to_unhealthy_fails(self) -> None:
        """Test failover to unhealthy DC fails."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)
        dc2.health.is_healthy = False

        new_primary = manager.execute_failover("dc-primary", "dc-secondary", "test")
        assert new_primary is None

    def test_get_best_data_center_same_region(self) -> None:
        """Test getting best DC prefers same region."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-east",
            name="East",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-west",
            name="West",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)
        dc2.status = DataCenterStatus.ACTIVE

        best = manager.get_best_data_center(DataCenterRegion.US_WEST)
        assert best is not None
        assert best.id == "dc-west"

    def test_get_best_data_center_returns_primary(self) -> None:
        """Test getting best DC returns primary if no region preference."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)
        dc2.status = DataCenterStatus.ACTIVE

        best = manager.get_best_data_center()
        assert best is not None
        assert best.id == "dc-primary"

    def test_get_routing_table(self) -> None:
        """Test getting routing table."""
        manager = DataCenterManager()

        config = DataCenterConfig(
            id="dc-east",
            name="East",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        manager.register_data_center(config)

        routing_table = manager.get_routing_table()
        assert DataCenterRegion.US_EAST.value in routing_table
        assert routing_table[DataCenterRegion.US_EAST.value]["primary_dc"] == "dc-east"

    def test_get_failover_history(self) -> None:
        """Test getting failover history."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)
        dc2.status = DataCenterStatus.STANDBY
        dc2.health.is_healthy = True

        manager.execute_failover("dc-primary", "dc-secondary", "test-reason")

        history = manager.get_failover_history()
        assert len(history) == 1
        assert history[0]["source_dc"] == "dc-primary"
        assert history[0]["target_dc"] == "dc-secondary"
        assert history[0]["reason"] == "test-reason"

    def test_get_system_status(self) -> None:
        """Test getting system status."""
        manager = DataCenterManager()

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        manager.register_data_center(config2)

        status = manager.get_system_status()
        assert status["total_data_centers"] == 2
        assert status["active"] == 1
        assert status["standby"] == 1
        assert status["primary_dc"] == "dc-primary"
        assert status["primary_dc_healthy"] is True

    def test_set_data_center_status(self) -> None:
        """Test setting data center status."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test",
            region=DataCenterRegion.US_EAST,
        )
        manager.register_data_center(config)

        dc = manager.set_data_center_status("dc-test", DataCenterStatus.MAINTENANCE)
        assert dc is not None
        assert dc.status == DataCenterStatus.MAINTENANCE

    def test_failover_callback_invoked(self) -> None:
        """Test that failover callback is invoked."""
        callback_invoked = {"value": False}
        captured_args = {}

        def failover_callback(old_dc: DataCenter, new_dc: DataCenter) -> None:
            callback_invoked["value"] = True
            captured_args["old"] = old_dc.id
            captured_args["new"] = new_dc.id

        manager = DataCenterManager(failover_callback=failover_callback)

        config1 = DataCenterConfig(
            id="dc-primary",
            name="Primary",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        config2 = DataCenterConfig(
            id="dc-secondary",
            name="Secondary",
            region=DataCenterRegion.US_WEST,
        )

        manager.register_data_center(config1)
        dc2 = manager.register_data_center(config2)
        dc2.status = DataCenterStatus.STANDBY
        dc2.health.is_healthy = True

        manager.execute_failover("dc-primary", "dc-secondary")

        assert callback_invoked["value"] is True
        assert captured_args["old"] == "dc-primary"
        assert captured_args["new"] == "dc-secondary"

    def test_get_data_center_summary(self) -> None:
        """Test getting data center summary."""
        manager = DataCenterManager()
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        manager.register_data_center(config)

        summary = manager.get_data_center_summary()
        assert len(summary) == 1
        assert summary[0]["id"] == "dc-test"
        assert summary[0]["name"] == "Test DC"
        assert summary[0]["region"] == "us-east"
