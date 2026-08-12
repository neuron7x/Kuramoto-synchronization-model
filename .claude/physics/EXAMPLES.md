# Physics Test Transformation Examples

> Claude Code: study these examples BEFORE writing physics tests.
> Each shows a REAL anti-pattern from this codebase and its fix.

## Example 1: Kuramoto R bounds (test_T2_explosive_sync.py)

### BEFORE (tests a number, not physics):
```python
def test_R_bounded(self, detector):
    result = detector.measure_proximity(N=5, seed=42)
    assert np.all(result.R_forward >= 0)
    assert np.all(result.R_forward <= 1)
    assert np.all(result.R_backward >= 0)
    assert np.all(result.R_backward <= 1)
```

Problems:
- No invariant reference → future dev doesn't know WHY this bound exists
- No error context → if it fails, you see "assert False" not "physics violated"
- N=5 is tiny → finite-size effects dominate, test is weak

### AFTER (tests physics):
```python
def test_R_bounded(self, detector):
    """INV-K1: Order parameter R ∈ [0,1] for all configurations.
    
    The Kuramoto order parameter is defined as |Z|/N where Z = Σexp(iθ_j).
    By triangle inequality, |Z| ≤ N, so R ≤ 1. By definition of modulus, R ≥ 0.
    This must hold regardless of coupling K, network topology, or N.
    """
    # Test with multiple N to ensure finite-size doesn't mask violations
    for N in [5, 20, 50]:
        result = detector.measure_proximity(N=N, seed=42)
        for label, R_arr in [("forward", result.R_forward), ("backward", result.R_backward)]:
            assert np.all(R_arr >= 0), (
                f"INV-K1 VIOLATED: R_{label} has negative values "
                f"(min={np.min(R_arr):.6f}) at N={N}. "
                f"Order parameter is |Z|/N, cannot be negative."
            )
            assert np.all(R_arr <= 1 + 1e-10), (
                f"INV-K1 VIOLATED: R_{label} exceeds 1 "
                f"(max={np.max(R_arr):.6f}) at N={N}. "
                f"By triangle inequality, |Z| ≤ N so R ≤ 1."
            )
```

## Example 2: Hysteresis (test_T2_explosive_sync.py)

### BEFORE:
```python
def test_hysteresis_non_negative(self, detector):
    result = detector.measure_proximity(N=5, seed=42)
    assert result.hysteresis_width >= 0
```

### AFTER:
```python
def test_hysteresis_non_negative(self, detector):
    """INV-ES1: Hysteresis width ≥ 0 (forward threshold ≥ backward).
    
    In explosive synchronization, the forward critical coupling K_c^↑
    (increasing K) is always ≥ backward K_c^↓ (decreasing K).
    Negative hysteresis would imply the system desynchronizes at HIGHER
    coupling than it synchronizes — thermodynamically forbidden for
    first-order transitions.
    """
    for seed in range(5):  # Multiple realizations for stochastic stability
        result = detector.measure_proximity(N=20, seed=seed)
        assert result.hysteresis_width >= -1e-10, (
            f"INV-ES1 VIOLATED: hysteresis_width={result.hysteresis_width:.6f} < 0 "
            f"at seed={seed}, N=20. Forward transition must occur at K ≥ backward."
        )
```

## Example 3: Serotonin bounds (new test)

### BEFORE (typical Claude Code output without physics kernel):
```python
def test_serotonin_output():
    controller = SerotoninController(config)
    result = controller.step(stress=1.5, drawdown=-0.03, novelty=0.5)
    assert 0 <= result.level <= 1
    assert result.hold == True  # stress >= 1.0
```

### AFTER (physics-grounded):
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(
    stress=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    drawdown=st.floats(min_value=-1.0, max_value=0.0, allow_nan=False),
    novelty=st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
)
@settings(max_examples=500)
def test_serotonin_bounded(stress, drawdown, novelty):
    """INV-5HT1: Serotonin signal s(t) ∈ [0, 1] for all inputs.
    
    Proof: s = σ(k·(tonic-θ)) · sensitivity
    σ ∈ (0,1) by sigmoid definition.
    sensitivity ∈ [0.1, 1.0] by explicit clamp.
    Product ∈ [0, 1).
    """
    controller = SerotoninController(default_config())
    result = controller.step(stress=stress, drawdown=drawdown, novelty=novelty)
    assert 0 <= result.level <= 1.0, (
        f"INV-5HT1 VIOLATED: level={result.level} outside [0,1] "
        f"at stress={stress:.3f}, drawdown={drawdown:.3f}, novelty={novelty:.3f}. "
        f"Sigmoid × sensitivity must stay in [0,1]."
    )


def test_serotonin_hard_veto():
    """INV-5HT7: stress ≥ 1.0 OR |drawdown| ≥ 0.5 → veto = True.
    
    This is a safety-critical gate. It overrides all other logic.
    If this fails, the system can trade during extreme conditions.
    """
    controller = SerotoninController(default_config())
    
    # Test stress threshold
    result = controller.step(stress=1.0, drawdown=0.0, novelty=0.0)
    assert result.veto is True, (
        f"INV-5HT7 VIOLATED: veto={result.veto} at stress=1.0. "
        f"Hard safety gate must fire at stress ≥ 1.0."
    )
    
    # Test drawdown threshold
    controller2 = SerotoninController(default_config())
    result2 = controller2.step(stress=0.0, drawdown=-0.5, novelty=0.0)
    assert result2.veto is True, (
        f"INV-5HT7 VIOLATED: veto={result2.veto} at drawdown=-0.5. "
        f"Hard safety gate must fire at |drawdown| ≥ 0.5."
    )
```

## Example 4: Dopamine RPE (algebraic test)

### BEFORE:
```python
def test_rpe_computation():
    controller = DopamineController(config)
    rpe = controller.compute_rpe(reward=1.0, value=0.5, next_value=0.5)
    assert abs(rpe - 0.95) < 0.01  # magic number
```

### AFTER:
```python
def test_rpe_algebraic():
    """INV-DA1: δ = r + γ·V' - V must hold exactly.
    
    TD(0) error is a deterministic algebraic expression.
    Unlike stochastic Kuramoto R, this CAN be tested with exact equality
    (up to floating point precision).
    """
    controller = DopamineController(default_config())
    
    r, V, V_next, gamma = 1.0, 0.5, 0.5, 0.9
    expected_delta = r + gamma * V_next - V  # = 1.0 + 0.45 - 0.5 = 0.95
    
    actual_delta = controller.compute_rpe(
        reward=r, value=V, next_value=V_next, discount_gamma=gamma
    )
    assert abs(actual_delta - expected_delta) < 1e-12, (
        f"INV-DA1 VIOLATED: δ={actual_delta}, expected={expected_delta} "
        f"for r={r}, V={V}, V'={V_next}, γ={gamma}. "
        f"TD(0) RPE is algebraically exact: δ = r + γV' - V."
    )


def test_rpe_linearity_in_reward():
    """INV-DA7: ∂δ/∂r = 1 (RPE is linear in reward).
    
    Holding V, V', γ constant, δ(r₂) - δ(r₁) = r₂ - r₁ exactly.
    This is a structural property of TD(0), not an approximation.
    """
    controller = DopamineController(default_config())
    V, V_next, gamma = 0.5, 0.5, 0.9
    
    delta_1 = controller.compute_rpe(reward=1.0, value=V, next_value=V_next, discount_gamma=gamma)
    delta_2 = controller.compute_rpe(reward=2.0, value=V, next_value=V_next, discount_gamma=gamma)
    
    assert abs((delta_2 - delta_1) - 1.0) < 1e-12, (
        f"INV-DA7 VIOLATED: Δδ = {delta_2 - delta_1}, expected 1.0. "
        f"RPE must be linear in reward: ∂δ/∂r = 1."
    )
```

## Example 5: GABA monotonicity (sweep test)

### BEFORE:
```python
def test_gaba_gate():
    gate = GABAPositionGate(config)
    result = gate.compute(volatility=0.5)
    assert 0 <= result <= 1
```

### AFTER:
```python
def test_gaba_monotone_in_volatility():
    """INV-GABA2: Higher volatility → higher or equal inhibition.
    
    The gate is σ(k·(vol - θ)), and sigmoid is monotonically increasing.
    This is the core safety property: more danger → more inhibition.
    A violation means the system could INCREASE risk during volatility spikes.
    """
    gate = GABAPositionGate(default_config())
    
    vol_values = np.linspace(0.0, 2.0, 50)
    inhibitions = [gate.compute(volatility=v) for v in vol_values]
    
    for i in range(len(inhibitions) - 1):
        assert inhibitions[i+1] >= inhibitions[i] - 1e-10, (
            f"INV-GABA2 VIOLATED: inhibition decreased from "
            f"{inhibitions[i]:.6f} (vol={vol_values[i]:.3f}) to "
            f"{inhibitions[i+1]:.6f} (vol={vol_values[i+1]:.3f}). "
            f"Sigmoid gate must be monotonically non-decreasing in volatility."
        )


@given(vol=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_gaba_position_reduction(vol):
    """INV-GABA3: effective_position ≤ raw_position.
    
    Inhibition can only REDUCE position, never amplify.
    effective = raw × (1 - inhibition), and inhibition ∈ [0,1].
    """
    gate = GABAPositionGate(default_config())
    raw_position = 1.0
    inhibition = gate.compute(volatility=vol)
    effective = raw_position * (1.0 - inhibition)
    
    assert effective <= raw_position + 1e-10, (
        f"INV-GABA3 VIOLATED: effective={effective:.6f} > raw={raw_position} "
        f"at vol={vol:.3f}, inhibition={inhibition:.6f}. "
        f"GABA gate must reduce position, never amplify."
    )
```

## Pattern Summary

| What | Before (code-level) | After (physics-level) |
|------|--------------------|-----------------------|
| Docstring | Empty or vague | INV-ID + theorem statement + why it matters |
| Assertion | `assert x < 0.3` | `assert x < C/√N` (derived from theory) |
| Error msg | None or generic | Invariant ID + expected + observed + reasoning |
| Input range | Single hardcoded | Multiple N, seeds, or hypothesis fuzzing |
| Test name | `test_output()` | `test_subcritical_decay()` (names the physics) |
