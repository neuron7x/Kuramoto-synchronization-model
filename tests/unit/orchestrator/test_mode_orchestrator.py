# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive tests for mode orchestration state machine.

Tests cover deterministic state transitions, hysteresis behavior,
timeout enforcement, and guard band logic.
"""

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


@pytest.fixture
def guard_band():
    """Create a standard guard band for testing."""
    return GuardBand(
        soft_limit=0.7,
        hard_limit=0.9,
        recover_limit=0.5,
    )


@pytest.fixture
def guard_config():
    """Create guard configuration for all metrics."""
    band = GuardBand(soft_limit=0.7, hard_limit=0.9, recover_limit=0.5)
    return GuardConfig(
        kappa=band,
        var=band,
        max_drawdown=band,
        heat=band,
    )


@pytest.fixture
def timeout_config():
    """Create timeout configuration."""
    return TimeoutConfig(
        action_max=60.0,
        cooldown_min=30.0,
        rest_min=45.0,
        cooldown_persistence=15.0,
        safe_exit_lock=120.0,
    )


@pytest.fixture
def delay_budget():
    """Create delay budget configuration."""
    return DelayBudget(
        action_to_cooldown=0.1,
        cooldown_to_rest=0.1,
        protective_to_safe_exit=0.05,
    )


@pytest.fixture
def orchestrator_config(guard_config, timeout_config, delay_budget):
    """Create complete orchestrator configuration."""
    return ModeOrchestratorConfig(
        guards=guard_config,
        timeouts=timeout_config,
        delays=delay_budget,
        initial_state=ModeState.REST,
    )


@pytest.fixture
def orchestrator(orchestrator_config):
    """Create mode orchestrator instance."""
    return ModeOrchestrator(config=orchestrator_config)


@pytest.fixture
def safe_metrics():
    """Create metrics snapshot with all values safe."""
    return MetricsSnapshot(
        kappa=0.3,
        var=0.2,
        max_drawdown=0.1,
        heat=0.4,
    )


@pytest.fixture
def soft_breach_metrics():
    """Create metrics snapshot with soft breach."""
    return MetricsSnapshot(
        kappa=0.75,  # Above soft limit
        var=0.2,
        max_drawdown=0.1,
        heat=0.4,
    )


@pytest.fixture
def hard_breach_metrics():
    """Create metrics snapshot with hard breach."""
    return MetricsSnapshot(
        kappa=0.95,  # Above hard limit
        var=0.2,
        max_drawdown=0.1,
        heat=0.4,
    )


class TestGuardBand:
    """Tests for GuardBand hysteresis logic."""

    def test_guard_band_initialization(self, guard_band):
        """Test GuardBand initialization with valid limits."""
        assert guard_band.soft_limit == 0.7
        assert guard_band.hard_limit == 0.9
        assert guard_band.recover_limit == 0.5

    def test_guard_band_invalid_ordering(self):
        """Test that invalid limit ordering raises error."""
        with pytest.raises(ValueError, match="recover_limit ≤ soft_limit ≤ hard_limit"):
            GuardBand(
                soft_limit=0.5,
                hard_limit=0.3,  # Invalid: hard < soft
                recover_limit=0.2,
            )

    def test_is_soft_breach(self, guard_band):
        """Test soft limit breach detection."""
        assert guard_band.is_soft_breach(0.7) is True  # At limit
        assert guard_band.is_soft_breach(0.75) is True  # Above limit
        assert guard_band.is_soft_breach(0.65) is False  # Below limit

    def test_is_hard_breach(self, guard_band):
        """Test hard limit breach detection."""
        assert guard_band.is_hard_breach(0.9) is True  # At limit
        assert guard_band.is_hard_breach(0.95) is True  # Above limit
        assert guard_band.is_hard_breach(0.85) is False  # Below limit

    def test_is_recovered(self, guard_band):
        """Test recovery detection."""
        assert guard_band.is_recovered(0.5) is True  # At limit
        assert guard_band.is_recovered(0.4) is True  # Below limit
        assert guard_band.is_recovered(0.6) is False  # Above limit

    def test_hysteresis_band(self, guard_band):
        """Test that hysteresis creates proper band between soft and recover."""
        # Value in hysteresis band
        value = 0.6  # Between recover (0.5) and soft (0.7)
        
        assert not guard_band.is_soft_breach(value)
        assert not guard_band.is_recovered(value)


class TestGuardConfig:
    """Tests for GuardConfig container."""

    def test_guard_config_initialization(self, guard_config):
        """Test GuardConfig with all guard bands."""
        assert guard_config.kappa.soft_limit == 0.7
        assert guard_config.var.soft_limit == 0.7
        assert guard_config.max_drawdown.soft_limit == 0.7
        assert guard_config.heat.soft_limit == 0.7


class TestTimeoutConfig:
    """Tests for TimeoutConfig."""

    def test_timeout_config_values(self, timeout_config):
        """Test timeout configuration values."""
        assert timeout_config.action_max == 60.0
        assert timeout_config.cooldown_min == 30.0
        assert timeout_config.rest_min == 45.0
        assert timeout_config.cooldown_persistence == 15.0
        assert timeout_config.safe_exit_lock == 120.0


class TestDelayBudget:
    """Tests for DelayBudget configuration."""

    def test_delay_budget_values(self, delay_budget):
        """Test delay budget values."""
        assert delay_budget.action_to_cooldown == 0.1
        assert delay_budget.cooldown_to_rest == 0.1
        assert delay_budget.protective_to_safe_exit == 0.05


class TestMetricsSnapshot:
    """Tests for MetricsSnapshot."""

    def test_metrics_snapshot_creation(self):
        """Test creating metrics snapshot."""
        metrics = MetricsSnapshot(
            kappa=0.5,
            var=0.3,
            max_drawdown=0.2,
            heat=0.4,
        )
        assert metrics.kappa == 0.5
        assert metrics.var == 0.3
        assert metrics.max_drawdown == 0.2
        assert metrics.heat == 0.4


class TestModeOrchestratorInitialization:
    """Tests for ModeOrchestrator initialization."""

    def test_initial_state_default(self, orchestrator):
        """Test orchestrator starts in configured initial state."""
        assert orchestrator.state == ModeState.REST

    def test_initial_state_custom(self, orchestrator_config):
        """Test orchestrator with custom initial state."""
        config = ModeOrchestratorConfig(
            guards=orchestrator_config.guards,
            timeouts=orchestrator_config.timeouts,
            delays=orchestrator_config.delays,
            initial_state=ModeState.ACTION,
        )
        orch = ModeOrchestrator(config=config)
        assert orch.state == ModeState.ACTION

    def test_reset_to_default(self, orchestrator):
        """Test reset to default initial state."""
        # Change state
        orchestrator._state = ModeState.ACTION
        
        # Reset
        orchestrator.reset(timestamp=10.0)
        
        assert orchestrator.state == ModeState.REST
        assert orchestrator._state_entered_at == 10.0
        assert orchestrator._last_timestamp == 10.0

    def test_reset_to_custom_state(self, orchestrator):
        """Test reset to specific state."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=20.0)
        
        assert orchestrator.state == ModeState.COOLDOWN
        assert orchestrator._state_entered_at == 20.0

    def test_snapshot_initial(self, orchestrator):
        """Test snapshot of initial orchestrator state."""
        snapshot = orchestrator.snapshot()
        
        assert snapshot["state"] == ModeState.REST.value
        assert snapshot["state_entered_at"] is None
        assert snapshot["last_timestamp"] is None


class TestModeOrchestratorBasicOperations:
    """Tests for basic orchestrator operations."""

    def test_first_update_initializes_timestamp(self, orchestrator, safe_metrics):
        """Test first update initializes timestamps."""
        orchestrator.update(safe_metrics, timestamp=0.0)
        
        assert orchestrator._state_entered_at == 0.0
        assert orchestrator._last_timestamp == 0.0

    def test_snapshot_after_update(self, orchestrator, safe_metrics):
        """Test snapshot reflects state after update."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=100.0)
        orchestrator.update(safe_metrics, timestamp=110.0)
        
        snapshot = orchestrator.snapshot()
        assert snapshot["state"] == orchestrator.state.value
        assert snapshot["last_timestamp"] == 110.0

    def test_state_property(self, orchestrator):
        """Test state property returns current state."""
        assert orchestrator.state == ModeState.REST
        
        orchestrator._state = ModeState.ACTION
        assert orchestrator.state == ModeState.ACTION


class TestModeOrchestratorDeterminism:
    """Tests for deterministic behavior."""

    def test_deterministic_sequence(self, orchestrator_config, safe_metrics):
        """Test that same input sequence produces same output."""
        # Run sequence twice
        results1 = []
        orch1 = ModeOrchestrator(config=orchestrator_config)
        orch1.reset(timestamp=0.0)
        
        for t in [0.0, 10.0, 20.0, 30.0]:
            state = orch1.update(safe_metrics, timestamp=t)
            results1.append(state)
        
        results2 = []
        orch2 = ModeOrchestrator(config=orchestrator_config)
        orch2.reset(timestamp=0.0)
        
        for t in [0.0, 10.0, 20.0, 30.0]:
            state = orch2.update(safe_metrics, timestamp=t)
            results2.append(state)
        
        assert results1 == results2

    def test_reset_restores_determinism(
        self, orchestrator, safe_metrics, soft_breach_metrics
    ):
        """Test that reset allows repeatable sequences."""
        # First run
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        orchestrator.update(soft_breach_metrics, timestamp=0.05)
        state1 = orchestrator.state
        
        # Reset and repeat
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        orchestrator.update(soft_breach_metrics, timestamp=0.05)
        state2 = orchestrator.state
        
        assert state1 == state2
