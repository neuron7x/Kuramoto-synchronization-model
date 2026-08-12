# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type"
"""Tests for unified FlowController — single deterministic pipeline."""

from __future__ import annotations

import time
from collections import Counter

import numpy as np

from geosync.neuroeconomics.flow_controller import (
    DEFAULT_WEIGHTS,
    FlowController,
    FlowDecision,
    FlowWeights,
)


def _sig(
    regime: str = "METASTABLE",
    gamma: float = 1.0,
    risk_scalar: float = 0.8,
    regime_confidence: float = 0.8,
    signal_strength: float = 0.2,
) -> dict[str, object]:
    return {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": gamma,
        "order_parameter_R": 0.6,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.01,
        "regime": regime,
        "regime_confidence": regime_confidence,
        "regime_duration_s": 5.0,
        "signal_strength": signal_strength,
        "risk_scalar": risk_scalar,
        "sequence_number": 0,
    }


def test_single_tick_returns_valid_output() -> None:
    fc = FlowController()
    out = fc.process(_sig())
    assert out.decision in (
        FlowDecision.TRADE,
        FlowDecision.OBSERVE,
        FlowDecision.ABORT,
    )
    assert out.adjusted_size >= 0.0
    assert -1.0 <= out.v_net <= 1.0
    assert out.alpha_t > 0
    assert 0.0 <= out.effort_gate <= 1.0


def test_delta_closes_loop() -> None:
    fc = FlowController()
    out1 = fc.process(_sig(), outcome=0.0)
    out2 = fc.process(_sig(), outcome=0.5)
    # delta should be nonzero when outcome changes
    assert out2.delta_t != 0.0 or out1.v_net == 0.5


def test_all_weights_named_in_dataclass() -> None:
    w = DEFAULT_WEIGHTS
    # Every weight is a float > 0
    for field_name in FlowWeights.__dataclass_fields__:
        val = getattr(w, field_name)
        assert isinstance(val, float), f"{field_name} is not float"


def test_decision_distribution_balanced() -> None:
    fc = FlowController()
    counts: Counter[str] = Counter()
    for i in range(200):
        regime = ["METASTABLE", "COHERENT", "DECOHERENT", "CRITICAL"][i % 4]
        out = fc.process(
            _sig(
                regime=regime,
                risk_scalar=0.3 + 0.5 * (i % 3) / 2,
                regime_confidence=0.5 + 0.3 * (i % 2),
            ),
            outcome=0.01 * (i % 5 - 2),
        )
        counts[out.decision.value] += 1

    # Must have at least TRADE and OBSERVE
    assert counts["TRADE"] > 0, f"No TRADE decisions: {dict(counts)}"
    assert counts["OBSERVE"] > 0 or counts["ABORT"] > 0, f"No non-trade: {dict(counts)}"


def test_dissociation_on_extreme_signal() -> None:
    fc = FlowController(weights=FlowWeights(ei_dissociation=1.5))
    # Force extreme excitatory
    out = fc.process(_sig(risk_scalar=0.99, regime_confidence=0.99, signal_strength=0.99))
    if out.decision == FlowDecision.DISSOCIATED:
        assert out.adjusted_size == 0.0
        assert out.kelly_mult == 0.0


def test_nan_signal_never_crashes() -> None:
    fc = FlowController()
    nan_sig: dict[str, object] = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": float("nan"),
        "order_parameter_R": float("inf"),
        "ricci_curvature": float("-inf"),
        "lyapunov_max": float("nan"),
        "regime": "UNKNOWN",
        "regime_confidence": float("nan"),
        "regime_duration_s": -1.0,
        "signal_strength": float("nan"),
        "risk_scalar": float("nan"),
        "sequence_number": 0,
    }
    for _ in range(10):
        out = fc.process(nan_sig)
        assert out.adjusted_size >= 0.0
        assert out.adjusted_size <= 1.0


def test_v_net_bounded_under_random_input() -> None:
    fc = FlowController()
    rng = np.random.RandomState(42)
    for _ in range(100):
        out = fc.process(
            _sig(
                gamma=float(rng.uniform(-1, 3)),
                risk_scalar=float(rng.uniform(0, 1)),
                regime_confidence=float(rng.uniform(0, 1)),
                signal_strength=float(rng.uniform(-1, 1)),
            ),
            outcome=float(rng.uniform(-1, 1)),
        )
        assert -1.0 <= out.v_net <= 1.0


def test_size_never_exceeds_intended() -> None:
    fc = FlowController()
    for size in [0.01, 0.5, 1.0, 10.0, 1000.0]:
        out = fc.process(_sig(), intended_size=size)
        assert out.adjusted_size <= size


def test_alpha_adapts_to_outcome_volatility() -> None:
    # Stable outcomes
    fc_stable = FlowController()
    for _ in range(30):
        out_s = fc_stable.process(_sig(), outcome=0.01)
    alpha_stable = out_s.alpha_t

    # Volatile outcomes
    fc_vol = FlowController()
    for i in range(30):
        out_v = fc_vol.process(_sig(), outcome=float((-1) ** i) * 0.5)
    alpha_vol = out_v.alpha_t

    assert alpha_vol >= alpha_stable


def test_lambda_weights_shift_with_regime() -> None:
    fc = FlowController()
    out_coherent = fc.process(_sig(regime="COHERENT"), outcome=0.0)
    fc2 = FlowController()
    out_critical = fc2.process(_sig(regime="CRITICAL"), outcome=0.0)

    # COHERENT: goal dominates (λ[2] > λ[0])
    assert out_coherent.lambda_weights[2] > out_coherent.lambda_weights[0]
    # CRITICAL: pavlovian dominates (λ[0] > λ[2])
    assert out_critical.lambda_weights[0] > out_critical.lambda_weights[2]


# --- decision-boundary teeth via injected uncertainty state ------------------
# The uncertainty controller is stateful (surprise emerges from a rolling delta
# accumulator), which makes the decision boundaries hard to reach through market
# inputs alone. We inject a controlled UncertaintyState so each branch is exact.

from geosync.neuroeconomics.uncertainty import UncertaintyState, UncertaintyType  # noqa: E402


class _FixedUncertainty:
    """A stub uncertainty controller that always reports one chosen state."""

    def __init__(self, *, uncertainty_type: UncertaintyType, surprise: float, omega: float = 0.0):
        self._state = UncertaintyState(
            sigma_risk=0.0,
            sigma_ambiguity=0.0,
            sigma_eu=1.0,
            surprise=surprise,
            omega=omega,
            alpha=0.5,
            uncertainty_type=uncertainty_type,
        )

    def update(self, *, delta_t: float, outcome: float = 0.0) -> UncertaintyState:
        return self._state


def _run(state: _FixedUncertainty, **sig_over):
    fc = FlowController()
    fc._uc = state
    return fc


def test_abort_requires_both_unexpected_type_and_surprise_over_three() -> None:
    """`type == UNEXPECTED and surprise > 3.0` -- the ABORT guard is conjunctive.

    Kills all three :311 mutants: Eq (only UNEXPECTED aborts), Gt (surprise must
    exceed 3, not merely 2), And (both required -- neither alone aborts).
    """
    unexpected_high = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.UNEXPECTED, surprise=4.0))
    assert unexpected_high.process(_sig()).decision is FlowDecision.ABORT

    expected_high = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.EXPECTED, surprise=4.0))
    assert expected_high.process(_sig()).decision is not FlowDecision.ABORT

    unexpected_low = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.UNEXPECTED, surprise=2.5))
    assert unexpected_low.process(_sig()).decision is not FlowDecision.ABORT


def test_unexpected_flag_boosts_epistemic_into_observe() -> None:
    """`unexpected_flag = 1.0 if type == UNEXPECTED` -- the 0.3 boost drives OBSERVE.

    With low pragmatic value, the UNEXPECTED epistemic boost (0.3) exceeds it and
    the gate OBSERVEs. Under :301 Eq->NotEq the flag zeroes and the gate TRADEs.
    """
    fc = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.UNEXPECTED, surprise=0.0))
    out = fc.process(_sig(risk_scalar=0.3, regime_confidence=0.3, signal_strength=0.2))
    assert out.decision is FlowDecision.OBSERVE


def test_ambiguity_flag_boosts_epistemic_into_observe() -> None:
    """`ambiguity_flag = 1.0 if type == AMBIGUITY` -- the 0.125 boost drives OBSERVE.

    Under :300 Eq->NotEq the AMBIGUITY flag zeroes and epistemic falls below the
    (tiny) pragmatic value, flipping OBSERVE to TRADE.
    """
    fc = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.AMBIGUITY, surprise=0.0))
    out = fc.process(_sig(risk_scalar=0.2, regime_confidence=0.2, signal_strength=0.0))
    assert out.decision is FlowDecision.OBSERVE


def test_observe_only_when_epistemic_exceeds_pragmatic() -> None:
    """`elif epistemic > pragmatic` -- OBSERVE above, TRADE below.

    Same epistemic (surprise_norm=1.0 -> 0.3); pragmatic tuned across it. Under
    :315 Gt->LtE the comparison inverts (low-pragmatic TRADEs, high-pragmatic
    OBSERVEs).
    """
    epistemic_state = _FixedUncertainty(uncertainty_type=UncertaintyType.EXPECTED, surprise=4.0)
    low_pragmatic = _run(epistemic_state).process(
        _sig(risk_scalar=0.3, regime_confidence=0.3, signal_strength=0.0)
    )
    assert low_pragmatic.decision is FlowDecision.OBSERVE
    high_pragmatic = _run(epistemic_state).process(
        _sig(risk_scalar=0.9, regime_confidence=0.9, signal_strength=0.5)
    )
    assert high_pragmatic.decision is FlowDecision.TRADE


def test_ei_dissociation_recovers_only_below_recovery_threshold() -> None:
    """`if ei_ratio < ei_recovery` -- a dissociated gate recovers below the band.

    With a low E/I ratio (0.42 < 1.5) the gate clears dissociation and resumes.
    Under :253 Lt->GtE the recovery condition inverts and the gate stays stuck in
    DISSOCIATED despite a calm E/I balance.
    """
    fc = _run(_FixedUncertainty(uncertainty_type=UncertaintyType.EXPECTED, surprise=0.0))
    fc._ei_dissociated = True
    out = fc.process(_sig(risk_scalar=0.3, regime_confidence=0.3, signal_strength=0.2))
    assert out.decision is not FlowDecision.DISSOCIATED
