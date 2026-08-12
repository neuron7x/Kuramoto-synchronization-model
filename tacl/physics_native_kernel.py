# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
# no-bio-claim
"""PNCC-F — Physics-Native Cognitive Kernel composition controller.

Status
------
EXPERIMENTAL / OPT-IN. Pure composition over the four PNCC primitives
shipped in PR #378 (PNCC-A: thermodynamic budget), #380 (PNCC-C:
reversible gate), #373 (DR-FREE distributionally robust free energy),
and #379 (PNCC-E: evidence ledger). This module adds **no new physics**
and **no new dataclasses** beyond the controller's I/O surface.

Composition diagram
-------------------
The kernel is a single decision controller that fuses three contracts
into one fail-closed selection step::

                    +-----------------------+
                    |  candidates: Sequence |
                    +-----------+-----------+
                                |
                                v
                  +----------------------------+
                  |  evaluate_candidate(c, ..) |
                  |   F_robust   <- DR-FREE    |  (tacl.dr_free)
                  |   thermo     <- budget     |  (core.physics
                  |   irrev_cost <- gate score |   .thermodynamic_budget,
                  +----------------------------+   .reversible_gate)
                                |
                                v
                  composite = F_robust
                            + lambda_thermo * thermo
                            + lambda_irreversibility * irrev_cost
                                |
                                v
                +--------------------------------+
                | argmin selection w/ tie guard  |
                |   tie within tolerance         |
                |   AND fail_closed_on_tie       |
                |     => DORMANT (chosen=None)   |
                +--------------------------------+
                                |
                                v
                +--------------------------------+
                | reversible_gate.gate(...)      |
                |   admit chosen action,         |
                |   record DecisionTrace         |
                +--------------------------------+
                                |
                                v
                       KernelDecision(
                         chosen, state,
                         scores, audit_hash,
                         decision_trace, ...
                       )

Public API
----------
``CandidateAction``               — one candidate under evaluation.
``PhysicsNativeKernelConfig``     — tradeoff weights + tie policy.
``CompositeScore``                — per-candidate score breakdown.
``KernelDecision``                — end-to-end output + audit trail.
``evaluate_candidate``            — pure composite-score function.
``select_action``                 — pure end-to-end selection.
``PhysicsNativeKernel``           — instance carries reversible-gate ledger.

Invariant
---------
``INV-FREE-ENERGY`` (P0, universal, kernel-selection scope):

    For any non-empty ``candidates`` and any ``(metrics, ambiguity, cfg)``,
    let ``composites = [evaluate_candidate(c, ...).composite for c in
    candidates]``. Then either:

      (a) ``decision.chosen is not None`` AND
          ``decision.chosen.composite == min(composites)``  (unique argmin), OR
      (b) ``decision.chosen is None`` AND ``decision.state == "DORMANT"``
          AND there are >= 2 candidates within ``tie_tolerance`` of the
          minimum (fail-closed on ambiguity).

    Equivalent: chosen action MUST be the unique-or-fail-closed argmin
    of the composite score.

    **Falsification axis.** 1000 random ``(candidates, metrics,
    ambiguity)`` draws — any decision where ``chosen.composite >
    min(composites) + tie_tolerance`` with ``state != "DORMANT"`` is
    a violation.

    **Disambiguation note.** GeoSync's pre-existing
    ``INV-FREE-ENERGY`` (CANONS.md §3, monotonicity of F = U - T*S)
    governs the ECS / energy-model dynamics. The kernel-selection-side
    invariant in this module is the same name but a different scope:
    here it asserts argmin-or-fail-closed selection over composite
    scores; there it asserts dF/dt <= 0 under active inference. A
    coordination PR will register this scope in ``physics_contracts/``
    after this module lands (per the brief).

Other contracts
---------------
``INV-HPC1`` (universal): bit-identical output under fixed inputs. The
kernel uses no global state, no RNG, and no time call; the underlying
``ReversibleGate`` ledger is instance-scoped.

``INV-HPC2`` (universal): finite inputs => finite outputs. NaN / Inf
inputs raise (delegated to underlying primitives' fail-closed checks).

No-bio-claim
------------
This module composes system-level decision controllers. It makes no
claim about human cognition, focus, productivity, or any biological
optimization. Cognitive-performance assertions about the combined loop
(HYP-5) require a registered ``EvidenceClaim`` — see
``tacl/evidence_ledger.py`` and ``docs/research/pncc/CANONS.md``.

References
----------
* Landauer 1961 — *Irreversibility and Heat Generation in the Computing
  Process*, IBM J. Res. Dev. 5, 183.
* Bennett 1973 — *Logical Reversibility of Computation*, IBM J. Res.
  Dev. 17, 525.
* Friston 2010 — *The free-energy principle: a unified brain theory?*,
  Nature Reviews Neuroscience 11, 127. (Free-Energy Principle reference
  for the F = U - T*S formulation; this module makes no biological
  claim.)
* Distributionally robust optimization (textbook, Wiesemann/Kuhn/Sim
  2014 generic reference; no specific paper claim).

Known limitations
-----------------
* ``lambda_thermo`` and ``lambda_irreversibility`` default to 0.0 — by
  default the kernel reduces to **pure DR-FREE selection**. Activating
  the thermodynamic / irreversibility penalties is opt-in per call site.
* No online learning of ``lambda_thermo`` / ``lambda_irreversibility``.
  The weights are constants per ``PhysicsNativeKernelConfig`` instance.
* No PNCC-D telemetry plug-in yet (``CNSProxyState`` has no constructor
  on ``main`` at the time of writing). Telemetry will be wired in once
  PNCC-D lands.
* The selection step is fully synchronous; there is no streaming /
  windowing layer. Callers must bound candidate-set size externally.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from core.physics.reversible_gate import (
    DecisionTrace,
    ReversibleGate,
    ReversibleGateConfig,
)
from core.physics.thermodynamic_budget import (
    ThermodynamicBudgetConfig,
    aggregate_entry,
    compute_entropy_cost,
    compute_irreversibility_cost,
    compute_latency_cost,
    compute_token_cost,
)

from .dr_free import AmbiguitySet, DRFreeEnergyModel, robust_energy_state
from .energy_model import EnergyMetrics

__all__ = [
    "CandidateAction",
    "CompositeScore",
    "KernelDecision",
    "PhysicsNativeKernel",
    "PhysicsNativeKernelConfig",
    "evaluate_candidate",
    "select_action",
]


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------


# Default warning/crisis thresholds for ``robust_energy_state``. These
# are conservative defaults that will rarely trigger DORMANT on its own;
# callers wishing to tune them should compose with their own
# ``robust_energy_state`` call upstream of the kernel.
_DEFAULT_WARNING_THRESHOLD: Final[float] = 1.0e9  # effectively disabled
_DEFAULT_CRISIS_THRESHOLD: Final[float] = 1.0e9  # effectively disabled

# Default p99 latency to feed into ``compute_latency_cost``: equal to
# wall_time_ns. p99 is recorded only; it does not enter the cost.
# Documented here so that the kernel does not silently fabricate a p99.

# Action-id used when constructing a thermodynamic-budget BudgetEntry
# inside ``evaluate_candidate``. The entry is per-candidate-evaluation,
# never persisted — it exists only to compute ``total_proxy_cost``.
_BUDGET_EVAL_ACTION_ID: Final[str] = "pncc-f.evaluate"


# ---------------------------------------------------------------------------
# Public dataclasses (controller I/O surface only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateAction:
    """One candidate action under evaluation by the kernel.

    All fields are caller-supplied, fully deterministic, and feed
    directly into the four PNCC primitives. ``irreversibility_score``
    must be in ``[0, 1]`` — the underlying ``ReversibleGate`` enforces
    this; we additionally enforce it here for fail-closed clarity at
    the kernel boundary.
    """

    action_id: str
    payload: bytes
    irreversibility_score: float  # in [0, 1]; 0 = fully reversible
    n_input_tokens: int
    n_output_tokens: int
    expected_wall_time_ns: int
    bits_consumed: float
    bits_erased: float


@dataclass(frozen=True, slots=True)
class PhysicsNativeKernelConfig:
    """Trade-off weights between robust free energy, thermodynamic cost,
    and irreversibility penalty.

    All defaults are conservative; defaults must NOT activate the kernel
    as a system default elsewhere. Activating ``lambda_thermo`` or
    ``lambda_irreversibility`` is opt-in per call site.

    Attributes
    ----------
    lambda_thermo:
        Weight on the per-candidate ``BudgetEntry.total_proxy_cost``.
        Must be >= 0 (non-negativity is checked in
        ``evaluate_candidate``). Default 0.0 makes the kernel reduce
        to pure DR-FREE selection.
    lambda_irreversibility:
        Weight on the irreversibility cost (``penalty * score``).
        Must be >= 0. Default 0.0.
    tie_tolerance:
        Numerical tolerance below which two composite scores are
        considered tied. Must be >= 0. Default 1e-12.
    fail_closed_on_tie:
        If True (default), a tie within ``tie_tolerance`` collapses
        the decision to DORMANT (chosen=None). If False, the first
        argmin in candidate order is chosen — used in tests only.
    ambiguity_radii:
        Per-metric box-radius defaults. Forwarded into a fresh
        ``AmbiguitySet`` when the caller does not supply one. Empty
        dict (default) yields the zero-radius / nominal-only case.
    irreversibility_penalty:
        Forwarded into ``ThermodynamicBudgetConfig`` for the
        budget-side irreversibility component. Independent of
        ``lambda_irreversibility`` (which weights the gate-side
        score).
    warning_threshold / crisis_threshold:
        Forwarded into ``robust_energy_state`` to compute the kernel's
        coarse state. Defaults are intentionally astronomical so that
        ``robust_energy_state`` does not flip to DORMANT on its own —
        callers wanting that behavior should override.
    """

    lambda_thermo: float = 0.0
    lambda_irreversibility: float = 0.0
    tie_tolerance: float = 1e-12
    fail_closed_on_tie: bool = True
    ambiguity_radii: Mapping[str, float] = field(default_factory=dict)
    irreversibility_penalty: float = 1.0
    warning_threshold: float = _DEFAULT_WARNING_THRESHOLD
    crisis_threshold: float = _DEFAULT_CRISIS_THRESHOLD


@dataclass(frozen=True, slots=True)
class CompositeScore:
    """Per-candidate score breakdown, used both as audit input and as
    the per-candidate row of ``KernelDecision.scores``.

    ``composite`` is the actual selection criterion::

        composite = f_robust
                  + lambda_thermo * thermo_cost
                  + lambda_irreversibility * irreversibility_cost
    """

    candidate: CandidateAction
    f_robust: float
    thermo_cost: float
    irreversibility_cost: float
    composite: float


@dataclass(frozen=True, slots=True)
class KernelDecision:
    """End-to-end decision: chosen action (or None for DORMANT) plus
    full audit trail.

    Fields
    ------
    chosen:
        The selected ``CandidateAction``, or ``None`` if the decision
        collapsed to DORMANT (fail-closed on tie, fail-closed on robust
        state, or empty candidate set).
    state:
        ``"NORMAL"`` / ``"WARNING"`` / ``"DORMANT"``. Matches the
        contract of ``robust_energy_state`` plus the kernel's own
        DORMANT collapse logic.
    scores:
        Per-candidate composite-score breakdown. Always populated when
        ``candidates`` is non-empty (even on DORMANT).
    audit_hash:
        SHA-256 of the chosen candidate's gated trace. ``None`` when
        ``chosen is None``.
    decision_trace:
        ``DecisionTrace`` from ``ReversibleGate.gate``. ``None`` when
        ``chosen is None``.
    robust_margin:
        ``robust_free_energy - nominal_free_energy`` for the chosen
        candidate (or for the argmin candidate if DORMANT-on-tie).
        ``0.0`` when no candidates were supplied.
    reason:
        Human-readable explanation. Empty for the normal pass-through;
        populated on DORMANT to explain the cause.
    """

    chosen: CandidateAction | None
    state: Literal["NORMAL", "WARNING", "DORMANT"]
    scores: tuple[CompositeScore, ...]
    audit_hash: str | None
    decision_trace: DecisionTrace | None
    robust_margin: float
    reason: str


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_config(cfg: PhysicsNativeKernelConfig) -> None:
    """Fail-closed checks on the kernel config. INV-HPC2."""
    if cfg.lambda_thermo < 0.0:
        raise ValueError(
            f"PhysicsNativeKernelConfig.lambda_thermo must be >= 0, "
            f"got {cfg.lambda_thermo!r}; weights are unsigned penalties."
        )
    if cfg.lambda_irreversibility < 0.0:
        raise ValueError(
            f"PhysicsNativeKernelConfig.lambda_irreversibility must be >= 0, "
            f"got {cfg.lambda_irreversibility!r}; weights are unsigned penalties."
        )
    if cfg.tie_tolerance < 0.0:
        raise ValueError(
            f"PhysicsNativeKernelConfig.tie_tolerance must be >= 0, "
            f"got {cfg.tie_tolerance!r}; tolerance is a non-negative epsilon."
        )
    if cfg.warning_threshold > cfg.crisis_threshold:
        raise ValueError(
            f"warning_threshold={cfg.warning_threshold!r} must be <= "
            f"crisis_threshold={cfg.crisis_threshold!r}."
        )
    if cfg.irreversibility_penalty < 0.0:
        raise ValueError(
            f"PhysicsNativeKernelConfig.irreversibility_penalty must be >= 0, "
            f"got {cfg.irreversibility_penalty!r}."
        )
    for name, radius in cfg.ambiguity_radii.items():
        if not isinstance(name, str):
            raise ValueError(f"ambiguity_radii keys must be strings, got {type(name).__name__}.")
        if radius < 0.0:
            raise ValueError(f"ambiguity_radii['{name}']={radius!r} must be >= 0.")


def _validate_candidate(candidate: CandidateAction) -> None:
    """Fail-closed checks on a single candidate. INV-HPC2 / INV-LANDAUER-PROXY."""
    if not isinstance(candidate.action_id, str) or not candidate.action_id:
        raise ValueError(
            f"CandidateAction.action_id must be a non-empty str, got {candidate.action_id!r}."
        )
    if not isinstance(candidate.payload, (bytes, bytearray)):
        raise TypeError(
            f"CandidateAction.payload must be bytes, got {type(candidate.payload).__name__}."
        )
    score = candidate.irreversibility_score
    if score != score:  # NaN check
        raise ValueError(f"CandidateAction.irreversibility_score must not be NaN, got {score!r}.")
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"CandidateAction.irreversibility_score must be in [0, 1], got {score!r}.")
    if candidate.n_input_tokens < 0 or candidate.n_output_tokens < 0:
        raise ValueError(
            f"CandidateAction token counts must be >= 0, "
            f"got n_in={candidate.n_input_tokens}, n_out={candidate.n_output_tokens}."
        )
    if candidate.expected_wall_time_ns < 0:
        raise ValueError(
            f"CandidateAction.expected_wall_time_ns must be >= 0, "
            f"got {candidate.expected_wall_time_ns!r}."
        )
    if candidate.bits_consumed < 0.0 or candidate.bits_erased < 0.0:
        raise ValueError(
            f"CandidateAction bits must be >= 0, "
            f"got bits_consumed={candidate.bits_consumed}, "
            f"bits_erased={candidate.bits_erased}."
        )


def _ambiguity_from(
    cfg: PhysicsNativeKernelConfig,
    ambiguity: AmbiguitySet | None,
) -> AmbiguitySet:
    """Resolve the effective ambiguity set: caller-supplied wins, then
    config-default, then zero-radius."""
    if ambiguity is not None:
        return ambiguity
    return AmbiguitySet(radii=dict(cfg.ambiguity_radii), mode="box")


# ---------------------------------------------------------------------------
# Pure composite-score function
# ---------------------------------------------------------------------------


def evaluate_candidate(
    candidate: CandidateAction,
    metrics: EnergyMetrics,
    ambiguity: AmbiguitySet,
    cfg: PhysicsNativeKernelConfig,
    *,
    free_energy_model: DRFreeEnergyModel,
) -> CompositeScore:
    """Compute the composite score for one candidate.

    ``composite = F_robust + lambda_thermo * thermo_cost
                + lambda_irreversibility * irreversibility_cost``

    Pure: no global state, no RNG, no I/O. The function delegates all
    fail-closed checks to the underlying primitives (DR-FREE, budget,
    gate score). INV-HPC1: same inputs => same composite to float
    precision.
    """
    _validate_candidate(candidate)
    _validate_config(cfg)

    # --- DR-FREE (robust free energy) -------------------------------
    dr_result = free_energy_model.evaluate_robust(metrics, ambiguity)
    f_robust = float(dr_result.robust_free_energy)

    # --- Thermodynamic budget proxy ---------------------------------
    budget_cfg = ThermodynamicBudgetConfig(
        irreversibility_penalty=cfg.irreversibility_penalty,
    )
    token = compute_token_cost(candidate.n_input_tokens, candidate.n_output_tokens)
    latency = compute_latency_cost(
        candidate.expected_wall_time_ns,
        candidate.expected_wall_time_ns,  # p99 == wall here; not on the cost path
    )
    entropy = compute_entropy_cost(candidate.bits_consumed, candidate.bits_erased)
    is_irreversible = candidate.irreversibility_score > 0.0
    irrev_budget = compute_irreversibility_cost(
        is_irreversible=is_irreversible,
        score=candidate.irreversibility_score,
        cfg=budget_cfg,
    )
    entry = aggregate_entry(
        action_id=_BUDGET_EVAL_ACTION_ID,
        timestamp_ns=0,
        token=token,
        lat=latency,
        ent=entropy,
        irr=irrev_budget,
    )
    thermo_cost = float(entry.total_proxy_cost)

    # --- Irreversibility-cost component (gate side) -----------------
    # The gate-side irreversibility cost is a *separate* lever from the
    # budget-side one above: it lets callers add an explicit penalty on
    # the score itself, independent of the budget aggregate. Setting
    # lambda_irreversibility=0 (default) yields no extra contribution.
    irreversibility_cost = float(candidate.irreversibility_score)

    composite = (
        f_robust
        + cfg.lambda_thermo * thermo_cost
        + cfg.lambda_irreversibility * irreversibility_cost
    )

    return CompositeScore(
        candidate=candidate,
        f_robust=f_robust,
        thermo_cost=thermo_cost,
        irreversibility_cost=irreversibility_cost,
        composite=composite,
    )


# ---------------------------------------------------------------------------
# Pure end-to-end selection (no gate side-effect; gate is wired in the class)
# ---------------------------------------------------------------------------


def select_action(
    candidates: Sequence[CandidateAction],
    metrics: EnergyMetrics,
    ambiguity: AmbiguitySet,
    cfg: PhysicsNativeKernelConfig,
    *,
    free_energy_model: DRFreeEnergyModel,
) -> KernelDecision:
    """Score all candidates, apply argmin selection with tie / DORMANT
    guards, and return a ``KernelDecision``.

    INV-FREE-ENERGY (kernel selection scope): chosen action MUST be the
    unique-or-fail-closed argmin of ``CompositeScore.composite``. Ties
    within ``cfg.tie_tolerance`` collapse to DORMANT (chosen=None) when
    ``cfg.fail_closed_on_tie`` is True; when False, the first argmin in
    candidate order is selected (used in tests only).

    This function is **pure** — it does not touch any reversible-gate
    ledger. ``KernelDecision.audit_hash`` and ``decision_trace`` are
    therefore always ``None`` from this entry point. To get a recorded
    trace and audit hash, use ``PhysicsNativeKernel.decide``.
    """
    _validate_config(cfg)

    # Empty candidate set => fail-closed DORMANT, with a reason.
    if not candidates:
        return KernelDecision(
            chosen=None,
            state="DORMANT",
            scores=(),
            audit_hash=None,
            decision_trace=None,
            robust_margin=0.0,
            reason="empty candidate set; fail-closed DORMANT",
        )

    # Score every candidate.
    scores = tuple(
        evaluate_candidate(
            c,
            metrics,
            ambiguity,
            cfg,
            free_energy_model=free_energy_model,
        )
        for c in candidates
    )

    # Robust state — uses the *first* candidate's DR-FREE result (all
    # candidates share the same metrics + ambiguity, so robust_F differs
    # only if metrics differ; for the kernel scope they don't).
    dr_result = free_energy_model.evaluate_robust(metrics, ambiguity)
    state: Literal["NORMAL", "WARNING", "DORMANT"] = robust_energy_state(
        dr_result,
        warning_threshold=cfg.warning_threshold,
        crisis_threshold=cfg.crisis_threshold,
    )
    robust_margin = float(dr_result.robust_margin)

    # If the robust state is DORMANT, fail closed regardless of
    # candidates. INV-CB-style safety: no dispatch under crisis state.
    if state == "DORMANT":
        return KernelDecision(
            chosen=None,
            state="DORMANT",
            scores=scores,
            audit_hash=None,
            decision_trace=None,
            robust_margin=robust_margin,
            reason="robust_energy_state == DORMANT; fail-closed",
        )

    # Argmin with tie tolerance.
    composites = [s.composite for s in scores]
    min_composite = min(composites)
    near_min_indices = [
        i for i, c in enumerate(composites) if c <= min_composite + cfg.tie_tolerance
    ]
    if len(near_min_indices) >= 2 and cfg.fail_closed_on_tie:
        return KernelDecision(
            chosen=None,
            state="DORMANT",
            scores=scores,
            audit_hash=None,
            decision_trace=None,
            robust_margin=robust_margin,
            reason=(
                f"INV-FREE-ENERGY tie: {len(near_min_indices)} candidates "
                f"within tie_tolerance={cfg.tie_tolerance!r} of min "
                f"composite={min_composite!r}; fail-closed DORMANT"
            ),
        )

    chosen_idx = near_min_indices[0]
    chosen = scores[chosen_idx].candidate

    return KernelDecision(
        chosen=chosen,
        state=state,
        scores=scores,
        audit_hash=None,
        decision_trace=None,
        robust_margin=robust_margin,
        reason="",
    )


# ---------------------------------------------------------------------------
# Stateful kernel: composes select_action with reversible_gate ledger
# ---------------------------------------------------------------------------


class PhysicsNativeKernel:
    """Stateless composition; instance carries the reversible-gate
    ledger only.

    Two distinct kernel instances cannot observe each other's gate
    ledgers. There is no global / module-level state.
    """

    def __init__(
        self,
        cfg: PhysicsNativeKernelConfig | None = None,
        *,
        free_energy_model: DRFreeEnergyModel | None = None,
        gate: ReversibleGate | None = None,
    ) -> None:
        self._cfg: Final[PhysicsNativeKernelConfig] = (
            cfg if cfg is not None else PhysicsNativeKernelConfig()
        )
        _validate_config(self._cfg)
        self._free_energy_model: Final[DRFreeEnergyModel] = (
            free_energy_model if free_energy_model is not None else DRFreeEnergyModel()
        )
        # The gate's irreversibility threshold is *independent* of the
        # kernel's lambda weights. We default to a permissive threshold
        # so that any candidate with score == 0 is treated as reversible.
        self._gate: Final[ReversibleGate] = (
            gate
            if gate is not None
            else ReversibleGate(
                ReversibleGateConfig(
                    irreversibility_threshold=0.05,
                    require_rollback_payload=False,
                    fail_on_hash_collision=True,
                    canonicalize_json=True,
                )
            )
        )

    @property
    def config(self) -> PhysicsNativeKernelConfig:
        return self._cfg

    @property
    def free_energy_model(self) -> DRFreeEnergyModel:
        return self._free_energy_model

    @property
    def gate(self) -> ReversibleGate:
        return self._gate

    def decide(
        self,
        candidates: Sequence[CandidateAction],
        metrics: EnergyMetrics,
        ambiguity: AmbiguitySet | None = None,
        timestamp_ns: int = 0,
    ) -> KernelDecision:
        """End-to-end: score all, select argmin, gate through
        ``reversible_gate``, return ``KernelDecision``.

        ``timestamp_ns`` is forwarded into ``ReversibleGate.gate`` so
        that the recorded ``DecisionTrace.audit_hash`` is deterministic.
        Default 0 is used in tests; production callers should pass a
        monotonic clock value.
        """
        if timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {timestamp_ns!r}.")
        eff_ambiguity = _ambiguity_from(self._cfg, ambiguity)
        decision = select_action(
            candidates,
            metrics,
            eff_ambiguity,
            self._cfg,
            free_energy_model=self._free_energy_model,
        )
        if decision.chosen is None:
            return decision

        chosen = decision.chosen
        # Build a deterministic pre/post-state pair from the candidate's
        # payload + composite score. We do not have access to a real
        # external pre-state here; the kernel's gate is an *internal*
        # decision audit, not a market-side rollback ledger.
        composite_repr = _composite_repr(decision.scores)
        pre_state = composite_repr
        post_state = _post_state_for(chosen)

        trace = self._gate.gate(
            action_id=chosen.action_id,
            pre_state=pre_state,
            action_payload=chosen.payload,
            post_state=post_state,
            irreversibility_score=chosen.irreversibility_score,
            timestamp_ns=timestamp_ns,
            rollback_payload=None,
        )

        return KernelDecision(
            chosen=chosen,
            state=decision.state,
            scores=decision.scores,
            audit_hash=trace.audit_hash,
            decision_trace=trace,
            robust_margin=decision.robust_margin,
            reason=decision.reason,
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _composite_repr(scores: Sequence[CompositeScore]) -> bytes:
    """Deterministic byte-encoding of all composite scores in selection
    order. Used as the gate's ``pre_state``: it is the kernel's view of
    the decision-time state (the score table). INV-HPC1 — same inputs
    yield identical bytes to byte precision.
    """
    h = hashlib.sha256()
    for s in scores:
        h.update(s.candidate.action_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(repr(float(s.composite)).encode("ascii"))
        h.update(b"\x00")
        h.update(repr(float(s.f_robust)).encode("ascii"))
        h.update(b"\x00")
        h.update(repr(float(s.thermo_cost)).encode("ascii"))
        h.update(b"\x00")
        h.update(repr(float(s.irreversibility_cost)).encode("ascii"))
        h.update(b"\x01")
    return h.digest()


def _post_state_for(chosen: CandidateAction) -> bytes:
    """Deterministic byte-encoding of the chosen candidate. Used as
    the gate's ``post_state``."""
    h = hashlib.sha256()
    h.update(b"pncc-f.post\x00")
    h.update(chosen.action_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(repr(float(chosen.irreversibility_score)).encode("ascii"))
    h.update(b"\x00")
    h.update(chosen.payload)
    return h.digest()
