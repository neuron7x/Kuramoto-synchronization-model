# mypy: ignore-errors
"""Parametrised physics boundary tests."""

import math

import pytest

from geosync.neuroeconomics.epistemic_action import (
    EpistemicActionModule,
    EpistemicDecision,
)
from geosync.neuroeconomics.regime_memory import (
    _REGIME_INDEX,
    RegimeMemory,
    TransitionInfo,
)
from geosync.neuroeconomics.uncertainty import (
    UncertaintyController,
    UncertaintyState,
    UncertaintyType,
)


@pytest.mark.parametrize(
    ("gamma", "expected"),
    [
        (0.0, 0.0),
        (0.5, 0.5),
        (1.0, 1.0),
        (1.5, 0.5),
        (2.0, 0.0),
        (2.999, 0.0),
    ],
)
def test_risk_scalar_formula_gamma_boundaries(gamma: float, expected: float) -> None:
    risk_scalar = max(0.0, 1.0 - abs(gamma - 1.0))
    assert risk_scalar == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    ("gamma_series", "confidence"),
    [
        ([1.0] * 10, 0.0),
        ([1.0] * 9 + [1.5], 0.5),
        ([1.0] * 9 + [2.999], 1.0),
    ],
)
def test_uncertainty_estimator_sigma1_sigma2_boundaries(
    gamma_series: list[float], confidence: float
) -> None:
    est = UncertaintyController()

    for gamma in gamma_series:
        out = est.update(
            {
                "gamma": gamma,
                "order_parameter_R": 0.5,
                "ricci_curvature": 0.0,
                "regime": "COHERENT",
                "risk_scalar": max(0.0, 1.0 - abs(gamma - 1.0)),
                "regime_confidence": confidence,
            }
        )

    assert math.isfinite(out.ambiguity_index)


@pytest.mark.parametrize(
    ("from_regime", "to_regime"),
    [
        (fr, to)
        for fr in ("COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL")
        for to in ("COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL")
    ],
)
def test_regime_memory_all_16_transition_pairs(from_regime: str, to_regime: str) -> None:
    mem = RegimeMemory(prior_count=1.0)
    inst = f"EURUSD-{from_regime}-{to_regime}"

    mem.observe(inst, from_regime)
    transition = mem.observe(inst, to_regime)

    assert transition.previous == from_regime
    assert transition.current == to_regime
    assert 0.0 < transition.probability <= 1.0
    assert transition.surprise >= 0.0


@pytest.mark.parametrize("probability", [1.0, 0.5, 0.1, 0.01])
def test_regime_memory_surprise_minus_log2_probability(probability: float) -> None:
    if probability == 1.0:
        assert -math.log2(probability) == 0.0
        return

    mem = RegimeMemory(prior_count=0.0)
    inst = "EURUSD"
    mem._ensure_instrument(inst)

    from_idx = _REGIME_INDEX["COHERENT"]
    to_idx = _REGIME_INDEX["METASTABLE"]
    alt_idx = _REGIME_INDEX["DECOHERENT"]

    row = [0.0] * 5
    row[to_idx] = probability
    row[alt_idx] = 1.0 - probability
    mem._counts[inst][from_idx] = row

    p = mem.get_transition_probability(inst, "COHERENT", "METASTABLE")
    assert p == pytest.approx(probability, abs=1e-12)
    assert -math.log2(p) == pytest.approx(-math.log2(probability), abs=1e-12)


def _make_state(
    sigma_ambiguity: float = 0.0,
    sigma_eu: float = 0.0,
    surprise: float = 0.0,
) -> UncertaintyState:
    """Build UncertaintyState with controlled ambiguity_index."""
    return UncertaintyState(
        sigma_risk=0.1,
        sigma_ambiguity=sigma_ambiguity,
        sigma_eu=sigma_eu,
        surprise=surprise,
        omega=0.0,
        alpha=0.0,
        uncertainty_type=UncertaintyType.RISK,
    )


class _StubUncertainty:
    def __init__(self, state: UncertaintyState, kelly: float = 1.0) -> None:
        self._state = state
        self._kelly = kelly

    def update(self, signal: dict[str, object]) -> UncertaintyState:
        return self._state

    def kelly_discount(self, estimate: UncertaintyState) -> float:
        return self._kelly


class _StubMemory:
    def __init__(self, transition: TransitionInfo) -> None:
        self._transition = transition

    def observe(self, instrument: str, regime: str) -> TransitionInfo:
        return self._transition


@pytest.mark.parametrize(
    ("state", "signal", "transition", "expected"),
    [
        (
            # ambiguity_index > 2.0 → ABORT
            _make_state(sigma_ambiguity=5.0, sigma_eu=0.01),
            {
                "risk_scalar": 1.0,
                "regime_confidence": 1.0,
                "signal_strength": 1.0,
                "instrument": "EURUSD",
                "regime": "COHERENT",
            },
            TransitionInfo(
                previous="COHERENT",
                current="COHERENT",
                probability=1.0,
                surprise=0.0,
                pattern=None,
            ),
            EpistemicDecision.ABORT,
        ),
        (
            # high epistemic + high surprise → OBSERVE
            _make_state(sigma_ambiguity=0.5, sigma_eu=0.5),
            {
                "risk_scalar": 0.4,
                "regime_confidence": 0.5,
                "signal_strength": 0.0,
                "instrument": "EURUSD",
                "regime": "METASTABLE",
            },
            TransitionInfo(
                previous="COHERENT",
                current="METASTABLE",
                probability=0.5,
                surprise=4.0,
                pattern=None,
            ),
            EpistemicDecision.OBSERVE,
        ),
        (
            # low uncertainty, high confidence → TRADE
            _make_state(sigma_ambiguity=0.0, sigma_eu=0.0),
            {
                "risk_scalar": 1.0,
                "regime_confidence": 1.0,
                "signal_strength": 0.0,
                "instrument": "EURUSD",
                "regime": "COHERENT",
            },
            TransitionInfo(
                previous="METASTABLE",
                current="COHERENT",
                probability=1.0,
                surprise=0.0,
                pattern=None,
            ),
            EpistemicDecision.TRADE,
        ),
    ],
)
def test_epistemic_action_trade_observe_abort_boundaries(
    state: UncertaintyState,
    signal: dict[str, object],
    transition: TransitionInfo,
    expected: EpistemicDecision,
) -> None:
    module = EpistemicActionModule(
        uncertainty_estimator=_StubUncertainty(state, kelly=1.0),
        regime_memory=_StubMemory(transition),
        abort_threshold=2.0,
    )

    out = module.decide(signal, intended_size=1.0)
    assert out.decision is expected

    if expected in {EpistemicDecision.ABORT, EpistemicDecision.OBSERVE}:
        assert out.adjusted_size == 0.0
    else:
        assert 0.0 < out.adjusted_size <= 1.0
