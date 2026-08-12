# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Budget-bounded epistemic evidence accumulator with fail-closed semantics.

This module provides a Layer 2 *sustainer* (per CLAUDE.md, Section 0:
"Ontology of Gradient") — a pure-functional, deterministic gate that
maintains an information-cost budget while accumulating windowed
evidence about the agreement between an observation stream
(``signal``) and a reference stream (``fact``). When the budget
is exhausted or the accumulated weight collapses below the configured
floor, the state transitions to a sticky ``HALTED`` phase. Recovery is
not possible without an external reset — by construction this composes
with :class:`runtime.rebus_gate.RebusGate` via the supplied
:class:`RebusBridge`, which translates a halted state into the
``stressed_state`` signal accepted by
``RebusGate.apply_external_safety_signal``.

Honest framing — what this module is and is not
-----------------------------------------------

* The cost function ``c(Δ) = T · log1p(|fact − signal|)`` is an
  information-theoretic surprise term measured in nats. It is **not**
  the Landauer cost (``k_B · T · ln 2`` per bit erased), and the
  multiplier ``T`` is dimensionless — calling it ``kT`` would be a
  category error against the system's INV-FE2 contract (Helmholtz
  components must be non-negative, but ``F = U − T·S`` itself can be
  negative; we deliberately use a separate, non-negative budget
  register here so the contract is not abused).
* The evidence weight is a *windowed exponential moving average*, not a
  Bayesian posterior. The variable name reflects the semantics.
* The module composes with — but does not implement — the
  Friston-style active inference loop in
  :mod:`geosync_hpc.hpc_active_inference_v4`. The relationship is that
  an exhausted budget on this gate signals that the active inference
  layer's variational free energy has accumulated more surprise than
  the configured tolerance admits.

Invariants enforced (referenced from CLAUDE.md ▸ INVARIANT REGISTRY)
-------------------------------------------------------------------

* **INV-FE2** (universal, P0): budget ≥ 0, weight ∈ [0, 1], and the
  surprise cost ``c(Δ) ≥ 0`` for every admissible Δ ≥ 0. Components
  are non-negative; the composite scoreboard ``(weight, budget)`` is
  not aggregated into a quantity that pretends to be Helmholtz F.
* **INV-HPC1** (universal, P0): seeded reproducibility — every public
  function is pure, takes no implicit state, and produces bit-identical
  output for identical input.
* **INV-HPC2** (universal, P0): finite-input ⟹ finite-output. NaN and
  ±Inf are rejected at every public entry point.

Chronology discipline (per ``feedback_chronology_discipline``)
--------------------------------------------------------------

* ``EpistemicState.seq`` is a monotonically increasing 64-bit counter.
* ``EpistemicState.state_hash`` is a SHA-256 chain over the prior hash
  and a deterministic packing of the new state. There are no
  "trust-me" booleans: ``halted`` is *derived* from ``budget`` and
  ``weight`` versus the configured floor, then frozen into the state
  for downstream comparators.
* The transition is one-way: ``ACTIVE → HALTED``. There is no
  ``REENTRY`` path inside this module.

Hashing format
--------------

The chain hash is computed over the concatenation of the prior hash
(32 raw bytes) and a packed payload. The packed payload is the
big-endian 64-bit ``seq``, followed by the IEEE-754 little-endian
double-precision encodings of ``weight``, ``budget``, and
``invariant_floor``, followed by a single byte (``\\x01`` if halted,
``\\x00`` otherwise). The format is documented inline in
:func:`_chain_state` and pinned by a regression test.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Final

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from runtime.rebus_gate import RebusGate

__all__ = [
    "EpistemicConfig",
    "EpistemicError",
    "EpistemicPhase",
    "EpistemicState",
    "HaltMargin",
    "RebusBridge",
    "halt_margin",
    "initial_state",
    "reset_with_external_proof",
    "update",
    "verify_stream",
]


class EpistemicPhase(str, Enum):
    """Two-state machine: pre-halt or sticky halt.

    The transition ``ACTIVE → HALTED`` is one-way inside this module.
    Recovery requires an external reset (typically by allocating a
    fresh state via :func:`initial_state`, often after
    :meth:`runtime.rebus_gate.RebusGate.emergency_exit` has restored
    the parent system to a safe weight set).
    """

    ACTIVE = "active"
    HALTED = "halted"


class EpistemicError(ValueError):
    """Raised on contract violations at module entry points.

    Re-uses :class:`ValueError` semantics (matching the pattern used by
    :class:`geosync_hpc.validation.ValidationService`) so existing
    fail-closed pathways catch it without a special-case ``except``.
    """


_GENESIS_HASH: Final[bytes] = b"\x00" * 32
_HEX_LEN: Final[int] = 64


@dataclass(frozen=True, slots=True)
class EpistemicConfig:
    """Static configuration; unchanged for the lifetime of a state lineage.

    Attributes
    ----------
    invariant_floor:
        Minimum admissible accumulated weight. Once
        ``state.weight < invariant_floor``, the state halts. Must lie
        in ``(0, 1)`` — a floor of 0 would never trigger a
        weight-based halt; a floor of 1 would halt on the first
        non-perfect observation. Tuning is the integrator's
        responsibility; this module enforces only the open-interval
        constraint.
    initial_budget:
        Strictly positive starting information budget, in nats. Each
        update spends ``T · log1p(|Δ|)`` from this register.
    initial_weight:
        Starting weight in the half-open interval ``[invariant_floor,
        1]``. Defaults to 0.5 if the floor admits it; otherwise
        ``invariant_floor``.
    temperature:
        Strictly positive multiplier on the surprise cost. Higher
        ``T`` ⟹ a given residual depletes the budget faster. Named
        ``temperature`` rather than ``kT`` to mark that it is
        dimensionless — see module docstring.
    learning_rate:
        EMA rate ``α ∈ (0, 1)`` for the evidence accumulator. The
        update is ``w' = (1 − α)·w + α·ℓ`` on a valid step, where
        ``ℓ = 1 / (1 + |Δ|)``. On an invalid step, weight decays as
        ``w' = (1 − α·decay_factor)·w``.
    decay_factor:
        Multiplier on ``α`` applied during the decay branch. In
        ``(0, 1)``; defaults to 0.1 — one-tenth of the active rate, so
        decay is slower than reinforcement.
    """

    invariant_floor: float
    initial_budget: float
    initial_weight: float = 0.5
    temperature: float = 1.0
    learning_rate: float = 0.5
    decay_factor: float = 0.1

    def __post_init__(self) -> None:
        if not (0.0 < self.invariant_floor < 1.0):
            raise EpistemicError(
                "INV-FE2: invariant_floor must lie in (0, 1); "
                f"got {self.invariant_floor!r}. "
                "Required so the weight-collapse halt is reachable but not vacuous."
            )
        if not math.isfinite(self.initial_budget) or self.initial_budget <= 0.0:
            raise EpistemicError(
                "INV-FE2: initial_budget must be a finite positive number; "
                f"got {self.initial_budget!r}."
            )
        if not math.isfinite(self.initial_weight) or not (
            self.invariant_floor <= self.initial_weight <= 1.0
        ):
            raise EpistemicError(
                "INV-FE2: initial_weight must lie in [invariant_floor, 1]; "
                f"got initial_weight={self.initial_weight!r}, "
                f"invariant_floor={self.invariant_floor!r}."
            )
        if not math.isfinite(self.temperature) or self.temperature <= 0.0:
            raise EpistemicError(
                f"INV-FE2: temperature must be a finite positive number; got {self.temperature!r}."
            )
        if not (0.0 < self.learning_rate < 1.0):
            raise EpistemicError(
                f"Configuration: learning_rate must lie in (0, 1); got {self.learning_rate!r}."
            )
        if not (0.0 < self.decay_factor < 1.0):
            raise EpistemicError(
                f"Configuration: decay_factor must lie in (0, 1); got {self.decay_factor!r}."
            )


@dataclass(frozen=True, slots=True)
class EpistemicState:
    """Immutable per-step state, identified by a hash chain.

    Attributes
    ----------
    seq:
        Monotonic 64-bit step counter starting at 0 for the genesis
        state and incrementing by exactly 1 per accepted update.
    weight:
        Accumulated evidence weight in ``[0, 1]``.
    budget:
        Remaining information budget in nats; ``≥ 0`` always
        (INV-FE2).
    invariant_floor:
        Static lower bound for ``weight``; copied from the originating
        :class:`EpistemicConfig` so each state is self-describing.
    phase:
        :class:`EpistemicPhase` — sticky once it reaches
        :attr:`EpistemicPhase.HALTED`.
    state_hash:
        Hex-encoded SHA-256 chain hash. Two state objects represent
        the same lineage iff their hashes are equal.
    halt_reason:
        Empty for active states. Populated with one of
        ``"budget_exhausted"`` or ``"weight_collapse"`` when the
        transition to :attr:`EpistemicPhase.HALTED` is taken.
    """

    seq: int
    weight: float
    budget: float
    invariant_floor: float
    phase: EpistemicPhase
    state_hash: str
    halt_reason: str = field(default="")

    @property
    def is_halted(self) -> bool:
        return self.phase is EpistemicPhase.HALTED


def _require_finite(label: str, **values: float) -> None:
    """Reject NaN / ±Inf — INV-HPC2 boundary check."""
    bad = [name for name, value in values.items() if not math.isfinite(value)]
    if bad:
        raise EpistemicError(
            f"INV-HPC2 VIOLATED: non-finite values in {label}: {bad}. "
            "Finite-input ⟹ finite-output is a P0 contract; "
            "fail closed at the boundary instead of propagating NaN."
        )


def _chain_state(
    prior_hash_hex: str,
    seq: int,
    weight: float,
    budget: float,
    invariant_floor: float,
    halted: bool,
) -> str:
    """Compute the SHA-256 chain hash for a successor state.

    Format (pinned by ``test_state_hash_format``):

    * 32 bytes — raw SHA-256 digest of the prior state.
    * 8 bytes — big-endian unsigned 64-bit ``seq``.
    * 8 bytes — IEEE-754 little-endian ``weight``.
    * 8 bytes — IEEE-754 little-endian ``budget``.
    * 8 bytes — IEEE-754 little-endian ``invariant_floor``.
    * 1 byte — ``0x01`` if halted else ``0x00``.

    Total: 65 bytes hashed per step.
    """
    prior_digest = bytes.fromhex(prior_hash_hex)
    if len(prior_digest) != 32:
        raise EpistemicError(
            f"chain integrity: prior hash must be 32 bytes, got {len(prior_digest)}."
        )
    payload = (
        prior_digest
        + struct.pack(">Q", seq)
        + struct.pack("<d", weight)
        + struct.pack("<d", budget)
        + struct.pack("<d", invariant_floor)
        + (b"\x01" if halted else b"\x00")
    )
    return hashlib.sha256(payload).hexdigest()


def initial_state(config: EpistemicConfig) -> EpistemicState:
    """Allocate the genesis state from configuration.

    Pure function: identical config ⟹ identical genesis state, so
    the lineage hash is reproducible across processes (INV-HPC1).
    """
    halted = False  # genesis is always active
    state_hash = _chain_state(
        prior_hash_hex=_GENESIS_HASH.hex(),
        seq=0,
        weight=config.initial_weight,
        budget=config.initial_budget,
        invariant_floor=config.invariant_floor,
        halted=halted,
    )
    return EpistemicState(
        seq=0,
        weight=config.initial_weight,
        budget=config.initial_budget,
        invariant_floor=config.invariant_floor,
        phase=EpistemicPhase.ACTIVE,
        state_hash=state_hash,
        halt_reason="",
    )


def update(
    state: EpistemicState,
    signal: float,
    fact: float,
    *,
    config: EpistemicConfig,
) -> EpistemicState:
    """Single-step update; pure and deterministic.

    Sticky halt: once ``state.phase`` is :attr:`EpistemicPhase.HALTED`,
    this function returns ``state`` unchanged. The seq counter does
    not advance — halt is the terminal vertex of the state machine.

    Parameters
    ----------
    state:
        Current state; must belong to a lineage created from
        ``config`` (the embedded ``invariant_floor`` is checked).
    signal, fact:
        Finite scalars. ``Δ = |fact − signal|``.
    config:
        Static configuration governing this lineage.

    Raises
    ------
    EpistemicError
        On non-finite inputs (INV-HPC2) or lineage mismatch.
    """
    if state.invariant_floor != config.invariant_floor:
        raise EpistemicError(
            "lineage mismatch: state.invariant_floor "
            f"({state.invariant_floor!r}) != "
            f"config.invariant_floor ({config.invariant_floor!r}). "
            "A state can only be advanced under the configuration that produced it."
        )
    if state.is_halted:
        return state

    _require_finite("update", signal=signal, fact=fact)

    delta = abs(fact - signal)
    cost = config.temperature * math.log1p(delta)
    # cost ≥ 0 because delta ≥ 0 ⟹ log1p ≥ 0 and T > 0 (INV-FE2 component).

    can_pay = cost <= state.budget
    above_floor = state.weight >= config.invariant_floor
    valid = can_pay and above_floor

    if valid:
        likelihood = 1.0 / (1.0 + delta)
        new_weight = (1.0 - config.learning_rate) * state.weight + (
            config.learning_rate * likelihood
        )
    else:
        new_weight = (1.0 - config.learning_rate * config.decay_factor) * state.weight

    # Always pay the cost — even on an invalid step the perception
    # event consumed information capacity.
    new_budget = state.budget - cost

    # Clamp weight to [0, 1]; invariant component (INV-FE2). The
    # arithmetic above is bounded by construction in exact arithmetic
    # but float drift can land at 1.0 + ε.
    if new_weight < 0.0:
        new_weight = 0.0
    elif new_weight > 1.0:
        new_weight = 1.0

    # Budget floor at 0; below 0 is a halt trigger, not a stored value.
    if new_budget < 0.0:
        new_budget = 0.0

    halted = (new_budget <= 0.0) or (new_weight < config.invariant_floor)
    if halted:
        if new_budget <= 0.0:
            halt_reason = "budget_exhausted"
        else:
            halt_reason = "weight_collapse"
        new_phase = EpistemicPhase.HALTED
    else:
        halt_reason = ""
        new_phase = EpistemicPhase.ACTIVE

    new_seq = state.seq + 1
    new_hash = _chain_state(
        prior_hash_hex=state.state_hash,
        seq=new_seq,
        weight=new_weight,
        budget=new_budget,
        invariant_floor=config.invariant_floor,
        halted=halted,
    )
    return replace(
        state,
        seq=new_seq,
        weight=new_weight,
        budget=new_budget,
        phase=new_phase,
        state_hash=new_hash,
        halt_reason=halt_reason,
    )


def verify_stream(
    state: EpistemicState,
    signals: NDArray[np.float64],
    facts: NDArray[np.float64],
    *,
    config: EpistemicConfig,
) -> EpistemicState:
    """Fold ``update`` over paired signal / fact streams.

    Stops short on the first halted state — subsequent samples are not
    evaluated, mirroring the sticky semantics of :func:`update`.

    Parameters
    ----------
    state:
        Initial state.
    signals, facts:
        1-D ``float64`` arrays of equal length. Both must be all-finite
        (INV-HPC2) — the check happens once up front rather than per
        step.
    config:
        Lineage configuration.
    """
    if signals.shape != facts.shape:
        raise EpistemicError(
            f"verify_stream: signals.shape ({signals.shape}) != facts.shape ({facts.shape})."
        )
    if signals.ndim != 1:
        raise EpistemicError(f"verify_stream: expected 1-D arrays, got ndim={signals.ndim}.")
    if not (np.isfinite(signals).all() and np.isfinite(facts).all()):
        raise EpistemicError(
            "INV-HPC2 VIOLATED: verify_stream rejects non-finite inputs upstream "
            "of the per-step update; check signal / fact pipelines."
        )

    current = state
    for signal, fact in zip(signals.tolist(), facts.tolist(), strict=True):
        if current.is_halted:
            break
        current = update(current, float(signal), float(fact), config=config)
    return current


def reset_with_external_proof(
    halted_state: EpistemicState,
    *,
    external_proof_hex: str,
    config: EpistemicConfig,
) -> EpistemicState:
    """Allocate a successor lineage from a halted state, anchored to external proof.

    The sticky-halt contract enforced by :func:`update` makes
    in-module recovery impossible by design — once a state's
    ``phase`` is :attr:`EpistemicPhase.HALTED`, no further updates
    advance the lineage. This function provides the *only* path out:
    the caller must present a SHA-256 proof token (32 raw bytes,
    encoded as 64 hex characters) representing a verifiable external
    safety event — typically the digest of a
    :class:`runtime.rebus_gate.RebusGate` ``emergency_exit`` audit
    record. The new state's chain hash is derived from both the
    halted state's hash AND the proof, so the external event is
    woven into the lineage and verifiable downstream.

    The new ``seq`` is ``halted_state.seq + 1`` — the lineage
    continues, it is not restarted from zero. This means the audit
    log of a system that has weathered N halts shows ``N`` resets,
    each one a distinguishable transition.

    Hashing format (pinned by :func:`tests.unit.neuro.test_epistemic_validation.test_reset_chain_format`):

    * 32 bytes — raw SHA-256 digest of the halted state's hash.
    * 32 bytes — raw external proof.
    * 8 bytes — IEEE-754 little-endian ``config.initial_weight``.
    * 8 bytes — IEEE-754 little-endian ``config.initial_budget``.
    * 8 bytes — IEEE-754 little-endian ``config.invariant_floor``.

    Total: 88 bytes hashed to derive the post-reset state hash.

    Parameters
    ----------
    halted_state:
        Must satisfy ``halted_state.is_halted``. Active states
        cannot be "reset" — they are not in need of one.
    external_proof_hex:
        Exactly 64 hexadecimal characters encoding a 32-byte digest.
        The function does not interpret the proof — verification of
        what it represents is the caller's responsibility.
    config:
        Lineage configuration. Must agree with the halted state's
        ``invariant_floor`` (a reset cannot quietly relax the
        contract).

    Raises
    ------
    EpistemicError
        If the state is not halted, the proof is malformed, or the
        config does not match the halted lineage.
    """
    if not halted_state.is_halted:
        raise EpistemicError(
            f"reset_with_external_proof: state is not HALTED "
            f"(phase={halted_state.phase.value!r}); "
            "an active lineage does not need — and cannot accept — an external reset."
        )
    if halted_state.invariant_floor != config.invariant_floor:
        raise EpistemicError(
            "reset_with_external_proof: lineage mismatch — "
            f"halted_state.invariant_floor={halted_state.invariant_floor!r} "
            f"!= config.invariant_floor={config.invariant_floor!r}. "
            "A reset cannot relax the contract that produced the halt."
        )
    if len(external_proof_hex) != _HEX_LEN:
        raise EpistemicError(
            "reset_with_external_proof: external_proof_hex must be exactly "
            f"{_HEX_LEN} hex characters (32 raw bytes); got "
            f"{len(external_proof_hex)} characters."
        )
    try:
        proof = bytes.fromhex(external_proof_hex)
    except ValueError as exc:
        raise EpistemicError(
            f"reset_with_external_proof: external_proof_hex is not valid hex: {exc}"
        ) from exc
    if len(proof) != 32:
        raise EpistemicError(
            f"reset_with_external_proof: decoded proof length {len(proof)} != 32 bytes."
        )
    prior_digest = bytes.fromhex(halted_state.state_hash)
    payload = (
        prior_digest
        + proof
        + struct.pack("<d", config.initial_weight)
        + struct.pack("<d", config.initial_budget)
        + struct.pack("<d", config.invariant_floor)
    )
    new_hash = hashlib.sha256(payload).hexdigest()
    return EpistemicState(
        seq=halted_state.seq + 1,
        weight=config.initial_weight,
        budget=config.initial_budget,
        invariant_floor=config.invariant_floor,
        phase=EpistemicPhase.ACTIVE,
        state_hash=new_hash,
        halt_reason="",
    )


@dataclass(frozen=True, slots=True)
class HaltMargin:
    """Two-axis observable describing how close a state is to its halt boundary.

    Reactive halt detection (the ``HALTED`` phase set by :func:`update`)
    only tells consumers that a halt has *already* happened. To gate
    downstream actions *before* halt, this observable exposes the
    distance to each halt trigger as a separate non-negotiable scalar.

    Attributes
    ----------
    budget_remaining:
        Information budget still available for spending.
        ``budget_remaining == 0.0`` is the budget-exhaustion boundary;
        the next non-zero cost crosses it. Always ``≥ 0`` by INV-FE2.
    weight_above_floor:
        ``state.weight − state.invariant_floor``. Strictly positive
        in healthy operation. Reaches zero (or below) at the
        weight-collapse boundary.
    is_halted:
        Convenience flag mirroring :attr:`EpistemicState.is_halted`
        — present here so consumers do not have to plumb the state
        object alongside the margin.

    Why this is *not* a halt predictor
    ----------------------------------

    A predictor would extrapolate future cost trajectories under
    explicit assumptions (i.i.d. costs, Markov surprise, regime
    stationarity). The right place for those assumptions is the
    consumer — they vary by deployment. This observable stays pure:
    it reports the current geometric distance from the boundary on
    each axis. Composing a predictor on top is straightforward
    (e.g., ``budget_remaining / mean(recent_costs) ≈ steps_to_halt``)
    and is documented in :func:`halt_margin`.
    """

    budget_remaining: float
    weight_above_floor: float
    is_halted: bool


def halt_margin(state: EpistemicState, *, config: EpistemicConfig) -> HaltMargin:
    """Compute the two-axis halt margin from a state.

    Pure function. Identical input ⟹ identical output (INV-HPC1).

    Composing a halt predictor on top — example
    ------------------------------------------

    Given a window of recent per-step costs, a consumer can extrapolate
    the budget-axis steps-to-halt as::

        margin = halt_margin(state, config=cfg)
        avg_cost = float(np.mean(recent_costs))
        if avg_cost > 0.0 and not margin.is_halted:
            steps_to_budget_halt = margin.budget_remaining / avg_cost
        else:
            steps_to_budget_halt = math.inf

    The weight-axis equivalent uses the EMA decay rate of recent
    weight observations. Both extrapolations live with the consumer,
    not in this module — they bake assumptions about the cost
    distribution that are deployment-specific.

    Parameters
    ----------
    state:
        Current state.
    config:
        Lineage configuration. Must agree with the state's
        ``invariant_floor`` (the lineage-mismatch contract from
        :func:`update` is enforced here too — a margin computed
        against the wrong floor would be silently wrong).

    Raises
    ------
    EpistemicError
        On lineage mismatch between state and config.
    """
    if state.invariant_floor != config.invariant_floor:
        raise EpistemicError(
            "halt_margin: lineage mismatch — "
            f"state.invariant_floor ({state.invariant_floor!r}) != "
            f"config.invariant_floor ({config.invariant_floor!r})."
        )
    return HaltMargin(
        budget_remaining=state.budget,
        weight_above_floor=state.weight - state.invariant_floor,
        is_halted=state.is_halted,
    )


@dataclass(frozen=True, slots=True)
class RebusBridge:
    """Composition primitive linking epistemic halt to RebusGate exits.

    Calling :meth:`maybe_escalate` with a halted state forwards the
    halt as a ``stressed_state=True`` external safety signal to a
    :class:`runtime.rebus_gate.RebusGate`, which (per its own
    contract) will trigger ``emergency_exit`` and restore the parent
    weight set if the gate is currently active. This makes epistemic
    halt a Layer 2-3 protector path — Cryptobiosis remains the
    Layer 3 last-resort.
    """

    def maybe_escalate(
        self,
        state: EpistemicState,
        gate: RebusGate,
    ) -> dict[str, float] | None:
        """Forward a halted state to the gate; no-op otherwise.

        Returns the restored weight set if RebusGate executed an
        emergency exit, else ``None``.
        """
        if not state.is_halted:
            return None
        return gate.apply_external_safety_signal(
            kill_switch_active=False,
            stressed_state=True,
        )
