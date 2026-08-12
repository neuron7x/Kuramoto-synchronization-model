# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Safety regression: ActionGate must fail closed on misordered gate thresholds.

ActionGate accepts an arbitrary DopamineSnapshot from any caller, so — unlike the
internal controller path, which pre-orders thresholds via check_monotonic_thresholds
— it can be handed a config where no_go_threshold > go_threshold. Such a config makes
the No-Go band (score < no_go_threshold) and the Go band (score > go_threshold)
overlap. The gate previously evaluated ``go`` before ``no_go`` and returned them as
independent booleans, so it could emit ``decision="GO"`` while ``no_go=True`` on the
same score. A safety gate must never emit GO under an invalid configuration.
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from geosync.core.neuro.dopamine.action_gate import ActionGate, DopamineSnapshot


class _Bounds:
    """Minimal structural temperature-bounds provider."""

    def temperature_bounds(self) -> tuple[float, float]:
        return (0.1, 5.0)


def _gate() -> ActionGate:
    return ActionGate(_Bounds())


def test_misordered_thresholds_fail_closed_to_no_go() -> None:
    # The exact contradictory-decision scenario: no_go_threshold (0.9) sits above
    # go_threshold (0.2). Score 0.7 is > go_threshold AND < no_go_threshold.
    snap = DopamineSnapshot(
        level=0.7,
        temperature=1.0,
        go_threshold=0.2,
        hold_threshold=0.0,
        no_go_threshold=0.9,
        release_gate_open=True,
    )
    ev = _gate().evaluate(snap)
    assert ev.decision == "NO_GO"
    assert ev.no_go is True
    assert ev.go is False


def test_ordered_config_still_emits_go() -> None:
    # A valid, ordered config (no_go 0.3 <= go 0.6) must be unaffected by the fix.
    snap = DopamineSnapshot(
        level=0.8,
        temperature=1.0,
        go_threshold=0.6,
        hold_threshold=0.2,
        no_go_threshold=0.3,
        release_gate_open=True,
    )
    ev = _gate().evaluate(snap)
    assert ev.decision == "GO"
    assert ev.go is True
    assert ev.no_go is False


@given(
    level=st.floats(min_value=-0.5, max_value=1.5),
    go_threshold=st.floats(min_value=0.0, max_value=1.0),
    hold_threshold=st.floats(min_value=0.0, max_value=1.0),
    no_go_threshold=st.floats(min_value=0.0, max_value=1.0),
    release_gate_open=st.booleans(),
    temperature=st.floats(min_value=0.05, max_value=3.0),
)
def test_flags_never_contradict_and_invalid_config_is_never_go(
    level: float,
    go_threshold: float,
    hold_threshold: float,
    no_go_threshold: float,
    release_gate_open: bool,
    temperature: float,
) -> None:
    snap = DopamineSnapshot(
        level=level,
        temperature=temperature,
        go_threshold=go_threshold,
        hold_threshold=hold_threshold,
        no_go_threshold=no_go_threshold,
        release_gate_open=release_gate_open,
    )
    ev = _gate().evaluate(snap)
    # go and no_go are mutually exclusive, and decision is their single source.
    assert not (ev.go and ev.no_go)
    assert (ev.decision == "GO") is ev.go
    assert (ev.decision == "NO_GO") is ev.no_go
    # Fail-closed contract: a misordered config can never produce GO.
    if no_go_threshold > go_threshold:
        assert ev.decision != "GO"
