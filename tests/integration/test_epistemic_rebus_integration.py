# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end integration tests for the EpistemicState ↔ RebusGate composition.

The unit tests in :mod:`tests.unit.neuro.test_epistemic_validation`
exercise :class:`core.neuro.epistemic_validation.RebusBridge` against
a :class:`unittest.mock.MagicMock` standing in for the gate. Mocks
verify the call shape but do *not* prove that the bridge composes
with the real gate's lifecycle invariants
(activation → step → forced reintegration → reset). These tests do.

Layout
------

* **Genesis composition** — a fresh, active gate accepts a halted
  epistemic state via ``RebusBridge.maybe_escalate`` and routes
  through ``emergency_exit``, restoring the prior weight set and
  resetting the gate to ``INACTIVE``.
* **Inactive-gate path** — a halted epistemic state forwarded to an
  inactive gate is a no-op (the bridge's contract is "forward only
  when both sides are open"; an inactive gate has nothing to
  restore).
* **Active-state path** — an active (non-halted) state never
  triggers escalation regardless of gate phase; the bridge
  short-circuits to ``None``.
* **Audit-trail consistency** — after escalation the gate's audit
  log records the ``emergency_exit`` event with the
  ``stressed_escalation`` reason that
  ``apply_external_safety_signal`` uses internally.

What these tests prove that the unit tests cannot
--------------------------------------------------

The bridge sends ``stressed_state=True`` to the gate. The gate's
:meth:`runtime.rebus_gate.RebusGate.apply_external_safety_signal`
method then calls :meth:`emergency_exit` *only if the gate is
currently active*. The unit tests with a MagicMock cannot enforce
that lifecycle precondition — they would happily call the mock
regardless of phase. These tests fail closed if the bridge ever
violates the contract.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from core.neuro.epistemic_validation import (
    EpistemicConfig,
    EpistemicState,
    RebusBridge,
    initial_state,
    update,
)
from runtime.rebus_gate import (
    ExplorationPhase,
    RebusGate,
)


def _priors() -> dict[str, float]:
    return {"alpha_w": 1.0, "beta_w": 0.5, "gamma_w": 2.0}


def _accept_callback(
    received: list[dict[str, float]],
) -> Callable[[Mapping[str, float]], bool]:
    """Build a callback that records its argument and returns success."""

    def _cb(weights: Mapping[str, float]) -> bool:
        received.append(dict(weights))
        return True

    return _cb


def _activate_gate(gate: RebusGate) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """Activate the gate with finite prior weights and recording callbacks.

    Returns the two sinks (attenuated, restored) that record what
    the gate handed back to the parent system across the lifecycle.
    """
    attenuated_recorded: list[dict[str, float]] = []
    restored_recorded: list[dict[str, float]] = []
    gate.activate(
        "test-cycle-epistemic",
        _priors(),
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_accept_callback(attenuated_recorded),
        apply_restored_priors=_accept_callback(restored_recorded),
    )
    assert gate.snapshot().phase is ExplorationPhase.ATTENUATION
    assert len(attenuated_recorded) == 1, (
        "RebusGate.activate did not invoke the attenuated callback exactly once; "
        "the test fixture is stale or the gate API has drifted."
    )
    return attenuated_recorded, restored_recorded


def _force_halt(cfg: EpistemicConfig) -> EpistemicState:
    """Drive a fresh epistemic lineage to HALTED via budget exhaustion."""
    state = initial_state(cfg)
    halted = update(state, 0.0, 1000.0, config=cfg)
    assert (
        halted.is_halted
    ), f"test fixture expected forced halt; got phase={halted.phase!r} budget={halted.budget!r}."
    return halted


def _halting_config() -> EpistemicConfig:
    return EpistemicConfig(
        invariant_floor=0.2,
        initial_budget=0.05,
        initial_weight=0.6,
        temperature=1.0,
        learning_rate=0.5,
        decay_factor=0.1,
    )


# ---------------------------------------------------------------------------
# Genesis composition: halted epistemic + active gate ⟹ emergency_exit
# ---------------------------------------------------------------------------


def test_halted_state_escalates_active_gate_to_emergency_exit() -> None:
    cfg = _halting_config()
    halted = _force_halt(cfg)

    gate = RebusGate()
    _, restored_recorded = _activate_gate(gate)

    bridge = RebusBridge()
    restored = bridge.maybe_escalate(halted, gate)

    assert restored is not None, (
        "bridge.maybe_escalate returned None for a halted state on an active gate; "
        "expected emergency_exit to fire and restore prior weights."
    )
    assert restored == _priors(), (
        f"restored weights {restored!r} != priors {_priors()!r}; "
        "RebusGate.emergency_exit must round-trip the activation prior set."
    )
    assert len(restored_recorded) == 1, (
        f"apply_restored_priors invoked {len(restored_recorded)} times; "
        "emergency_exit must apply the restoration exactly once."
    )
    assert restored_recorded[0] == _priors()
    assert gate.snapshot().phase is ExplorationPhase.INACTIVE, (
        f"gate phase after escalation is {gate.snapshot().phase!r}; "
        "expected INACTIVE — emergency_exit terminates the cycle."
    )


def test_emergency_exit_audit_event_records_stressed_escalation_reason() -> None:
    cfg = _halting_config()
    halted = _force_halt(cfg)
    gate = RebusGate()
    _activate_gate(gate)

    RebusBridge().maybe_escalate(halted, gate)

    events = list(gate.audit_log())
    emergency_events = [e for e in events if e.event == "emergency_exit"]
    assert len(emergency_events) == 1, (
        f"expected exactly one emergency_exit audit event, got {len(emergency_events)}; "
        f"audit log: {[e.event for e in events]}."
    )
    reason = emergency_events[0].details.get("reason")
    assert reason == "stressed_escalation", (
        f"emergency_exit reason was {reason!r}; "
        "RebusBridge.maybe_escalate must forward via stressed_state=True, which "
        "the gate routes to reason 'stressed_escalation'. A different reason "
        "implies the bridge's external-signal contract has drifted."
    )


# ---------------------------------------------------------------------------
# Inactive-gate path: halted epistemic + inactive gate ⟹ no-op
# ---------------------------------------------------------------------------


def test_halted_state_against_inactive_gate_returns_none() -> None:
    cfg = _halting_config()
    halted = _force_halt(cfg)

    gate = RebusGate()
    assert gate.snapshot().phase is ExplorationPhase.INACTIVE
    bridge = RebusBridge()
    out = bridge.maybe_escalate(halted, gate)
    assert out is None, (
        f"bridge returned {out!r} on an inactive gate; "
        "RebusGate.apply_external_safety_signal short-circuits to None when the gate "
        "is inactive — there is no prior backup to restore."
    )
    # Gate must remain INACTIVE; no events should be appended.
    assert gate.snapshot().phase is ExplorationPhase.INACTIVE
    events = list(gate.audit_log())
    assert all(e.event != "emergency_exit" for e in events), (
        "no emergency_exit may be logged when the gate is inactive; "
        f"got events: {[e.event for e in events]}."
    )


# ---------------------------------------------------------------------------
# Active state: bridge always short-circuits regardless of gate phase
# ---------------------------------------------------------------------------


def test_active_state_against_active_gate_does_not_escalate() -> None:
    """Bridge contract: only halted states forward.

    An active state must not consume the gate's emergency_exit
    capacity even if that capacity is available — escalation is
    fail-closed routing, not opportunistic rollback.
    """
    cfg = EpistemicConfig(
        invariant_floor=0.2,
        initial_budget=100.0,
        initial_weight=0.6,
        temperature=1.0,
        learning_rate=0.5,
        decay_factor=0.1,
    )
    state = initial_state(cfg)
    advanced = update(state, 0.0, 0.0, config=cfg)
    assert not advanced.is_halted

    gate = RebusGate()
    _activate_gate(gate)

    bridge = RebusBridge()
    out = bridge.maybe_escalate(advanced, gate)
    assert out is None
    # Gate must remain in its post-activation phase, not INACTIVE.
    assert gate.snapshot().phase is ExplorationPhase.ATTENUATION


def test_active_state_against_inactive_gate_does_not_escalate() -> None:
    cfg = EpistemicConfig(
        invariant_floor=0.2,
        initial_budget=100.0,
        initial_weight=0.6,
    )
    state = initial_state(cfg)
    gate = RebusGate()
    bridge = RebusBridge()
    assert bridge.maybe_escalate(state, gate) is None
    assert gate.snapshot().phase is ExplorationPhase.INACTIVE


# ---------------------------------------------------------------------------
# Repeated escalation: a single halt-event must not double-fire
# ---------------------------------------------------------------------------


def test_repeated_escalation_after_first_returns_none() -> None:
    """After emergency_exit the gate is INACTIVE; second forward is a no-op.

    This is the post-halt sticky composition: the epistemic state
    remains halted (sticky in :func:`update`), but the gate is now
    inactive, so further escalation is correctly suppressed by the
    gate's own contract. Two protectors agreeing on the resting
    state is the desired end-of-cycle invariant.
    """
    cfg = _halting_config()
    halted = _force_halt(cfg)
    gate = RebusGate()
    _activate_gate(gate)

    bridge = RebusBridge()
    first = bridge.maybe_escalate(halted, gate)
    second = bridge.maybe_escalate(halted, gate)

    assert first is not None
    assert second is None, (
        f"second escalation on the same halted state returned {second!r}; "
        "post-emergency-exit gate must be INACTIVE and thus no-op the bridge."
    )


# ---------------------------------------------------------------------------
# Pytest collection: catch import-time regressions if the public API drifts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "EpistemicConfig",
        "EpistemicState",
        "RebusBridge",
        "initial_state",
        "update",
    ],
)
def test_public_symbol_importable(name: str) -> None:
    """If any public symbol is renamed silently this test fails fast."""
    import core.neuro.epistemic_validation as mod

    assert hasattr(mod, name), (
        f"public API drift: {name!r} no longer exported from "
        "core.neuro.epistemic_validation; integration consumers will break."
    )
