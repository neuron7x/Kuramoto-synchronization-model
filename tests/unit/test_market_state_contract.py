import math
import pandas as pd
from hypothesis import given, settings, strategies as st

from core.indicators.kuramoto_ricci_composite import CompositeSignal, MarketPhase
from core.indicators.market_state_contract import (
    compile_market_state, MarketRegime, EntryState, MarketStateContract,
)

# adversarial floats: include NaN, +/-inf, extreme magnitudes
adv_float = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True),
    st.floats(min_value=-1e9, max_value=1e9),
    st.sampled_from([float("nan"), float("inf"), float("-inf"), 0.0, -0.0]),
)

def make(phase, **kw):
    base = dict(
        phase=phase, confidence=0.0, kuramoto_R=0.0, consensus_R=0.0,
        cross_scale_coherence=0.0, static_ricci=0.0, temporal_ricci=0.0,
        topological_transition=0.0, entry_signal=0.0, exit_signal=0.0,
        risk_multiplier=1.0, dominant_timeframe_sec=60,
        timestamp=pd.Timestamp("2026-01-01"), skipped_timeframes=[],
    )
    base.update(kw)
    return CompositeSignal(**base)

@settings(max_examples=400, deadline=None)
@given(
    phase=st.sampled_from(list(MarketPhase)),
    confidence=adv_float, kuramoto_R=adv_float, consensus_R=adv_float,
    cross_scale_coherence=adv_float, static_ricci=adv_float, temporal_ricci=adv_float,
    topological_transition=adv_float, entry_signal=adv_float, exit_signal=adv_float,
    risk_multiplier=adv_float,
)
def test_bounds_hold_under_adversarial_input(phase, **fields):
    c = compile_market_state(make(phase, **fields))
    assert -math.pi <= c.phase <= math.pi, c.phase
    assert 0.0 <= c.confidence <= 1.0, c.confidence
    assert 0.0 <= c.risk <= 1.0, c.risk
    assert isinstance(c.regime, MarketRegime)
    assert isinstance(c.entry, EntryState)
    assert isinstance(c.exit, bool)
    d = c.to_dict()
    assert set(d["evidence"]) == {"kuramoto", "ricci", "fusion", "classification"}
    # no NaN/inf leaks into the envelope numerics
    for v in (d["phase"], d["confidence"], d["risk"]):
        assert math.isfinite(v)

def test_contract_has_exact_public_keys():
    sig = make(MarketPhase.STRONG_EMERGENT, confidence=0.9, consensus_R=0.82,
               entry_signal=0.6, risk_multiplier=1.2)
    d = compile_market_state(sig).to_dict()
    # "provenance" is part of the public envelope as of the MarketState
    # provenance evidence fields + claim-boundary firewall (#1055).
    assert set(d) == {
        "phase",
        "confidence",
        "regime",
        "entry",
        "exit",
        "risk",
        "evidence",
        "provenance",
    }


def test_determinism_same_input_same_output():
    sig = make(MarketPhase.STRONG_EMERGENT, confidence=0.9, consensus_R=0.82,
               entry_signal=0.6, risk_multiplier=1.2)
    a = compile_market_state(sig).to_dict()
    b = compile_market_state(sig).to_dict()
    assert a == b

def test_low_confidence_forces_flat():
    sig = make(MarketPhase.STRONG_EMERGENT, confidence=0.3, entry_signal=0.9)
    assert compile_market_state(sig).entry == EntryState.FLAT

def test_transition_phase_maps_hold():
    sig = make(MarketPhase.TRANSITION, confidence=0.9, entry_signal=0.9)
    c = compile_market_state(sig)
    assert c.regime == MarketRegime.TRANSITION
    assert c.entry == EntryState.HOLD

def test_chaotic_lowsync_is_neutral_not_overconfident_entry():
    # low consensus + low coherence -> NEUTRAL -> FLAT even with high entry_signal
    sig = make(MarketPhase.CHAOTIC, confidence=0.99, consensus_R=0.1,
               cross_scale_coherence=0.1, entry_signal=0.95)
    c = compile_market_state(sig)
    assert c.regime == MarketRegime.NEUTRAL
    assert c.entry == EntryState.FLAT

def test_public_export_wired():
    import core.indicators as ci

    assert ci.compile_market_state is compile_market_state
    assert ci.MarketStateContract is MarketStateContract
    assert {"compile_market_state", "MarketStateContract", "MarketRegime", "EntryState"} <= set(ci.__all__)


def test_canonical_namespace_export_wired():
    # geosync.indicators is the canonical public package surface (__CANONICAL__).
    import geosync.indicators as gi

    assert gi.compile_market_state is compile_market_state
    assert gi.MarketStateContract is MarketStateContract
    assert gi.MarketRegime is MarketRegime
    assert gi.EntryState is EntryState
    assert {"compile_market_state", "MarketStateContract", "MarketRegime", "EntryState"} <= set(gi.__all__)


def test_nan_everywhere_fails_closed():
    nan = float("nan")
    sig = make(MarketPhase.CHAOTIC, confidence=nan, consensus_R=nan,
               cross_scale_coherence=nan, static_ricci=nan, temporal_ricci=nan,
               topological_transition=nan, entry_signal=nan, exit_signal=nan,
               risk_multiplier=nan)
    c = compile_market_state(sig)
    assert math.isfinite(c.phase) and math.isfinite(c.confidence) and math.isfinite(c.risk)
    assert c.entry == EntryState.FLAT  # nan confidence -> 0.0 -> <0.5 -> FLAT
