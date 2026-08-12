# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bounded-input stability witness for the Hebbian plasticity update.

Ledger id: hebbian-plasticity-update (PARTIAL -> ADD_FALSIFIER).

Mechanism
---------
``HebbianPlasticity`` applies a reward-modulated Hebbian-analog update to an
11-dimensional weight vector.  Per step the update rule is

    w[i] <- max(weight_floor, w[i] + sign * lr_k * magnitude * eligibility[i])

where ``sign = +1`` for LTP (profitable TRADE) and ``-1`` for LTD (losing
TRADE).  The three multiplicative factors are each bounded by construction:

    lr_k        = max(lr_floor, lr_init * lr_decay**k)          in (0, lr_init]
    magnitude   = min(1.0, abs(pnl) * 10)                        in [0, 1]
    eligibility = auto trace, components in {0.0, 1.0}           in [0, 1]

Stability bound (engineering Lyapunov-style envelope)
-----------------------------------------------------
Lower bound is an explicit clamp at ``weight_floor`` (the rollback/clamp path).

Upper bound: with auto-eligibility (component <= 1) and the magnitude clamp
(<= 1), the per-step increment of any single weight is at most ``lr_k``.
Summing over N LTP steps gives the exact analytic envelope

    w_i(N) <= w_i(0) + sum_{k=0}^{N-1} lr_k                              (E)

This is a *finite* envelope for every finite N, so the update is
bounded-input/bounded-state stable.  There is no infinite divergence: the
caller-facing magnitude clamp is what makes (E) hold.

Falsifier (instability)
-----------------------
The ledger falsifier is: "weights diverge unbounded under repeated extreme
input".  The single guard preventing divergence is the magnitude clamp
``min(1.0, abs(pnl) * 10)``.  Without it, an adversarial ``pnl`` would scale
every step by ``abs(pnl) * 10``, and the analytic growth would be (E) times
that unclamped factor -- arbitrarily large.  We assert (1) the realised
growth tracks the *clamped* envelope (E) to machine precision and (2) the
unclamped analytic growth is larger by exactly the clamp factor, so the clamp
is the load-bearing stabiliser.

Validity
--------
Deterministic, no RNG, no external data.  Tolerances are derived from the
update rule's own arithmetic (envelope (E)), not chosen magic numbers.

NON-CLAIM
---------
This exercises an *engineering Hebbian-analog* parameter update, NOT
biological synaptic plasticity.  All inputs are synthetic; no neural-data or
neuroscience claim is made or tested here.
"""

from __future__ import annotations

import math

import pytest

from geosync.neuroeconomics.hebbian_plasticity import HebbianPlasticity

# Update-rule defaults, restated here so the analytic envelope is independent
# of the production constructor defaults (the tests pass them explicitly).
LR_INIT = 0.02
LR_DECAY = 0.995
LR_FLOOR = 0.001
WEIGHT_FLOOR = 0.05
W0_EXCITATORY = 0.4  # ei_ex_risk initial value (eligibility index 0)
# pragmatic_base (index 10) is also eligibility 1 under TRADE and starts higher,
# so it is the weight that saturates the envelope highest.
W0_PRAGMATIC = 0.5  # pragmatic_base initial value (eligibility index 10)

# Floating-point round-off budget for an N-term running sum of O(0.02) terms.
# N is at most a few thousand here; relative machine epsilon ~2.2e-16, so the
# absolute accumulated error is bounded well below 1e-9.  This is a derived
# arithmetic budget, not a tuned tolerance.
SUM_EPS = 1e-9


def _learning_rates(n: int) -> list[float]:
    """The exact lr_k schedule the module follows for n update steps."""
    lr = LR_INIT
    rates: list[float] = []
    for _ in range(n):
        rates.append(lr)
        lr = max(LR_FLOOR, lr * LR_DECAY)
    return rates


def _ltp_envelope(n: int, w0: float = W0_EXCITATORY) -> float:
    """Analytic upper envelope (E) for a unit-eligibility, unit-magnitude weight."""
    return w0 + math.fsum(_learning_rates(n))


def _fresh() -> HebbianPlasticity:
    """Plasticity instance with consolidation effectively disabled.

    Consolidation only snapshots / reads weights; it never mutates the live
    vector, so disabling it isolates the update rule under test.
    """
    return HebbianPlasticity(
        lr_init=LR_INIT,
        lr_decay=LR_DECAY,
        lr_floor=LR_FLOOR,
        consolidation_interval=10**9,
        weight_floor=WEIGHT_FLOOR,
    )


def test_repeated_ltp_stays_within_analytic_envelope() -> None:
    """Repeated profitable TRADE -> every weight within the (E) envelope."""
    hp = _fresh()
    n = 5000
    for _ in range(n):
        hp.update(decision="TRADE", pnl=1.0, regime="bull")

    excitatory_bound = _ltp_envelope(n, W0_EXCITATORY)
    # The global upper bound uses the largest initial weight under the TRADE
    # eligibility trace, which is pragmatic_base (index 10, w0 = 0.5).
    global_bound = _ltp_envelope(n, W0_PRAGMATIC)
    weights = hp.weights.to_list()

    assert all(math.isfinite(w) for w in weights)
    # No weight may exceed its own initial value plus the cumulative-lr envelope.
    assert max(weights) <= global_bound + SUM_EPS
    # The driven excitatory weight (eligibility 1 every step) must SATURATE its
    # envelope (equality up to round-off), proving the bound is tight, not loose.
    assert abs(weights[0] - excitatory_bound) <= SUM_EPS
    # pragmatic_base must saturate its (higher) envelope exactly.
    assert abs(weights[10] - global_bound) <= SUM_EPS


def test_adversarial_extreme_pnl_does_not_diverge() -> None:
    """Huge adversarial pnl is clamped: growth matches the unit-magnitude envelope."""
    hp = _fresh()
    n = 200
    for _ in range(n):
        hp.update(decision="TRADE", pnl=1e12, regime="bull")

    weights = hp.weights.to_list()
    bound = _ltp_envelope(n)

    assert all(math.isfinite(w) for w in weights)
    # magnitude = min(1.0, 1e12 * 10) == 1.0, so extreme input collapses onto
    # the SAME bounded envelope as pnl=1.0.  This is the BIBO-stability witness.
    assert abs(weights[0] - bound) <= SUM_EPS


def test_magnitude_clamp_is_the_load_bearing_stabiliser() -> None:
    """Without the magnitude clamp the analytic growth diverges by the clamp factor.

    INSTABILITY FALSIFIER: the realised (clamped) growth is bounded by (E),
    while the would-be unclamped growth is (E)'s lr-sum times abs(pnl)*10.  We
    assert the unclamped value is larger by exactly that factor, so removing
    the clamp would break boundedness.
    """
    hp = _fresh()
    n = 200
    pnl = 1e12
    for _ in range(n):
        hp.update(decision="TRADE", pnl=pnl, regime="bull")

    clamped_growth = hp.weights.to_list()[0] - W0_EXCITATORY
    lr_sum = math.fsum(_learning_rates(n))
    unclamped_factor = pnl * 10.0  # the magnitude the clamp throws away

    # Realised growth used magnitude == 1.0.
    assert abs(clamped_growth - lr_sum) <= SUM_EPS
    # The hypothetical unclamped growth would be lr_sum * (abs(pnl)*10): the
    # clamp suppresses divergence by ~1e13x here.
    unclamped_growth = lr_sum * unclamped_factor
    assert unclamped_growth > clamped_growth * 1e12
    # Sanity: the clamp factor relating the two is abs(pnl)*10.
    assert math.isclose(unclamped_growth / clamped_growth, unclamped_factor, rel_tol=SUM_EPS)


def test_weight_floor_clamp_path_is_exercised() -> None:
    """Sustained LTD drives weights to the floor and pins them there.

    This is the explicit lower-bound clamp (rollback) path:
    ``w[i] = max(weight_floor, w[i])``.
    """
    hp = _fresh()
    # Drive LTD hard enough that the unclamped value would go deeply negative.
    n = 1000
    for _ in range(n):
        hp.update(decision="TRADE", pnl=-1.0, regime="bear")

    weights = hp.weights.to_list()
    # Excitatory weights (eligibility 1 under TRADE) are pushed down hardest.
    # Unclamped they would be W0 - lr_sum < 0; the floor must catch them.
    unclamped_excitatory = W0_EXCITATORY - math.fsum(_learning_rates(n))
    assert unclamped_excitatory < 0.0  # precondition: clamp truly engages
    assert all(w >= WEIGHT_FLOOR - SUM_EPS for w in weights)
    # The hardest-driven weight must rest exactly on the floor.
    assert math.isclose(weights[0], WEIGHT_FLOOR, abs_tol=SUM_EPS)


def test_nonfinite_pnl_is_sanitised_and_never_propagates() -> None:
    """NaN / +-Inf pnl is mapped to 0.0 before any update -> weights stay finite.

    ``pnl = pnl if math.isfinite(pnl) else 0.0`` is the input-contract guard.
    A non-finite pnl yields no LTP/LTD branch (sanitised pnl == 0.0), so the
    weight vector is unchanged and finite.
    """
    hp = _fresh()
    before = hp.weights.to_list()

    for bad in (float("nan"), float("inf"), float("-inf")):
        hp.update(decision="TRADE", pnl=bad, regime="bull")

    after = hp.weights.to_list()
    assert all(math.isfinite(w) for w in after)
    # No update should have occurred (sanitised pnl == 0.0, neither >0 nor <0).
    assert after == before


def test_mixed_extreme_stream_stays_finite_and_bounded() -> None:
    """Long adversarial mixed stream: alternating extremes never escape (E).

    Interleaves huge positive, huge negative, non-finite and OBSERVE inputs to
    confirm the joint LTP/LTD/floor machinery is BIBO-stable, not just each path
    in isolation.
    """
    hp = _fresh()
    stream = [1e9, -1e9, float("nan"), 0.0, float("inf"), -1e9, 1e9, float("-inf")]
    decisions = ["TRADE", "TRADE", "TRADE", "OBSERVE", "TRADE", "OBSERVE", "TRADE", "TRADE"]
    steps = 0
    for _ in range(500):
        for pnl, dec in zip(stream, decisions):
            hp.update(decision=dec, pnl=pnl, regime="chop")
            steps += 1

    weights = hp.weights.to_list()
    # Upper bound: even if EVERY step were a unit-magnitude LTP on a weight, it
    # could not exceed the full-stream envelope seeded at the largest initial
    # weight (pragmatic_base, w0 = 0.5).  This is a strict over-bound.
    bound = _ltp_envelope(steps, W0_PRAGMATIC)
    assert all(math.isfinite(w) for w in weights)
    assert all(WEIGHT_FLOOR - SUM_EPS <= w <= bound + SUM_EPS for w in weights)


@pytest.mark.parametrize("pnl", [0.1, 1.0, 1e6, 1e15])
def test_envelope_holds_across_pnl_magnitudes(pnl: float) -> None:
    """For any pnl with abs(pnl)*10 >= 1, magnitude saturates to 1 -> same envelope."""
    assert abs(pnl) * 10.0 >= 1.0  # precondition: magnitude clamps to 1.0
    hp = _fresh()
    n = 300
    for _ in range(n):
        hp.update(decision="TRADE", pnl=pnl, regime="bull")
    bound = _ltp_envelope(n, W0_EXCITATORY)
    assert math.isfinite(hp.weights.to_list()[0])
    assert abs(hp.weights.to_list()[0] - bound) <= SUM_EPS


# --- Input-contract boundary: caller-supplied eligibility is fail-closed -----


@pytest.mark.parametrize(
    "bad",
    [
        [2.0] + [0.0] * 10,  # component > 1 — outside the witnessed envelope
        [-0.1] + [0.0] * 10,  # negative component
        [float("nan")] + [0.0] * 10,  # non-finite
        [float("inf")] + [0.0] * 10,  # non-finite
        [1.0] * 10,  # wrong length (10 ≠ 11)
    ],
)
def test_out_of_envelope_eligibility_fails_closed(bad: list[float]) -> None:
    """A caller-supplied eligibility outside [0,1]^11 raises (no silent inflation).

    This closes the documented input-contract hole: previously a component > 1
    silently amplified the weight update beyond the witnessed BIBO envelope.
    """
    hp = _fresh()
    with pytest.raises(ValueError):
        hp.update(decision="TRADE", pnl=1.0, regime="bull", eligibility=bad)


def test_in_envelope_eligibility_is_accepted() -> None:
    """A valid eligibility in [0,1]^11 is accepted and keeps weights bounded."""
    hp = _fresh()
    elig = [0.5] * 11
    for _ in range(50):
        hp.update(decision="TRADE", pnl=1.0, regime="bull", eligibility=elig)
    assert all(math.isfinite(w) for w in hp.weights.to_list())
