from datetime import datetime, timedelta, timezone

import pytest

from src.system.state_model import LifecycleModel, LifecycleState


def test_valid_transition_sequence_respects_invariants() -> None:
    model = LifecycleModel()
    now = datetime.now(timezone.utc)

    model.transition(LifecycleState.READY, reason="config loaded", at=now)
    model.transition(
        LifecycleState.RUNNING,
        reason="services healthy",
        at=now + timedelta(seconds=1),
    )
    model.transition(
        LifecycleState.DEGRADED,
        reason="latency spike",
        at=now + timedelta(seconds=2),
    )
    model.transition(
        LifecycleState.RECOVERING,
        reason="rollback initiated",
        at=now + timedelta(seconds=3),
    )
    model.transition(
        LifecycleState.RUNNING,
        reason="stabilized",
        at=now + timedelta(seconds=4),
    )

    model.verify_invariants()
    assert model.state == LifecycleState.RUNNING
    assert [t.to_state for t in model.transitions] == [
        LifecycleState.READY,
        LifecycleState.RUNNING,
        LifecycleState.DEGRADED,
        LifecycleState.RECOVERING,
        LifecycleState.RUNNING,
    ]


def test_invalid_transition_is_rejected() -> None:
    model = LifecycleModel()
    with pytest.raises(ValueError):
        model.transition(LifecycleState.RUNNING)


def test_terminal_state_blocks_additional_changes() -> None:
    model = LifecycleModel()
    model.transition(LifecycleState.READY)
    model.transition(LifecycleState.RUNNING)
    model.transition(LifecycleState.STOPPED)

    assert model.state == LifecycleState.STOPPED
    with pytest.raises(ValueError):
        model.transition(LifecycleState.RUNNING)


def test_monotonic_timestamp_invariant_enforced() -> None:
    model = LifecycleModel()
    now = datetime.now(timezone.utc)
    model.transition(LifecycleState.READY, at=now)

    with pytest.raises(ValueError):
        model.transition(LifecycleState.RUNNING, at=now - timedelta(seconds=1))
