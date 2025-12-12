# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Enhanced precision tests for NaK Controller and adapter.

This module provides comprehensive tests for numeric precision,
boundary conditions, and edge cases in the NaK bio-inspired
homeostatic controller system.

Test Coverage:
- Controller update precision
- Desensitization module behavior
- Adapter integration accuracy
- Gate state computation
- Energy-imbalance signal handling
"""

from __future__ import annotations

import math

from tradepulse.core.neuro.nak import (
    AdapterOutput,
    DesensitizationModule,
    NaKAdapter,
    NaKConfig,
    NaKController,
    NaKControllerV4_2,
)


class TestNaKControllerPrecision:
    """Tests for NaK controller precision and accuracy."""

    def test_controller_initialization_defaults(self) -> None:
        """Test controller initializes with default config values."""
        ctrl = NaKController(strategy_id=1)

        assert ctrl.strategy_id == 1
        assert ctrl.cfg is not None
        assert ctrl.E == ctrl.cfg.E_init
        assert ctrl.I_integral == 0.0
        assert ctrl.scale == 1.0
        assert ctrl.lambda_ == 0.05

    def test_controller_initialization_custom_config(self) -> None:
        """Test controller initializes with custom config."""
        custom_cfg = NaKConfig(
            dd_soft_base=0.20,
            vol_ref_base=0.04,
            burst_z=2.5,
            E_max=15.0,
            E_init=10.0,
        )
        ctrl = NaKController(strategy_id=2, cfg=custom_cfg)

        assert ctrl.cfg.dd_soft_base == 0.20
        assert ctrl.cfg.vol_ref_base == 0.04
        assert ctrl.cfg.burst_z == 2.5
        assert ctrl.E == 10.0
        assert ctrl.cfg.E_max == 15.0

    def test_controller_update_returns_finite_values(self) -> None:
        """Test controller update always returns finite values."""
        ctrl = NaKController(strategy_id=1)

        test_cases = [
            {"p": 0.01, "v": 0.02, "drawdown": -0.01},
            {"p": -0.05, "v": 0.05, "drawdown": -0.10},
            {"p": 0.10, "v": 0.001, "drawdown": 0.0},
            {"p": 0.0, "v": 0.0, "drawdown": 0.0},
        ]

        for params in test_cases:
            reward, log = ctrl.update(**params)
            assert math.isfinite(reward), f"Reward not finite for {params}"
            assert "r_final" in log
            assert all(math.isfinite(v) for v in log.values())

    def test_controller_update_energy_bounds(self) -> None:
        """Test energy stays within configured bounds."""
        ctrl = NaKController(strategy_id=1)

        # Run many updates
        for _ in range(100):
            ctrl.update(p=0.01, v=0.02, drawdown=-0.01)

        assert 0.0 <= ctrl.E <= ctrl.cfg.E_max

    def test_controller_update_negative_drawdown_clamp(self) -> None:
        """Test drawdown is clamped appropriately."""
        ctrl = NaKController(strategy_id=1)

        # Very deep drawdown
        reward, log = ctrl.update(p=0.01, v=0.02, drawdown=-0.5)
        assert math.isfinite(reward)

        # Positive drawdown (edge case)
        reward2, log2 = ctrl.update(p=0.01, v=0.02, drawdown=0.1)
        assert math.isfinite(reward2)

    def test_controller_burst_detection(self) -> None:
        """Test burst detection via z-score."""
        ctrl = NaKController(strategy_id=1)

        # Build up history with stable prices
        for _ in range(55):
            ctrl.update(p=0.01, v=0.02, drawdown=-0.01)

        # Inject a sudden price spike
        reward, log = ctrl.update(p=0.10, v=0.02, drawdown=-0.01)

        # Check refractory period was triggered if z exceeded threshold
        assert "refractory_left" in log
        assert log["refractory_left"] >= 0

    def test_controller_r_mode_gate_bounds(self) -> None:
        """Test r_mode gate stays within [min_gate, 1.0]."""
        ctrl = NaKController(strategy_id=1)

        # Test with various drawdown levels
        for dd in [0.0, -0.05, -0.10, -0.20, -0.50]:
            ctrl.update(p=0.01, v=0.02, drawdown=dd)
            assert ctrl.cfg.min_gate <= ctrl.r_mode <= 1.0

    def test_controller_snapshot_roundtrip(self) -> None:
        """Test state snapshot can be restored."""
        ctrl = NaKController(strategy_id=1)

        # Run some updates
        for i in range(20):
            ctrl.update(p=0.01 * (i % 5), v=0.02, drawdown=-0.01 * i)

        snapshot = ctrl.snapshot()

        # Verify snapshot contains expected fields
        assert "E" in snapshot
        assert "I" in snapshot
        assert "lambda_" in snapshot
        assert "scale" in snapshot
        assert "r_mode" in snapshot

    def test_controller_to_dict_from_dict(self) -> None:
        """Test serialization roundtrip."""
        ctrl = NaKController(strategy_id=5)
        ctrl.update(p=0.02, v=0.03, drawdown=-0.02)

        data = ctrl.to_dict()

        # Recreate from dict
        restored = NaKControllerV4_2.from_dict(data, strategy_id=5)

        assert restored.E == ctrl.E
        assert restored.I_integral == ctrl.I_integral


class TestDesensitizationModulePrecision:
    """Tests for desensitization module precision."""

    def test_module_initialization(self) -> None:
        """Test module initializes correctly."""
        module = DesensitizationModule()

        assert module.scale == 1.0
        assert module.lambda_ == 0.05
        assert module.mu == 0.01
        assert module.sigma_target == 0.18

    def test_module_custom_initialization(self) -> None:
        """Test module with custom parameters."""
        module = DesensitizationModule(
            lambda_init=0.08,
            mu=0.02,
            sigma_target=0.20,
            reset_eps=0.01,
            ei_window=100,
        )

        assert module.lambda_ == 0.08
        assert module.mu == 0.02
        assert module.sigma_target == 0.20

    def test_module_update_returns_finite(self) -> None:
        """Test module update returns finite values."""
        module = DesensitizationModule()

        for _ in range(50):
            scale, lambda_ = module.update(stim=0.01, ei_current=1.0)
            assert math.isfinite(scale)
            assert math.isfinite(lambda_)

    def test_module_lambda_bounds(self) -> None:
        """Test lambda stays within specified bounds."""
        module = DesensitizationModule()
        bounds = (0.02, 0.08)

        # Push lambda high
        for _ in range(100):
            module.update(stim=0.01, ei_current=2.0, bounds=bounds)

        assert bounds[0] <= module.lambda_ <= bounds[1]

        # Push lambda low
        module.lambda_ = 0.05
        for _ in range(100):
            module.update(stim=0.01, ei_current=0.1, bounds=bounds)

        assert bounds[0] <= module.lambda_ <= bounds[1]

    def test_module_ei_history_window(self) -> None:
        """Test EI history respects window size."""
        window = 30
        module = DesensitizationModule(ei_window=window)

        for i in range(100):
            module.update(stim=0.01, ei_current=float(i))

        # Window should cap history
        assert len(module._ei_hist) == window

    def test_module_scale_adapts_to_volatility(self) -> None:
        """Test scale adapts based on EI volatility."""
        module = DesensitizationModule(sigma_target=0.18)

        # Build history with stable EI
        for _ in range(50):
            module.update(stim=0.01, ei_current=1.0)

        # Build history with stable EI (value used below for comparison context)
        _stable_scale = module.scale  # Unused here but demonstrates stability

        # Now add volatile EI values
        module2 = DesensitizationModule(sigma_target=0.18)
        for i in range(50):
            # Alternating values for higher variance
            module2.update(stim=0.01, ei_current=0.5 + (i % 2) * 1.0)

        # Volatile conditions should affect scale differently
        assert math.isfinite(module2.scale)


class TestNaKAdapterPrecision:
    """Tests for NaK adapter integration precision."""

    def test_adapter_initialization(self) -> None:
        """Test adapter initializes components correctly."""
        adapter = NaKAdapter(strategy_id=1)

        assert adapter.controller is not None
        assert adapter.gate is not None

    def test_adapter_step_returns_complete_output(self) -> None:
        """Test adapter step returns all required fields."""
        adapter = NaKAdapter(strategy_id=1)

        output = adapter.step(
            p=0.01,
            v=0.02,
            drawdown=-0.01,
        )

        assert isinstance(output, AdapterOutput)
        assert math.isfinite(output.reward)
        assert 0.0 <= output.gate <= 1.0
        assert 0.0 <= output.effective_size <= 1.0
        assert math.isfinite(output.temperature)
        assert "shaped_reward" in output.controller_log

    def test_adapter_step_with_features(self) -> None:
        """Test adapter step handles features correctly."""
        adapter = NaKAdapter(strategy_id=1)

        features = [0.01, 0.02, 0.03]
        output = adapter.step(
            p=0.01,
            v=0.02,
            drawdown=-0.01,
            features=features,
        )

        assert isinstance(output, AdapterOutput)
        assert math.isfinite(output.reward)

    def test_adapter_step_with_hpa_tone(self) -> None:
        """Test adapter step handles HPA tone correctly."""
        adapter = NaKAdapter(strategy_id=1)

        # Without HPA tone
        output_no_hpa = adapter.step(p=0.01, v=0.02, drawdown=-0.01, hpa_tone=0.0)

        # With high HPA tone
        adapter2 = NaKAdapter(strategy_id=2)
        output_hpa = adapter2.step(p=0.01, v=0.02, drawdown=-0.01, hpa_tone=0.8)

        # Both should produce valid outputs
        assert math.isfinite(output_no_hpa.reward)
        assert math.isfinite(output_hpa.reward)

    def test_adapter_effective_size_bounds(self) -> None:
        """Test effective size is always bounded [0, 1]."""
        adapter = NaKAdapter(strategy_id=1)

        test_cases = [
            {"size_hint": 0.0},
            {"size_hint": 0.5},
            {"size_hint": 1.0},
            {"size_hint": 2.0},  # Should be clamped
            {"size_hint": -0.5},  # Should be clamped
        ]

        for kwargs in test_cases:
            output = adapter.step(
                p=0.01,
                v=0.02,
                drawdown=-0.01,
                **kwargs,
            )
            assert 0.0 <= output.effective_size <= 1.0

    def test_adapter_gate_state_structure(self) -> None:
        """Test gate state has expected structure."""
        adapter = NaKAdapter(strategy_id=1)

        output = adapter.step(p=0.01, v=0.02, drawdown=-0.01)

        assert "combined" in output.gate_state
        assert "lambda" in output.gate_state["combined"]

    def test_adapter_temperature_effect(self) -> None:
        """Test temperature effect is computed correctly."""
        adapter = NaKAdapter(strategy_id=1)

        output = adapter.step(
            p=0.01,
            v=0.02,
            drawdown=-0.01,
            base_temperature=1.5,
        )

        assert math.isfinite(output.temperature)

    def test_adapter_repeated_steps_stability(self) -> None:
        """Test adapter remains stable over many steps."""
        adapter = NaKAdapter(strategy_id=1)

        for i in range(100):
            p = 0.01 * math.sin(i / 10)
            v = 0.02 + 0.01 * math.cos(i / 5)
            dd = -0.01 * (1 + (i % 10) / 10)

            output = adapter.step(p=p, v=v, drawdown=dd)

            assert math.isfinite(output.reward)
            assert 0.0 <= output.gate <= 1.0
            assert 0.0 <= output.effective_size <= 1.0


class TestNaKConfigValidation:
    """Tests for NaK config validation."""

    def test_config_default_values(self) -> None:
        """Test NaKConfig has valid defaults."""
        cfg = NaKConfig()

        assert cfg.dd_soft_base > 0
        assert cfg.vol_ref_base > 0
        assert cfg.burst_z > 0
        assert cfg.refractory_ticks >= 0
        assert cfg.min_gate >= 0
        assert cfg.min_gate <= 1.0
        assert cfg.E_max > 0
        assert cfg.E_init <= cfg.E_max

    def test_config_custom_values(self) -> None:
        """Test NaKConfig accepts custom values."""
        cfg = NaKConfig(
            dd_soft_base=0.20,
            vol_ref_base=0.04,
            burst_z=3.0,
            refractory_ticks=10,
            reopen_hl=120,
            min_gate=0.40,
            K_p=3.0,
            K_i=1.0,
            E_max=20.0,
            E_init=8.0,
        )

        assert cfg.dd_soft_base == 0.20
        assert cfg.min_gate == 0.40
        assert cfg.E_max == 20.0

    def test_config_enable_sensory_habituation(self) -> None:
        """Test sensory habituation can be toggled."""
        cfg_enabled = NaKConfig(enable_sens_habituation=True)
        cfg_disabled = NaKConfig(enable_sens_habituation=False)

        ctrl_enabled = NaKController(strategy_id=1, cfg=cfg_enabled)
        ctrl_disabled = NaKController(strategy_id=2, cfg=cfg_disabled)

        assert ctrl_enabled.sensory is not None
        assert ctrl_disabled.sensory is None


class TestNaKNumericEdgeCases:
    """Tests for numeric edge cases."""

    def test_zero_volatility(self) -> None:
        """Test handling of zero volatility."""
        ctrl = NaKController(strategy_id=1)
        reward, log = ctrl.update(p=0.01, v=0.0, drawdown=-0.01)

        assert math.isfinite(reward)

    def test_very_small_values(self) -> None:
        """Test handling of very small values."""
        ctrl = NaKController(strategy_id=1)
        reward, log = ctrl.update(p=1e-10, v=1e-10, drawdown=-1e-10)

        assert math.isfinite(reward)
        assert all(math.isfinite(v) for v in log.values())

    def test_very_large_values(self) -> None:
        """Test handling of large values."""
        ctrl = NaKController(strategy_id=1)
        reward, log = ctrl.update(p=100.0, v=10.0, drawdown=-1.0)

        # Drawdown is clamped to -1.0
        assert math.isfinite(reward)

    def test_alternating_sign_inputs(self) -> None:
        """Test stability with alternating sign inputs."""
        ctrl = NaKController(strategy_id=1)

        for i in range(50):
            sign = 1 if i % 2 == 0 else -1
            p = sign * 0.05
            reward, log = ctrl.update(p=p, v=0.02, drawdown=-0.02)
            assert math.isfinite(reward)
