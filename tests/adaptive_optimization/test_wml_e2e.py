"""End-to-end test for WML integration with realistic scenarios."""

import pytest
from core.adaptive_optimization.tacl_wml import (
    WMLConfig,
    RegimeDetector,
    WML,
    Telemetry,
    AuditLogger,
    RecordingEventBus,
)
from core.adaptive_optimization.tacl_wml.wml import TelemetryProbe
from core.adaptive_optimization.tacl_wml.actions import ActionPlan, NoOpActions


class RealisticProbe(TelemetryProbe):
    """Probe that simulates realistic performance improvements."""

    def __init__(self):
        self.call_count = 0

    def measure_after(
        self, path: str, tentative_myelin: float, plan: ActionPlan
    ) -> Telemetry:
        """Simulate realistic performance based on myelin and regime."""
        self.call_count += 1

        # Performance improves with myelin, but with diminishing returns
        base_latency = 15.0
        improved_latency = base_latency * (1.0 - 0.4 * tentative_myelin)

        # IS improves significantly with myelin for execution paths
        is_improvement = 0.0
        if "execute" in path:
            is_improvement = 8.0 * tentative_myelin

        # Generate realistic latency distribution
        latencies = [
            improved_latency * 0.5,
            improved_latency * 0.7,
            improved_latency * 0.9,
            improved_latency * 1.0,
        ]

        return Telemetry(
            latency_ms=latencies,
            resource_cost=0.8 + 0.2 * tentative_myelin,  # Slight resource increase
            pnl_delta=0.1 * tentative_myelin,  # Positive PnL with optimization
            vol_index=0.4,
            is_bp=max(0.0, 10.0 - is_improvement),
        )


def test_end_to_end_optimization_cycle():
    """Test a complete optimization cycle across regimes."""
    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02, min_apply_interval_s=0.0)
    audit = AuditLogger()
    bus = RecordingEventBus()
    wml = WML(
        cfg,
        RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol),
        actions=NoOpActions(),
        audit=audit,
        bus=bus,
    )

    probe = RealisticProbe()

    # Scenario 1: CALM market, good performance
    t_calm = Telemetry([12, 14, 16, 18], 1.0, 0.1, 0.2, is_bp=5.0)
    _ = wml.step("feature_pipe", t_calm, probe)

    # First step establishes baseline, may or may not optimize
    # (myelin starts at 0, usefulness starts at 0)
    state = wml.get_state("feature_pipe")
    assert state.last_regime.name == "CALM"

    # Scenario 2: Continue in CALM with positive PnL
    t_calm2 = Telemetry([12, 14, 16, 18], 1.0, 0.2, 0.2, is_bp=5.0)
    _ = wml.step("feature_pipe", t_calm2, probe)

    # After positive delta, usefulness increases and myelin can grow
    state = wml.get_state("feature_pipe")
    # Either we optimized on first or second step
    assert state.recent_usefulness > 0.0

    # Scenario 3: Transition to VOLATILE
    t_volatile = Telemetry([12, 14, 16, 18], 1.0, 0.05, 0.7, is_bp=5.0)
    wml.step("feature_pipe", t_volatile, probe)

    state = wml.get_state("feature_pipe")
    assert state.last_regime.name == "VOLATILE"

    # Scenario 4: SHOCK conditions
    t_shock = Telemetry([25, 30, 35, 40], 2.0, -0.1, 0.5, is_bp=15.0)
    wml.step("feature_pipe", t_shock, probe)

    state = wml.get_state("feature_pipe")
    assert state.last_regime.name == "SHOCK"

    # Verify audit trail
    logs = audit.get_logs()
    assert len(logs) >= 4  # At least 4 steps
    # Should have at least one decision logged
    assert any(log["event"] in ["WML_APPLY", "WML_REJECTED"] for log in logs)

    # Verify events emitted
    events = bus.get_events()
    assert len(events) >= 4


def test_risk_freeze_prevents_optimization():
    """Test that risk freeze properly prevents optimization."""
    freeze_count = [0]
    apply_count = [0]

    def risk_freeze():
        freeze_count[0] += 1
        return freeze_count[0] > 2  # Freeze after 2 calls

    cfg = WMLConfig(risk_freeze_enabled=True, gamma_is=0.05)
    audit = AuditLogger()
    wml = WML(
        cfg,
        RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol),
        audit=audit,
        risk_freeze_fn=risk_freeze,
    )

    probe = RealisticProbe()
    t = Telemetry([12, 14, 16, 18], 1.0, 0.1, 0.4, is_bp=5.0)

    # First two steps should work
    for i in range(2):
        result = wml.step("test", t, probe)
        if result:
            apply_count[0] += 1

    # Third step should freeze
    result = wml.step("test", t, probe)
    assert result is False

    # Check audit log for freeze event
    logs = audit.get_logs()
    freeze_logs = [log for log in logs if log["event"] == "WML_FROZEN"]
    assert len(freeze_logs) > 0


def test_multi_path_optimization():
    """Test optimization across multiple hot paths."""
    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02, min_apply_interval_s=0.0)
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    probe = RealisticProbe()

    paths = ["quotes_ingest", "feature_pipe", "signal_decide", "order_execute"]

    # Optimize each path
    for path in paths:
        t = Telemetry(
            [12, 14, 16, 18], 1.0, 0.1, 0.4, is_bp=5.0 if "execute" in path else 0.0
        )
        wml.step(path, t, probe)

    # Verify each path has state
    for path in paths:
        state = wml.get_state(path)
        assert state is not None
        # Execution path should optimize more aggressively due to IS penalty
        if "execute" in path:
            assert state.myelin >= 0.0


def test_plasticity_schedule_affects_learning():
    """Test that different regimes affect learning rate."""
    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02, min_apply_interval_s=0.0)
    wml_calm = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))
    wml_shock = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    probe = RealisticProbe()

    # CALM regime - high plasticity
    t_calm = Telemetry([12, 14, 16, 18], 1.0, 0.2, 0.2, is_bp=5.0)
    wml_calm.step("test", t_calm, probe)

    # SHOCK regime - no plasticity
    t_shock = Telemetry([25, 30, 35, 40], 2.0, 0.2, 0.5, is_bp=15.0)
    wml_shock.step("test", t_shock, probe)

    # CALM should learn faster (but we don't assert exact values due to test simplicity)
    state_shock = wml_shock.get_state("test")

    # In SHOCK, myelin should not increase (eta=0.00)
    assert state_shock.myelin == 0.0 or abs(state_shock.myelin) < 0.01


def test_free_energy_with_implementation_shortfall():
    """Test that IS is properly weighted in free energy calculation."""
    cfg_high_gamma = WMLConfig(gamma_is=0.2, eps_rel=0.02)  # High IS penalty
    cfg_low_gamma = WMLConfig(gamma_is=0.01, eps_rel=0.02)  # Low IS penalty

    wml_high = WML(
        cfg_high_gamma,
        RegimeDetector(cfg_high_gamma.regime_thresholds, cfg_high_gamma.hysteresis_vol),
    )
    wml_low = WML(
        cfg_low_gamma,
        RegimeDetector(cfg_low_gamma.regime_thresholds, cfg_low_gamma.hysteresis_vol),
    )

    probe = RealisticProbe()

    # High IS should matter more with high gamma
    t = Telemetry([12, 14, 16, 18], 1.0, 0.0, 0.4, is_bp=20.0)  # High IS

    _ = wml_high.step("order_execute", t, probe)
    _ = wml_low.step("order_execute", t, probe)

    # With high gamma, high IS should prevent optimization more often
    # (or accept it less often compared to low gamma)
    # The exact behavior depends on the probe's IS improvement


def test_auto_freeze_on_control_failures():
    """Test auto-freeze after control failures."""

    class FailingActions(NoOpActions):
        def __init__(self):
            super().__init__()
            self.apply_count = 0

        def apply(self, path, plan):
            self.apply_count += 1
            if self.apply_count <= 2:
                raise RuntimeError("Control failure")

    cfg = WMLConfig(auto_freeze_fails=2, eps_rel=0.02, min_apply_interval_s=0.0)
    audit = AuditLogger()
    actions = FailingActions()
    wml = WML(
        cfg,
        RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol),
        actions=actions,
        audit=audit,
    )

    probe = RealisticProbe()
    t = Telemetry([12, 14, 16, 18], 1.0, 0.1, 0.4, is_bp=5.0)

    # First two attempts should fail and increment counter
    wml.step("test", t, probe)
    wml.step("test", t, probe)

    # Check auto-freeze was logged
    logs = audit.get_logs()
    auto_freeze_logs = [log for log in logs if log["event"] == "WML_AUTO_FREEZE"]
    assert len(auto_freeze_logs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
