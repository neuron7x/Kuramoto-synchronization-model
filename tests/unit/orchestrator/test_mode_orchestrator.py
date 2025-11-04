"""Comprehensive tests for ModeOrchestrator state machine with hysteresis."""

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
def standard_guards() -> GuardConfig:
    """Standard guard configuration for testing."""
    return GuardConfig(
        kappa=GuardBand(soft_limit=0.7, hard_limit=0.9, recover_limit=0.5),
        var=GuardBand(soft_limit=0.02, hard_limit=0.05, recover_limit=0.01),
        max_drawdown=GuardBand(soft_limit=0.10, hard_limit=0.20, recover_limit=0.05),
        heat=GuardBand(soft_limit=0.6, hard_limit=0.8, recover_limit=0.4),
    )


@pytest.fixture
def standard_timeouts() -> TimeoutConfig:
    """Standard timeout configuration for testing."""
    return TimeoutConfig(
        action_max=300.0,
        cooldown_min=60.0,
        rest_min=120.0,
        cooldown_persistence=180.0,
        safe_exit_lock=600.0,
    )


@pytest.fixture
def standard_delays() -> DelayBudget:
    """Standard delay budget for testing."""
    return DelayBudget(
        action_to_cooldown=0.1,
        cooldown_to_rest=0.1,
        protective_to_safe_exit=0.05,
    )


@pytest.fixture
def orchestrator(
    standard_guards: GuardConfig,
    standard_timeouts: TimeoutConfig,
    standard_delays: DelayBudget,
) -> ModeOrchestrator:
    """Create a standard orchestrator instance."""
    config = ModeOrchestratorConfig(
        guards=standard_guards,
        timeouts=standard_timeouts,
        delays=standard_delays,
        initial_state=ModeState.REST,
    )
    return ModeOrchestrator(config=config)


@pytest.fixture
def safe_metrics() -> MetricsSnapshot:
    """Metrics representing a safe, healthy system."""
    return MetricsSnapshot(
        kappa=0.3,
        var=0.005,
        max_drawdown=0.02,
        heat=0.2,
    )


@pytest.fixture
def soft_breach_metrics() -> MetricsSnapshot:
    """Metrics with soft limit breaches."""
    return MetricsSnapshot(
        kappa=0.75,  # Above soft limit (0.7)
        var=0.015,   # Below all limits
        max_drawdown=0.08,  # Below all limits
        heat=0.5,    # Below all limits
    )


@pytest.fixture
def hard_breach_metrics() -> MetricsSnapshot:
    """Metrics with hard limit breaches."""
    return MetricsSnapshot(
        kappa=0.95,  # Above hard limit (0.9)
        var=0.008,
        max_drawdown=0.04,
        heat=0.3,
    )


class TestGuardBand:
    """Test GuardBand hysteresis logic."""

    def test_guard_band_soft_breach_detection(self) -> None:
        """Verify soft breach detection works correctly."""
        band = GuardBand(soft_limit=0.7, hard_limit=0.9, recover_limit=0.5)
        
        assert not band.is_soft_breach(0.6)
        assert band.is_soft_breach(0.7)
        assert band.is_soft_breach(0.8)
        assert band.is_soft_breach(1.0)

    def test_guard_band_hard_breach_detection(self) -> None:
        """Verify hard breach detection works correctly."""
        band = GuardBand(soft_limit=0.7, hard_limit=0.9, recover_limit=0.5)
        
        assert not band.is_hard_breach(0.8)
        assert band.is_hard_breach(0.9)
        assert band.is_hard_breach(1.0)

    def test_guard_band_recovery_detection(self) -> None:
        """Verify recovery detection works correctly."""
        band = GuardBand(soft_limit=0.7, hard_limit=0.9, recover_limit=0.5)
        
        assert band.is_recovered(0.4)
        assert band.is_recovered(0.5)
        assert not band.is_recovered(0.6)

    def test_guard_band_validation_rejects_invalid_ordering(self) -> None:
        """Verify guard band validation rejects invalid configurations."""
        with pytest.raises(ValueError, match="recover_limit ≤ soft_limit ≤ hard_limit"):
            GuardBand(soft_limit=0.7, hard_limit=0.5, recover_limit=0.9)

    def test_guard_band_validation_accepts_valid_ordering(self) -> None:
        """Verify guard band validation accepts valid configurations."""
        band = GuardBand(soft_limit=0.5, hard_limit=0.9, recover_limit=0.3)
        assert band.soft_limit == 0.5
        assert band.hard_limit == 0.9
        assert band.recover_limit == 0.3


class TestModeOrchestratorInitialization:
    """Test orchestrator initialization and state management."""

    def test_orchestrator_starts_in_configured_initial_state(self, orchestrator: ModeOrchestrator) -> None:
        """Verify orchestrator starts in the configured initial state."""
        assert orchestrator.state == ModeState.REST

    def test_orchestrator_can_start_in_action_mode(
        self,
        standard_guards: GuardConfig,
        standard_timeouts: TimeoutConfig,
        standard_delays: DelayBudget,
    ) -> None:
        """Verify orchestrator can start in ACTION mode."""
        config = ModeOrchestratorConfig(
            guards=standard_guards,
            timeouts=standard_timeouts,
            delays=standard_delays,
            initial_state=ModeState.ACTION,
        )
        orch = ModeOrchestrator(config=config)
        assert orch.state == ModeState.ACTION

    def test_orchestrator_reset_changes_state(self, orchestrator: ModeOrchestrator) -> None:
        """Verify reset() changes orchestrator state."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        assert orchestrator.state == ModeState.ACTION

    def test_orchestrator_snapshot_provides_debug_info(self, orchestrator: ModeOrchestrator) -> None:
        """Verify snapshot() returns useful debug information."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=10.0)
        snap = orchestrator.snapshot()
        
        assert snap["state"] == "action"
        assert snap["state_entered_at"] == 10.0
        assert snap["last_timestamp"] == 10.0


class TestModeTransitions:
    """Test mode transitions and state machine logic."""

    def test_action_to_cooldown_on_soft_breach(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify ACTION → COOLDOWN transition on soft breach."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        new_state = orchestrator.update(soft_breach_metrics, timestamp=1.0)
        
        assert new_state == ModeState.COOLDOWN

    def test_action_to_cooldown_on_timeout(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify ACTION → COOLDOWN transition after action_max timeout."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # Stay in ACTION for less than timeout
        state = orchestrator.update(safe_metrics, timestamp=100.0)
        assert state == ModeState.ACTION
        
        # Transition after timeout
        state = orchestrator.update(safe_metrics, timestamp=301.0)
        assert state == ModeState.COOLDOWN

    def test_cooldown_to_action_on_recovery(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify COOLDOWN → ACTION transition on recovery after min dwell."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=0.0)
        
        # Stay in COOLDOWN before min dwell
        state = orchestrator.update(safe_metrics, timestamp=30.0)
        assert state == ModeState.COOLDOWN
        
        # Transition after min dwell
        state = orchestrator.update(safe_metrics, timestamp=61.0)
        assert state == ModeState.ACTION

    def test_cooldown_to_rest_on_persistence(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify COOLDOWN → REST transition when metrics don't recover."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=0.0)
        
        # Stay in COOLDOWN before persistence timeout
        state = orchestrator.update(soft_breach_metrics, timestamp=100.0)
        assert state == ModeState.COOLDOWN
        
        # Transition after persistence timeout
        state = orchestrator.update(soft_breach_metrics, timestamp=181.0)
        assert state == ModeState.REST

    def test_rest_to_action_on_recovery(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify REST → ACTION transition after recovery and min dwell."""
        orchestrator.reset(state=ModeState.REST, timestamp=0.0)
        
        # Stay in REST before min dwell
        state = orchestrator.update(safe_metrics, timestamp=60.0)
        assert state == ModeState.REST
        
        # Transition after min dwell
        state = orchestrator.update(safe_metrics, timestamp=121.0)
        assert state == ModeState.ACTION

    def test_any_state_to_safe_exit_on_hard_breach(
        self,
        orchestrator: ModeOrchestrator,
        hard_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify immediate SAFE_EXIT transition on hard breach from any state."""
        for initial_state in [ModeState.ACTION, ModeState.COOLDOWN, ModeState.REST]:
            orchestrator.reset(state=initial_state, timestamp=0.0)
            
            new_state = orchestrator.update(hard_breach_metrics, timestamp=1.0)
            
            assert new_state == ModeState.SAFE_EXIT

    def test_safe_exit_to_rest_after_lock_and_recovery(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify SAFE_EXIT → REST transition after lock duration and recovery."""
        orchestrator.reset(state=ModeState.SAFE_EXIT, timestamp=0.0)
        
        # Stay in SAFE_EXIT before lock expires
        state = orchestrator.update(safe_metrics, timestamp=300.0)
        assert state == ModeState.SAFE_EXIT
        
        # Transition after lock expires
        state = orchestrator.update(safe_metrics, timestamp=601.0)
        assert state == ModeState.REST

    def test_safe_exit_stays_locked_without_recovery(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify SAFE_EXIT stays locked even after timeout if not recovered."""
        orchestrator.reset(state=ModeState.SAFE_EXIT, timestamp=0.0)
        
        state = orchestrator.update(soft_breach_metrics, timestamp=700.0)
        
        assert state == ModeState.SAFE_EXIT


class TestHysteresisAndBoundaryConditions:
    """Test hysteresis behavior and boundary conditions."""

    def test_hysteresis_prevents_rapid_oscillation(
        self,
        orchestrator: ModeOrchestrator,
    ) -> None:
        """Verify hysteresis prevents rapid oscillation at boundaries."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # Metrics slightly above soft limit
        metrics_above = MetricsSnapshot(kappa=0.71, var=0.005, max_drawdown=0.02, heat=0.2)
        # Metrics slightly below soft limit but above recover limit
        metrics_between = MetricsSnapshot(kappa=0.65, var=0.005, max_drawdown=0.02, heat=0.2)
        
        # Transition to COOLDOWN
        state = orchestrator.update(metrics_above, timestamp=1.0)
        assert state == ModeState.COOLDOWN
        
        # Stay in COOLDOWN even when metrics drop below soft limit
        # (because they're still above recover limit)
        state = orchestrator.update(metrics_between, timestamp=2.0)
        assert state == ModeState.COOLDOWN

    def test_exact_boundary_values_trigger_transitions(
        self,
        orchestrator: ModeOrchestrator,
    ) -> None:
        """Verify exact boundary values trigger appropriate transitions."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # Exactly at soft limit should trigger transition
        exact_soft = MetricsSnapshot(kappa=0.7, var=0.005, max_drawdown=0.02, heat=0.2)
        state = orchestrator.update(exact_soft, timestamp=1.0)
        assert state == ModeState.COOLDOWN


class TestTimestampValidation:
    """Test timestamp validation and monotonicity checks."""

    def test_timestamp_regression_raises_error(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify timestamp regression raises ValueError."""
        orchestrator.reset(state=ModeState.REST, timestamp=100.0)
        orchestrator.update(safe_metrics, timestamp=101.0)
        
        with pytest.raises(ValueError, match="Timestamp regression detected"):
            orchestrator.update(safe_metrics, timestamp=99.0)

    def test_equal_timestamps_allowed(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify equal timestamps are allowed (monotonic, not strictly increasing)."""
        orchestrator.reset(state=ModeState.REST, timestamp=100.0)
        
        state1 = orchestrator.update(safe_metrics, timestamp=100.0)
        state2 = orchestrator.update(safe_metrics, timestamp=100.0)
        
        assert state1 == ModeState.REST
        assert state2 == ModeState.REST

    def test_increasing_timestamps_accepted(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Verify increasing timestamps work correctly."""
        orchestrator.reset(state=ModeState.REST, timestamp=0.0)
        
        for t in [1.0, 2.0, 5.0, 10.0, 100.0]:
            orchestrator.update(safe_metrics, timestamp=t)
        
        # Should complete without errors


class TestMultipleGuardBreach:
    """Test behavior when multiple guards are breached simultaneously."""

    def test_multiple_soft_breaches_trigger_cooldown(
        self,
        orchestrator: ModeOrchestrator,
    ) -> None:
        """Verify multiple soft breaches trigger COOLDOWN."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # Multiple soft breaches
        multi_breach = MetricsSnapshot(
            kappa=0.75,    # Soft breach
            var=0.025,     # Soft breach
            max_drawdown=0.03,  # Below all limits
            heat=0.3,      # Below all limits
        )
        
        state = orchestrator.update(multi_breach, timestamp=1.0)
        assert state == ModeState.COOLDOWN

    def test_any_hard_breach_triggers_safe_exit(
        self,
        orchestrator: ModeOrchestrator,
    ) -> None:
        """Verify any single hard breach triggers SAFE_EXIT."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # Only heat has hard breach, others safe
        metrics = MetricsSnapshot(
            kappa=0.3,
            var=0.005,
            max_drawdown=0.02,
            heat=0.85,  # Hard breach
        )
        
        state = orchestrator.update(metrics, timestamp=1.0)
        assert state == ModeState.SAFE_EXIT

    def test_recovery_requires_all_guards_below_recover_limit(
        self,
        orchestrator: ModeOrchestrator,
    ) -> None:
        """Verify recovery requires ALL guards below recover limit."""
        orchestrator.reset(state=ModeState.COOLDOWN, timestamp=0.0)
        
        # One guard above recover limit
        partial_recovery = MetricsSnapshot(
            kappa=0.4,    # Below recover (0.5) ✓
            var=0.005,    # Below recover (0.01) ✓
            max_drawdown=0.03,  # Below recover (0.05) ✓
            heat=0.45,    # Above recover (0.4) ✗
        )
        
        # Should stay in COOLDOWN
        state = orchestrator.update(partial_recovery, timestamp=100.0)
        assert state == ModeState.COOLDOWN
        
        # Full recovery
        full_recovery = MetricsSnapshot(
            kappa=0.4,
            var=0.005,
            max_drawdown=0.03,
            heat=0.35,  # Now below recover
        )
        
        # Should transition after min dwell
        state = orchestrator.update(full_recovery, timestamp=200.0)
        assert state == ModeState.ACTION


class TestDelayBudgetValidation:
    """Test delay budget validation."""

    def test_negative_delay_budget_raises_error(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Verify negative delay budgets are rejected."""
        # Create orchestrator with negative delay
        config = ModeOrchestratorConfig(
            guards=orchestrator.config.guards,
            timeouts=orchestrator.config.timeouts,
            delays=DelayBudget(
                action_to_cooldown=-0.1,  # Negative
                cooldown_to_rest=0.1,
                protective_to_safe_exit=0.05,
            ),
            initial_state=ModeState.ACTION,
        )
        orch = ModeOrchestrator(config=config)
        
        with pytest.raises(ValueError, match="Delay budget cannot be negative"):
            orch.update(soft_breach_metrics, timestamp=1.0)


class TestEndToEndScenarios:
    """Test realistic end-to-end scenarios."""

    def test_complete_recovery_cycle(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
        soft_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Test complete cycle: ACTION → COOLDOWN → ACTION."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # 1. Start in ACTION with safe metrics
        state = orchestrator.update(safe_metrics, timestamp=10.0)
        assert state == ModeState.ACTION
        
        # 2. Soft breach triggers COOLDOWN
        state = orchestrator.update(soft_breach_metrics, timestamp=20.0)
        assert state == ModeState.COOLDOWN
        
        # 3. Stay in COOLDOWN briefly
        state = orchestrator.update(safe_metrics, timestamp=30.0)
        assert state == ModeState.COOLDOWN
        
        # 4. Recover after min dwell
        state = orchestrator.update(safe_metrics, timestamp=90.0)
        assert state == ModeState.ACTION

    def test_persistent_degradation_to_rest(
        self,
        orchestrator: ModeOrchestrator,
        soft_breach_metrics: MetricsSnapshot,
        safe_metrics: MetricsSnapshot,
    ) -> None:
        """Test cycle: ACTION → COOLDOWN → REST → ACTION."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # 1. Transition to COOLDOWN
        state = orchestrator.update(soft_breach_metrics, timestamp=1.0)
        assert state == ModeState.COOLDOWN
        
        # 2. Metrics don't recover, transition to REST
        state = orchestrator.update(soft_breach_metrics, timestamp=200.0)
        assert state == ModeState.REST
        
        # 3. Eventually recover
        state = orchestrator.update(safe_metrics, timestamp=350.0)
        assert state == ModeState.ACTION

    def test_hard_breach_emergency_shutdown(
        self,
        orchestrator: ModeOrchestrator,
        safe_metrics: MetricsSnapshot,
        hard_breach_metrics: MetricsSnapshot,
    ) -> None:
        """Test emergency shutdown: ACTION → SAFE_EXIT → REST."""
        orchestrator.reset(state=ModeState.ACTION, timestamp=0.0)
        
        # 1. Immediate transition to SAFE_EXIT
        state = orchestrator.update(hard_breach_metrics, timestamp=1.0)
        assert state == ModeState.SAFE_EXIT
        
        # 2. Stay locked in SAFE_EXIT
        state = orchestrator.update(safe_metrics, timestamp=300.0)
        assert state == ModeState.SAFE_EXIT
        
        # 3. Release after lock expires
        state = orchestrator.update(safe_metrics, timestamp=650.0)
        assert state == ModeState.REST
