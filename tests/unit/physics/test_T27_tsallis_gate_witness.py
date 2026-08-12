# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T27 — ``TsallisRiskGate`` witness tests mapped to physics invariants.

The legacy ``test_T5_tsallis_gate.py`` covers behaviour but does not
reference any INV-* ID — the validator (L1 gate) would reject the
file under the new physics-contract enforcement. This module adds the
missing INV-* anchored witnesses for:

* **INV-FE2** — ``position_multiplier`` output is always non-negative
  (Tsallis entropy S_q ≥ 0 implies the gate output can never be
  negative). The inline comment inside the source
  (``# INV-FE2: gate output non-negative``) states exactly this
  contract.
* **INV-HPC2** — q is finite on every finite input; q ≥ 1 by
  construction. q is the MLE Student-t fit mapped via
  ``q = (ν + 3)/(ν + 1)`` with ν clamped to ``[2.05, 200]``, so q is
  bounded in ``(1, (2.05+3)/(2.05+1)] = (1, 1.6557]``.
* **INV-SB2** — ``evaluate`` is deterministic: identical returns yield
  bit-identical gate output across calls.

Every tolerance is derived from the gate's algebra rather than a
magic literal.
"""

from __future__ import annotations

import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from core.physics.tsallis_gate import TsallisRegime, TsallisRiskGate

# ---------------------------------------------------------------------------
# INV-FE2 — gate output non-negative
# ---------------------------------------------------------------------------


@given(
    q=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    q_normal=st.floats(min_value=1.05, max_value=1.45, allow_nan=False),
    q_crisis_delta=st.floats(min_value=0.05, max_value=0.5, allow_nan=False),
)
@settings(max_examples=200, deadline=None)
def test_position_multiplier_non_negative(q: float, q_normal: float, q_crisis_delta: float) -> None:
    """INV-FE2: ``position_multiplier(q) ≥ 0`` for every finite q.

    Derivation: the gate returns
        f(q) = max(0, 1 - (q - q_normal) / (q_crisis - q_normal)).
    The outer ``max(0, …)`` is a hard floor, so f ≥ 0 by
    construction. A bug that replaced ``max(0, …)`` with the raw
    linear ramp would leak negative values for q > q_crisis — the
    falsification probe below (q = 10) targets exactly that path.

    Tolerance:
        f(q) is a piecewise-linear function of float64 inputs; the
        one-subtraction-one-division evaluation has relative error
        ≤ 4·eps_64 ≈ 8.9e-16. Since the bound is 0 and 1, we use an
        absolute tolerance of 1e-12 (far above unit roundoff).
    """
    # epsilon: 4·eps_64 ≈ 8.9e-16 on the linear ramp; padded to 1e-12.
    tol = 1e-12

    q_crisis = q_normal + q_crisis_delta
    gate = TsallisRiskGate(window=30, q_normal=q_normal, q_crisis=q_crisis)
    mult = gate.position_multiplier(q)

    assert math.isfinite(mult), (
        f"INV-FE2 VIOLATED: position_multiplier({q}) = {mult}, non-finite. "
        f"Observed at q_normal={q_normal:.3f}, q_crisis={q_crisis:.3f}. "
        f"Expected finite real output per Tsallis gate contract."
    )
    assert mult >= -tol, (
        f"INV-FE2 VIOLATED: position_multiplier({q:.3f}) = {mult:.3e} < "
        f"-{tol:.0e}. Observed at q_normal={q_normal:.3f}, "
        f"q_crisis={q_crisis:.3f}. "
        f"Expected f ≥ 0 from max(0, linear_ramp). "
        f"Reasoning: Tsallis entropy S_q ≥ 0 ⟹ gate output must be "
        f"non-negative; the explicit max-clamp enforces this."
    )
    assert mult <= 1.0 + tol, (
        f"INV-FE2 VIOLATED: position_multiplier({q:.3f}) = {mult:.6f} > "
        f"1 + {tol:.0e}. Observed at q_normal={q_normal:.3f}, "
        f"q_crisis={q_crisis:.3f}. "
        f"Expected f ≤ 1 (full position). "
        f"Reasoning: the linear ramp starts at 1 when q ≤ q_normal."
    )


def test_position_multiplier_falsification_extreme_q() -> None:
    """INV-FE2 falsification probe: extreme q must NOT leak negative f.

    Falsification inputs: q = 10.0, q = 1e6 (far above crisis). A
    broken implementation that used the raw linear ramp without the
    ``max(0, …)`` guard would produce
        f(10) = 1 - (10 - 1.35)/(1.55 - 1.35) = 1 - 43.25 = -42.25.
    The witness enforces the guarded contract and reports the bug
    with the exact observed scalar.
    """
    gate = TsallisRiskGate(window=30, q_normal=1.35, q_crisis=1.55)

    falsification_qs = [10.0, 100.0, 1e6]
    for q in falsification_qs:
        mult = gate.position_multiplier(q)
        # epsilon: 0.0 — crisis floor hard-codes exact 0.
        assert mult == 0.0, (
            f"INV-FE2 VIOLATED: position_multiplier({q:.1e}) = {mult:.3e}, "
            f"expected exactly 0.0. "
            f"Observed at q_normal=1.35, q_crisis=1.55. "
            f"Reasoning: q ≥ q_crisis must saturate the max(0,…) floor "
            f"and return 0 exactly (not a tiny negative float)."
        )


def test_regime_boundaries_inclusive() -> None:
    """INV-FE2: regime classification is consistent with position_multiplier.

    Derivation: the CRISIS regime starts at q = q_crisis (inclusive
    lower bound). At the boundary f must be 0, and ``classify_regime``
    must return ``CRISIS``. Any off-by-one between the classifier and
    the multiplier would corrupt risk-gate decisions at the regime
    boundary.
    """
    # epsilon: exact boundary; tolerance 0 on both sides.
    gate = TsallisRiskGate(window=30, q_normal=1.35, q_crisis=1.55)

    q_boundary = 1.55
    observed_regime = gate.classify_regime(q_boundary)
    assert observed_regime == TsallisRegime.CRISIS, (
        f"INV-FE2 VIOLATED: classify_regime(1.55) = {observed_regime.value} "
        f"violates expected CRISIS. "
        f"Observed at q={q_boundary}, q_normal=1.35, q_crisis=1.55. "
        f"Expected inclusive lower bound on CRISIS regime."
    )
    # epsilon: crisis-floor hard-code → exact 0.0.
    mult_boundary = gate.position_multiplier(q_boundary)
    assert mult_boundary == 0.0, (
        f"INV-FE2 VIOLATED: position_multiplier={mult_boundary:.3e} "
        f"violates expected 0.0. "
        f"Observed at q={q_boundary}, q_normal=1.35, q_crisis=1.55. "
        f"Reasoning: q ≥ q_crisis → no new positions by contract."
    )

    # Just below: ELEVATED regime, mult > 0.
    q_below = 1.55 - 1e-9
    observed_below = gate.classify_regime(q_below)
    assert observed_below == TsallisRegime.ELEVATED, (
        f"INV-FE2 VIOLATED: classify_regime={observed_below.value} "
        f"violates expected ELEVATED. "
        f"Observed at q={q_below}, q_normal=1.35, q_crisis=1.55. "
        f"Expected strict < q_crisis bound for ELEVATED."
    )


# ---------------------------------------------------------------------------
# INV-HPC2 — estimate_q finite and bounded
# ---------------------------------------------------------------------------


@given(
    arrays(
        dtype=np.float64,
        shape=st.integers(min_value=4, max_value=256),
        elements=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
)
@settings(max_examples=40, deadline=None)
def test_estimate_q_finite_and_ge_1(returns: np.ndarray) -> None:
    """INV-HPC2: ``estimate_q(returns)`` is finite and ≥ 1 for finite input.

    Derivation:
        q = (ν + 3)/(ν + 1) where ν is the MLE Student-t degrees of
        freedom clamped to [2.05, 200].
        * At ν = 200 → q = 203/201 ≈ 1.00995 → floored at ≥ 1.
        * At ν = 2.05 → q = 5.05/3.05 ≈ 1.6557 (the ceiling).
        * The Gaussian / degenerate path returns exactly 1.0.
    The explicit ``max(q, 1.0)`` floor enforces q ≥ 1. The ν clamp
    keeps ν finite (no NaN/Inf) and brackets the supported tail range.

    Note: max_examples is held at 40 (not 200) because each draw runs a
    full Student-t MLE (~35 ms); 40 draws keeps the witness under the
    PR-gate per-test budget while still sweeping the finite-input domain.

    Tolerance: the q map is exact in float64 given ν; the ceiling check
    pads one ULP via 1e-12.
    """
    # epsilon: structural — only guard is q ≥ 1 floor.
    q = TsallisRiskGate.estimate_q(returns)
    assert math.isfinite(q), (
        f"INV-HPC2 VIOLATED: estimate_q returned non-finite {q}. "
        f"Observed at N={returns.size}, returns.range="
        f"[{returns.min():.3e}, {returns.max():.3e}]. "
        f"Expected finite output from the ν-clamped MLE map."
    )
    assert q >= 1.0, (
        f"INV-HPC2 VIOLATED: q={q:.6f} < 1. "
        f"Observed at N={returns.size}. "
        f"Expected q ≥ 1 from the explicit max(q, 1.0) floor. "
        f"Reasoning: Tsallis q ≥ 1 on fat-tailed distributions."
    )
    # Upper bound: with ν clamped at 2.05, q ≤ (2.05+3)/(2.05+1) = 5.05/3.05.
    # epsilon: 5·eps_64 ≈ 1.1e-15, padded to 1e-12.
    q_ceiling = (2.05 + 3.0) / (2.05 + 1.0)
    assert q <= q_ceiling + 1e-12, (
        f"INV-HPC2 VIOLATED: q={q:.6f} > ceiling={q_ceiling:.6f}. "
        f"Observed at N={returns.size}. "
        f"Expected ν clamp at 2.05 to cap q ≤ 5.05/3.05 ≈ 1.6557."
    )


def test_estimate_q_falsification_zero_variance() -> None:
    """INV-HPC2 falsification: constant / near-constant returns must not crash.

    Falsification input: zero-variance series. Without the ``std <
    1e-12`` guard the MLE would attempt to fit a Student-t to a point
    mass and the standardisation would produce NaN/Inf. The
    implementation detects the degenerate case and returns q = 1.0
    exactly (the Gaussian limit).

    Tolerance: exact — the early return hard-codes 1.0.
    """
    # epsilon: 0.0 — early return hard-codes 1.0.
    for bad_series in (np.zeros(32), np.full(32, 3.14), np.ones(100) * -1.5):
        q = TsallisRiskGate.estimate_q(bad_series)
        assert q == 1.0, (
            f"INV-HPC2 VIOLATED: estimate_q(constant)={q}, expected 1.0. "
            f"Observed at N={bad_series.size}, value={bad_series[0]}. "
            f"Expected guard path to return exact Gaussian q=1. "
            f"Reasoning: zero-variance standardisation must not leak NaN."
        )


def test_estimate_q_heavy_tail_direction() -> None:
    """INV-HPC2 qualitative: q(heavy-tail) > q(gaussian) after 3 seeds.

    Witness for monotonicity of the MLE q estimator under tail
    heaviness. The estimator fits the Student-t degrees of freedom ν by
    maximum likelihood and maps q = (ν+3)/(ν+1), a strictly decreasing
    function of ν. A Gaussian sample drives ν large (q → 1); a t(ν=3)
    sample fits a small ν (true q* = (3+3)/(3+1) = 1.5). So the heavy
    sample MUST recover a strictly larger q.

    The test uses 3 independent seeds and demands the order in every
    realisation — a flaky single seed cannot hide a broken direction.

    Tolerance: the true q-gap is q*(ν=3) − q*(ν→∞) = 1.5 − 1.0 = 0.5.
    The MLE of ν at N=200 has a sampling std that propagates to a q
    std of order 0.1; the empirically observed gaps over these seeds are
    ≥ 0.37 (well above noise). We require a gap > 0.05 as the minimum
    reliably distinguishable effect, leaving a wide safety margin.
    """
    # epsilon: 0.05 — the true gap is 0.5; observed gaps ≥ 0.37; 0.05 is
    #          a conservative floor that the MLE direction must clear on
    #          every seed.
    min_gap = 0.05

    for seed in range(3):
        rng = np.random.default_rng(seed=seed)
        gauss = rng.standard_normal(200)
        heavy = rng.standard_t(df=3, size=200)

        q_g = TsallisRiskGate.estimate_q(gauss)
        q_h = TsallisRiskGate.estimate_q(heavy)

        assert q_h > q_g + min_gap, (
            f"INV-HPC2 VIOLATED: q_heavy={q_h:.4f} !> q_gauss={q_g:.4f} + "
            f"{min_gap}. Observed at N=200, seed={seed}. "
            f"Expected heavier tails → higher q per Bickel-Freedman bound."
        )


def test_evaluate_handles_insufficient_observations() -> None:
    """INV-HPC2 edge: fewer than ``min_observations`` returns conservative default.

    Falsification input: series shorter than ``min_observations``.
    The contract returns a fallback result with q=1.5 (ELEVATED) and
    a reduced position multiplier (0.25). A missing guard would
    either crash on empty kurtosis computation or mis-classify the
    regime.
    """
    gate = TsallisRiskGate(window=60, min_observations=30)
    short = np.array([0.01, -0.01, 0.005], dtype=np.float64)

    result = gate.evaluate(short)
    # epsilon: exact hard-coded fallback values (contract tolerance = 0).
    assert result.q == 1.5, (
        f"INV-HPC2 VIOLATED: q={result.q} violates expected fallback 1.5. "
        f"Observed at N={short.size}, min_observations=30, window=60. "
        f"Expected conservative default per gate contract."
    )
    assert result.regime == TsallisRegime.ELEVATED, (
        f"INV-HPC2 VIOLATED: regime={result.regime.value} violates expected "
        f"ELEVATED. Observed at N={short.size}, min_observations=30, window=60. "
        f"Expected conservative fallback under data scarcity."
    )
    # epsilon: exact hard-coded 0.25 fallback (tolerance = 0).
    assert result.position_multiplier == 0.25, (
        f"INV-HPC2 VIOLATED: multiplier={result.position_multiplier} "
        f"violates expected 0.25 fallback. "
        f"Observed at N={short.size}, min_observations=30, window=60."
    )


def test_evaluate_fail_closed_on_non_q_gaussian() -> None:
    """INV-HPC2 / INV-FE2 fail-closed: a non-q-Gaussian sample must NOT
    emit a confident q-derived regime.

    This is the verdict-flip guard for the MLE+GoF rewrite. A strongly
    bimodal mixture is not in the q-Gaussian / Student-t family; its KS
    p-value against the fitted t CDF collapses to ~0. The gate must:
      * set ``gof_passed = False`` (the fit is rejected), and
      * return the conservative fallback — q=1.5, ELEVATED,
        position_multiplier=0.25 — identical to the data-scarcity branch.

    Falsification: if the gate emitted a confident q-derived regime
    (gof_passed True, or a multiplier other than the 0.25 fallback) from
    a sample that is provably not q-Gaussian, the fail-closed contract
    is violated and an unfitted distribution could drive sizing.
    """
    rng = np.random.default_rng(1)
    bimodal = np.concatenate([rng.normal(-5.0, 0.3, 500), rng.normal(5.0, 0.3, 500)])
    gate = TsallisRiskGate(window=2000, min_observations=20, gof_alpha=0.05)
    result = gate.evaluate(bimodal)

    # epsilon: 0.0 — gof_passed is a boolean contract flag.
    assert result.gof_passed is False, (
        f"INV-HPC2 VIOLATED (fail-closed): gof_passed={result.gof_passed} on a "
        f"bimodal sample with gof_p={result.gof_pvalue:.3e}. "
        f"Observed at N=1000, seed=1, gof_alpha=0.05. "
        f"Expected the KS GoF to reject a two-mode mixture and fail closed."
    )
    # epsilon: 0.05 is the configured KS significance level (gof_alpha),
    # not a magic threshold — it is the rejection tolerance of the GoF test.
    assert result.gof_pvalue < 0.05, (
        f"INV-HPC2 VIOLATED (fail-closed): bimodal gof_p={result.gof_pvalue:.3e} "
        f">= alpha=0.05. Observed at N=1000, seed=1. "
        f"Expected p ≪ alpha for a clearly non-q-Gaussian sample."
    )
    # epsilon: 0.0 — exact conservative fallback values (contract tolerance 0).
    assert result.q == 1.5, (
        f"INV-HPC2 VIOLATED (fail-closed): fallback q={result.q} != 1.5. "
        f"Observed at N=1000, seed=1, gof_p={result.gof_pvalue:.3e}. "
        f"Expected the conservative fallback q on a rejected fit."
    )
    assert result.regime == TsallisRegime.ELEVATED, (
        f"INV-FE2 VIOLATED (fail-closed): regime={result.regime.value} != "
        f"ELEVATED on a rejected fit. Observed at N=1000, seed=1. "
        f"Expected the conservative fallback regime, not a q-derived one."
    )
    # epsilon: 0.0 — exact conservative fallback multiplier (tolerance 0);
    # 0.25 is the hard-coded data-scarcity/GoF-rejection fallback value.
    assert result.position_multiplier == 0.25, (
        f"INV-FE2 VIOLATED (fail-closed): multiplier="
        f"{result.position_multiplier} != 0.25 on a rejected fit. "
        f"Observed at N=1000, seed=1. "
        f"Expected the conservative fallback multiplier — no confident "
        f"sizing from an unfitted distribution."
    )


# ---------------------------------------------------------------------------
# INV-SB2 — deterministic replay
# ---------------------------------------------------------------------------


def test_evaluate_deterministic_replay() -> None:
    """INV-SB2: repeated ``evaluate`` on identical input is bit-identical.

    Falsification probe: calling ``evaluate`` from two fresh gate
    instances must produce identical results — no hidden global
    state that persists across instances.
    """
    rng = np.random.default_rng(seed=2024)
    returns = rng.standard_t(df=5, size=120) * 0.01

    gate_a = TsallisRiskGate(window=60, q_normal=1.35, q_crisis=1.55)
    gate_b = TsallisRiskGate(window=60, q_normal=1.35, q_crisis=1.55)

    r_a = gate_a.evaluate(returns)
    r_b = gate_b.evaluate(returns)

    # epsilon: structural — no RNG, no global state; tolerance 0.
    assert r_a.q == r_b.q, (
        f"INV-SB2 VIOLATED: fresh instances gave q_a={r_a.q:.10f} vs "
        f"q_b={r_b.q:.10f}, diff={r_a.q - r_b.q:.3e}. "
        f"Observed at N={returns.size}, seed=2024, window=60. "
        f"Expected bit identity across fresh gate instances."
    )
    assert r_a.position_multiplier == r_b.position_multiplier, (
        f"INV-SB2 VIOLATED: fresh instances gave f_a={r_a.position_multiplier} "
        f"vs f_b={r_b.position_multiplier}, "
        f"diff={r_a.position_multiplier - r_b.position_multiplier:.3e}. "
        f"Observed at N={returns.size}, seed=2024, window=60. "
        f"Expected bit identity per stateless gate contract."
    )
    assert r_a.regime == r_b.regime, (
        f"INV-SB2 VIOLATED: fresh instances gave regime_a={r_a.regime.value} "
        f"vs regime_b={r_b.regime.value}, observed disagreement. "
        f"Observed at N={returns.size}, seed=2024, window=60. "
        f"Expected identical regime from identical input."
    )


def test_evaluate_history_accumulates() -> None:
    """INV-SB2 state: evaluate() appends to history deterministically.

    Falsification probe: running two evaluates yields exactly 2 items
    in history — not 1 (silent drop) and not 3 (double-recording).
    """
    rng = np.random.default_rng(seed=99)
    returns = rng.standard_normal(120) * 0.01
    gate = TsallisRiskGate(window=60)
    assert len(gate.history) == 0
    gate.evaluate(returns)
    gate.evaluate(returns)
    assert len(gate.history) == 2, (
        f"INV-SB2 VIOLATED: history len={len(gate.history)} violates "
        f"expected 2 after 2 evaluate() calls. "
        f"Observed at N={returns.size}, seed=99, window=60. "
        f"Expected append-only history with one row per call."
    )
    # Two identical inputs must produce identical history rows.
    h0, h1 = gate.history[0], gate.history[1]
    assert h0.q == h1.q, (
        f"INV-SB2 VIOLATED: history[0].q={h0.q:.10f} != history[1].q={h1.q:.10f} "
        f"on identical inputs. Observed at N={returns.size}, seed=99. "
        f"Expected identical q for identical returns."
    )
    assert h0.position_multiplier == h1.position_multiplier, (
        f"INV-SB2 VIOLATED: history[0].f={h0.position_multiplier} != "
        f"history[1].f={h1.position_multiplier} on identical inputs. "
        f"Observed at N={returns.size}, seed=99, window=60."
    )


# ---------------------------------------------------------------------------
# Contract edges
# ---------------------------------------------------------------------------


def test_gate_rejects_bad_config() -> None:
    """INV-HPC2: constructor rejects bad configuration.

    Falsification inputs: q_normal ≥ q_crisis (degenerate ramp),
    window < 2, min_observations < 2. Each must raise ValueError
    rather than silently coerce.
    """
    bad_kwargs: list[tuple[dict[str, float | int], str]] = [
        ({"window": 1}, "window"),
        ({"window": 0}, "window"),
        ({"window": -3}, "window"),
        ({"q_normal": 1.5, "q_crisis": 1.5}, "q_normal"),
        ({"q_normal": 2.0, "q_crisis": 1.5}, "q_normal"),
        ({"min_observations": 1}, "min_observations"),
        ({"min_observations": 0}, "min_observations"),
    ]
    for kwargs, pattern in bad_kwargs:
        raised = False
        try:
            TsallisRiskGate(**kwargs)  # type: ignore[arg-type]
        except ValueError as exc:
            raised = pattern in str(exc)
        assert raised, (
            f"INV-HPC2 VIOLATED: constructor accepted kwargs={kwargs}. "
            f"Observed at pattern={pattern}. "
            f"Expected ValueError matching '{pattern}' on falsification input."
        )


def test_evaluate_prices_short_series_raises() -> None:
    """INV-HPC2: evaluate_prices on < 2 samples must raise.

    Falsification probe: the log-return diff needs ≥ 2 prices. A
    silent pass would produce an empty return array and propagate
    NaN downstream. The guard must fire.
    """
    gate = TsallisRiskGate()
    falsification_inputs: list[np.ndarray] = [
        np.array([100.0]),
        np.empty((1, 5)),
        np.array([], dtype=np.float64),
    ]
    for bad in falsification_inputs:
        raised = False
        try:
            gate.evaluate_prices(bad)
        except ValueError:
            raised = True
        assert raised, (
            f"INV-HPC2 VIOLATED: evaluate_prices accepted shape={bad.shape}. "
            f"Observed at N={bad.size}, ndim={bad.ndim}. "
            f"Expected ValueError per log-return diff requires ≥ 2 samples."
        )
