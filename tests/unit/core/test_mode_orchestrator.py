# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for core/orchestrator/mode_orchestrator.py."""

from __future__ import annotations

import pytest

from core.orchestrator.mode_orchestrator import (
    DelayBudget,
    GuardBand,
    GuardConfig,
    MetricsSnapshot,
    ModeOrchestrator,
    ModeOrchestratorConfig,
    ModeState,
    TimeoutConfig,
)


class TestModeState:
    """Tests for ModeState enum."""

    def test_mode_state_values(self) -> None:
        """Verify all expected mode states exist."""
        assert ModeState.ACTION.value == "action"
        assert ModeState.COOLDOWN.value == "cooldown"
        assert ModeState.REST.value == "rest"
        assert ModeState.SAFE_EXIT.value == "safe_exit"


class TestGuardBand:
    """Tests for GuardBand dataclass."""

    def test_valid_guard_band(self) -> None:
        """Verify valid guard band is created."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.8, recover_limit=0.3)

        assert band.soft_limit == 0.5
        assert band.hard_limit == 0.8
        assert band.recover_limit == 0.3

    def test_guard_band_equal_limits(self) -> None:
        """Verify equal limits are accepted."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.5, recover_limit=0.5)
        assert band.soft_limit == 0.5

    def test_is_soft_breach(self) -> None:
        """Verify soft breach detection."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.8, recover_limit=0.3)

        assert band.is_soft_breach(0.5) is True
        assert band.is_soft_breach(0.6) is True
        assert band.is_soft_breach(0.4) is False

    def test_is_hard_breach(self) -> None:
        """Verify hard breach detection."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.8, recover_limit=0.3)

        assert band.is_hard_breach(0.8) is True
        assert band.is_hard_breach(0.9) is True
        assert band.is_hard_breach(0.7) is False

    def test_is_recovered(self) -> None:
        """Verify recovery detection."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.8, recover_limit=0.3)

        assert band.is_recovered(0.3) is True
        assert band.is_recovered(0.2) is True
        assert band.is_recovered(0.4) is False


class TestGuardConfig:
    """Tests for GuardConfig dataclass."""

    @pytest.fixture
    def guard_config(self) -> GuardConfig:
        """Create a test guard config."""
        return GuardConfig(
            kappa=GuardBand(0.5, 0.8, 0.3),
            var=GuardBand(0.05, 0.1, 0.02),
            max_drawdown=GuardBand(0.1, 0.15, 0.05),
            heat=GuardBand(0.7, 0.9, 0.5),
        )

    def test_guard_config_structure(self, guard_config: GuardConfig) -> None:
        """Verify guard config contains all required bands."""
        assert guard_config.kappa is not None
        assert guard_config.var is not None
        assert guard_config.max_drawdown is not None
        assert guard_config.heat is not None


class TestTimeoutConfig:
    """Tests for TimeoutConfig dataclass."""

    def test_timeout_config_values(self) -> None:
        """Verify timeout config stores all values."""
        config = TimeoutConfig(
            action_max=60.0,
            cooldown_min=30.0,
            rest_min=120.0,
            cooldown_persistence=90.0,
            safe_exit_lock=300.0,
        )

        assert config.action_max == 60.0
        assert config.cooldown_min == 30.0
        assert config.rest_min == 120.0
        assert config.cooldown_persistence == 90.0
        assert config.safe_exit_lock == 300.0


class TestDelayBudget:
    """Tests for DelayBudget dataclass."""

    def test_delay_budget_values(self) -> None:
        """Verify delay budget stores all values."""
        budget = DelayBudget(
            action_to_cooldown=0.01,
            cooldown_to_rest=0.05,
            protective_to_safe_exit=0.001,
        )

        assert budget.action_to_cooldown == 0.01
        assert budget.cooldown_to_rest == 0.05
        assert budget.protective_to_safe_exit == 0.001


class TestMetricsSnapshot:
    """Tests for MetricsSnapshot dataclass."""

    def test_metrics_snapshot_values(self) -> None:
        """Verify metrics snapshot stores all values."""
        snapshot = MetricsSnapshot(
            kappa=0.4,
            var=0.03,
            max_drawdown=0.08,
            heat=0.6,
        )

        assert snapshot.kappa == 0.4
        assert snapshot.var == 0.03
        assert snapshot.max_drawdown == 0.08
        assert snapshot.heat == 0.6


class TestModeOrchestrator:
    """Tests for ModeOrchestrator class."""

    @pytest.fixture
    def orchestrator_config(self) -> ModeOrchestratorConfig:
        """Create a test orchestrator config."""
        return ModeOrchestratorConfig(
            guards=GuardConfig(
                kappa=GuardBand(0.5, 0.8, 0.3),
                var=GuardBand(0.05, 0.1, 0.02),
                max_drawdown=GuardBand(0.1, 0.15, 0.05),
                heat=GuardBand(0.7, 0.9, 0.5),
            ),
            timeouts=TimeoutConfig(
                action_max=60.0,
                cooldown_min=30.0,
                rest_min=120.0,
                cooldown_persistence=90.0,
                safe_exit_lock=300.0,
            ),
            delays=DelayBudget(
                action_to_cooldown=0.01,
                cooldown_to_rest=0.05,
                protective_to_safe_exit=0.001,
            ),
            initial_state=ModeState.REST,
        )

    @pytest.fixture
    def orchestrator(
        self, orchestrator_config: ModeOrchestratorConfig
    ) -> ModeOrchestrator:
        """Create a test orchestrator."""
        return ModeOrchestrator(config=orchestrator_config)

    @pytest.fixture
    def healthy_metrics(self) -> MetricsSnapshot:
        """Create healthy metrics (below all soft limits)."""
        return MetricsSnapshot(
            kappa=0.2,
            var=0.01,
            max_drawdown=0.03,
            heat=0.4,
        )

    @pytest.fixture
    def soft_breach_metrics(self) -> MetricsSnapshot:
        """Create metrics with soft breach."""
        return MetricsSnapshot(
            kappa=0.6,  # Soft breach on kappa
            var=0.01,
            max_drawdown=0.03,
            heat=0.4,
        )

    @pytest.fixture
    def hard_breach_metrics(self) -> MetricsSnapshot:
        """Create metrics with hard breach."""
        return MetricsSnapshot(
            kappa=0.9,  # Hard breach on kappa
            var=0.01,
            max_drawdown=0.03,
            heat=0.4,
        )

    def test_initial_state(self, orchestrator: ModeOrchestrator) -> None:
        """Verify orchestrator starts in configured initial state."""
        assert orchestrator.state == ModeState.REST

    def test_reset(self, orchestrator: ModeOrchestrator) -> None:
        """Verify reset resets state and timestamps."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=100.0)

        assert orchestrator.state == ModeState.ACTION

    def test_snapshot(self, orchestrator: ModeOrchestrator) -> None:
        """Verify snapshot returns current state."""
        orchestrator.reset(timestamp=0.0)
        snapshot = orchestrator.snapshot()

        assert snapshot["state"] == "rest"
        assert "state_entered_at" in snapshot
        assert "last_timestamp" in snapshot

    def test_update_from_rest_to_action(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from REST to ACTION after rest_min elapsed."""
        orchestrator.reset(state=ModeState.REST, timestamp=0.0)

        # Update with healthy metrics after rest_min elapsed
        new_state = orchestrator.update(healthy_metrics, timestamp=125.0)

        assert new_state == ModeState.ACTION

    def test_update_remains_in_rest(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify remains in REST if rest_min not elapsed."""
        orchestrator.reset(state=ModeState.REST, timestamp=0.0)

        # Update before rest_min elapsed
        new_state = orchestrator.update(healthy_metrics, timestamp=50.0)

        assert new_state == ModeState.REST

    def test_update_action_to_cooldown_on_soft_breach(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from ACTION to COOLDOWN on soft breach."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)

        new_state = orchestrator.update(soft_breach_metrics, timestamp=1.0)

        assert new_state == ModeState.COOLDOWN

    def test_update_action_to_cooldown_on_timeout(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from ACTION to COOLDOWN after action_max elapsed."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)

        # Update after action_max elapsed
        new_state = orchestrator.update(healthy_metrics, timestamp=65.0)

        assert new_state == ModeState.COOLDOWN

    def test_update_hard_breach_to_safe_exit(
        self,
        orchestrator: ModeOrchestrator,
        hard_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify hard breach triggers immediate safe exit."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)

        new_state = orchestrator.update(hard_breach_metrics, timestamp=1.0)

        assert new_state == ModeState.SAFE_EXIT

    def test_update_cooldown_to_action_on_recovery(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from COOLDOWN to ACTION after recovery."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=0.0)

        # Update with healthy metrics after cooldown_min elapsed
        new_state = orchestrator.update(healthy_metrics, timestamp=35.0)

        assert new_state == ModeState.ACTION

    def test_update_cooldown_to_rest_on_persistence(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from COOLDOWN to REST after cooldown_persistence."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=0.0)

        # Update with soft breach metrics after cooldown_persistence elapsed
        new_state = orchestrator.update(soft_breach_metrics, timestamp=95.0)

        assert new_state == ModeState.REST

    def test_update_safe_exit_to_rest_after_lock(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify transition from SAFE_EXIT to REST after lock period."""
        orchestrator.reset(state=ModeState.SAFE_EXIT, timestamp=0.0)

        # Update with healthy metrics after safe_exit_lock elapsed
        new_state = orchestrator.update(healthy_metrics, timestamp=305.0)

        assert new_state == ModeState.REST

    def test_timestamp_regression_raises(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify timestamp regression raises ValueError."""
        orchestrator.reset(timestamp=100.0)
        orchestrator.update(healthy_metrics, timestamp=110.0)

        with pytest.raises(ValueError, match="Timestamp regression"):
            orchestrator.update(healthy_metrics, timestamp=105.0)

    def test_action_state_remains_with_healthy_metrics(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify ACTION remains if no breach and timeout not elapsed."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)

        new_state = orchestrator.update(healthy_metrics, timestamp=30.0)

        assert new_state == ModeState.ACTION

    def test_safe_exit_remains_if_not_recovered(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify SAFE_EXIT remains if not recovered even after lock."""
        orchestrator.reset(state=ModeState.SAFE_EXIT, timestamp=0.0)

        # Update with soft breach metrics after safe_exit_lock elapsed
        new_state = orchestrator.update(soft_breach_metrics, timestamp=305.0)

        assert new_state == ModeState.SAFE_EXIT

    def test_initial_state_entered_at_set_on_first_update(
        self,
        orchestrator: ModeOrchestrator,
        healthy_metrics: MetricsSnapshot,
    ) -> None:
        """Verify state_entered_at is set on first update if not set."""
        # Don't call reset to leave _state_entered_at as None
        orchestrator.update(healthy_metrics, timestamp=10.0)

        snapshot = orchestrator.snapshot()
        assert snapshot["state_entered_at"] == 10.0
