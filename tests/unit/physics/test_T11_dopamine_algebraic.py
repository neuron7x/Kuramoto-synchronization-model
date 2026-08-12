# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T11 — Dopamine TD-error witnesses for INV-DA1 and INV-DA7.

The dopamine controller in ``geosync.core.neuro.dopamine.dopamine_controller``
exposes ``compute_rpe(reward, value, next_value, discount_gamma)`` which
implements the canonical TD(0) prediction error:

    δ = r + γ · V(s') − V(s)

Two invariants follow directly from this algebraic form:

* **INV-DA1 — sign directionality**: δ > 0 when the observed reward
  exceeds the prediction (positive surprise), δ < 0 when it falls short
  (negative surprise), δ ≈ 0 when reward matches the prediction. The
  sign reflects the surprise direction.

* **INV-DA7 — linearity in reward**: ∂δ/∂r = 1 exactly. Equivalently,
  δ(r₂) − δ(r₁) = r₂ − r₁ for any fixed (V, V', γ). This is an
  algebraic identity and must hold to double-precision on the exact
  closed-form TD update.

The witnesses call the production ``compute_rpe`` with a live
controller loaded from ``config/dopamine.yaml`` so any regression in
the TD-error path surfaces here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from geosync.core.neuro.dopamine import DopamineController

_CONFIG_PATH = Path("config/dopamine.yaml")


@pytest.fixture()
def controller(tmp_path: Path) -> DopamineController:
    """Load the shipped dopamine config into a scratch working directory.

    Mirrors the fixture pattern in ``tests/core/neuro/dopamine/
    test_dopamine_controller.py`` so the witness uses exactly the
    production config without mutating the repo copy.
    """
    target = tmp_path / "dopamine.yaml"
    target.write_text(_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return DopamineController(str(target))


def test_td_error_sign_reflects_surprise_direction(
    controller: DopamineController,
) -> None:
    """INV-DA1: sign of δ = r + γ·V' − V matches the surprise direction.

    Sweeps a 4×2 grid of (reward, fixed V/V') scenarios split into three
    surprise classes — better than expected, worse than expected,
    matching expectation — and asserts each δ lands on the correct side
    of zero. The bounds are derived from the TD formula itself, not
    from a lucky numerical threshold.
    """
    value_estimate = 0.5
    next_value_estimate = 0.6
    gamma = 0.98

    # Baseline prediction r_pred = V − γ·V'  ⟹  δ(r_pred) = 0 exactly.
    baseline_reward = value_estimate - gamma * next_value_estimate

    # Δ = 0.2 is large enough to dominate any float-accumulation noise
    # yet small enough to stay in the controller's validated range.
    delta = 0.2
    scenarios: list[tuple[str, float, str]] = [
        ("better_than_expected", baseline_reward + delta, "positive"),
        ("worse_than_expected", baseline_reward - delta, "negative"),
        ("as_expected", baseline_reward, "zero"),
        ("strongly_better", baseline_reward + 2.0 * delta, "positive"),
        ("strongly_worse", baseline_reward - 2.0 * delta, "negative"),
    ]

    for label, reward, expected_class in scenarios:
        rpe = controller.compute_rpe(
            reward=reward,
            value=value_estimate,
            next_value=next_value_estimate,
            discount_gamma=gamma,
        )
        if expected_class == "positive":
            # Sign check: theoretical epsilon is exactly 0 because the
            # TD formula is affine with slope +1, so any positive Δ
            # on top of r_pred gives a strictly positive δ.
            assert rpe > 0.0, (
                f"INV-DA1 VIOLATED on scenario={label}: rpe={rpe:.6f} ≤ 0 "
                f"for reward > baseline. "
                f"Expected δ > 0 when reward exceeds prediction. "
                f"Observed at reward={reward:.6f}, V={value_estimate}, "
                f"V'={next_value_estimate}, gamma={gamma}. "
                f"Physical reasoning: δ = r + γV' − V is linear in r with "
                f"slope +1, so δ(r_pred + Δ) > δ(r_pred) = 0 for Δ > 0."
            )
        elif expected_class == "negative":
            # Sign check with epsilon=0: linearity of δ in r makes the
            # threshold theoretical, not a fitted tolerance.
            assert rpe < 0.0, (
                f"INV-DA1 VIOLATED on scenario={label}: rpe={rpe:.6f} ≥ 0 "
                f"for reward < baseline. "
                f"Expected δ < 0 when reward falls short of prediction. "
                f"Observed at reward={reward:.6f}, V={value_estimate}, "
                f"V'={next_value_estimate}, gamma={gamma}. "
                f"Physical reasoning: δ = r + γV' − V decreases linearly "
                f"with r, so a smaller reward yields a negative δ."
            )
        else:  # "zero"
            # Baseline case — δ should sit at machine zero since
            # controller.compute_rpe is the exact TD formula without
            # noise or clipping.
            assert abs(rpe) < 1e-12, (
                f"INV-DA1 VIOLATED on scenario={label}: rpe={rpe:.3e} ≠ 0 "
                f"for reward matching the baseline prediction. "
                f"Expected |δ| < 1e-12 (machine-zero) at r = V − γV'. "
                f"Observed at reward={reward}, V={value_estimate}, "
                f"V'={next_value_estimate}, gamma={gamma}. "
                f"Physical reasoning: by construction r_pred cancels every "
                f"term in δ = r + γV' − V exactly at float precision."
            )


def test_td_error_is_linear_in_reward(controller: DopamineController) -> None:
    """INV-DA7: ∂δ/∂r = 1 exactly for fixed (V, V', γ).

    Holds (V, V', γ) fixed and sweeps reward through a grid. For every
    pair (r_i, r_j) in the grid the finite difference δ(r_j) − δ(r_i)
    must equal r_j − r_i to double-precision — this is the algebraic
    linearity of the TD formula.
    """
    value_estimate = 0.3
    next_value_estimate = 0.7
    gamma = 0.95
    reward_grid = [-0.5, -0.2, -0.05, 0.0, 0.05, 0.2, 0.5]

    rpe_values: list[tuple[float, float]] = []
    for reward in reward_grid:
        rpe = controller.compute_rpe(
            reward=reward,
            value=value_estimate,
            next_value=next_value_estimate,
            discount_gamma=gamma,
        )
        rpe_values.append((reward, rpe))

    # Linearity tolerance is float-precision — the TD formula adds and
    # multiplies finite values, so the finite-difference slope should
    # equal 1 within a few ULPs across the 0.5-wide reward range.
    float_precision_epsilon = 1e-12

    for i, (reward_i, rpe_i) in enumerate(rpe_values):
        for j, (reward_j, rpe_j) in enumerate(rpe_values):
            if i >= j:
                continue
            reward_delta = reward_j - reward_i
            rpe_delta = rpe_j - rpe_i
            slope_error = abs(rpe_delta - reward_delta)
            assert slope_error < float_precision_epsilon, (
                f"INV-DA7 VIOLATED: ∂δ/∂r ≠ 1 between reward={reward_i} "
                f"and reward={reward_j}. "
                f"Expected δ(r_j) − δ(r_i) = r_j − r_i = {reward_delta:.6f}. "
                f"Observed δ-delta = {rpe_delta:.6f}, slope error = "
                f"{slope_error:.3e}. "
                f"At V={value_estimate}, V'={next_value_estimate}, "
                f"gamma={gamma}. "
                f"Physical reasoning: δ = r + γV' − V is affine in r with "
                f"slope +1 exactly; any deviation means the controller "
                f"added non-linear reward processing."
            )


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic showed
# core/neuro/dopamine_execution_adapter.py killing 0 of 3 logic mutants
# (:130 Lt->GtE insufficient-data guard, :135 Eq->NotEq empty-segment guard,
# :139 Gt->LtE zero-variance guard). Nothing asserted compute_sharpe_delta's value,
# so every guard could be inverted undetected.
# ---------------------------------------------------------------------------
def test_sharpe_delta_is_exactly_zero_when_data_is_insufficient() -> None:
    """Fewer than 2*window returns yields no delta (the insufficient-data guard)."""
    from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter

    assert DopamineExecutionAdapter.compute_sharpe_delta([0.01, 0.02, 0.03], window=2) == 0.0


def test_sharpe_delta_equals_independently_computed_window_difference() -> None:
    """With sufficient data the delta is Sharpe(recent) - Sharpe(previous), computed here
    independently.

    Kills all three guards: under Lt->GtE sufficient data would return 0.0; under
    Eq->NotEq every non-empty segment would score 0.0; under Gt->LtE a positive-variance
    segment would divide by 1e-12 and explode instead of by its standard deviation.
    """
    import math

    from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter

    window = 2
    previous = [0.01, 0.03]
    recent = [0.02, 0.08]
    returns = previous + recent

    def sharpe(segment: list[float]) -> float:
        n = len(segment)
        mean = sum(segment) / n
        var = sum((x - mean) ** 2 for x in segment) / n
        return mean / math.sqrt(var)

    expected = sharpe(recent) - sharpe(previous)
    actual = DopamineExecutionAdapter.compute_sharpe_delta(returns, window=window)
    assert actual == pytest.approx(expected, rel=1e-12), (
        f"sharpe delta must equal Sharpe(recent) - Sharpe(previous) = {expected}; got {actual}"
    )
    assert actual != 0.0, "a genuine window difference must not read as zero"
    assert math.isfinite(actual) and abs(actual) < 1e3, (
        "a positive-variance segment must be divided by its std, not by the 1e-12 floor"
    )
