# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T16 — NeuroSignalBus acyclic-fanout witness for INV-SB1.

INV-SB1 states that, within a single scheduler tick, the signal
producer→consumer graph on ``core.neuro.signal_bus.NeuroSignalBus`` is
a DAG: every subscriber fires exactly once per publish call, and the
cross-channel callback graph is free of cycles.

The witness builds a three-layer DAG of subscribers:

    dopamine ──[callback_A]──▶ gaba ──[callback_B]──▶ kuramoto ──[callback_C]

Publishing on the ``dopamine`` channel must fan out down the DAG so
that each of the three callbacks (A on dopamine, B on gaba, C on
kuramoto) fires exactly once. No callback may fire zero or twice. The
final snapshot must reflect every downstream publish the DAG produced.

A hidden cycle in the fanout (e.g. a callback that re-publishes to its
own channel) would either silently skip notifications or trigger
unbounded recursion — both are INV-SB1 violations. The witness's
"exactly once" check catches the silent case; Python's recursion limit
catches the unbounded case automatically via RecursionError which
would surface as a test failure.
"""

from __future__ import annotations

import math

import pytest

from core.neuro.signal_bus import NeuroSignalBus, NeuroSignals


def test_signalbus_dag_fanout_fires_each_subscriber_exactly_once() -> None:
    """INV-SB1: three-layer DAG fanout fires each subscriber once per publish.

    Builds a linear DAG dopamine → gaba → kuramoto via subscribers that
    publish to the next channel. Asserts every callback fires exactly
    once when the top of the DAG is triggered, and that the final bus
    snapshot reflects the full downstream propagation.
    """
    bus = NeuroSignalBus()

    # Published values are DAG inputs, not fitted thresholds — latch
    # tolerance is zero because the bus is a pure latch.
    payload_root_rpe: float = 0.15  # epsilon: exact latch value for dopamine
    payload_gaba: float = 0.42  # epsilon: exact latch value for gaba
    payload_kuramoto: float = 0.55  # epsilon: exact latch value for kuramoto

    call_counts: dict[str, int] = {
        "dopamine_callback": 0,
        "gaba_callback": 0,
        "kuramoto_callback": 0,
    }

    # Layer 1: dopamine subscriber publishes to gaba. This adds a
    # dopamine → gaba edge to the fanout DAG.
    def on_dopamine(signals: NeuroSignals) -> None:
        call_counts["dopamine_callback"] += 1
        bus.publish_gaba(inhibition=payload_gaba)

    # Layer 2: gaba subscriber publishes to kuramoto. Adds gaba → kuramoto.
    def on_gaba(signals: NeuroSignals) -> None:
        call_counts["gaba_callback"] += 1
        bus.publish_kuramoto(R=payload_kuramoto)

    # Layer 3: kuramoto subscriber is a leaf — no further publishes,
    # so the DAG terminates here.
    def on_kuramoto(signals: NeuroSignals) -> None:
        call_counts["kuramoto_callback"] += 1

    bus.subscribe("dopamine", on_dopamine)
    bus.subscribe("gaba", on_gaba)
    bus.subscribe("kuramoto", on_kuramoto)

    # Trigger the DAG from the root.
    bus.publish_dopamine(rpe=payload_root_rpe)

    # Each of the three callbacks must have fired exactly once — the
    # direct INV-SB1 "each node per tick" guarantee.
    expected_calls = 1
    for callback_name in (
        "dopamine_callback",
        "gaba_callback",
        "kuramoto_callback",
    ):
        observed = call_counts[callback_name]
        assert observed == expected_calls, (
            f"INV-SB1 VIOLATED: {callback_name} fired {observed} times, "
            f"expected {expected_calls}. "
            f"Expected every subscriber to fire exactly once per DAG "
            f"traversal from a single root publish. "
            f"Observed at N=3 DAG layers, seed=none (deterministic bus). "
            f"Physical reasoning: acyclic fanout means each node is visited "
            f"exactly once — zero firings mean a missing edge, two or more "
            f"mean a cycle or duplicated subscription."
        )

    # The downstream publishes must have landed on the bus snapshot —
    # if the DAG were broken, gaba and kuramoto would still be at their
    # defaults (0.0 each).
    snapshot = bus.snapshot()
    assert snapshot.dopamine_rpe == payload_root_rpe, (
        f"INV-SB1 VIOLATED: snapshot dopamine_rpe={snapshot.dopamine_rpe} "
        f"≠ published {payload_root_rpe}. "
        f"Expected publish_dopamine to latch the exact payload. "
        f"Observed at N=3 DAG layers, seed=none. "
        f"Physical reasoning: the root publish must reach the snapshot "
        f"latch even without any subscribers."
    )
    assert snapshot.gaba_inhibition == payload_gaba, (
        f"INV-SB1 VIOLATED: snapshot gaba_inhibition="
        f"{snapshot.gaba_inhibition} ≠ expected {payload_gaba}. "
        f"Expected the layer-1 callback to publish the gaba payload. "
        f"Observed at N=3 DAG layers, seed=none. "
        f"Physical reasoning: if the dopamine → gaba edge fires, the "
        f"bus snapshot must reflect the downstream latched value."
    )
    assert snapshot.kuramoto_R == payload_kuramoto, (
        f"INV-SB1 VIOLATED: snapshot kuramoto_R={snapshot.kuramoto_R} "
        f"≠ expected {payload_kuramoto}. "
        f"Expected the layer-2 callback to publish at the DAG leaf. "
        f"Observed at N=3 DAG layers, seed=none. "
        f"Physical reasoning: a full three-layer traversal must land "
        f"the leaf publish on the snapshot."
    )

    # Sanity check on DAG shape — the total number of callback invocations
    # equals the number of DAG nodes (3), not 3² or 3^k.
    total_fanout_invocations = sum(call_counts.values())
    expected_total = 3
    assert total_fanout_invocations == expected_total, (
        f"INV-SB1 VIOLATED: total fanout invocations={total_fanout_invocations} "
        f"≠ N={expected_total} DAG nodes. "
        f"Expected a linear DAG to produce one invocation per node. "
        f"Observed at N=3 DAG layers, seed=none. "
        f"Physical reasoning: a properly acyclic fanout fires each "
        f"subscriber exactly once, so total invocations = number of nodes."
    )


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic showed core/neuro/signal_bus.py
# killing only 1 of 17 logic mutants. should_hold() — the Protector veto with
# UNCONDITIONAL priority per the maintenance hierarchy (CLAUDE.md §0, INV-YV1 L2) —
# had every branch invertible undetected (:238 Gt->LtE on the serotonin threshold,
# :240 Eq->NotEq on the crisis check, :241 Or->And joining them). The truth table
# below pins all three: each veto must fire ALONE, and neither firing must not veto.
# ---------------------------------------------------------------------------
def test_should_hold_serotonin_veto_fires_alone() -> None:
    """INV-5HT7 (serotonin veto is a SAFETY gate): serotonin strictly above the hold
    threshold vetoes on its own, with no crisis regime, for every level above it
    (kills Gt->LtE, Or->And)."""
    for excess in (0.01, 0.1, 0.29):
        bus = NeuroSignalBus()
        threshold = bus._config.serotonin_hold_threshold
        bus.publish_serotonin(level=threshold + excess)
        assert bus.should_hold() is True, (
            "INV-5HT7 VIOLATED: serotonin veto did not fire above threshold; expected hold. "
            f"At level={threshold + excess:.3f}, threshold={threshold}, crisis=False"
        )


def test_should_hold_is_false_below_threshold_without_crisis() -> None:
    """INV-5HT7 converse: neither Protector firing means no veto for every level below the
    threshold — the baseline the inversions would break."""
    for deficit in (0.01, 0.1, 0.5):
        bus = NeuroSignalBus()
        threshold = bus._config.serotonin_hold_threshold
        bus.publish_serotonin(level=threshold - deficit)
        assert bus.should_hold() is False, (
            "INV-5HT7 VIOLATED: veto fired below threshold with no crisis; expected no hold. "
            f"At level={threshold - deficit:.3f}, threshold={threshold}, crisis=False"
        )


def test_should_hold_threshold_is_strict() -> None:
    """INV-5HT7 boundary: exactly AT the threshold is not above it — the veto is strictly
    greater-than, so the boundary and its immediate neighbours are pinned."""
    bus = NeuroSignalBus()
    threshold = bus._config.serotonin_hold_threshold
    bus.publish_serotonin(level=threshold)
    at_hold = bus.should_hold()
    assert at_hold is False, (
        f"INV-5HT7 VIOLATED: got should_hold={at_hold} exactly at the threshold; expected "
        f"strict '>' (no hold). At level={threshold}, threshold={threshold}"
    )
    # tolerance: one float ulp above the threshold must already veto, one below must not
    above = NeuroSignalBus()
    above.publish_serotonin(level=math.nextafter(threshold, 1.0))
    above_hold = above.should_hold()
    assert above_hold is True, (
        f"INV-5HT7 VIOLATED: got should_hold={above_hold} one ulp above threshold; expected "
        f"hold. At threshold={threshold}"
    )
    below = NeuroSignalBus()
    below.publish_serotonin(level=math.nextafter(threshold, 0.0))
    below_hold = below.should_hold()
    assert below_hold is False, (
        f"INV-5HT7 VIOLATED: got should_hold={below_hold} one ulp below threshold; expected "
        f"no hold. At threshold={threshold}"
    )


def test_should_hold_protector_veto_zeroes_the_position() -> None:
    """INV-YV1 Layer 2: a firing Protector zeroes position size for every Kelly base, it
    does not merely dampen it. Exact zero by design (hard gate, cf. INV-CB1), so no
    tolerance is admissible."""
    for kelly_base in (0.1, 1.0, 2.5):
        bus = NeuroSignalBus()
        bus.publish_serotonin(level=bus._config.serotonin_hold_threshold + 0.1)
        hold = bus.should_hold()
        assert hold is True, (
            f"INV-YV1 L2 VIOLATED: got should_hold={hold} above threshold; expected hold. "
            f"At kelly_base={kelly_base}"
        )
        # exact zero: Protector veto is a hard gate, tolerance = 0 by contract (INV-YV1 L2)
        multiplier = bus.compute_position_multiplier(kelly_base=kelly_base)
        assert multiplier == 0.0, (
            f"INV-YV1 L2 VIOLATED: multiplier={multiplier!r} under a firing Protector; "
            f"expected exactly 0.0 (veto zeroes, never dampens). At kelly_base={kelly_base}"
        )


# ---------------------------------------------------------------------------
# TEETH — _update_regime is a four-branch classifier whose every comparison and
# boolean join survived mutation (:345 Lt->GtE/And->Or, :346 Gt->LtE,
# :351 Eq->NotEq/Lt->GtE/And->Or, :355 Gt->LtE/Lt->GtE/Or->And, :360 NotEq->Eq).
# Nothing asserted which regime a given signal vector produces. The truth table below
# pins each branch and each conjunct, so no single flip can reproduce it.
# ---------------------------------------------------------------------------
def _bus_with(rpe: float, serotonin: float) -> NeuroSignalBus:
    bus = NeuroSignalBus()
    bus.publish_dopamine(rpe=rpe)
    bus.publish_serotonin(level=serotonin)
    return bus


def test_regime_normal_when_nothing_is_elevated() -> None:
    """INV-SB2 (deterministic latch) on the stress-regime classifier: positive RPE and low
    serotonin -> NORMAL (the else branch), for several such inputs."""
    from core.neuro.signal_bus import StressRegime

    for rpe, serotonin in ((0.1, 0.1), (0.5, 0.3), (0.0, 0.0)):
        bus = _bus_with(rpe=rpe, serotonin=serotonin)
        regime = bus.snapshot().stress_regime
        assert regime is StressRegime.NORMAL, (
            f"INV-SB2 VIOLATED: got regime={regime} with nothing elevated; expected NORMAL. "
            f"At rpe={rpe}, serotonin={serotonin}"
        )


def test_regime_elevated_on_negative_rpe_alone() -> None:
    """INV-SB2 classifier, ELEVATED is an OR: negative RPE alone suffices for several
    magnitudes (kills Or->And)."""
    from core.neuro.signal_bus import StressRegime

    for rpe in (-0.01, -0.1, -0.29):
        bus = _bus_with(rpe=rpe, serotonin=0.1)
        regime = bus.snapshot().stress_regime
        assert regime is StressRegime.ELEVATED, (
            f"INV-SB2 VIOLATED: regime={regime} on negative RPE alone; expected ELEVATED. "
            f"At rpe={rpe}, serotonin=0.1"
        )


def test_regime_elevated_on_moderate_serotonin_alone() -> None:
    """INV-SB2 classifier, the other OR arm: serotonin above the elevated threshold alone
    suffices for several levels."""
    from core.neuro.signal_bus import StressRegime

    for serotonin in (0.55, 0.6, 0.7):
        bus = _bus_with(rpe=0.1, serotonin=serotonin)
        regime = bus.snapshot().stress_regime
        assert regime is StressRegime.ELEVATED, (
            f"INV-SB2 VIOLATED: regime={regime} on moderate serotonin alone; expected "
            f"ELEVATED. At rpe=0.1, serotonin={serotonin}"
        )


def test_regime_crisis_requires_both_conjuncts() -> None:
    """INV-SB2 classifier, CRISIS is an AND: deeply negative RPE *and* high serotonin
    (kills And->Or); each conjunct alone must not reach CRISIS."""
    from core.neuro.signal_bus import StressRegime

    both = _bus_with(rpe=-0.5, serotonin=0.9)
    assert both.snapshot().stress_regime is StressRegime.CRISIS, (
        "INV-SB2 VIOLATED: both conjuncts true but regime is not CRISIS; expected CRISIS. "
        "At rpe=-0.5, serotonin=0.9"
    )
    # each conjunct alone must NOT reach CRISIS
    rpe_only = _bus_with(rpe=-0.5, serotonin=0.1)
    assert rpe_only.snapshot().stress_regime is not StressRegime.CRISIS, (
        "INV-SB2 VIOLATED: CRISIS from negative RPE alone; expected a non-CRISIS regime. "
        "At rpe=-0.5, serotonin=0.1"
    )
    sero_only = _bus_with(rpe=0.1, serotonin=0.9)
    assert sero_only.snapshot().stress_regime is not StressRegime.CRISIS, (
        "INV-SB2 VIOLATED: CRISIS from high serotonin alone; expected a non-CRISIS regime. "
        "At rpe=0.1, serotonin=0.9"
    )


def test_regime_recovery_only_from_crisis_with_falling_free_energy() -> None:
    """INV-SB2 classifier path dependence: RECOVERY requires the previous regime to BE
    crisis and free energy below threshold; the same inputs from NORMAL do not recover."""
    from core.neuro.signal_bus import StressRegime

    bus = _bus_with(rpe=-0.5, serotonin=0.9)
    assert bus.snapshot().stress_regime is StressRegime.CRISIS, (
        "INV-SB2 VIOLATED: fixture did not enter CRISIS; expected CRISIS at rpe=-0.5, "
        "serotonin=0.9"
    )
    # leave the crisis trigger, publish low free energy -> RECOVERY
    bus.publish_dopamine(rpe=0.1)
    bus.publish_ecs(free_energy=0.1)
    assert bus.snapshot().stress_regime is StressRegime.RECOVERY, (
        "INV-SB2 VIOLATED: no RECOVERY after CRISIS with falling free energy; expected "
        "RECOVERY. At rpe=0.1, free_energy=0.1, previous=CRISIS"
    )
    never_crisis = _bus_with(rpe=0.1, serotonin=0.9)
    never_crisis.publish_ecs(free_energy=0.1)
    assert never_crisis.snapshot().stress_regime is not StressRegime.RECOVERY, (
        "INV-SB2 VIOLATED: RECOVERY without a preceding CRISIS; expected any other regime. "
        "At rpe=0.1, serotonin=0.9, free_energy=0.1, previous=non-CRISIS"
    )


def test_coherence_scaling_pins_the_piecewise_bounds() -> None:
    """INV-KELLY2: the Kelly coherence map is piecewise and capped: R<=floor -> min
    fraction, R>=ceil -> max fraction, and every R in between stays within [min, max].

    Pins :281/:283. With NORMAL regime (scale 1.0) and zero GABA the multiplier is exactly
    kelly_base * coherence_scale, so an inverted bound cannot reproduce both endpoints.
    """
    cfg_bus = NeuroSignalBus()
    cfg = cfg_bus._config

    low = NeuroSignalBus()
    low.publish_gaba(inhibition=0.0)
    low.publish_kuramoto(R=cfg.kelly_coherence_floor - 0.1)
    low_multiplier = low.compute_position_multiplier(kelly_base=1.0)
    assert low_multiplier == pytest.approx(cfg.kelly_min_fraction, abs=1e-12), (
        f"INV-KELLY2 VIOLATED: got multiplier={low_multiplier:.6f}; R below the floor must "
        f"clamp to the MINIMUM Kelly fraction {cfg.kelly_min_fraction}. "
        f"At R={cfg.kelly_coherence_floor - 0.1:.4f}, kelly_base=1.0"
    )

    high = NeuroSignalBus()
    high.publish_gaba(inhibition=0.0)
    high.publish_kuramoto(R=cfg.kelly_coherence_ceil + 0.1)
    high_multiplier = high.compute_position_multiplier(kelly_base=1.0)
    assert high_multiplier == pytest.approx(cfg.kelly_max_fraction, abs=1e-12), (
        f"INV-KELLY2 VIOLATED: got multiplier={high_multiplier:.6f}; R above the ceiling must "
        f"reach the MAXIMUM Kelly fraction {cfg.kelly_max_fraction}. "
        f"At R={cfg.kelly_coherence_ceil + 0.1:.4f}, kelly_base=1.0"
    )

    for r_mid in (cfg.kelly_coherence_floor, 0.5 * (cfg.kelly_coherence_floor + cfg.kelly_coherence_ceil), cfg.kelly_coherence_ceil):
        mid = NeuroSignalBus()
        mid.publish_gaba(inhibition=0.0)
        mid.publish_kuramoto(R=r_mid)
        multiplier = mid.compute_position_multiplier(kelly_base=1.0)
        assert cfg.kelly_min_fraction <= multiplier <= cfg.kelly_max_fraction, (
            f"INV-KELLY2 VIOLATED: multiplier={multiplier:.6f} outside the configured cap "
            f"[{cfg.kelly_min_fraction}, {cfg.kelly_max_fraction}]; expected the applied "
            f"fraction never to exceed the cap. At R={r_mid:.4f}, kelly_base=1.0"
        )


def test_history_is_capped_at_max_history() -> None:
    """INV-SB2 (pure latch, bounded state): the ring buffer trims only when it exceeds the
    cap, and it does trim — pins :382."""
    bus = NeuroSignalBus()
    bus._max_history = 3
    for i in range(6):
        bus.publish_dopamine(rpe=0.01 * i)
    assert len(bus._history) == 3, (
        f"INV-SB2 VIOLATED: got history length={len(bus._history)}, expected the cap 3 — an "
        f"inverted bound either never trims or trims while under the cap. At max_history=3, "
        f"publishes=6"
    )
