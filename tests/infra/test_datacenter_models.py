# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for data center models."""

from __future__ import annotations

import pytest

from infra.datacenter.models import (
    AvailabilityZone,
    DataCenter,
    DataCenterConfig,
    DataCenterHealth,
    DataCenterRegion,
    DataCenterStatus,
    FailoverPolicy,
    ReplicationConfig,
    create_default_availability_zones,
)


class TestAvailabilityZone:
    """Tests for AvailabilityZone."""

    def test_create_availability_zone(self) -> None:
        """Test creating a valid availability zone."""
        az = AvailabilityZone(
            name="us-east-1a",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        assert az.name == "us-east-1a"
        assert az.region == DataCenterRegion.US_EAST
        assert az.is_primary is True

    def test_availability_zone_empty_name_fails(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            AvailabilityZone(
                name="",
                region=DataCenterRegion.US_EAST,
            )

    def test_availability_zone_default_not_primary(self) -> None:
        """Test default is_primary is False."""
        az = AvailabilityZone(
            name="us-east-1b",
            region=DataCenterRegion.US_EAST,
        )
        assert az.is_primary is False


class TestDataCenterHealth:
    """Tests for DataCenterHealth."""

    def test_default_health_values(self) -> None:
        """Test default health values."""
        health = DataCenterHealth()
        assert health.latency_ms == 0.0
        assert health.packet_loss_rate == 0.0
        assert health.cpu_utilization == 0.0
        assert health.is_healthy is True

    def test_health_score_perfect(self) -> None:
        """Test health score for perfect health."""
        health = DataCenterHealth()
        score = health.calculate_health_score()
        assert score == 100.0

    def test_health_score_high_latency(self) -> None:
        """Test health score with high latency."""
        health = DataCenterHealth(latency_ms=200.0)
        score = health.calculate_health_score()
        assert score < 100.0
        assert score > 80.0  # Should still be reasonably healthy

    def test_health_score_high_error_rate(self) -> None:
        """Test health score with high error rate."""
        health = DataCenterHealth(error_rate=0.5)
        score = health.calculate_health_score()
        assert score < 90.0

    def test_health_score_degraded(self) -> None:
        """Test health score for degraded conditions."""
        health = DataCenterHealth(
            latency_ms=500.0,
            packet_loss_rate=0.1,
            cpu_utilization=90.0,
            error_rate=0.1,
        )
        score = health.calculate_health_score()
        assert score < 50.0

    def test_health_score_high_cpu_low_others(self) -> None:
        """Test health score with high CPU but low memory and disk.

        This test verifies the new max utilization logic:
        - With max utilization (90% CPU), penalty is applied
        - Score = 100 - (90-70)/1.0 = 80.0
        """
        health = DataCenterHealth(
            cpu_utilization=90.0,
            memory_utilization=10.0,
            disk_utilization=10.0,
        )
        score = health.calculate_health_score()
        # Penalty: min(20.0, (90-70)/1.0) = 20.0
        # Expected: 100 - 20 = 80.0
        assert score == 80.0

    def test_health_score_high_memory_low_others(self) -> None:
        """Test health score with high memory but low CPU and disk.

        This verifies max utilization catches memory constraint:
        - Max utilization = 85% (memory)
        - Score = 100 - (85-70)/1.0 = 85.0
        """
        health = DataCenterHealth(
            cpu_utilization=20.0,
            memory_utilization=85.0,
            disk_utilization=15.0,
        )
        score = health.calculate_health_score()
        # Penalty: min(20.0, (85-70)/1.0) = 15.0
        # Expected: 100 - 15 = 85.0
        assert score == 85.0

    def test_health_score_high_disk_low_others(self) -> None:
        """Test health score with high disk but low CPU and memory.

        This verifies max utilization catches disk constraint:
        - Max utilization = 95% (disk)
        - Penalty capped at 20.0 since (95-70)/1.0 = 25.0 > 20.0
        """
        health = DataCenterHealth(
            cpu_utilization=30.0,
            memory_utilization=25.0,
            disk_utilization=95.0,
        )
        score = health.calculate_health_score()
        # Penalty: min(20.0, (95-70)/1.0) = 20.0 (capped)
        # Expected: 100 - 20 = 80.0
        assert score == 80.0

    def test_health_score_balanced_high_load(self) -> None:
        """Test health score with balanced high load across all resources.

        This verifies behavior when all resources are equally high:
        - Max utilization = 85% (all equal)
        - Score = 100 - (85-70)/1.0 = 85.0
        """
        health = DataCenterHealth(
            cpu_utilization=85.0,
            memory_utilization=85.0,
            disk_utilization=85.0,
        )
        score = health.calculate_health_score()
        # Penalty: min(20.0, (85-70)/1.0) = 15.0
        # Expected: 100 - 15 = 85.0
        assert score == 85.0

    def test_health_score_low_load_everywhere(self) -> None:
        """Test health score with low load across all resources.

        This verifies no penalty when all resources are below threshold:
        - Max utilization = 50% (all below 70% threshold)
        - No penalty applied
        """
        health = DataCenterHealth(
            cpu_utilization=50.0,
            memory_utilization=40.0,
            disk_utilization=30.0,
        )
        score = health.calculate_health_score()
        # No penalty since max(50, 40, 30) = 50 < 70
        # Expected: 100.0
        assert score == 100.0

    def test_health_score_threshold_boundary(self) -> None:
        """Test health score at exactly the 70% threshold.

        This verifies that exactly 70% doesn't trigger penalty:
        - Max utilization = 70%
        - No penalty should be applied
        """
        health = DataCenterHealth(
            cpu_utilization=70.0,
            memory_utilization=50.0,
            disk_utilization=60.0,
        )
        score = health.calculate_health_score()
        # No penalty since 70 is not > 70
        # Expected: 100.0
        assert score == 100.0

    def test_health_score_just_above_threshold(self) -> None:
        """Test health score just above the 70% threshold.

        This verifies penalty calculation for minimal overage:
        - Max utilization = 71%
        - Small penalty of (71-70)/1.0 = 1.0
        """
        health = DataCenterHealth(
            cpu_utilization=71.0,
            memory_utilization=50.0,
            disk_utilization=60.0,
        )
        score = health.calculate_health_score()
        # Penalty: min(20.0, (71-70)/1.0) = 1.0
        # Expected: 100 - 1 = 99.0
        assert score == 99.0

    def test_negative_latency_fails(self) -> None:
        """Test that negative latency raises ValueError."""
        with pytest.raises(ValueError, match="cannot be negative"):
            DataCenterHealth(latency_ms=-1.0)

    def test_invalid_packet_loss_rate_fails(self) -> None:
        """Test that invalid packet loss rate raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            DataCenterHealth(packet_loss_rate=1.5)

    def test_invalid_error_rate_fails(self) -> None:
        """Test that invalid error rate raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            DataCenterHealth(error_rate=-0.1)


class TestReplicationConfig:
    """Tests for ReplicationConfig."""

    def test_create_replication_config(self) -> None:
        """Test creating a valid replication config."""
        config = ReplicationConfig(
            target_dc_id="dc-secondary",
            mode="sync",
            lag_threshold_ms=500.0,
        )
        assert config.target_dc_id == "dc-secondary"
        assert config.mode == "sync"
        assert config.lag_threshold_ms == 500.0
        assert config.enabled is True

    def test_default_mode_is_async(self) -> None:
        """Test default mode is async."""
        config = ReplicationConfig(target_dc_id="dc-secondary")
        assert config.mode == "async"

    def test_invalid_mode_fails(self) -> None:
        """Test that invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="must be 'sync' or 'async'"):
            ReplicationConfig(
                target_dc_id="dc-secondary",
                mode="invalid",
            )

    def test_negative_lag_threshold_fails(self) -> None:
        """Test that negative lag threshold raises ValueError."""
        with pytest.raises(ValueError, match="cannot be negative"):
            ReplicationConfig(
                target_dc_id="dc-secondary",
                lag_threshold_ms=-100.0,
            )


class TestDataCenterConfig:
    """Tests for DataCenterConfig."""

    def test_create_config(self) -> None:
        """Test creating a valid config."""
        config = DataCenterConfig(
            id="dc-primary",
            name="Primary US East",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        assert config.id == "dc-primary"
        assert config.name == "Primary US East"
        assert config.region == DataCenterRegion.US_EAST
        assert config.is_primary is True

    def test_default_values(self) -> None:
        """Test default values."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_WEST,
        )
        assert config.is_primary is False
        assert config.failover_policy == FailoverPolicy.AUTOMATIC
        assert config.max_connections == 10000
        assert config.health_check_interval_seconds == 30
        assert config.failover_threshold_score == 50.0

    def test_empty_id_fails(self) -> None:
        """Test that empty ID raises ValueError."""
        with pytest.raises(ValueError, match="ID cannot be empty"):
            DataCenterConfig(
                id="",
                name="Test DC",
                region=DataCenterRegion.US_EAST,
            )

    def test_empty_name_fails(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            DataCenterConfig(
                id="dc-test",
                name="",
                region=DataCenterRegion.US_EAST,
            )

    def test_invalid_max_connections_fails(self) -> None:
        """Test that invalid max_connections raises ValueError."""
        with pytest.raises(ValueError, match="must be at least 1"):
            DataCenterConfig(
                id="dc-test",
                name="Test DC",
                region=DataCenterRegion.US_EAST,
                max_connections=0,
            )

    def test_invalid_health_check_interval_fails(self) -> None:
        """Test that invalid health_check_interval raises ValueError."""
        with pytest.raises(ValueError, match="must be at least 1 second"):
            DataCenterConfig(
                id="dc-test",
                name="Test DC",
                region=DataCenterRegion.US_EAST,
                health_check_interval_seconds=0,
            )

    def test_invalid_failover_threshold_fails(self) -> None:
        """Test that invalid failover_threshold raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 100"):
            DataCenterConfig(
                id="dc-test",
                name="Test DC",
                region=DataCenterRegion.US_EAST,
                failover_threshold_score=150.0,
            )

    def test_with_primary_status(self) -> None:
        """Test with_primary_status method."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            is_primary=False,
        )
        new_config = config.with_primary_status(True)

        assert new_config.is_primary is True
        assert new_config.id == config.id
        assert new_config.name == config.name
        assert new_config.region == config.region
        assert new_config.failover_policy == config.failover_policy

    def test_with_primary_status_preserves_other_fields(self) -> None:
        """Test that with_primary_status preserves all other fields."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.EU_WEST,
            is_primary=True,
            max_connections=5000,
            health_check_interval_seconds=60,
            failover_threshold_score=40.0,
        )
        new_config = config.with_primary_status(False)

        assert new_config.is_primary is False
        assert new_config.max_connections == 5000
        assert new_config.health_check_interval_seconds == 60
        assert new_config.failover_threshold_score == 40.0


class TestDataCenter:
    """Tests for DataCenter."""

    def test_create_data_center(self) -> None:
        """Test creating a data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        dc = DataCenter(config=config, status=DataCenterStatus.ACTIVE)

        assert dc.id == "dc-test"
        assert dc.name == "Test DC"
        assert dc.region == DataCenterRegion.US_EAST
        assert dc.is_primary is True
        assert dc.status == DataCenterStatus.ACTIVE

    def test_is_available_active(self) -> None:
        """Test is_available for active data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        dc = DataCenter(config=config, status=DataCenterStatus.ACTIVE)
        assert dc.is_available is True

    def test_is_available_degraded(self) -> None:
        """Test is_available for degraded data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        dc = DataCenter(config=config, status=DataCenterStatus.DEGRADED)
        assert dc.is_available is True

    def test_is_not_available_offline(self) -> None:
        """Test is_available for offline data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
        )
        dc = DataCenter(config=config, status=DataCenterStatus.OFFLINE)
        assert dc.is_available is False

    def test_should_failover_healthy(self) -> None:
        """Test should_failover for healthy data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            failover_threshold_score=50.0,
        )
        dc = DataCenter(config=config)
        assert dc.should_failover() is False

    def test_should_failover_unhealthy(self) -> None:
        """Test should_failover for unhealthy data center."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            failover_threshold_score=50.0,
        )
        health = DataCenterHealth(
            latency_ms=1000.0,
            error_rate=0.5,
            cpu_utilization=95.0,
        )
        dc = DataCenter(config=config, health=health)
        assert dc.should_failover() is True

    def test_to_dict(self) -> None:
        """Test to_dict method."""
        config = DataCenterConfig(
            id="dc-test",
            name="Test DC",
            region=DataCenterRegion.US_EAST,
            is_primary=True,
        )
        dc = DataCenter(config=config, status=DataCenterStatus.ACTIVE)
        result = dc.to_dict()

        assert result["id"] == "dc-test"
        assert result["name"] == "Test DC"
        assert result["region"] == "us-east"
        assert result["status"] == "active"
        assert result["is_primary"] is True
        assert result["health_score"] == 100.0


class TestCreateDefaultAvailabilityZones:
    """Tests for create_default_availability_zones function."""

    def test_creates_three_zones(self) -> None:
        """Test that three zones are created."""
        zones = create_default_availability_zones(DataCenterRegion.US_EAST)
        assert len(zones) == 3

    def test_first_zone_is_primary(self) -> None:
        """Test that first zone is primary."""
        zones = create_default_availability_zones(DataCenterRegion.US_EAST)
        assert zones[0].is_primary is True
        assert zones[1].is_primary is False
        assert zones[2].is_primary is False

    def test_zone_names_have_correct_prefix(self) -> None:
        """Test zone names have correct prefix."""
        zones = create_default_availability_zones(DataCenterRegion.US_EAST)
        assert zones[0].name.startswith("us-east-1")
        assert zones[1].name.startswith("us-east-1")
        assert zones[2].name.startswith("us-east-1")

    def test_zone_names_have_suffixes(self) -> None:
        """Test zone names have a, b, c suffixes."""
        zones = create_default_availability_zones(DataCenterRegion.US_EAST)
        assert zones[0].name.endswith("a")
        assert zones[1].name.endswith("b")
        assert zones[2].name.endswith("c")

    def test_all_zones_have_same_region(self) -> None:
        """Test all zones have same region."""
        zones = create_default_availability_zones(DataCenterRegion.EU_WEST)
        for zone in zones:
            assert zone.region == DataCenterRegion.EU_WEST
