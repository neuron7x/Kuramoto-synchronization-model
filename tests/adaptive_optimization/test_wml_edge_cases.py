"""Additional edge case and property-based tests for WML."""

import pytest
from hypothesis import given, strategies as st

from core.adaptive_optimization.tacl_wml import (
    WMLConfig,
    RegimeDetector,
    WML,
    Telemetry,
    Regime,
)
from core.adaptive_optimization.tacl_wml.metrics import percentile
from core.adaptive_optimization.tacl_wml.mfe import free_energy


class TestPercentileEdgeCases:
    """Test edge cases for percentile calculation."""

    def test_percentile_empty_list(self):
        """Test percentile with empty list."""
        assert percentile([], 50) == 0.0

    def test_percentile_single_value(self):
        """Test percentile with single value."""
        assert percentile([5.0], 50) == 5.0
        assert percentile([5.0], 99) == 5.0

    def test_percentile_two_values(self):
        """Test percentile with two values."""
        result = percentile([1.0, 2.0], 50)
        assert 1.0 <= result <= 2.0

    def test_percentile_invalid_range(self):
        """Test percentile with invalid percentile value."""
        with pytest.raises(ValueError):
            percentile([1, 2, 3], -1)
        with pytest.raises(ValueError):
            percentile([1, 2, 3], 101)

    @given(
        values=st.lists(
            st.floats(
                min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
            min_size=1,
            max_size=100,
        ),
        p=st.floats(min_value=0.0, max_value=100.0),
    )
    def test_percentile_properties(self, values, p):
        """Property-based test: percentile result should be within data range."""
        result = percentile(values, p)
        # Allow small floating-point tolerance
        assert min(values) - 1e-10 <= result <= max(values) + 1e-10


class TestTelemetryValidation:
    """Test telemetry validation and edge cases."""

    def test_telemetry_empty_latency_raises(self):
        """Test that empty latency list raises ValueError."""
        with pytest.raises(ValueError, match="latency_ms cannot be empty"):
            Telemetry([], 1.0, 0.0, 0.5, is_bp=0.0)

    def test_telemetry_negative_values_normalized(self):
        """Test that negative values are normalized to zero."""
        t = Telemetry([-5, 10, 15], -1.0, 0.0, -0.5, is_bp=-10.0)
        assert all(x >= 0 for x in t.latency_ms)
        assert t.resource_cost >= 0
        assert t.vol_index >= 0
        assert t.is_bp >= 0

    def test_telemetry_mean_property(self):
        """Test mean latency calculation."""
        t = Telemetry([10, 20, 30], 1.0, 0.0, 0.5)
        assert t.mean == 20.0

    @given(
        latencies=st.lists(
            st.floats(
                min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),
            min_size=1,
            max_size=50,
        ),
        resource_cost=st.floats(min_value=0.0, max_value=10.0),
        pnl_delta=st.floats(min_value=-1.0, max_value=1.0),
        vol_index=st.floats(min_value=0.0, max_value=1.0),
        is_bp=st.floats(min_value=0.0, max_value=100.0),
    )
    def test_telemetry_creation_properties(
        self, latencies, resource_cost, pnl_delta, vol_index, is_bp
    ):
        """Property-based test: Telemetry should always be created successfully."""
        t = Telemetry(latencies, resource_cost, pnl_delta, vol_index, is_bp)
        assert t.p99 >= t.p50 >= 0
        assert t.jitter >= 0
        assert t.mean >= 0


class TestConfigValidation:
    """Test configuration validation with edge cases."""

    def test_config_invalid_bounds_order(self):
        """Test config with m_min > m_max."""
        cfg = WMLConfig()
        cfg.bounds = {"m_min": 0.8, "m_max": 0.2}
        with pytest.raises(ValueError, match="Invalid myelin bounds"):
            cfg.validate()

    def test_config_invalid_bounds_range(self):
        """Test config with bounds outside [0, 1]."""
        cfg = WMLConfig()
        cfg.bounds = {"m_min": -0.1, "m_max": 0.5}
        with pytest.raises(ValueError, match="Invalid myelin bounds"):
            cfg.validate()

        cfg.bounds = {"m_min": 0.5, "m_max": 1.5}
        with pytest.raises(ValueError, match="Invalid myelin bounds"):
            cfg.validate()

    def test_config_negative_margin(self):
        """Test config with negative margin."""
        cfg = WMLConfig()
        cfg.mfe_margin = -0.1
        with pytest.raises(ValueError, match="mfe_margin must be non-negative"):
            cfg.validate()

    def test_config_invalid_eps_rel(self):
        """Test config with invalid eps_rel."""
        cfg = WMLConfig()
        cfg.eps_rel = -0.1
        with pytest.raises(ValueError, match="eps_rel must be in range"):
            cfg.validate()

        cfg.eps_rel = 1.0
        with pytest.raises(ValueError, match="eps_rel must be in range"):
            cfg.validate()

    def test_config_negative_gamma_is(self):
        """Test config with negative gamma_is."""
        cfg = WMLConfig()
        cfg.gamma_is = -0.1
        with pytest.raises(ValueError, match="gamma_is must be non-negative"):
            cfg.validate()

    def test_config_zero_auto_freeze_fails(self):
        """Test config with zero auto_freeze_fails."""
        cfg = WMLConfig()
        cfg.auto_freeze_fails = 0
        with pytest.raises(ValueError, match="auto_freeze_fails must be at least 1"):
            cfg.validate()


class TestFreeEnergyProperties:
    """Test free energy calculation properties."""

    def test_free_energy_increases_with_worse_metrics(self):
        """Test that free energy increases with worse performance."""
        t_good = Telemetry([5, 6, 7, 8], 0.5, 0.0, 0.4, is_bp=2.0)
        t_bad = Telemetry([15, 20, 25, 30], 1.5, 0.0, 0.4, is_bp=10.0)

        f_good = free_energy(t_good, 0.5, 0.3, 0.02)
        f_bad = free_energy(t_bad, 0.5, 0.3, 0.02)

        assert f_bad > f_good

    def test_free_energy_is_weighted_sum(self):
        """Test that free energy is proper weighted sum."""
        t = Telemetry([10, 12, 15, 20], 2.0, 0.0, 0.5, is_bp=5.0)
        alpha, beta, gamma = 0.5, 0.3, 0.02

        f = free_energy(t, alpha, beta, gamma)
        expected = t.p99 + alpha * t.jitter + beta * t.resource_cost + gamma * t.is_bp

        assert abs(f - expected) < 1e-10

    @given(
        alpha=st.floats(min_value=0.0, max_value=1.0),
        beta=st.floats(min_value=0.0, max_value=1.0),
        gamma=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_free_energy_non_negative_with_positive_weights(self, alpha, beta, gamma):
        """Property test: free energy should be non-negative with valid inputs."""
        t = Telemetry([10, 12, 15, 20], 1.0, 0.0, 0.5, is_bp=5.0)
        f = free_energy(t, alpha, beta, gamma)
        assert f >= 0


@pytest.mark.parametrize(
    "vol_index,expected_regime",
    [
        (0.1, Regime.CALM),
        (0.25, Regime.CALM),
        (0.29, Regime.CALM),  # Just below boundary
        (0.3, Regime.TREND),  # Boundary - exactly at threshold
        (0.4, Regime.TREND),
        (0.5, Regime.TREND),
        (0.59, Regime.TREND),  # Just below boundary
        (0.6, Regime.VOLATILE),  # Boundary
        (0.7, Regime.VOLATILE),
        (0.9, Regime.VOLATILE),
    ],
)
def test_regime_detection_parametrized(vol_index, expected_regime):
    """Parametrized test for regime detection boundaries."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)
    t = Telemetry([5, 6, 7, 8], 1.0, 0.0, vol_index, is_bp=0.0)
    regime = detector.detect(t)
    assert regime == expected_regime


@pytest.mark.parametrize(
    "latencies,expected_regime,description",
    [
        ([5, 6, 7, 8], Regime.TREND, "Normal latencies - below SHOCK thresholds"),
        ([5, 10, 20, 25], Regime.SHOCK, "High p99 (25 > 20) triggers SHOCK"),
        ([5, 5, 5, 16], Regime.SHOCK, "High jitter triggers SHOCK"),
        ([25, 28, 30, 35], Regime.SHOCK, "Both p99 and jitter high"),
    ],
)
def test_shock_regime_detection_parametrized(latencies, expected_regime, description):
    """Parametrized test for SHOCK regime detection."""
    cfg = WMLConfig()
    detector = RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol)

    t = Telemetry(latencies, 1.0, 0.0, 0.5, is_bp=0.0)
    regime = detector.detect(t)

    # Add diagnostic info
    msg = (
        f"{description}: p99={t.p99:.1f}, jitter={t.jitter:.1f}, "
        f"expected={expected_regime}, got={regime}"
    )
    assert regime == expected_regime, msg


class TestWMLErrorHandling:
    """Test WML error handling and logging."""

    def test_wml_logs_apply_errors(self):
        """Test that WML logs errors during apply."""
        from core.adaptive_optimization.tacl_wml import AuditLogger
        from core.adaptive_optimization.tacl_wml.actions import Action

        class FailingAction(Action):
            def apply(self, path, plan):
                raise RuntimeError("Intentional failure")

            def rollback(self, path, plan):
                pass

        cfg = WMLConfig(auto_freeze_fails=3, eps_rel=0.1)
        audit = AuditLogger()
        wml = WML(
            cfg,
            RegimeDetector(cfg.regime_thresholds, cfg.hysteresis_vol),
            actions=FailingAction(),
            audit=audit,
        )

        from core.adaptive_optimization.tacl_wml.adapters.canary_probe import (
            CanaryProbe,
        )

        probe = CanaryProbe(mode="synthetic")
        t = Telemetry([10, 12, 15, 18], 1.0, 0.1, 0.4, is_bp=5.0)

        # First failure should log error
        wml.step("test_path", t, probe)

        logs = audit.get_logs()
        error_logs = [log for log in logs if log["event"] == "WML_APPLY_ERROR"]
        assert len(error_logs) > 0
        assert error_logs[0]["data"]["error_type"] == "RuntimeError"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
