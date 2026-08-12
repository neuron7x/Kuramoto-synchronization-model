# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for GABAPositionGate — inhibition-based position sizing.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import pytest

from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.signal_bus import NeuroSignalBus


@pytest.fixture
def bus() -> NeuroSignalBus:
    return NeuroSignalBus()


@pytest.fixture
def gate(bus: NeuroSignalBus) -> GABAPositionGate:
    return GABAPositionGate(bus)


# ── Gating reduces position size ─────────────────────────────────────


@pytest.mark.L3
class TestGatePositionSize:
    """GABA inhibition multiplicatively reduces position size."""

    def test_zero_inhibition_passes_through(
        self, bus: NeuroSignalBus, gate: GABAPositionGate
    ) -> None:
        """INV-GABA3: zero inhibition leaves any raw position unchanged.

        Sweeps several base sizes under inhibition=0 and asserts the
        gate returns each base verbatim. This is the identity-under-
        rest witness of the position_reduction contract.
        """
        bus.publish_gaba(0.0)
        for base in (10.0, 100.0, 1_000.0, 10_000.0):
            result = gate.gate_position_size(base)
            assert result == pytest.approx(base), (
                f"INV-GABA3 VIOLATED: gate at inhibition=0 returned {result:.6f} "
                f"instead of raw base={base}. "
                f"Expected effective=raw when no inhibition applied. "
                f"Observed at inhibition=0.0, base_size={base}. "
                f"Physical reasoning: GABA is a multiplicative brake; no brake → identity."
            )
            assert result <= base, (
                f"INV-GABA3 VIOLATED: effective={result:.6f} > raw={base}. "
                f"Expected effective ≤ raw at all base sizes. "
                f"Observed at inhibition=0.0, base_size={base}. "
                f"Physical reasoning: inhibition may only reduce, never amplify."
            )

    def test_full_inhibition_zeros_position(
        self, bus: NeuroSignalBus, gate: GABAPositionGate
    ) -> None:
        """INV-GABA3: full inhibition collapses every raw base to zero.

        Sweeps base sizes under inhibition=1 and asserts the gate clamps
        every one to zero. This is the saturation witness of the
        position_reduction contract.
        """
        bus.publish_gaba(1.0)
        for base in (10.0, 100.0, 1_000.0, 10_000.0):
            result = gate.gate_position_size(base)
            assert result == pytest.approx(0.0), (
                f"INV-GABA3 VIOLATED at saturation: effective={result:.6f} ≠ 0 "
                f"for base={base} at inhibition=1.0. "
                f"Expected effective=0 at maximum inhibition. "
                f"Observed at inhibition=1.0, base_size={base}. "
                f"Physical reasoning: gate must collapse position on full brake."
            )
            assert result <= base, (
                f"INV-GABA3 VIOLATED: effective={result:.6f} > raw={base} "
                f"at maximum inhibition. "
                f"Expected effective ≤ raw at all inhibition levels. "
                f"Observed at inhibition=1.0, base_size={base}. "
                f"Physical reasoning: GABA cannot amplify position under any state."
            )

    def test_partial_inhibition_reduces_proportionally(
        self, bus: NeuroSignalBus, gate: GABAPositionGate
    ) -> None:
        """INV-GABA3: partial inhibition reduces position proportionally
        across every base size.

        Sweeps base sizes under inhibition=0.5 and asserts the effective
        position equals base/2 in every case — the linear-scaling
        witness of position_reduction.
        """
        bus.publish_gaba(0.5)
        for base in (10.0, 100.0, 1_000.0, 10_000.0):
            result = gate.gate_position_size(base)
            expected = base * 0.5
            assert 0.0 < result < base, (
                f"INV-GABA3 VIOLATED: effective={result:.6f} outside (0, {base}) "
                f"under partial inhibition. "
                f"Expected 0 < effective < raw. "
                f"Observed at inhibition=0.5, base_size={base}. "
                f"Physical reasoning: mid-range inhibition is neither passthrough nor zero."
            )
            assert result == pytest.approx(expected), (
                f"INV-GABA3 VIOLATED: effective={result:.6f} ≠ expected={expected}. "
                f"Expected linear scaling effective = base × (1 − inhibition). "
                f"Observed at inhibition=0.5, base_size={base}. "
                f"Physical reasoning: default gate is multiplicative-linear."
            )

    def test_result_never_negative(self, bus: NeuroSignalBus, gate: GABAPositionGate) -> None:
        """INV-GABA1: gate output stays in [0, 1]-scaled range across inputs.

        Sweeps inhibition over its full [0, 1] domain and asserts the
        effective position is always non-negative and bounded by the raw.
        """
        base = 100.0
        # Lower bound derived from the GABA1 gate law: the multiplicative
        # brake on a non-negative base cannot yield a negative effective
        # size, so the theoretical epsilon floor is 0.0 exactly.
        lower_bound_epsilon = 0.0
        for inhibition in (0.0, 0.25, 0.5, 0.75, 1.0):
            bus.publish_gaba(inhibition)
            result = gate.gate_position_size(base)
            assert result >= lower_bound_epsilon, (
                f"INV-GABA1 VIOLATED: effective={result:.6f} < epsilon="
                f"{lower_bound_epsilon} at inhibition={inhibition}. "
                f"Expected effective ≥ 0 by gate clamp. "
                f"Observed at base_size=100.0. "
                f"Physical reasoning: negative position from a brake is meaningless."
            )
            assert result <= base, (
                f"INV-GABA1 VIOLATED: effective={result:.6f} > base={base} "
                f"at inhibition={inhibition}. "
                f"Expected effective ≤ base across the full inhibition range. "
                f"Observed at base_size=100.0. "
                f"Physical reasoning: multiplicative gate outputs in [0, 1]·base."
            )


# ── Inhibition update from market state ──────────────────────────────


@pytest.mark.L3
class TestUpdateInhibition:
    """Market-driven inhibition via sigmoid activation."""

    def test_high_vix_increases_inhibition(
        self, bus: NeuroSignalBus, gate: GABAPositionGate
    ) -> None:
        """INV-GABA2: monotone rise in inhibition as VIX increases.

        Sweeps VIX across several levels with other inputs held fixed,
        and demands the inhibition sequence is monotonically non-
        decreasing. A drop anywhere in the sweep is a violation of the
        qualitative "higher VIX → stronger inhibition" contract.
        """
        vix_sweep = [5.0, 10.0, 20.0, 40.0, 60.0, 80.0]
        inh_sweep = [gate.update_inhibition(vix=v, volatility=0.1, rpe=0.0) for v in vix_sweep]
        for i in range(1, len(inh_sweep)):
            assert inh_sweep[i] >= inh_sweep[i - 1] - 1e-12, (
                f"INV-GABA2 VIOLATED: inhibition dropped from "
                f"{inh_sweep[i - 1]:.6f} (vix={vix_sweep[i - 1]}) to "
                f"{inh_sweep[i]:.6f} (vix={vix_sweep[i]}). "
                f"Expected monotone non-decreasing inhibition as vix rises. "
                f"Observed at vol=0.1, rpe=0.0 with full vix sweep {vix_sweep}. "
                f"Physical reasoning: sigmoid(w_vix·vix/30 + …) is monotone in vix, "
                f"so inhibition must be monotone in vix with other inputs fixed."
            )
        assert inh_sweep[-1] > inh_sweep[0], (
            f"INV-GABA2 VIOLATED: inhibition at vix=80 ({inh_sweep[-1]:.6f}) "
            f"did not exceed vix=5 ({inh_sweep[0]:.6f}). "
            f"Expected strict rise across an order-of-magnitude vix change. "
            f"Observed at vol=0.1, rpe=0.0. "
            f"Physical reasoning: sigmoid responds to a finite change in argument."
        )

    def test_negative_rpe_increases_inhibition(
        self, bus: NeuroSignalBus, gate: GABAPositionGate
    ) -> None:
        pos = gate.update_inhibition(vix=20.0, volatility=0.1, rpe=0.5)
        neg = gate.update_inhibition(vix=20.0, volatility=0.1, rpe=-0.5)
        assert neg > pos

    def test_inhibition_bounded_zero_one(self, bus: NeuroSignalBus, gate: GABAPositionGate) -> None:
        """INV-GABA1: inhibition gate output lies in [0, 1] across the
        full (vix × vol × rpe) grid.

        Iterates a 4×4×5 Cartesian grid of market-state inputs and asserts
        the sigmoid-based inhibition never leaves [0, 1]. This is the
        universal-bound witness for INV-GABA1 on the update path.
        """
        for vix in [0.0, 15.0, 50.0, 100.0]:
            for vol in [0.0, 0.1, 0.5, 1.0]:
                for rpe in [-1.0, -0.5, 0.0, 0.5, 1.0]:
                    inh = gate.update_inhibition(vix=vix, volatility=vol, rpe=rpe)
                    assert 0.0 <= inh <= 1.0, (
                        f"INV-GABA1 VIOLATED: inhibition={inh:.6f} outside [0, 1] "
                        f"at vix={vix}, vol={vol}, rpe={rpe}. "
                        f"Expected inhibition ∈ [0, 1] as sigmoid output. "
                        f"Physical reasoning: σ(z) ∈ (0, 1) strictly; any escape "
                        f"means the update bypassed the sigmoid clamp."
                    )

    def test_publishes_to_bus(self, bus: NeuroSignalBus, gate: GABAPositionGate) -> None:
        inh = gate.update_inhibition(vix=30.0, volatility=0.2, rpe=0.0)
        assert bus.snapshot().gaba_inhibition == pytest.approx(inh, abs=1e-6)


# ── STDP-like plasticity ─────────────────────────────────────────────


@pytest.mark.L3
class TestSTDPPlasticity:
    """Negative RPE increases inhibition sensitivity (learn from pain)."""

    def test_repeated_negative_rpe_increases_w_rpe(self, bus: NeuroSignalBus) -> None:
        gate = GABAPositionGate(bus, plasticity_rate=0.1)
        initial_w = gate.w_rpe

        # Repeatedly feed negative RPE
        for _ in range(10):
            gate.update_inhibition(vix=20.0, volatility=0.1, rpe=-0.8)

        assert gate.w_rpe > initial_w, "w_rpe should grow after negative RPE"

    def test_positive_rpe_does_not_change_w_rpe(self, bus: NeuroSignalBus) -> None:
        gate = GABAPositionGate(bus, plasticity_rate=0.1)
        initial_w = gate.w_rpe

        for _ in range(10):
            gate.update_inhibition(vix=20.0, volatility=0.1, rpe=0.5)

        assert gate.w_rpe == pytest.approx(initial_w)

    def test_plasticity_increases_inhibition_over_time(self, bus: NeuroSignalBus) -> None:
        gate = GABAPositionGate(bus, plasticity_rate=0.1)

        # First call: baseline sensitivity
        inh_first = gate.update_inhibition(vix=20.0, volatility=0.1, rpe=-0.5)
        # After repeated negative RPE, same inputs should yield higher inhibition
        for _ in range(20):
            gate.update_inhibition(vix=20.0, volatility=0.1, rpe=-0.5)
        inh_later = gate.update_inhibition(vix=20.0, volatility=0.1, rpe=-0.5)

        assert inh_later > inh_first
