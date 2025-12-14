import numpy as np

from core.neuro.ecs_regulator import ECSInspiredRegulator, StressMode


def test_stress_increase_raises_threshold_and_actions_contract():
    regulator = ECSInspiredRegulator(initial_risk_threshold=0.05, stress_threshold=0.02)

    regulator.update_stress(np.array([0.001, 0.002]), drawdown=0.0)
    regulator.adapt_parameters()
    low_stress_threshold = regulator.risk_threshold
    action_low = regulator.decide_action(0.06)

    regulator.update_stress(np.array([0.1, 0.12, -0.08]), drawdown=0.2, previous_fe=regulator.free_energy_proxy)
    regulator.adapt_parameters()
    high_stress_threshold = regulator.risk_threshold
    action_high = regulator.decide_action(0.06)

    assert high_stress_threshold >= low_stress_threshold
    assert abs(action_high) <= abs(action_low)


def test_crisis_mode_blocks_aggressive_actions_by_default():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.02, stress_threshold=0.01, crisis_threshold=0.015
    )

    regulator.update_stress(
        np.array([0.3, 0.25, 0.35]), drawdown=0.5, previous_fe=None
    )
    regulator.adapt_parameters()

    assert regulator.stress_mode == StressMode.CRISIS
    action = regulator.decide_action(0.5)
    assert action == 0


def test_crisis_reduce_only_allows_position_reduction():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.02,
        stress_threshold=0.005,
        crisis_threshold=0.006,
        crisis_action_mode="reduce_only",
        smoothing_alpha=0.1,
    )

    regulator.update_stress(np.array([0.2, 0.25, 0.3]), drawdown=0.35, previous_fe=None)
    regulator.adapt_parameters()

    assert regulator.stress_mode == StressMode.CRISIS
    sell_action = regulator.decide_action(-0.5)
    buy_action = regulator.decide_action(0.5)
    assert sell_action == -1
    assert buy_action == 0


def test_free_energy_does_not_increase_without_research_mode():
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.05, stress_threshold=0.02, max_fe_step_up=0.0
    )

    regulator.update_stress(np.array([0.01, 0.02]), drawdown=0.0, previous_fe=0.0)
    prev_fe = regulator.free_energy_proxy
    regulator.update_stress(np.array([0.2, 0.25]), drawdown=0.5, previous_fe=prev_fe)

    assert regulator.free_energy_proxy <= prev_fe + 1e-6


def test_deterministic_outputs_given_same_inputs_and_reset():
    regulator = ECSInspiredRegulator(initial_risk_threshold=0.05, seed=42)

    regulator.update_stress(np.array([0.01, 0.02]), drawdown=0.0, previous_fe=0.0)
    regulator.adapt_parameters()
    first_action = regulator.decide_action(0.1)

    regulator.reset()
    regulator.update_stress(np.array([0.01, 0.02]), drawdown=0.0, previous_fe=0.0)
    regulator.adapt_parameters()
    second_action = regulator.decide_action(0.1)

    assert first_action == second_action


def test_nan_inputs_default_to_hold_for_safety():
    regulator = ECSInspiredRegulator(initial_risk_threshold=0.05)

    regulator.update_stress(np.array([np.nan, np.inf]), drawdown=0.0, previous_fe=0.0)
    regulator.adapt_parameters()
    action = regulator.decide_action(float("nan"))

    assert action == 0


def test_fe_invariant_over_multiple_stress_updates():
    """FE should not increase beyond previous + max_fe_step_up over multiple updates."""
    from core.neuro.ecs_regulator import FE_STABILITY_EPSILON

    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.05,
        stress_threshold=0.02,
        max_fe_step_up=0.0,
        enforce_monotonicity=True,
    )

    # First update
    regulator.update_stress(np.array([0.01, 0.02]), drawdown=0.0, previous_fe=0.0)
    fe_values = [regulator.free_energy_proxy]

    # Multiple high-stress updates - FE should stay bounded
    for _ in range(10):
        prev_fe = regulator.free_energy_proxy
        regulator.update_stress(
            np.array([0.2, 0.25, -0.15]), drawdown=0.3, previous_fe=prev_fe
        )
        fe_values.append(regulator.free_energy_proxy)
        # Each FE should not exceed previous + epsilon
        assert regulator.free_energy_proxy <= prev_fe + FE_STABILITY_EPSILON


def test_stress_mode_transitions_correctly():
    """Stress mode should transition based on actual stress level."""
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.05,
        stress_threshold=0.03,
        crisis_threshold=0.05,
        smoothing_alpha=0.3,  # Lower alpha for faster response
    )

    # Initially NORMAL
    assert regulator.stress_mode == StressMode.NORMAL

    # Low stress - should stay NORMAL
    regulator.update_stress(np.array([0.01, 0.02]), drawdown=0.01)
    assert regulator.stress_mode == StressMode.NORMAL

    # Medium stress - should become ELEVATED
    for _ in range(5):
        regulator.update_stress(np.array([0.08, -0.06, 0.07]), drawdown=0.1)
    assert regulator.stress_mode in [StressMode.ELEVATED, StressMode.CRISIS]

    # High stress - should become CRISIS
    for _ in range(5):
        regulator.update_stress(np.array([0.15, -0.12, 0.14]), drawdown=0.2)
    assert regulator.stress_mode == StressMode.CRISIS


def test_stress_independent_of_fe_constraint():
    """Stress level should increase even when FE is constrained.
    
    This tests the fix for the semantic bug where FE monotonicity
    was incorrectly clamping the stress level.
    """
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.05,
        stress_threshold=0.02,
        max_fe_step_up=0.0,
        enforce_monotonicity=True,
        smoothing_alpha=0.5,
    )

    # First update with low stress
    regulator.update_stress(np.array([0.001, 0.002]), drawdown=0.0)
    low_stress = regulator.stress_level
    prev_fe = regulator.free_energy_proxy

    # High stress update with FE constraint
    regulator.update_stress(np.array([0.2, 0.25, -0.15]), drawdown=0.3, previous_fe=prev_fe)
    high_stress = regulator.stress_level

    # Stress should increase despite FE being constrained
    assert high_stress > low_stress, (
        f"Stress should increase: {low_stress} -> {high_stress}"
    )
    # FE should be constrained
    assert regulator.free_energy_proxy <= prev_fe + 1e-6
