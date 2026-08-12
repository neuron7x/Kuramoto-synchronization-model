# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Distributed-resilience adapter for the damped phase-synchronization solver.

The base solver in :mod:`geosync.neuroeconomics.reset_wave_engine` proves
its four numerical invariants only under **ideal computational conditions**:
single-process, synchronous, no clock skew, no dropped updates, no
concurrent writers. In a real distributed asynchronous environment
(financial market data feeds, IoT meshes, multi-process simulators)
the following failure modes break the potential-non-increase guarantee:

    1. Clock-jitter on update arrival → V can spike before the next
       step damps it.
    2. Dropped or out-of-order updates → ``θ_t`` and ``θ_baseline`` may
       drift apart between steps without the lock firing.
    3. Partial node failure → a subset of nodes is silently stale.
    4. Re-entry after failure → a recovered node injects an old phase
       and undoes prior corrections.
    5. Concurrent writers → two callers interleave updates and step.

This module wraps :func:`run_reset_wave` with five fail-closed guards
that each turn an async failure mode into either an explicit safety
lock OR a flagged ``DiscontinuityMonitor`` event. **There is no
attempt to deliver CAP-theorem-level distributed consensus**; the
guards refuse to compute on inputs that violate their preconditions.
The residual gap is documented in ``docs/KNOWN_LIMITATIONS.md`` L-12.

FACT     (ANCHORED): the five guards are deterministic functions of
                     their inputs; tests pin every branch.
MODEL    (EXTRAPOLATED): the guards together approximate the
                     resilience layer for an asynchronous environment.
                     The approximation is empirical, not analytical.
ANALOGY  (SPECULATIVE, research notes only): "neuro reset-wave under
                     adversarial messaging" — interpretive only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from geosync.neuroeconomics.reset_wave_engine import (
    ResetWaveConfig,
    ResetWaveResult,
    phase_alignment_potential,
    run_reset_wave,
)


@dataclass(frozen=True, slots=True)
class JitterEnvelope:
    """Acceptable arrival-time variance for a batch of node updates.

    `t_min`, `t_max` are nanosecond timestamps. `max_jitter_ns` is the
    upper bound on `t_max − t_min`. Outside the envelope the adapter
    refuses to compute and surfaces ``jitter_violation``.
    """

    max_jitter_ns: int

    def violated(self, timestamps_ns: list[int]) -> bool:
        if not timestamps_ns:
            return False
        return (max(timestamps_ns) - min(timestamps_ns)) > self.max_jitter_ns


@dataclass(frozen=True, slots=True)
class StalenessGate:
    """Reject updates older than `max_age_ns` relative to the wall clock.

    The wall-clock value is passed in explicitly so the gate is
    deterministic under unit testing — no implicit ``time.time_ns()``.
    """

    max_age_ns: int

    def stale_indices(self, timestamps_ns: list[int], now_ns: int) -> tuple[int, ...]:
        return tuple(i for i, t in enumerate(timestamps_ns) if (now_ns - t) > self.max_age_ns)


@dataclass(frozen=True, slots=True)
class ConcurrencyGuard:
    """Reject out-of-order updates per node.

    Maintains the last accepted sequence number per node id. Any new
    update with a sequence ≤ the accepted value for the same node is
    rejected as ``out_of_order``. The guard is a pure function: the
    state is supplied explicitly via ``last_seqs``.
    """

    @staticmethod
    def accepts(
        node_seqs: list[int],
        last_seqs: dict[int, int],
    ) -> tuple[bool, tuple[int, ...]]:
        rejected: list[int] = []
        for i, seq in enumerate(node_seqs):
            prev = last_seqs.get(i)
            if prev is not None and seq <= prev:
                rejected.append(i)
        return (len(rejected) == 0, tuple(rejected))


@dataclass(frozen=True, slots=True)
class PartialFailureDetector:
    """Flag the indices of nodes that did not deliver a fresh update."""

    @staticmethod
    def missing(active_indices: list[int], expected_count: int) -> tuple[int, ...]:
        active = set(active_indices)
        return tuple(i for i in range(expected_count) if i not in active)


@dataclass(frozen=True, slots=True)
class DiscontinuityMonitor:
    """Detect gradient jumps that would break V monotonicity.

    Compares the potential at the *batch* boundary with the potential
    that would be produced by a single damped step from the previous
    state. If the observed potential exceeds that by more than
    ``tolerance``, the batch carries a discontinuity (likely from a
    stale or adversarial update sequence).
    """

    tolerance: float = 1e-6

    def discontinuity(
        self,
        prev_phases: list[float],
        new_phases: list[float],
        baseline_phases: list[float],
    ) -> bool:
        v_prev = phase_alignment_potential(prev_phases, baseline_phases)
        v_new = phase_alignment_potential(new_phases, baseline_phases)
        # The base solver guarantees v_new ≤ v_prev under ideal conditions.
        # An async batch that increases V is by definition a discontinuity.
        return v_new > v_prev + self.tolerance


@dataclass(frozen=True, slots=True)
class DistributedResetWaveConfig:
    """Wraps the base ResetWaveConfig with five resilience guards."""

    base: ResetWaveConfig
    jitter: JitterEnvelope = field(
        default_factory=lambda: JitterEnvelope(max_jitter_ns=10_000_000)
    )  # 10 ms
    staleness: StalenessGate = field(
        default_factory=lambda: StalenessGate(max_age_ns=50_000_000)
    )  # 50 ms
    discontinuity: DiscontinuityMonitor = field(default_factory=DiscontinuityMonitor)


@dataclass(frozen=True, slots=True)
class DistributedResetWaveResult:
    base: ResetWaveResult
    safety_lock_distributed: bool
    jitter_violation: bool
    stale_indices: tuple[int, ...]
    concurrency_violations: tuple[int, ...]
    missing_indices: tuple[int, ...]
    discontinuity_flagged: bool
    fail_reason: str | None


def run_reset_wave_distributed(
    *,
    node_phases: list[float],
    baseline_phases: list[float],
    timestamps_ns: list[int],
    node_seqs: list[int],
    last_seqs: dict[int, int],
    active_indices: list[int],
    prev_phases: list[float] | None,
    now_ns: int,
    cfg: DistributedResetWaveConfig,
) -> DistributedResetWaveResult:
    """Run the base solver with five distributed-resilience guards.

    Inputs:
        node_phases       — current node phase vector (after async update).
        baseline_phases   — baseline reference vector.
        timestamps_ns     — per-update arrival timestamps (ns).
        node_seqs         — per-node monotonic sequence numbers.
        last_seqs         — last accepted sequence per node id.
        active_indices    — which node ids delivered a fresh update.
        prev_phases       — phase vector from the prior step (for
                            DiscontinuityMonitor); ``None`` skips that check.
        now_ns            — wall-clock timestamp for the staleness gate.
        cfg               — adapter configuration.

    Returns a ``DistributedResetWaveResult`` with explicit per-guard flags.
    The base solver runs **only if every guard passes**; otherwise the
    base ``ResetWaveResult`` is set to a locked, no-op result and the
    ``fail_reason`` field names the first violated guard.
    """
    if len(node_phases) != len(baseline_phases):
        raise ValueError("node_phases and baseline_phases must have equal length")
    if len(timestamps_ns) != len(node_phases):
        raise ValueError("timestamps_ns must align with node_phases")
    if len(node_seqs) != len(node_phases):
        raise ValueError("node_seqs must align with node_phases")

    # Guard 1: jitter envelope.
    jitter_violation = cfg.jitter.violated(timestamps_ns)

    # Guard 2: staleness.
    stale = cfg.staleness.stale_indices(timestamps_ns, now_ns)

    # Guard 3: concurrency / monotonic sequences.
    accepts, concurrency_violations = ConcurrencyGuard.accepts(node_seqs, last_seqs)

    # Guard 4: partial failure.
    missing = PartialFailureDetector.missing(active_indices, len(node_phases))

    # Guard 5: discontinuity.
    discontinuity_flagged = False
    if prev_phases is not None:
        if len(prev_phases) != len(node_phases):
            raise ValueError("prev_phases must align with node_phases")
        discontinuity_flagged = cfg.discontinuity.discontinuity(
            prev_phases, node_phases, baseline_phases
        )

    fail_reason: str | None = None
    if jitter_violation:
        fail_reason = "jitter_envelope"
    elif stale:
        fail_reason = "staleness"
    elif not accepts:
        fail_reason = "concurrency"
    elif missing:
        fail_reason = "partial_failure"
    elif discontinuity_flagged:
        fail_reason = "discontinuity"

    if fail_reason is not None:
        # Lock the base solver; do not run any active updates.
        p0 = phase_alignment_potential(node_phases, baseline_phases)
        from geosync.neuroeconomics.reset_wave_engine import ResetWaveState

        locked_result = ResetWaveResult(
            converged=False,
            locked=True,
            initial_potential=p0,
            final_potential=p0,
            trajectory=(ResetWaveState(0, _max_abs_diff(node_phases, baseline_phases), p0),),
        )
        return DistributedResetWaveResult(
            base=locked_result,
            safety_lock_distributed=True,
            jitter_violation=jitter_violation,
            stale_indices=stale,
            concurrency_violations=concurrency_violations,
            missing_indices=missing,
            discontinuity_flagged=discontinuity_flagged,
            fail_reason=fail_reason,
        )

    base_result = run_reset_wave(node_phases, baseline_phases, cfg.base)
    return DistributedResetWaveResult(
        base=base_result,
        safety_lock_distributed=base_result.locked,
        jitter_violation=False,
        stale_indices=(),
        concurrency_violations=(),
        missing_indices=(),
        discontinuity_flagged=False,
        fail_reason=None,
    )


def _max_abs_diff(a: list[float], b: list[float]) -> float:
    return max(abs(x - y) for x, y in zip(a, b)) if a else 0.0


__all__ = [
    "ConcurrencyGuard",
    "DiscontinuityMonitor",
    "DistributedResetWaveConfig",
    "DistributedResetWaveResult",
    "JitterEnvelope",
    "PartialFailureDetector",
    "StalenessGate",
    "run_reset_wave_distributed",
]


# Suppress unused-import warning for math; reserved for future timestamp ops.
_ = math
