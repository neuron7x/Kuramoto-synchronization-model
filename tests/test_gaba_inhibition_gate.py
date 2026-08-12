# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import math

import pytest
import torch

from modules.gaba_inhibition_gate import (
    GABAInhibitionGate,
    GateMetrics,
    GateParams,
    GateState,
)


def base_state(vix=20.0, vol=0.1, ret=0.01, pos=1.0, rpe=0.0, dt_ms=20.0):
    return {
        "vix": torch.tensor(vix),
        "volatility": torch.tensor(vol),
        "return": torch.tensor(ret),
        "position": torch.tensor(pos),
        "rpe": torch.tensor(rpe),
        "delta_t_ms": torch.tensor(dt_ms),
    }


def test_inhibition_monotonic_with_vol():
    """Test that inhibition increases with volatility."""
    gate = GABAInhibitionGate()
    a = torch.tensor([1.0])
    _, m1 = gate(base_state(vix=10.0), a)
    _, m2 = gate(base_state(vix=30.0), a)
    assert m2.inhibition > m1.inhibition


def test_risk_weight_bounds():
    """Test that risk_weight stays within [0.5, 1.5] bounds."""
    gate = GABAInhibitionGate()
    a = torch.tensor([2.0])
    for _ in range(200):
        gate(base_state(vix=80.0, ret=0.5, dt_ms=10.0), a)
    _, m = gate(base_state(vix=80.0), a)
    assert 0.5 <= m.risk_weight <= 1.5


def test_cycle_modulation_range():
    """Test that cycle modulation produces output variation."""
    gate = GABAInhibitionGate()
    a = torch.tensor([1.0])
    outputs = []
    for _ in range(200):
        g, _ = gate(base_state(), a)
        outputs.append(g.item())
    assert max(outputs) > min(outputs)  # cycles actually modulate


def test_custom_gate_params():
    """Test gate with custom parameters."""
    custom_params = GateParams(k_inhibit=0.6, cycle_modulation=False, risk_min=0.3, risk_max=2.0)
    gate = GABAInhibitionGate(params=custom_params)
    a = torch.tensor([1.0])
    gated, metrics = gate(base_state(), a)

    assert isinstance(gated, torch.Tensor)
    assert isinstance(metrics, GateMetrics)
    assert hasattr(metrics, "inhibition")
    assert hasattr(metrics, "gaba_level")
    assert hasattr(metrics, "risk_weight")
    assert hasattr(metrics, "cycle_multiplier")
    assert hasattr(metrics, "stdp_delta")
    assert hasattr(metrics, "ltp_ltd_delta")
    assert hasattr(metrics, "adaptive_delta")


def test_device_parameter():
    """Test gate initialization with explicit device."""
    gate = GABAInhibitionGate(device="cpu")
    assert gate.device.type == "cpu"

    a = torch.tensor([1.0])
    gated, _ = gate(base_state(), a)
    assert gated.device.type == "cpu"


def test_apply_hedge():
    """Test hedge function modifies GABA levels."""
    gate = GABAInhibitionGate()

    # Get initial state
    _, m1 = gate(base_state(), torch.tensor([1.0]))
    initial_gaba = m1.gaba_level
    initial_risk = m1.risk_weight

    # Apply hedge
    gate.apply_hedge(strength=1.0)

    # Check GABA increased
    _, m2 = gate(base_state(), torch.tensor([1.0]))
    assert m2.gaba_level > initial_gaba
    assert m2.risk_weight < initial_risk


def test_apply_hedge_invalid_strength():
    """Test hedge function validates strength parameter."""
    gate = GABAInhibitionGate()

    with pytest.raises(ValueError, match="strength must be in"):
        gate.apply_hedge(strength=3.0)

    with pytest.raises(ValueError, match="strength must be in"):
        gate.apply_hedge(strength=-1.0)


def test_missing_market_state_keys():
    """Test forward raises KeyError for missing market_state keys."""
    gate = GABAInhibitionGate()
    incomplete_state = {"vix": torch.tensor(20.0)}

    with pytest.raises(KeyError, match="Missing required keys"):
        gate(incomplete_state, torch.tensor([1.0]))


def test_invalid_action_values():
    """Test forward raises ValueError for NaN/Inf action values."""
    gate = GABAInhibitionGate()

    with pytest.raises(ValueError, match="NaN or Inf"):
        gate(base_state(), torch.tensor([float("nan")]))

    with pytest.raises(ValueError, match="NaN or Inf"):
        gate(base_state(), torch.tensor([float("inf")]))


def test_get_set_state():
    """Test state save/restore functionality."""
    gate = GABAInhibitionGate()

    # Run a few steps
    for _ in range(10):
        gate(base_state(vix=30.0), torch.tensor([1.0]))

    # Save state
    state = gate.get_state()
    assert isinstance(state, GateState)

    # Continue running
    for _ in range(10):
        gate(base_state(vix=40.0), torch.tensor([1.5]))

    # Restore state
    gate.set_state(state)

    # Verify state restored
    restored_state = gate.get_state()
    assert torch.allclose(restored_state.gaba_fast, state.gaba_fast)
    assert torch.allclose(restored_state.gaba_slow, state.gaba_slow)
    assert torch.allclose(restored_state.risk_weight, state.risk_weight)
    assert torch.allclose(restored_state.t_ms, state.t_ms)


def test_reset_state():
    """Resetting the gate should clear inhibition memory and restore defaults."""

    gate = GABAInhibitionGate()
    a = torch.tensor([1.0])

    # Build up state
    for _ in range(50):
        gate(base_state(vix=60.0, ret=0.2, dt_ms=5.0), a)

    # Ensure we have non-zero state prior to reset
    populated = gate.get_state()
    assert populated.gaba_fast.item() > 0
    assert populated.gaba_slow.item() > 0
    assert populated.risk_weight.item() != 1.0
    assert populated.t_ms.item() > 0

    gate.reset_state()

    reset = gate.get_state()
    assert pytest.approx(reset.gaba_fast.item(), abs=1e-6) == 0.0
    assert pytest.approx(reset.gaba_slow.item(), abs=1e-6) == 0.0
    assert pytest.approx(reset.risk_weight.item(), abs=1e-6) == 1.0
    assert pytest.approx(reset.t_ms.item(), abs=1e-6) == 0.0


def test_no_gradient_leak():
    """Test that forward pass doesn't create gradient graphs."""
    gate = GABAInhibitionGate()
    action = torch.tensor([1.0], requires_grad=True)

    gated, _ = gate(base_state(), action)

    # Should not have gradient tracking
    assert not gated.requires_grad


def test_market_state_nan_validation():
    """Test that NaN/Inf in market_state tensors raises ValueError."""
    gate = GABAInhibitionGate()

    # Test NaN in vix
    state_with_nan = base_state()
    state_with_nan["vix"] = torch.tensor(float("nan"))
    with pytest.raises(ValueError, match="vix contains NaN or Inf"):
        gate(state_with_nan, torch.tensor([1.0]))

    # Test Inf in volatility
    state_with_inf = base_state()
    state_with_inf["volatility"] = torch.tensor(float("inf"))
    with pytest.raises(ValueError, match="volatility contains NaN or Inf"):
        gate(state_with_inf, torch.tensor([1.0]))


def test_cycle_modulation_determinism():
    """Test that cycle_modulation affects output variance over time."""
    # Test with cycles enabled - should see oscillations
    params_cycles = GateParams(cycle_modulation=True)
    gate_cycles = GABAInhibitionGate(params=params_cycles)

    a = torch.tensor([1.0])
    # Run enough steps to see cycle effects (need time to pass)
    outputs_with_cycles = []
    for _ in range(200):
        g, _ = gate_cycles(base_state(), a)
        outputs_with_cycles.append(g.item())

    variance_with_cycles = max(outputs_with_cycles) - min(outputs_with_cycles)

    # Test with cycles disabled - should see less variation from cycles
    params_no_cycles = GateParams(cycle_modulation=False)
    gate_no_cycles = GABAInhibitionGate(params=params_no_cycles)

    outputs_no_cycles = []
    for _ in range(200):
        g, _ = gate_no_cycles(base_state(), a)
        outputs_no_cycles.append(g.item())

    variance_no_cycles = max(outputs_no_cycles) - min(outputs_no_cycles)

    # With cycles enabled, we should see oscillatory behavior over time
    # Both will have GABA dynamics, but cycles adds oscillations
    # The key test is that with cycles we get meaningful variation
    assert (
        variance_with_cycles > 0.01
    ), f"With cycles enabled, should see oscillatory variation: {variance_with_cycles:.6f}"

    print(f"  Variance with cycles: {variance_with_cycles:.6f}")
    print(f"  Variance without cycles: {variance_no_cycles:.6f}")


def test_mfd_guarantee():
    """Test that MFD guarantee prevents action amplification under high GABA."""
    gate = GABAInhibitionGate()

    # Prime the gate with high volatility to build up GABA
    high_vol_state = base_state(vix=80.0)
    a = torch.tensor([1.0])
    for _ in range(20):
        gate(high_vol_state, a)

    # Now test that gated action doesn't exceed input with risk_weight boost
    test_action = torch.tensor([2.0])
    gated, metrics = gate(high_vol_state, test_action)

    # With MFD guarantee, gated action magnitude should not exceed input
    assert gated.abs().item() <= test_action.abs().item() + 1e-6


def test_mfd_guarantee_disabled():
    """Test that MFD guarantee can be disabled."""
    params = GateParams(enforce_mfd=False)
    gate = GABAInhibitionGate(params=params)

    # Prime with high volatility
    high_vol_state = base_state(vix=80.0)
    a = torch.tensor([1.0])
    for _ in range(20):
        gate(high_vol_state, a)

    # With MFD disabled, action could potentially be amplified by risk_weight
    # Just verify it runs without error
    test_action = torch.tensor([2.0])
    gated, metrics = gate(high_vol_state, test_action)
    assert isinstance(gated, torch.Tensor)


def test_gate_metrics_type():
    """Test that forward returns GateMetrics dataclass."""
    gate = GABAInhibitionGate()
    _, metrics = gate(base_state(), torch.tensor([1.0]))

    assert isinstance(metrics, GateMetrics)
    assert isinstance(metrics.inhibition, float)
    assert isinstance(metrics.gaba_level, float)
    assert isinstance(metrics.risk_weight, float)
    assert isinstance(metrics.cycle_multiplier, float)
    assert isinstance(metrics.stdp_delta, float)
    assert isinstance(metrics.ltp_ltd_delta, float)
    assert isinstance(metrics.adaptive_delta, float)


def test_plasticity_metric_direction():
    """STDP/LTP-LTD metrics should reflect timing and co-activity polarity."""

    gate = GABAInhibitionGate()
    action = torch.tensor([1.0])

    # Positive timing and cooperative activity => potentiation
    state_potentiate = base_state(vix=45.0, vol=0.9, ret=0.5, dt_ms=5.0)
    state_potentiate["delta_t_ms"] = torch.tensor(5.0)
    _, metrics_potentiate = gate(state_potentiate, action)

    assert metrics_potentiate.stdp_delta > 0
    assert metrics_potentiate.ltp_ltd_delta > 0

    # Negative timing and anti-correlated returns => depression
    state_depress = base_state(vix=45.0, vol=0.9, ret=-0.5, dt_ms=-5.0)
    state_depress["delta_t_ms"] = torch.tensor(-5.0)
    _, metrics_depress = gate(state_depress, action)

    assert metrics_depress.stdp_delta < 0
    assert metrics_depress.ltp_ltd_delta < 0


def test_gate_params_validation():
    """Invalid parameter settings should raise informative errors."""

    with pytest.raises(ValueError):
        GateParams(dt_ms=0.0)

    with pytest.raises(ValueError):
        GateParams(max_inhibition=1.5)


def test_gate_params_range_validation():
    """Range-based parameter constraints should be enforced."""

    with pytest.raises(ValueError, match="risk_min must be <= risk_max"):
        GateParams(risk_min=1.2, risk_max=1.1)

    with pytest.raises(ValueError, match="min_dt_ms must be <= max_dt_ms"):
        GateParams(min_dt_ms=10.0, max_dt_ms=1.0)

    with pytest.raises(ValueError, match="min_dt_ms must be positive"):
        GateParams(min_dt_ms=0.0)


def test_gate_params_from_dict_partial():
    """from_dict should ignore unknown keys while applying overrides."""

    params = GateParams.from_dict({"k_inhibit": 0.75, "nonexistent": 5})
    assert pytest.approx(params.k_inhibit, rel=1e-6) == 0.75


def test_gate_configure_runtime_updates():
    """configure should allow safe runtime parameter updates."""

    gate = GABAInhibitionGate()
    original_decay = gate.decay_fast.clone()

    gate.configure(dt_ms=0.2, tau_gaba_a_ms=5.0)

    assert pytest.approx(gate.p.dt_ms, rel=1e-6) == 0.2
    assert pytest.approx(gate.p.tau_gaba_a_ms, rel=1e-6) == 5.0
    assert not torch.allclose(original_decay, gate.decay_fast)


def test_gate_configure_conflict_check():
    """configure should reject mixing full params with overrides."""

    gate = GABAInhibitionGate()
    with pytest.raises(ValueError):
        gate.configure(GateParams(), k_inhibit=0.5)


def test_gate_config_round_trip():
    """Configuration dict round-trip should preserve overrides."""

    gate = GABAInhibitionGate()
    gate.configure(k_inhibit=0.55, gamma_cycle_amplitude=0.05)
    config = gate.to_config()

    rebuilt = GABAInhibitionGate.from_config(config)
    assert pytest.approx(rebuilt.p.k_inhibit, rel=1e-6) == 0.55
    assert pytest.approx(rebuilt.p.gamma_cycle_amplitude, rel=1e-6) == 0.05


def test_dynamic_dt_modulates_decay():
    """Large dt should produce stronger decay than small dt."""

    gate = GABAInhibitionGate()
    action = torch.tensor([1.0])

    gate.reset_state()
    gate(base_state(dt_ms=1.0, vix=60.0), action)
    decay_small = gate.decay_fast.clone()

    gate.reset_state()
    gate(base_state(dt_ms=200.0, vix=60.0), action)
    decay_large = gate.decay_fast.clone()

    assert decay_large.item() < decay_small.item()


def test_clamp_dt_respects_bounds_and_abs():
    """Clamp should enforce dt bounds and treat negative deltas as positive."""

    gate = GABAInhibitionGate()
    dt_values = torch.tensor([-1e-6, gate.p.min_dt_ms / 10.0, gate.p.max_dt_ms * 10.0])
    clamped = gate._clamp_dt(dt_values)

    assert pytest.approx(clamped[0].item(), rel=1e-6) == gate.p.min_dt_ms
    assert pytest.approx(clamped[1].item(), rel=1e-6) == gate.p.min_dt_ms
    assert pytest.approx(clamped[2].item(), rel=1e-6) == gate.p.max_dt_ms


def test_forward_bounds_and_no_nan():
    """Forward pass should keep outputs within bounds and free of NaN/Inf."""

    gate = GABAInhibitionGate()
    action = torch.tensor([2.0])
    market_states = [
        base_state(vix=10.0, vol=0.05, ret=0.01, dt_ms=gate.p.min_dt_ms),
        base_state(vix=80.0, vol=1.0, ret=0.3, dt_ms=gate.p.max_dt_ms),
        base_state(vix=40.0, vol=0.3, ret=-0.2, dt_ms=50.0),
    ]

    for state in market_states:
        gated, metrics = gate(state, action)

        assert 0.0 <= metrics.inhibition <= gate.p.max_inhibition
        assert gate.p.risk_min <= metrics.risk_weight <= gate.p.risk_max
        assert torch.isfinite(gated).all()
        assert all(
            math.isfinite(value)
            for value in (
                metrics.inhibition,
                metrics.gaba_level,
                metrics.risk_weight,
                metrics.cycle_multiplier,
                metrics.stdp_delta,
                metrics.ltp_ltd_delta,
                metrics.adaptive_delta,
            )
        )

        if metrics.gaba_level > 0.1:
            assert gated.abs().item() <= action.abs().item() + 1e-6


def test_delta_t_ms_extremes_use_clamped_decay():
    """Min/max delta_t_ms should clamp integration and update decay factors."""

    gate = GABAInhibitionGate()
    action = torch.tensor([1.0])

    gate.reset_state()
    gate(base_state(dt_ms=1e-9, vix=60.0), action)
    expected_min = gate._compute_decay(
        torch.tensor(gate.p.min_dt_ms, device=gate.device),
        gate.p.tau_gaba_a_ms,
    )
    assert torch.allclose(gate.decay_fast, expected_min)

    gate.reset_state()
    gate(base_state(dt_ms=1e9, vix=60.0), action)
    expected_max = gate._compute_decay(
        torch.tensor(gate.p.max_dt_ms, device=gate.device),
        gate.p.tau_gaba_a_ms,
    )
    assert torch.allclose(gate.decay_fast, expected_max)


def test_risk_weight_relaxes_to_baseline():
    """Risk weight should relax back toward baseline when threat subsides."""

    params = GateParams(risk_decay_tau_ms=50.0)
    gate = GABAInhibitionGate(params=params)
    action = torch.tensor([1.0])

    # build up potentiation
    high_state = base_state(vix=80.0, ret=0.6, vol=1.0, dt_ms=5.0)
    for _ in range(20):
        gate(high_state, action)
    _, metrics_peak = gate(high_state, action)

    # low threat should relax weight downward
    low_state = base_state(vix=10.0, ret=0.0, vol=0.05, dt_ms=50.0)
    for _ in range(40):
        gate(low_state, action)
    _, metrics_relaxed = gate(low_state, action)

    assert metrics_relaxed.risk_weight < metrics_peak.risk_weight
    assert metrics_relaxed.risk_weight > 0.9  # not collapsed


def test_rpe_and_position_adaptive_plasticity():
    """RPE and exposure should modulate adaptive plasticity term."""

    gate = GABAInhibitionGate()
    action = torch.tensor([1.0])

    positive_state = base_state(vix=50.0, vol=0.6, ret=0.4, rpe=0.9, pos=0.2, dt_ms=10.0)
    _, metrics_positive = gate(positive_state, action)

    negative_state = base_state(vix=50.0, vol=0.6, ret=0.4, rpe=-0.9, pos=3.0, dt_ms=10.0)
    _, metrics_negative = gate(negative_state, action)

    assert metrics_positive.adaptive_delta > metrics_negative.adaptive_delta


def test_apply_hedge_dampens_risk():
    """Hedge should immediately dampen accumulated risk sensitivity."""

    gate = GABAInhibitionGate()
    action = torch.tensor([1.0])
    for _ in range(10):
        gate(base_state(vix=60.0, ret=0.5, vol=0.8, dt_ms=10.0), action)

    _, before = gate(base_state(vix=60.0, dt_ms=10.0), action)
    gate.apply_hedge(strength=1.5)
    _, after = gate(base_state(vix=60.0, dt_ms=10.0), action)

    assert after.risk_weight < before.risk_weight
