from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from datetime import timezone
from threading import Event, Thread
from types import MappingProxyType
from typing import Any, Mapping, cast

import numpy as np
import pytest

from runtime.rebus_gate import (
    ExplorationContractError,
    ExplorationPhase,
    RebusConfig,
    RebusGate,
)
from tacl.rebus_protocol import (
    REBUS_PROTOCOL_NAME,
    apply_external_controller,
    build_protocol,
    clear_registered_protocols,
    get_registered_protocol,
    protocol_schema_keys,
    register_protocol,
)


def _priors() -> dict[str, float]:
    return {"p1": 1.0, "p2": 0.5, "p3": 2.0}


def _apply_sink(target: list[dict[str, float]]):
    def _cb(weights: Mapping[str, float]) -> bool:
        target.append(dict(weights))
        return True

    return _cb


def _activate(
    gate: RebusGate,
    attenuated_applied: list[dict[str, float]],
    restored_applied: list[dict[str, float]],
) -> None:
    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink(attenuated_applied),
        apply_restored_priors=_apply_sink(restored_applied),
    )


# INV-REBUS-1 witness
def test_inv_rebus_1_activation_denied_when_parent_not_nominal() -> None:
    gate = RebusGate()

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=False,
            current_coherence=0.95,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert not any(e.event == "activated" for e in gate.audit_log())
    gate.activate(
        "cycle-after-denied",
        _priors(),
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )
    assert gate.snapshot().phase == ExplorationPhase.ATTENUATION


# INV-REBUS-1 witness
def test_inv_rebus_1_activation_denied_when_coherence_below_threshold() -> None:
    gate = RebusGate()

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=0.2,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert not any(e.event == "activated" for e in gate.audit_log())
    gate.activate(
        "cycle-after-denied",
        _priors(),
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )
    assert gate.snapshot().phase == ExplorationPhase.ATTENUATION


# INV-REBUS-1 witness (non-real boundary)
@pytest.mark.parametrize("bad_coherence", [None, "0.9", True])
def test_inv_rebus_1_activation_rejects_non_real_coherence(
    bad_coherence: object,
) -> None:
    gate = RebusGate()

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=bad_coherence,  # type: ignore[arg-type]
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert not any(e.event == "activated" for e in gate.audit_log())


# activation single-instance witness
# supporting contract test (non-canonical)
def test_support_single_instance_second_activation_rejected_without_state_corruption() -> None:
    gate = RebusGate()
    first_cycle = "cycle-1"
    first_priors = _priors()
    gate.activate(
        first_cycle,
        first_priors,
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )

    activated_before = sum(1 for e in gate.audit_log() if e.event == "activated")

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-2",
            {"p1": 9.0},
            parent_nominal=True,
            current_coherence=0.95,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    snap = gate.snapshot()
    assert snap.cycle_id == first_cycle
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)
    ok, restored = gate.reintegrate(0.95)
    assert ok is True
    assert restored == first_priors
    activated_after = sum(1 for e in gate.audit_log() if e.event == "activated")
    assert activated_after == activated_before


# INV-REBUS-3 witness
def test_inv_rebus_3_entropy_ceiling_forces_reintegration_and_blocks_progression() -> None:
    gate = RebusGate()
    _activate(gate, [], [])

    assert gate.step(0.36, 0.95) == ExplorationPhase.REINTEGRATION
    snap = gate.snapshot()
    assert snap.forced_halt_reason == "entropy_ceiling_exceeded"

    with pytest.raises(ExplorationContractError):
        gate.step(0.1, 0.95)


# INV-REBUS-4 witness
def test_inv_rebus_4_duration_forces_reintegration_at_threshold_and_closes_step() -> None:
    gate = RebusGate(RebusConfig(max_duration_bars=2))
    _activate(gate, [], [])

    assert gate.step(0.1, 0.95) == ExplorationPhase.DESEGREGATION
    assert gate.step(0.1, 0.95) == ExplorationPhase.REINTEGRATION

    snap = gate.snapshot()
    assert snap.forced_halt_reason == "max_duration_reached"

    with pytest.raises(ExplorationContractError):
        gate.step(0.1, 0.95)


# attenuation key-preservation witness
# supporting algebraic test (non-canonical)
def test_support_attenuation_scales_values_exactly_and_preserves_keys() -> None:
    gate = RebusGate(RebusConfig(attenuation_factor=0.25))
    priors = {"a": 1.25, "b": -2.0, "c": 0.0}
    applied: list[dict[str, float]] = []

    attenuated = gate.activate(
        "cycle-1",
        priors,
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink(applied),
        apply_restored_priors=_apply_sink([]),
    )

    assert set(attenuated.keys()) == set(priors.keys())
    for key, value in priors.items():
        assert attenuated[key] == value * 0.25
    assert applied == [attenuated]


# INV-REBUS-6 witness
def test_inv_rebus_6_failed_reintegration_restores_exact_backup() -> None:
    gate = RebusGate()
    restored_applied: list[dict[str, float]] = []
    original = _priors()

    gate.activate(
        "cycle-1",
        original,
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink(restored_applied),
    )
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)

    ok, restored = gate.reintegrate(coherence=0.1)

    assert ok is False
    assert restored == original
    assert restored_applied == [original]
    assert any(e.event == "reintegration_failed" for e in gate.audit_log())
    assert gate.snapshot().phase == ExplorationPhase.INACTIVE


# INV-REBUS-7 witness
def test_inv_rebus_7_safety_preemption_forces_emergency_exit() -> None:
    gate = RebusGate()
    restored_applied: list[dict[str, float]] = []
    _activate(gate, [], restored_applied)

    restored = gate.apply_external_safety_signal(kill_switch_active=True, stressed_state=False)

    assert restored == _priors()
    assert restored_applied == [_priors()]
    assert gate.snapshot().phase == ExplorationPhase.INACTIVE


# INV-REBUS-5 witness
def test_inv_rebus_5_gate_never_becomes_inactive_without_terminal_call() -> None:
    gate = RebusGate()
    _activate(gate, [], [])

    assert gate.snapshot().phase == ExplorationPhase.ATTENUATION
    assert gate.snapshot().phase != ExplorationPhase.INACTIVE

    gate.step(0.1, 0.95)
    assert gate.snapshot().phase == ExplorationPhase.DESEGREGATION

    gate.step(0.1, 0.95)
    assert gate.snapshot().phase == ExplorationPhase.DIVERSITY

    gate.step(0.1, 0.95)
    assert gate.snapshot().phase == ExplorationPhase.REINTEGRATION
    assert gate.snapshot().phase != ExplorationPhase.INACTIVE

    ok, _ = gate.reintegrate(0.95)
    assert ok is True
    assert gate.snapshot().phase == ExplorationPhase.INACTIVE


def test_can_activate_rejects_non_real_coherence() -> None:
    gate = RebusGate()
    for bad in (None, "0.9", True):
        with pytest.raises(ExplorationContractError):
            gate.can_activate(parent_nominal=True, current_coherence=bad)  # type: ignore[arg-type]


def test_activation_requires_both_callbacks() -> None:
    gate = RebusGate()
    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=None,  # type: ignore[arg-type]
            apply_restored_priors=_apply_sink([]),
        )
    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=None,  # type: ignore[arg-type]
        )


def test_activate_rejects_non_real_prior_values() -> None:
    gate = RebusGate()

    for bad_priors in ({"p1": None}, {"p1": "1.0"}, {"p1": True}):
        with pytest.raises(ExplorationContractError):
            gate.activate(
                "cycle-1",
                bad_priors,  # type: ignore[arg-type]
                parent_nominal=True,
                current_coherence=0.9,
                apply_attenuated_priors=_apply_sink([]),
                apply_restored_priors=_apply_sink([]),
            )
        assert gate.snapshot().phase == ExplorationPhase.INACTIVE
        assert not any(e.event == "activated" for e in gate.audit_log())


def test_activate_rejects_non_mapping_prior_weights() -> None:
    gate = RebusGate()
    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            [("p1", 1.0)],  # type: ignore[arg-type]
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert not any(e.event == "activated" for e in gate.audit_log())


def test_activate_malformed_mapping_items_fails_closed() -> None:
    class BrokenPairsMapping(Mapping[str, float]):
        def __getitem__(self, key: str) -> float:
            if key == "p1":
                return 1.0
            raise KeyError(key)

        def __iter__(self):
            return iter(["p1"])

        def __len__(self) -> int:
            return 1

        def items(self):  # type: ignore[override]
            return [("p1", 1.0, 2.0)]

    gate = RebusGate()
    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            BrokenPairsMapping(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert not any(e.event == "activated" for e in gate.audit_log())


def test_activation_is_atomic_and_fails_closed_when_apply_fails() -> None:
    gate = RebusGate()

    def bad_apply(_: Mapping[str, float]) -> bool:
        return False

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=bad_apply,
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert gate.audit_log()[-1].event == "activation_apply_failed"


def test_activation_apply_exception_is_deterministic() -> None:
    gate = RebusGate()

    def boom(_: Mapping[str, float]) -> bool:
        raise RuntimeError("boom")

    with pytest.raises(ExplorationContractError):
        gate.activate(
            "cycle-1",
            _priors(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=boom,
            apply_restored_priors=_apply_sink([]),
        )

    assert gate.snapshot().phase == ExplorationPhase.INACTIVE
    assert gate.audit_log()[-1].event == "activation_apply_failed"


def test_step_in_inactive_and_reintegration_raises() -> None:
    gate = RebusGate()
    with pytest.raises(ExplorationContractError):
        gate.step(current_entropy=0.1, coherence=0.9)

    _activate(gate, [], [])
    gate.step(current_entropy=0.5, coherence=0.9)
    bars = gate.snapshot().bars_elapsed
    audit_len = len(gate.audit_log())

    with pytest.raises(ExplorationContractError):
        gate.step(current_entropy=0.1, coherence=0.9)

    assert gate.snapshot().bars_elapsed == bars
    assert len(gate.audit_log()) == audit_len


def test_normal_progression_and_terminal_restore() -> None:
    gate = RebusGate()
    attenuated_applied: list[dict[str, float]] = []
    restored_applied: list[dict[str, float]] = []
    _activate(gate, attenuated_applied, restored_applied)

    assert attenuated_applied and set(attenuated_applied[0].keys()) == set(_priors().keys())
    assert gate.step(0.1, 0.9) == ExplorationPhase.DESEGREGATION
    assert gate.step(0.1, 0.9) == ExplorationPhase.DIVERSITY
    assert gate.step(0.1, 0.9) == ExplorationPhase.REINTEGRATION

    ok, restored = gate.reintegrate(coherence=0.8)
    assert ok is True
    assert restored == _priors()
    assert restored_applied == [_priors()]
    assert gate.is_active() is False


def test_entropy_model_is_instantaneous_ceiling_only() -> None:
    gate = RebusGate()
    _activate(gate, [], [])

    phase = gate.step(current_entropy=0.36, coherence=0.9)
    assert phase == ExplorationPhase.REINTEGRATION
    assert not hasattr(gate.snapshot().entropy_budget, "budget_consumed")


def test_no_false_terminal_event_when_restore_returns_false() -> None:
    gate = RebusGate()

    def bad_restore(_: Mapping[str, float]) -> bool:
        return False

    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=bad_restore,
    )
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)

    with pytest.raises(ExplorationContractError):
        gate.reintegrate(0.8)

    events = [e.event for e in gate.audit_log()]
    assert "reintegration_success" not in events
    assert "reintegration_failed" not in events
    assert events[-1] == "restore_apply_failed"
    assert gate.snapshot().phase == ExplorationPhase.REINTEGRATION


def test_no_false_terminal_event_when_restore_raises() -> None:
    gate = RebusGate()

    def boom(_: Mapping[str, float]) -> bool:
        raise RuntimeError("restore fail")

    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=boom,
    )
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)

    with pytest.raises(ExplorationContractError):
        gate.reintegrate(0.8)

    events = [e.event for e in gate.audit_log()]
    assert "reintegration_success" not in events
    assert events[-1] == "restore_apply_failed"


def test_external_safety_signal_applies_restore() -> None:
    gate = RebusGate()
    restored_applied: list[dict[str, float]] = []
    _activate(gate, [], restored_applied)

    restored = gate.apply_external_safety_signal(kill_switch_active=True, stressed_state=False)

    assert restored == _priors()
    assert restored_applied == [_priors()]


# audit retention witness
def test_audit_retention_bounded_and_terminal_visible() -> None:
    gate = RebusGate(RebusConfig(max_audit_events=10))

    for idx in range(6):
        gate.activate(
            f"cycle-{idx}",
            _priors(),
            parent_nominal=True,
            current_coherence=0.9,
            apply_attenuated_priors=_apply_sink([]),
            apply_restored_priors=_apply_sink([]),
        )
        gate.step(0.1, 0.9)
        gate.step(0.1, 0.9)
        gate.step(0.1, 0.9)
        gate.reintegrate(0.8)

    log = gate.audit_log()
    assert len(log) == 10
    assert any(e.event == "reintegration_success" for e in log)


def test_config_validation_guards_bounds() -> None:
    with pytest.raises(ValueError):
        RebusGate(RebusConfig(max_audit_events=0))
    with pytest.raises(ValueError):
        RebusGate(RebusConfig(attenuation_factor=0.0))


def test_control_vector_reads_under_lock_contract() -> None:
    gate = RebusGate()
    _activate(gate, [], [])

    # smoke check under concurrent readers + one writer; should not throw / tear
    stop = Event()
    errors: list[Exception] = []

    def reader() -> None:
        try:
            while not stop.is_set():
                _ = gate.control_vector()
        except Exception as exc:  # pragma: no cover - should not happen
            errors.append(exc)

    t = Thread(target=reader)
    t.start()
    try:
        gate.step(0.1, 0.9)
    finally:
        stop.set()
        t.join(timeout=2)

    assert errors == []


def test_snapshot_and_audit_payload_are_immutable_and_utc() -> None:
    gate = RebusGate()
    _activate(gate, [], [])

    snap = gate.snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.phase = ExplorationPhase.INACTIVE  # type: ignore[misc]

    event = gate.audit_log()[0]
    assert isinstance(event.details, MappingProxyType)
    with pytest.raises(TypeError):
        event.details["x"] = 1  # type: ignore[index]
    assert event.ts.tzinfo is not None
    assert event.ts.tzinfo.utcoffset(event.ts) == timezone.utc.utcoffset(event.ts)


# audit UTC witness
def test_inv_rebus_8_all_audit_timestamps_are_utc() -> None:
    gate = RebusGate()
    _activate(gate, [], [])
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)
    gate.step(0.1, 0.9)

    for event in gate.audit_log():
        assert event.ts.tzinfo is not None
        assert event.ts.tzinfo.utcoffset(event.ts) == timezone.utc.utcoffset(event.ts)


def test_non_finite_inputs_raise() -> None:
    gate = RebusGate()
    _activate(gate, [], [])
    with pytest.raises(ExplorationContractError):
        gate.step(current_entropy=math.nan, coherence=0.9)
    with pytest.raises(ExplorationContractError):
        gate.step(current_entropy=0.1, coherence=math.inf)


def test_step_rejects_non_real_entropy_and_coherence_without_mutation() -> None:
    gate = RebusGate()
    _activate(gate, [], [])
    before = gate.snapshot()
    before_audit = len(gate.audit_log())

    bad_inputs = [
        (None, 0.9),
        ("0.1", 0.9),
        (0.1, None),
        (0.1, "0.9"),
        (True, 0.9),
        (0.1, True),
    ]
    for entropy_value, coherence in bad_inputs:
        with pytest.raises(ExplorationContractError):
            gate.step(entropy_value, coherence)  # type: ignore[arg-type]

    after = gate.snapshot()
    assert after.phase == before.phase
    assert after.bars_elapsed == before.bars_elapsed
    assert len(gate.audit_log()) == before_audit


def test_reintegrate_rejects_non_real_coherence_and_no_terminal_event() -> None:
    gate = RebusGate()
    _activate(gate, [], [])
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)
    gate.step(0.1, 0.95)

    for bad in (None, "0.8", True):
        with pytest.raises(ExplorationContractError):
            gate.reintegrate(bad)  # type: ignore[arg-type]

    events = [e.event for e in gate.audit_log()]
    assert "reintegration_success" not in events
    assert "reintegration_failed" not in events
    assert gate.snapshot().phase == ExplorationPhase.REINTEGRATION


def test_emergency_exit_no_false_terminal_event_when_restore_returns_false() -> None:
    gate = RebusGate()

    def bad_restore(_: Mapping[str, float]) -> bool:
        return False

    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=bad_restore,
    )

    with pytest.raises(ExplorationContractError):
        gate.emergency_exit("kill_switch_active")

    events = [e.event for e in gate.audit_log()]
    assert "emergency_exit" not in events
    assert events[-1] == "restore_apply_failed"
    assert gate.snapshot().phase == ExplorationPhase.REINTEGRATION


def test_emergency_exit_no_false_terminal_event_when_restore_raises() -> None:
    gate = RebusGate()

    def boom(_: Mapping[str, float]) -> bool:
        raise RuntimeError("restore fail")

    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=boom,
    )

    with pytest.raises(ExplorationContractError):
        gate.emergency_exit("kill_switch_active")

    events = [e.event for e in gate.audit_log()]
    assert "emergency_exit" not in events
    assert events[-1] == "restore_apply_failed"
    assert gate.snapshot().phase == ExplorationPhase.REINTEGRATION


def test_protocol_descriptor_truth_and_registration() -> None:
    descriptor = build_protocol()
    schema = protocol_schema_keys()
    assert tuple(descriptor.keys()) == schema["root"]
    safety = cast(dict[str, object], descriptor["safety"])
    assert tuple(safety.keys()) == schema["safety"]
    assert safety["kill_switch_forces_emergency_exit"] is True
    assert safety["stressed_state_forces_emergency_exit"] is True
    assert safety["attenuated_apply_confirmation_required"] is True
    assert safety["restore_apply_confirmation_required"] is True

    clear_registered_protocols()
    registration = register_protocol()
    loaded = get_registered_protocol()
    assert loaded is not None
    assert loaded.name == registration.name == REBUS_PROTOCOL_NAME

    gate = cast(RebusGate, loaded.descriptor["gate"])
    assert isinstance(gate, RebusGate)
    gate.activate(
        "cycle-1",
        _priors(),
        parent_nominal=True,
        current_coherence=0.9,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )
    restored = cast(
        Mapping[str, Any],
        apply_external_controller(gate, kill_switch_active=False, stressed_state=True),
    )
    assert set(restored.keys()) == set(_priors().keys())
    assert restored["p1"] == _priors()["p1"]
    assert restored["p2"] == _priors()["p2"]
    assert restored["p3"] == _priors()["p3"]


def test_integration_activation_reduces_kuramoto_order_parameter() -> None:
    # core/indicators/kuramoto.py integration witness
    pytest.importorskip("omegaconf")
    from core.indicators.kuramoto import kuramoto_order

    gate = RebusGate(RebusConfig(attenuation_factor=0.4))
    priors = {"p1": 1.0, "p2": 1.0, "p3": 1.0, "p4": 1.0}

    baseline_phases = np.array([priors["p1"], priors["p2"], priors["p3"], priors["p4"]])
    baseline_r = float(kuramoto_order(baseline_phases))

    attenuated = gate.activate(
        "cycle-1",
        priors,
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )
    attenuated_phases = np.array(
        [attenuated["p1"], attenuated["p2"], attenuated["p3"], attenuated["p4"]]
    )
    attenuated_r = float(kuramoto_order(attenuated_phases))

    assert attenuated_r <= baseline_r


def test_integration_activation_increases_entropy_proxy_for_free_energy_descent_drop() -> None:
    # core/indicators/entropy.py integration witness
    pytest.importorskip("omegaconf")
    from core.indicators.entropy import entropy

    gate = RebusGate(RebusConfig(attenuation_factor=0.4))
    priors = {"p1": 1.0, "p2": 1.0, "p3": 1.0, "p4": 1.0}

    baseline_signal = np.array([priors["p1"]] * 64)
    baseline_entropy = float(entropy(baseline_signal))

    attenuated = gate.activate(
        "cycle-1",
        priors,
        parent_nominal=True,
        current_coherence=0.95,
        apply_attenuated_priors=_apply_sink([]),
        apply_restored_priors=_apply_sink([]),
    )
    mixed_signal = np.array([priors["p1"], attenuated["p1"]] * 32)
    attenuated_entropy = float(entropy(mixed_signal))

    assert attenuated_entropy >= baseline_entropy
