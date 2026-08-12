# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier witnesses for the DopamineExecutionAdapter tanh normaliser.

Mechanism
    ``DopamineExecutionAdapter.compute_rpe`` maps a raw reward-prediction
    residual to a bounded executive signal::

        raw = (realized_pnl - predicted_return) - |slippage| * slip_scale
        out = tanh(tanh_scale * raw)

Formula
    out = tanh(k * raw),  k = tanh_scale > 0.

Validity
    Defined for every finite ``(realized_pnl, predicted_return, slippage)``
    and every ``tanh_scale > 0``. tanh: ℝ → (−1, 1); in float64 it saturates
    to exactly ±1.0 once |k·raw| ≳ 20, so the *closed* bound out ∈ [−1, 1]
    holds for all finite inputs.

Falsifier
    Any output outside [−1, 1], or any output that reproduces the raw
    TD-error δ when |δ| > 1 (i.e. the tanh was dropped and the path silently
    upgraded to an unbounded raw-TD signal), refutes the adapter contract.

NON-CLAIM
    This adapter is a *normalized executive adapter*, NOT raw TD-error and
    NOT a biological dopamine claim; synthetic-only. The raw TD-error
    (δ = r + γV′ − V, owned by ``DopamineController`` and governed by
    INV-DA7: ∂δ/∂r = 1) and this adapter are never mixed. INV-DA7 is scoped
    to the controller; on the adapter ∂out/∂r = k·sech²(k·raw) ≠ 1 by design.
    These witnesses assert that separation rather than asserting any market
    edge.
"""

from __future__ import annotations

import math

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus

# --- Tolerance / bound derivations (no magic numbers) ----------------------
#
# SATURATION_BOUND: tanh(x) ∈ (−1, 1) for finite x and saturates to exactly
# ±1.0 in float64 once |x| ≳ 20 (cosh overflow region). Hence the *closed*
# bound |out| ≤ 1.0 is exact, not approximate.
SATURATION_BOUND = 1.0

# EXTREME_MAGNITUDE: a finite magnitude large enough to drive k·raw past the
# float64 tanh saturation knee (|x| ≳ 20) even for the smallest scale tested,
# so we exercise the closed end of the bound.
EXTREME_MAGNITUDE = 1.0e9

# TANH_SCALES: small, unit, and large k. All share the same |out| ≤ 1 bound;
# sweeping them guards the bound against any scale-dependent regression.
TANH_SCALES = (0.1, 1.0, 25.0)

# ODD_SYMMETRY_ATOL: tanh is exactly odd, tanh(−x) = −tanh(x). The only error
# is float64 round-off in evaluating tanh twice plus negating raw. Each tanh
# result has magnitude ≤ 1, so its ULP is ≤ 2·eps. Allow a few ULPs:
#   atol = 4 · eps  (eps = 2.220446e-16) ≈ 8.9e-16.
_EPS = float(2.0**-52)  # IEEE-754 double machine epsilon = 2.220446e-16
ODD_SYMMETRY_ATOL = 4.0 * _EPS


def _make_adapter(tanh_scale: float = 1.0) -> DopamineExecutionAdapter:
    """Construct an adapter on a fresh bus (synthetic, no market state)."""
    return DopamineExecutionAdapter(NeuroSignalBus(), tanh_scale=tanh_scale)


def test_output_bounded_in_closed_interval_for_finite_inputs() -> None:
    """Saturation bound: out = tanh(k·raw) ∈ [−1, 1] and finite for all inputs.

    Sweeps a deterministic grid of finite ``(pnl, predicted, slippage)`` —
    including extreme finite magnitudes that push tanh into float64 saturation —
    across several ``tanh_scale`` values. Bound is the exact closed interval
    [−SATURATION_BOUND, SATURATION_BOUND] (tanh image, saturating to ±1.0).
    """
    inputs = (
        (0.0, 0.0, 0.0),
        (1.0, 0.5, 0.1),
        (-1.0, 0.5, 0.2),
        (EXTREME_MAGNITUDE, -EXTREME_MAGNITUDE, EXTREME_MAGNITUDE),
        (-EXTREME_MAGNITUDE, EXTREME_MAGNITUDE, 0.0),
        (EXTREME_MAGNITUDE, 0.0, EXTREME_MAGNITUDE),
    )
    for tanh_scale in TANH_SCALES:
        adapter = _make_adapter(tanh_scale)
        for pnl, predicted, slippage in inputs:
            out = adapter.compute_rpe(
                realized_pnl=pnl,
                predicted_return=predicted,
                slippage=slippage,
            )
            assert math.isfinite(out), (
                "adapter bound VIOLATED: non-finite output "
                f"out={out} at (pnl={pnl}, predicted={predicted}, "
                f"slippage={slippage}, tanh_scale={tanh_scale}); every finite "
                "input must map to a finite tanh value"
            )
            assert -SATURATION_BOUND <= out <= SATURATION_BOUND, (
                "adapter bound VIOLATED: out="
                f"{out:.6f} not in [−{SATURATION_BOUND:.1f}, {SATURATION_BOUND:.1f}] "
                f"at (pnl={pnl}, predicted={predicted}, slippage={slippage}, "
                f"tanh_scale={tanh_scale}); tanh must saturate within [−1, 1]"
            )


def test_adapter_output_is_not_raw_td_error_when_raw_exceeds_bound() -> None:
    """Key non-claim falsifier: adapter ≠ raw TD-error when |raw| > 1.

    Choose an input whose raw residual raw = pnl − predicted − |slippage| is
    well outside [−1, 1] (raw = 5.0). A raw TD-error path would return 5.0; the
    adapter must instead return tanh(k·5) which is strictly inside the bound and
    strictly smaller in magnitude than raw. If the adapter ever equals raw here,
    the tanh was dropped and the signal silently upgraded to unbounded raw-TD.

    Tolerance: gap = raw − out. For k=1, out = tanh(5) ≈ 0.9999092 and the
    distance from the bound is 1 − tanh(5) = sech²-tail ≈ 9.08e-5 > 0; we assert
    the strict, sign-correct inequalities (out < raw and out ≤ 1) — no relaxed
    epsilon needed because the separation is O(1), not O(eps).
    """
    pnl, predicted, slippage = 5.0, 0.0, 0.0
    raw = (pnl - predicted) - abs(slippage)  # = 5.0, the raw TD-error analogue
    assert raw > SATURATION_BOUND, "test setup invalid: need raw outside the bound"

    adapter = _make_adapter(tanh_scale=1.0)
    out = adapter.compute_rpe(realized_pnl=pnl, predicted_return=predicted, slippage=slippage)

    assert out <= SATURATION_BOUND, (
        "NON-CLAIM falsifier VIOLATED: adapter out="
        f"{out:.6f} exceeds the bound for raw={raw}; tanh must saturate"
    )
    assert out < raw, (
        "NON-CLAIM falsifier VIOLATED: adapter out="
        f"{out:.6f} reproduced (≥) the raw TD-error raw={raw}; the adapter is "
        "NOT raw TD-error and must compress |raw| > 1 below the bound"
    )
    assert not math.isclose(out, raw), (
        "NON-CLAIM falsifier VIOLATED: adapter out="
        f"{out:.6f} equals raw TD-error raw={raw}; the tanh normalisation was "
        "dropped and the path silently upgraded to unbounded raw-TD"
    )


def test_inv_da7_linearity_does_not_hold_for_adapter_in_saturation() -> None:
    """INV-DA7 (∂δ/∂r = 1) is scoped to the controller, NOT the adapter.

    INV-DA7 — exact reward-linearity ∂δ/∂r = 1 — belongs to
    ``DopamineController`` (raw TD path). For the adapter, out = tanh(k·raw), so
    analytically ∂out/∂r = k·sech²(k·raw), which is ≪ 1 deep in saturation. We
    measure the centred finite-difference slope around raw=5 and assert it sits
    far below 1, refuting any inheritance of INV-DA7 by the adapter.

    Tolerance ceiling derivation (analytic, not magic):
        ∂out/∂r = k·sech²(k·raw). With k=1, raw=5:
        sech²(5) = 1/cosh²(5) ≈ 1.815e-4 ≪ 1.
    The centred secant over a small symmetric step h has error
    O(h²·|f‴|) and, being a secant of a concave-then-convex tanh tail, stays
    below the local derivative ceiling. We use a generous ceiling of
    LINEARITY_CEILING = 1e-2 (≈ 55× the analytic slope) so the assertion
    *cannot* pass at slope = 1 (the controller value) yet is robust to the
    finite-difference error; the gap to 1.0 is what falsifies INV-DA7 here.
    """
    k = 1.0
    raw_center = 5.0
    h = 1.0e-4  # FD step; small vs 1/k so k·raw stays in deep saturation
    adapter = _make_adapter(tanh_scale=k)

    out_hi = adapter.compute_rpe(realized_pnl=raw_center + h, predicted_return=0.0)
    out_lo = adapter.compute_rpe(realized_pnl=raw_center - h, predicted_return=0.0)
    slope = (out_hi - out_lo) / (2.0 * h)

    analytic_slope = k / (math.cosh(k * raw_center) ** 2)  # k·sech²(k·raw)
    linearity_ceiling = 1.0e-2  # ≈ 55× analytic_slope, still ≪ 1 (controller's)

    assert slope < linearity_ceiling, (
        "INV-DA7 scope VIOLATED: adapter slope ∂out/∂r="
        f"{slope:.3e} ≥ ceiling {linearity_ceiling:.1e} near raw={raw_center}; "
        f"analytic k·sech²(k·raw)={analytic_slope:.3e}. A slope at 1 would mean "
        "the adapter inherited INV-DA7 (raw-TD linearity); it must not — INV-DA7 "
        "is scoped to DopamineController, the adapter is tanh-nonlinear by design"
    )
    # Sanity: the analytic derivative the FD approximates is itself ≪ 1.
    assert analytic_slope < linearity_ceiling, (
        "INV-DA7 scope check setup invalid: analytic slope="
        f"{analytic_slope:.3e} not below ceiling {linearity_ceiling:.1e}"
    )


def test_adapter_is_monotonic_increasing_in_reward() -> None:
    """Monotonicity: out is strictly increasing in realized_pnl.

    tanh is strictly increasing and k>0, raw is affine-increasing in
    realized_pnl, so out(r) must be strictly increasing. A non-increasing pair
    refutes the monotone-normaliser contract. Strict ``>`` — no tolerance —
    because tanh is strictly monotone for any finite distinct arguments.
    """
    adapter = _make_adapter(tanh_scale=1.0)
    rewards = (-3.0, -1.0, -0.25, 0.0, 0.25, 1.0, 3.0)
    outs = [adapter.compute_rpe(realized_pnl=r, predicted_return=0.0) for r in rewards]
    for (r_lo, o_lo), (r_hi, o_hi) in zip(zip(rewards, outs), zip(rewards[1:], outs[1:])):
        assert o_hi > o_lo, (
            "monotonicity VIOLATED: out is not strictly increasing — "
            f"out({r_hi})={o_hi:.6f} ≤ out({r_lo})={o_lo:.6f}; tanh(k·raw) "
            "must be strictly increasing in reward"
        )


def test_adapter_is_odd_symmetric_about_zero_residual() -> None:
    """Odd symmetry: out(−raw) = −out(raw) since out = tanh(k·raw).

    With slippage=0 and predicted=0, raw = realized_pnl, and tanh is exactly
    odd: tanh(−x) = −tanh(x). The only departure is float64 round-off.

    Tolerance derivation: each tanh value has |out| ≤ 1, so its representation
    error is ≤ 1 ULP ≤ 2·eps; summing the two evaluations and the negation
    bounds the residual by ≈ 4·eps = ODD_SYMMETRY_ATOL ≈ 8.9e-16. No physical
    slack — purely IEEE-754 round-off.
    """
    adapter = _make_adapter(tanh_scale=1.0)
    for magnitude in (0.0, 0.3, 1.0, 4.0, 25.0):
        pos = adapter.compute_rpe(realized_pnl=magnitude, predicted_return=0.0)
        neg = adapter.compute_rpe(realized_pnl=-magnitude, predicted_return=0.0)
        assert math.isclose(neg, -pos, abs_tol=ODD_SYMMETRY_ATOL, rel_tol=0.0), (
            "odd-symmetry VIOLATED: out(−raw) ≠ −out(raw) at magnitude="
            f"{magnitude}: out(+)={pos:.17g}, out(−)={neg:.17g}, "
            f"residual={abs(neg + pos):.3e} > atol={ODD_SYMMETRY_ATOL:.3e}; "
            "tanh(k·raw) must be exactly odd up to float64 round-off"
        )
