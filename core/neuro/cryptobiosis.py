# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cryptobiosis — phase-transition survival for the neuromodulation stack.

Biological basis:
    Tardigrades survive lethal conditions (vacuum, radiation, desiccation)
    not by resisting them but by **exiting the space** where the threat
    applies: vitrifying into a tun state where metabolism drops to zero.
    Recovery is staged: rehydration is cautious, multi-phase, and
    abortable if the threat returns.

GeoSync analogue:
    When combined neuromodulator distress T exceeds the entry threshold,
    the system vitrifies: all position multipliers drop to **exactly 0.0**
    (not 0.01, not "close to zero" — zero). No computation on a
    discharged gradient. On recovery, rehydration proceeds through staged
    ramp-up with hysteresis to prevent oscillation at the threshold
    boundary.

State machine::

    ACTIVE ─── T ≥ entry ───▶ VITRIFYING ── O(1) ──▶ DORMANT
      ▲                                                  │
      │                                          T < exit │
      │                                                  ▼
      └──────── ramp complete ◀── REHYDRATING ◀──────────┘
                                    │
                                    │ T ≥ entry
                                    ▼
                                  DORMANT (abort)

Invariants (see INVARIANTS.yaml INV-CB1..CB8):
    CB1: DORMANT ⟹ multiplier == 0.0 EXACTLY
    CB2: Vitrification is O(1) — no iterative wind-down
    CB3: Snapshot sufficient for recovery
    CB4: Rehydration stages non-decreasing
    CB5: Entry threshold > every individual module threshold
    CB6: T ∈ [0, 1]
    CB7: exit < entry (hysteresis)
    CB8: T ≥ entry during rehydration → DORMANT
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from geosync.core.compat import default_clock


class CryptobiosisState(Enum):
    """Phase of the cryptobiosis lifecycle."""

    ACTIVE = "ACTIVE"
    VITRIFYING = "VITRIFYING"
    DORMANT = "DORMANT"
    REHYDRATING = "REHYDRATING"


@dataclass(frozen=True, slots=True)
class CryptobiosisSnapshot:
    """Minimal state sufficient for recovery (INV-CB3).

    Captures everything the system needs to resume from DORMANT:
    the distress score at entry, the timestamp, and any metadata the
    caller wants to persist (e.g. last known positions, risk state).
    """

    entry_T: float
    entry_timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CryptobiosisConfig:
    """Tunable parameters for the cryptobiosis state machine.

    entry_threshold must be strictly greater than exit_threshold
    (INV-CB7: hysteresis).
    """

    entry_threshold: float = 0.85
    exit_threshold: float = 0.60
    n_rehydration_stages: int = 4

    def __post_init__(self) -> None:
        if not (0.0 < self.exit_threshold < self.entry_threshold <= 1.0):
            raise ValueError(
                f"Must have 0 < exit ({self.exit_threshold}) "
                f"< entry ({self.entry_threshold}) ≤ 1. "
                f"INV-CB7: hysteresis requires exit < entry."
            )
        if self.n_rehydration_stages < 1:
            raise ValueError("n_rehydration_stages must be ≥ 1")


class CryptobiosisController:
    """Phase-transition survival controller.

    Usage::

        ctrl = CryptobiosisController()
        T = compute_distress(bus.snapshot())  # ∈ [0, 1]
        result = ctrl.update(T)
        position_multiplier = result["multiplier"]
        # Apply: effective_size = raw_size * position_multiplier
    """

    def __init__(self, config: CryptobiosisConfig | None = None) -> None:
        self._cfg = config or CryptobiosisConfig()
        self._state = CryptobiosisState.ACTIVE
        self._rehydration_stage: int = 0
        self._snapshot: CryptobiosisSnapshot | None = None
        self._last_T: float = 0.0

    # ── Properties ───────────────────────────────────────────────────

    @property
    def state(self) -> CryptobiosisState:
        return self._state

    @property
    def multiplier(self) -> float:
        """Current position multiplier.

        INV-CB1: DORMANT ⟹ exactly 0.0.
        INV-CB4: REHYDRATING ⟹ staged ramp in (0, 1).
        ACTIVE / VITRIFYING ⟹ 1.0.
        """
        if self._state == CryptobiosisState.DORMANT:
            return 0.0  # INV-CB1: EXACTLY zero, not approximately
        if self._state == CryptobiosisState.REHYDRATING:
            # INV-CB4: staged non-decreasing ramp
            n = self._cfg.n_rehydration_stages
            return float(self._rehydration_stage) / float(n)
        return 1.0

    @property
    def snapshot(self) -> CryptobiosisSnapshot | None:
        """The snapshot taken at vitrification, or None if ACTIVE."""
        return self._snapshot

    @property
    def distress(self) -> float:
        """Last observed distress T."""
        return self._last_T

    # ── Core transition logic ────────────────────────────────────────

    def update(
        self,
        T: float,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Advance the state machine by one tick.

        Parameters
        ----------
        T : float
            Combined neuromodulator distress score ∈ [0, 1] (INV-CB6).
        metadata : dict, optional
            Extra state to include in the vitrification snapshot.

        Returns
        -------
        dict
            state, multiplier, rehydration_stage, distress, snapshot.
        """
        # INV-CB6: T ∈ [0, 1]
        T = max(0.0, min(1.0, float(T)))  # INV-CB6: distress score clamped to [0, 1]
        self._last_T = T

        if self._state == CryptobiosisState.ACTIVE:
            if T >= self._cfg.entry_threshold:
                self._enter_vitrification(T, metadata or {})
        elif self._state == CryptobiosisState.VITRIFYING:
            # INV-CB2: O(1) transition — vitrification completes in ONE tick
            self._state = CryptobiosisState.DORMANT
        elif self._state == CryptobiosisState.DORMANT:
            if T < self._cfg.exit_threshold:
                self._begin_rehydration()
        elif self._state == CryptobiosisState.REHYDRATING:
            # INV-CB8: if distress returns above entry during rehydration → abort
            if T >= self._cfg.entry_threshold:
                self._state = CryptobiosisState.DORMANT
                self._rehydration_stage = 0
            else:
                self._advance_rehydration()

        return {
            "state": self._state.value,
            "multiplier": self.multiplier,
            "rehydration_stage": self._rehydration_stage,
            "distress": T,
            "snapshot": asdict(self._snapshot) if self._snapshot else None,
        }

    # ── Internal transitions ─────────────────────────────────────────

    def _enter_vitrification(self, T: float, metadata: dict[str, Any]) -> None:
        """ACTIVE → VITRIFYING. Capture snapshot (INV-CB3)."""
        self._state = CryptobiosisState.VITRIFYING
        self._snapshot = CryptobiosisSnapshot(
            entry_T=T,
            entry_timestamp=default_clock().epoch_ns() / 1_000_000_000,
            metadata=dict(metadata),
        )
        self._rehydration_stage = 0

    def _begin_rehydration(self) -> None:
        """DORMANT → REHYDRATING at stage 0."""
        self._state = CryptobiosisState.REHYDRATING
        self._rehydration_stage = 0

    def _advance_rehydration(self) -> None:
        """Advance rehydration by one stage. Complete → ACTIVE."""
        self._rehydration_stage += 1
        if self._rehydration_stage >= self._cfg.n_rehydration_stages:
            self._state = CryptobiosisState.ACTIVE
            self._rehydration_stage = 0
            self._snapshot = None

    # ── Reset ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Force-reset to ACTIVE. For testing / emergency override only."""
        self._state = CryptobiosisState.ACTIVE
        self._rehydration_stage = 0
        self._snapshot = None
        self._last_T = 0.0
