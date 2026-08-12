# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T17 — Cryptobiosis state-machine witnesses for INV-CB1 through INV-CB8.

The cryptobiosis controller is a tardigrade-inspired survival mechanism:
when combined neuromodulator distress exceeds a threshold, the system
**exits the space where the threat applies** by zeroing all position
multipliers (DORMANT). Recovery is staged, hysteretic, and abortable.

These witnesses exercise every P0 invariant of the state machine against
the production ``core.neuro.cryptobiosis.CryptobiosisController``.
"""

from __future__ import annotations

import pytest

from core.neuro.cryptobiosis import (
    CryptobiosisConfig,
    CryptobiosisController,
    CryptobiosisState,
)

# ── INV-CB1: DORMANT multiplier == 0.0 EXACTLY ──────────────────────


def test_dormant_multiplier_is_exactly_zero() -> None:
    """INV-CB1: DORMANT ⟹ multiplier == 0.0, not approximately.

    Drives the controller through ACTIVE → VITRIFYING → DORMANT and
    asserts the multiplier is bitwise 0.0. The tolerance is zero
    because this is a safety contract: any nonzero multiplier in
    DORMANT means the system is trading during a threat.
    """
    ctrl = CryptobiosisController()
    # Push into DORMANT: tick 1 = VITRIFYING, tick 2 = DORMANT
    ctrl.update(T=0.95)  # ACTIVE → VITRIFYING
    result = ctrl.update(T=0.95)  # VITRIFYING → DORMANT
    assert ctrl.state.value == CryptobiosisState.DORMANT.value, (
        f"INV-CB1 pre-check failed: state={ctrl.state}, expected DORMANT. "
        f"Observed at T=0.95, entry=0.85."
    )
    # INV-CB1: EXACTLY zero — not 1e-10, not 0.001, not float min.
    assert result["multiplier"] == 0.0, (
        f"INV-CB1 VIOLATED: DORMANT multiplier={result['multiplier']} ≠ 0.0. "
        f"Expected exactly 0.0 — system must not trade during DORMANT. "
        f"Observed at T=0.95, entry_threshold=0.85. "
        f"Physical reasoning: DORMANT = zero metabolism = zero computation."
    )
    assert ctrl.multiplier == 0.0, (
        f"INV-CB1 VIOLATED: property multiplier={ctrl.multiplier} ≠ 0.0. "
        f"Expected exactly 0.0 via property accessor. "
        f"Observed at T=0.95, state=DORMANT."
    )


# ── INV-CB2: Vitrification O(1) ─────────────────────────────────────


def test_vitrification_completes_in_one_tick() -> None:
    """INV-CB2: VITRIFYING → DORMANT in exactly 1 tick.

    Vitrification is O(1): the system spends at most 1 tick in
    VITRIFYING before landing in DORMANT. No iterative wind-down.
    """
    ctrl = CryptobiosisController()
    ctrl.update(T=0.90)
    assert (
        ctrl.state.value == CryptobiosisState.VITRIFYING.value
    ), f"INV-CB2 pre-check: expected VITRIFYING, got {ctrl.state}. Observed at T=0.90, entry=0.85."
    ctrl.update(T=0.90)
    assert ctrl.state.value == CryptobiosisState.DORMANT.value, (
        f"INV-CB2 VIOLATED: state={ctrl.state} after 2nd tick, expected DORMANT. "
        f"Expected O(1) vitrification: 1 tick VITRIFYING → DORMANT. "
        f"Observed at T=0.90, entry_threshold=0.85. "
        f"Physical reasoning: vitrification is a phase transition, not a process."
    )


# ── INV-CB3: Snapshot sufficiency ────────────────────────────────────


def test_snapshot_exists_in_dormant() -> None:
    """INV-CB3: snapshot is non-None in DORMANT state.

    The vitrification snapshot must contain the data needed for recovery.
    A None snapshot in DORMANT means the system cannot resume.
    """
    ctrl = CryptobiosisController()
    ctrl.update(T=0.90, metadata={"positions": [100, 200]})
    ctrl.update(T=0.90)  # → DORMANT
    assert ctrl.state.value == CryptobiosisState.DORMANT.value
    snap = ctrl.snapshot
    assert snap is not None, (
        "INV-CB3 VIOLATED: snapshot is None in DORMANT. "
        "Expected non-None snapshot with entry_T, timestamp, metadata. "
        "Observed at T=0.90, state=DORMANT. "
        "Physical reasoning: recovery requires a checkpoint."
    )
    assert snap.entry_T == 0.90, (
        f"INV-CB3 VIOLATED: snapshot.entry_T={snap.entry_T} ≠ 0.90. "
        f"Expected entry_T to match the T that triggered vitrification. "
        f"Observed at T=0.90. "
        f"Physical reasoning: recovery needs to know the distress at entry."
    )
    assert snap.metadata.get("positions") == [100, 200], (
        f"INV-CB3 VIOLATED: metadata={snap.metadata} lost caller data. "
        f"Expected positions=[100,200] in metadata. "
        f"Observed at T=0.90. "
        f"Physical reasoning: snapshot must capture all caller-provided state."
    )


# ── INV-CB4: Rehydration non-decreasing ─────────────────────────────


def test_rehydration_stages_non_decreasing() -> None:
    """INV-CB4: rehydration_stage(t+1) ≥ rehydration_stage(t) under safe T.

    Pushes controller through full lifecycle and records rehydration
    stages. Each tick at T < exit must advance or hold (never regress).
    """
    cfg = CryptobiosisConfig(entry_threshold=0.80, exit_threshold=0.50, n_rehydration_stages=5)
    ctrl = CryptobiosisController(cfg)
    # Enter DORMANT
    ctrl.update(T=0.90)
    ctrl.update(T=0.90)
    assert ctrl.state.value == CryptobiosisState.DORMANT.value

    # Begin rehydration
    stages: list[int] = []
    for tick in range(10):
        result = ctrl.update(T=0.30)
        if ctrl.state.value == CryptobiosisState.REHYDRATING.value:
            stages.append(result["rehydration_stage"])
        elif ctrl.state.value == CryptobiosisState.ACTIVE.value:
            break

    # INV-CB4: non-decreasing trajectory
    for i in range(1, len(stages)):
        assert stages[i] >= stages[i - 1], (
            f"INV-CB4 VIOLATED at tick={i}: stage dropped from "
            f"{stages[i - 1]} to {stages[i]}. "
            f"Expected non-decreasing rehydration stages. "
            f"Observed at T=0.30, exit=0.50, n_stages=5. "
            f"Physical reasoning: rehydration is a monotone ramp-up."
        )


# ── INV-CB6: Distress bounded ───────────────────────────────────────


def test_distress_clamped_to_unit_interval() -> None:
    """INV-CB6: T ∈ [0, 1] after any update, regardless of input.

    Feeds extreme inputs (negative, >1, huge) and asserts the internal
    distress is clamped to [0, 1] on every tick.
    """
    ctrl = CryptobiosisController()
    extreme_inputs = [-100.0, -0.5, 0.0, 0.5, 1.0, 1.5, 999.0]
    # epsilon: T is clamped by definition to [0, 1]
    for raw_T in extreme_inputs:
        ctrl.update(T=raw_T)
        assert 0.0 <= ctrl.distress <= 1.0, (
            f"INV-CB6 VIOLATED: distress={ctrl.distress} outside [0, 1] "
            f"for input T={raw_T}. "
            f"Expected clamped distress ∈ [0, 1]. "
            f"Observed at raw_T={raw_T}. "
            f"Physical reasoning: distress is a normalised signal."
        )


# ── INV-CB7: Hysteresis ─────────────────────────────────────────────


def test_hysteresis_exit_less_than_entry() -> None:
    """INV-CB7: exit_threshold < entry_threshold enforced at config time.

    Attempts to create configs with exit ≥ entry and asserts ValueError.
    """
    invalid_configs = [
        (0.80, 0.80),  # exit == entry
        (0.80, 0.90),  # exit > entry
        (0.50, 0.50),
        (1.00, 1.00),
    ]
    for entry, exit_val in invalid_configs:
        with pytest.raises(ValueError):
            CryptobiosisConfig(entry_threshold=entry, exit_threshold=exit_val)

    # Valid config must pass
    valid = CryptobiosisConfig(entry_threshold=0.85, exit_threshold=0.60)
    assert valid.exit_threshold < valid.entry_threshold, (
        f"INV-CB7 VIOLATED: exit={valid.exit_threshold} ≥ entry="
        f"{valid.entry_threshold}. "
        f"Expected strict hysteresis: exit < entry. "
        f"Observed at entry=0.85, exit=0.60. "
        f"Physical reasoning: without hysteresis the system oscillates."
    )


# ── INV-CB8: Rehydration abort ──────────────────────────────────────


def test_rehydration_aborts_on_distress_return() -> None:
    """INV-CB8: T ≥ entry during REHYDRATING → immediate DORMANT.

    Starts rehydration, then re-introduces distress above entry.
    The controller must abort rehydration and return to DORMANT
    in the same tick — no delay, no partial ramp.
    """
    ctrl = CryptobiosisController()
    # Enter DORMANT
    ctrl.update(T=0.90)
    ctrl.update(T=0.90)
    assert ctrl.state.value == CryptobiosisState.DORMANT.value

    # Start rehydration
    ctrl.update(T=0.30)
    assert ctrl.state.value == CryptobiosisState.REHYDRATING.value

    # Distress returns above entry
    result = ctrl.update(T=0.90)
    assert ctrl.state.value == CryptobiosisState.DORMANT.value, (
        f"INV-CB8 VIOLATED: state={ctrl.state} after distress return "
        f"during rehydration. "
        f"Expected immediate DORMANT on T={0.90} ≥ entry={0.85}. "
        f"Observed at T=0.90, previous state=REHYDRATING. "
        f"Physical reasoning: if threat returns during recovery, "
        f"abort immediately — do not finish ramp-up into danger."
    )
    # INV-CB1 must also hold: multiplier back to 0.0
    assert result["multiplier"] == 0.0, (
        f"INV-CB1 VIOLATED after abort: multiplier={result['multiplier']}. "
        f"Expected 0.0 in DORMANT after rehydration abort. "
        f"Observed at T=0.90. "
        f"Physical reasoning: aborted rehydration = back to zero metabolism."
    )


# ── Full lifecycle integration ───────────────────────────────────────


def test_full_lifecycle_active_dormant_rehydrate_active() -> None:
    """INV-CB1 + CB2 + CB4 + CB6: full round-trip lifecycle.

    Drives the controller through the complete state machine:
    ACTIVE → VITRIFYING → DORMANT → REHYDRATING → ACTIVE
    and asserts every invariant holds at every stage.
    """
    cfg = CryptobiosisConfig(entry_threshold=0.80, exit_threshold=0.50, n_rehydration_stages=3)
    ctrl = CryptobiosisController(cfg)

    # Phase 1: ACTIVE at low distress
    result = ctrl.update(T=0.30)
    assert ctrl.state.value == CryptobiosisState.ACTIVE.value
    assert result["multiplier"] == 1.0

    # Phase 2: enter vitrification
    result = ctrl.update(T=0.85)
    assert ctrl.state.value == CryptobiosisState.VITRIFYING.value

    # Phase 3: DORMANT
    result = ctrl.update(T=0.85)
    assert ctrl.state.value == CryptobiosisState.DORMANT.value
    assert result["multiplier"] == 0.0  # INV-CB1

    # Phase 4: start rehydration
    result = ctrl.update(T=0.30)
    assert ctrl.state.value == CryptobiosisState.REHYDRATING.value
    prev_stage = result["rehydration_stage"]

    # Phase 5: advance through rehydration stages
    for _ in range(5):
        result = ctrl.update(T=0.30)
        if ctrl.state.value == CryptobiosisState.ACTIVE.value:
            break
        assert result["rehydration_stage"] >= prev_stage  # INV-CB4
        prev_stage = result["rehydration_stage"]

    # Phase 6: back to ACTIVE
    assert ctrl.state.value == CryptobiosisState.ACTIVE.value, (
        f"Full lifecycle failed: state={ctrl.state}, expected ACTIVE. "
        f"Observed at T=0.30, n_stages=3. "
        f"Physical reasoning: 3 rehydration stages + sufficient ticks "
        f"should complete recovery."
    )
    assert ctrl.multiplier == 1.0


# ---------------------------------------------------------------------------
# TEETH — measured gap: mutation_probe --only-logic left :220 GtE->Lt alive in
# _advance_rehydration. Under that mutant rehydration completes on the FIRST advance
# instead of after n_rehydration_stages, i.e. the staged ramp collapses and the system
# resumes full metabolism immediately after a threat. Nothing asserted the stage count.
# ---------------------------------------------------------------------------
def test_rehydration_takes_exactly_the_configured_number_of_stages() -> None:
    """INV-CB4: the ramp is STAGED — ACTIVE is reached only after n stages, not before."""
    cfg = CryptobiosisConfig(n_rehydration_stages=4)
    ctrl = CryptobiosisController(config=cfg)
    ctrl.update(T=0.95)  # ACTIVE → VITRIFYING
    ctrl.update(T=0.95)  # VITRIFYING → DORMANT
    assert ctrl.state.value == CryptobiosisState.DORMANT.value

    ctrl.update(T=0.10)  # DORMANT → REHYDRATING (threat cleared)
    assert ctrl.state.value == CryptobiosisState.REHYDRATING.value, (
        "a cleared threat must enter the staged ramp, not jump straight to ACTIVE"
    )
    # Every advance before the last must still be REHYDRATING.
    for stage in range(cfg.n_rehydration_stages - 1):
        ctrl.update(T=0.10)
        assert ctrl.state.value == CryptobiosisState.REHYDRATING.value, (
            f"ramp collapsed at stage {stage + 1}/{cfg.n_rehydration_stages}: "
            f"state={ctrl.state}. The staged ramp must not complete early."
        )
    ctrl.update(T=0.10)  # final stage completes the ramp
    assert ctrl.state.value == CryptobiosisState.ACTIVE.value, (
        f"ramp did not complete after {cfg.n_rehydration_stages} stages: state={ctrl.state}"
    )
