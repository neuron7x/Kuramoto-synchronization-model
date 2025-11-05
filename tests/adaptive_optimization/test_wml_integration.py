"""Integration tests for WML adaptive optimization system."""

import pytest
from core.adaptive_optimization.tacl_wml import (
    WMLConfig,
    RegimeDetector,
    WML,
    Telemetry,
    Regime,
)
from core.adaptive_optimization.tacl_wml.wml import TelemetryProbe
from core.adaptive_optimization.tacl_wml.actions import ActionPlan
from core.adaptive_optimization.tacl_wml.adapters.canary_probe import CanaryProbe


class MockProbe(TelemetryProbe):
    """Mock probe that returns predictable results based on myelin."""

    def measure_after(
        self, path: str, tentative_myelin: float, plan: ActionPlan
    ) -> Telemetry:
        """Return telemetry that improves with higher myelin."""
        # p99 and IS decrease as myelin increases
        base = 12.0 - 6.0 * tentative_myelin
        is_bp = max(0.0, 10.0 - 8.0 * tentative_myelin)

        return Telemetry(
            latency_ms=[base * 0.6, base * 0.8, base * 0.9, base],
            resource_cost=1.0,
            pnl_delta=0.0,
            vol_index=0.4,
            is_bp=is_bp,
        )


def test_wml_config_validation():
    """Test WML configuration validation."""
    cfg = WMLConfig()
    cfg.validate()  # Should not raise

    # Test invalid bounds
    cfg_invalid = WMLConfig()
    cfg_invalid.bounds = {"m_min": 1.5, "m_max": 1.0}
    with pytest.raises(AssertionError):
        cfg_invalid.validate()


def test_regime_detection():
    """Test regime detection based on telemetry."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)

    # CALM regime: low volatility
    t_calm = Telemetry([5, 6, 7, 8], 1.0, 0.0, 0.2, is_bp=0.0)
    assert detector.detect(t_calm) == Regime.CALM

    # VOLATILE regime: high volatility
    t_volatile = Telemetry([5, 6, 7, 8], 1.0, 0.0, 0.7, is_bp=0.0)
    assert detector.detect(t_volatile) == Regime.VOLATILE

    # SHOCK regime: extreme latency
    t_shock = Telemetry([25, 30, 35, 40], 1.0, 0.0, 0.5, is_bp=0.0)
    assert detector.detect(t_shock) == Regime.SHOCK


def test_wml_accepts_when_free_energy_drops():
    """Test that WML accepts optimization when free energy decreases."""
    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02)
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    # Start with poor performance
    t0 = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=10.0)

    # WML should accept optimization (MockProbe returns better metrics)
    assert wml.step("feature_pipe", t0, MockProbe()) is True


def test_wml_rejects_when_free_energy_increases():
    """Test that WML rejects optimization when free energy would increase."""

    class WorseProbe(TelemetryProbe):
        """Probe that returns worse performance."""

        def measure_after(self, path, tentative_myelin, plan):
            # Return worse performance than baseline
            return Telemetry([20, 25, 30, 35], 2.0, 0.0, 0.4, is_bp=20.0)

    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02)
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    # Start with decent performance
    t0 = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=5.0)

    # WML should reject (WorseProbe returns worse metrics)
    assert wml.step("feature_pipe", t0, WorseProbe()) is False


def test_wml_risk_freeze():
    """Test that WML respects risk freeze conditions."""
    cfg = WMLConfig(risk_freeze_enabled=True, gamma_is=0.05, eps_rel=0.02)

    # Create freeze function that always returns True
    def always_freeze():
        return True

    wml = WML(
        cfg,
        RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol),
        risk_freeze_fn=always_freeze,
    )

    # Even with good telemetry, should freeze
    t0 = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=10.0)
    assert wml.step("feature_pipe", t0, MockProbe()) is False


def test_wml_audit_logging():
    """Test that WML logs decisions to audit log."""
    from core.adaptive_optimization.tacl_wml import AuditLogger

    cfg = WMLConfig(gamma_is=0.05, eps_rel=0.02)
    audit = AuditLogger()
    wml = WML(
        cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol), audit=audit
    )

    t0 = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=10.0)
    wml.step("feature_pipe", t0, MockProbe())

    # Should have logged decision
    logs = audit.get_logs()
    assert len(logs) > 0
    assert logs[0]["event"] in ["WML_APPLY", "WML_REJECTED"]


def test_wml_plasticity_by_regime():
    """Test that plasticity parameters change by regime."""
    cfg = WMLConfig()
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    # CALM regime should have high plasticity
    calm_params = wml.schedule_params(Regime.CALM)
    assert calm_params["eta"] == 0.04

    # SHOCK regime should freeze learning
    shock_params = wml.schedule_params(Regime.SHOCK)
    assert shock_params["eta"] == 0.00


def test_wml_implementation_shortfall_tracking():
    """Test that IS is properly tracked and penalized."""
    cfg = WMLConfig(gamma_is=0.1, eps_rel=0.02)  # High IS penalty
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    # High IS should make free energy worse
    t_high_is = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=50.0)

    class HighISProbe(TelemetryProbe):
        def measure_after(self, path, m, plan):
            return Telemetry([9, 11, 14, 17], 1.0, 0.0, 0.4, is_bp=60.0)  # Higher IS

    # Should reject because IS is getting worse
    assert wml.step("order_execute", t_high_is, HighISProbe()) is False


def test_canary_probe_synthetic_mode():
    """Test synthetic canary probe."""
    probe = CanaryProbe(mode="synthetic")

    # High myelin should give better metrics
    result_low = probe.measure_after("test", 0.0, ActionPlan({}, {}, {}))
    result_high = probe.measure_after("test", 1.0, ActionPlan({}, {}, {}))

    assert result_high.p99 < result_low.p99
    assert result_high.is_bp < result_low.is_bp


def test_canary_probe_callable_mode():
    """Test callable canary probe."""
    call_count = [0]

    def test_fn():
        call_count[0] += 1

    probe = CanaryProbe(mode="callable", fn=test_fn, samples=10)
    result = probe.measure_after("test", 0.5, ActionPlan({}, {}, {}))

    # Should have called the function
    assert call_count[0] >= 10
    assert len(result.latency_ms) > 0


def test_wml_myelin_bounds():
    """Test that myelin stays within configured bounds."""
    cfg = WMLConfig()
    cfg.bounds = {"m_min": 0.2, "m_max": 0.8}
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    # Run multiple steps
    t = Telemetry([10, 12, 15, 18], 1.0, 0.1, 0.4, is_bp=5.0)
    for _ in range(10):
        wml.step("test_path", t, MockProbe())

    # Check myelin is within bounds
    state = wml.get_state("test_path")
    assert cfg.bounds["m_min"] <= state.myelin <= cfg.bounds["m_max"]


def test_wml_min_apply_interval():
    """Test minimum apply interval is respected."""
    cfg = WMLConfig(min_apply_interval_s=0.5, eps_rel=0.1)
    wml = WML(cfg, RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol))

    t = Telemetry([10, 12, 15, 18], 1.0, 0.0, 0.4, is_bp=5.0)

    # First step should apply
    result1 = wml.step("test_path", t, MockProbe())

    # Immediate second step should skip (within interval)
    result2 = wml.step("test_path", t, MockProbe())

    # At least one should have been skipped due to interval
    assert result1 or result2  # At least one succeeded
    if result1:
        assert not result2  # Second should be blocked by interval


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
