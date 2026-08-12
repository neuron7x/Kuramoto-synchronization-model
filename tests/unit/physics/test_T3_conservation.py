# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T3 — Conservation Laws tests.

Tests for portfolio energy conservation.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

import core.physics.portfolio_conservation as pc_module
from core.physics.portfolio_conservation import PortfolioEnergyConservation


@pytest.fixture
def conserv() -> PortfolioEnergyConservation:
    return PortfolioEnergyConservation(epsilon=0.05, return_window=5)


class TestRebalancePreservesEnergy:
    """Portfolio rebalancing should conserve energy within ε."""

    def test_identical_state_conserved(self, conserv):
        pos = np.array([1.0, 1.0, 1.0])
        ret = np.array([0.01, -0.01, 0.005])
        er = np.array([0.02, 0.01, 0.015])

        E1 = conserv.compute_total(pos, ret, er)
        E2 = conserv.compute_total(pos, ret, er)
        assert conserv.check_conservation(E1, E2) is True

    def test_small_rebalance_conserved(self, conserv):
        pos1 = np.array([1.0, 1.0, 1.0])
        pos2 = np.array([1.01, 0.99, 1.0])
        ret = np.array([0.01, -0.01, 0.005])
        er = np.array([0.02, 0.01, 0.015])

        E1 = conserv.compute_total(pos1, ret, er)
        E2 = conserv.compute_total(pos2, ret, er)
        # Small rebalance → small ΔE
        delta = abs(E2 - E1)
        assert delta < 1.0  # reasonable bound


class TestRegimeChangeDetected:
    """Large energy violations should be detected as regime changes."""

    def test_large_delta_violates(self, conserv):
        assert conserv.check_conservation(1.0, 2.0) is False
        assert conserv.violation_count == 1

    def test_violation_counter_increments(self, conserv):
        conserv.check_conservation(1.0, 2.0)
        conserv.check_conservation(1.0, 3.0)
        assert conserv.violation_count == 2

    def test_reset_violations(self, conserv):
        conserv.check_conservation(1.0, 2.0)
        conserv.reset_violations()
        assert conserv.violation_count == 0


class TestSyntheticTrendingMarket:
    """In trending market, kinetic energy dominates."""

    def test_trending_has_high_kinetic(self, conserv):
        pos = np.array([1.0, 1.0])
        large_returns = np.array([0.50, 0.40])  # very strong trend
        er = np.array([0.02, 0.02])  # small expected returns

        ek = conserv.compute_kinetic(pos, large_returns)
        ep = conserv.compute_potential(pos, er)
        assert ek > abs(ep), "Kinetic should dominate in trending market"


class TestSyntheticMeanRevertingMarket:
    """In mean-reverting market, potential energy dominates."""

    def test_mean_reverting_has_low_kinetic(self, conserv):
        pos = np.array([1.0, 1.0])
        small_returns = np.array([0.001, -0.001])  # nearly flat
        er = np.array([0.10, 0.10])  # strong mean-reversion signal

        ek = conserv.compute_kinetic(pos, small_returns)
        ep = conserv.compute_potential(pos, er)
        assert abs(ep) > ek, "Potential should dominate in mean-reverting market"


class TestKineticEnergy:
    def test_zero_returns_zero_kinetic(self, conserv):
        pos = np.array([1.0, 2.0])
        ret = np.array([0.0, 0.0])
        assert conserv.compute_kinetic(pos, ret) == 0.0

    def test_kinetic_non_negative(self, conserv):
        rng = np.random.default_rng(42)
        for _ in range(20):
            pos = rng.normal(0, 10, 5)
            ret = rng.normal(0, 0.05, 5)
            assert conserv.compute_kinetic(pos, ret) >= 0


class TestPotentialEnergy:
    def test_aligned_positions_negative_potential(self, conserv):
        """Positions aligned with expected returns → negative potential (stable)."""
        pos = np.array([1.0, 1.0])
        er = np.array([0.05, 0.05])
        ep = conserv.compute_potential(pos, er)
        assert ep < 0, "Aligned positions should have negative potential"

    def test_shape_mismatch_raises(self, conserv):
        with pytest.raises(ValueError, match="must match"):
            conserv.compute_potential(np.array([1.0]), np.array([1.0, 2.0]))


class TestHonestBudgetToleranceFraming:
    """Pins the truth-in-labeling reframe: this is a tunable |ΔE| ≤ ε budget
    tolerance on a descriptive scalar, NOT a Noether conservation law.

    EXTRAPOLATED heuristic — no continuous symmetry, no conserved current.
    """

    def test_check_is_a_budget_tolerance_band_at_epsilon(self, conserv):
        """A move with |ΔE| just above ε is flagged; just below/at ε is allowed.

        This is the operational meaning of a budget tolerance: the verdict is
        a threshold comparison against the tunable ε, with no appeal to any
        conserved quantity.
        """
        eps = conserv.epsilon
        # Just below the band: allowed (within budget).
        assert conserv.check_conservation(0.0, eps - 1e-6) is True
        # Exactly at the band edge (≤ comparison): allowed.
        assert conserv.check_conservation(0.0, eps) is True
        # Just above the band: flagged (over budget) — and counted.
        before_flags = conserv.violation_count
        assert conserv.check_conservation(0.0, eps + 1e-6) is False
        assert conserv.violation_count == before_flags + 1

    def test_epsilon_is_a_tunable_threshold_not_a_constant(self):
        """ε is a free, caller-set threshold — the band moves when ε moves."""
        loose = PortfolioEnergyConservation(epsilon=1.0)
        tight = PortfolioEnergyConservation(epsilon=0.001)
        # Same |ΔE| = 0.1: inside the loose budget, outside the tight one.
        assert loose.check_conservation(0.0, 0.1) is True
        assert tight.check_conservation(0.0, 0.1) is False

    def test_public_docstrings_disclaim_conservation_law_framing(self):
        """The module/class/method docstrings must NOT assert a conservation
        law, energy preservation, or a gravitational potential — and MUST
        state the honest budget-tolerance framing and EXTRAPOLATED tier.
        """
        # Collapse internal whitespace so newline-wrapped phrases still match.
        def _norm(text: str) -> str:
            return " ".join(text.split()).lower()

        module_doc = pc_module.__doc__ or ""
        module_lower = _norm(module_doc)
        class_doc = PortfolioEnergyConservation.__doc__ or ""
        potential_doc = inspect.getdoc(PortfolioEnergyConservation.compute_potential) or ""
        potential_lower = _norm(potential_doc)

        # The conservation-law / Noether framing must appear only in DISOWNED
        # (negated) form. The bare positive claim "preserves energy" must be
        # absent; the disclaimer "not a Noether conservation law" must be present.
        assert "not a noether conservation law" in module_lower
        assert "preserves energy" not in module_lower
        assert "preserves any" not in module_lower
        # The original "mirrors gravitational potential" claim is gone and is
        # explicitly disowned in compute_potential.
        assert "mirrors gravitational potential" not in potential_lower
        assert "not a gravitational potential" in potential_lower

        # Honest budget-tolerance framing and provenance tier are present.
        assert "budget" in module_lower
        assert "tolerance" in module_lower
        assert "tunable" in module_lower
        assert "EXTRAPOLATED" in module_doc
        assert "budget tolerance" in class_doc.lower()
