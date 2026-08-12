# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial async-failure tests for the distributed reset-wave adapter.

Each test injects one async failure mode named in
``geosync/neuroeconomics/reset_wave_distributed.py`` and asserts that
the adapter either fires the safety lock with the correct
``fail_reason`` OR (for benign cases) lets the base solver run.

There are five failure modes covered, plus an end-to-end happy-path
test that confirms the guards do not over-trigger when inputs are
clean.

Inputs are passed via :class:`AsyncInputs`, a frozen dataclass — this
keeps the kwargs strongly typed (no ``# type: ignore`` smell) while
remaining mutable-by-replace via ``dataclasses.replace``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from geosync.neuroeconomics.reset_wave_distributed import (
    ConcurrencyGuard,
    DiscontinuityMonitor,
    DistributedResetWaveConfig,
    DistributedResetWaveResult,
    JitterEnvelope,
    PartialFailureDetector,
    StalenessGate,
    run_reset_wave_distributed,
)
from geosync.neuroeconomics.reset_wave_engine import ResetWaveConfig


@dataclass(frozen=True, slots=True)
class AsyncInputs:
    """Strongly-typed bundle for ``run_reset_wave_distributed`` test inputs."""

    node_phases: list[float]
    baseline_phases: list[float]
    timestamps_ns: list[int]
    node_seqs: list[int]
    last_seqs: dict[int, int]
    active_indices: list[int]
    prev_phases: list[float] | None
    now_ns: int
    cfg: DistributedResetWaveConfig


def _clean_inputs() -> AsyncInputs:
    """Inputs that pass every guard so the base solver actually runs."""
    return AsyncInputs(
        node_phases=[0.05, -0.05, 0.04],
        baseline_phases=[0.0, 0.0, 0.0],
        timestamps_ns=[1_000_000_000, 1_000_000_500, 1_000_001_000],
        node_seqs=[10, 11, 12],
        last_seqs={0: 9, 1: 10, 2: 11},
        active_indices=[0, 1, 2],
        prev_phases=[0.06, -0.06, 0.05],
        now_ns=1_000_002_000,
        cfg=DistributedResetWaveConfig(
            base=ResetWaveConfig(coupling_gain=0.8, dt=0.05),
            jitter=JitterEnvelope(max_jitter_ns=10_000_000),
            staleness=StalenessGate(max_age_ns=50_000_000),
            discontinuity=DiscontinuityMonitor(tolerance=1e-3),
        ),
    )


def _run(inputs: AsyncInputs) -> DistributedResetWaveResult:
    return run_reset_wave_distributed(
        node_phases=inputs.node_phases,
        baseline_phases=inputs.baseline_phases,
        timestamps_ns=inputs.timestamps_ns,
        node_seqs=inputs.node_seqs,
        last_seqs=inputs.last_seqs,
        active_indices=inputs.active_indices,
        prev_phases=inputs.prev_phases,
        now_ns=inputs.now_ns,
        cfg=inputs.cfg,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_distributed_clean_inputs_run_base_solver() -> None:
    out = _run(_clean_inputs())
    assert out.fail_reason is None
    assert not out.safety_lock_distributed
    assert out.base.final_potential <= out.base.initial_potential


# ---------------------------------------------------------------------------
# Failure mode 1 — clock-jitter envelope
# ---------------------------------------------------------------------------


def test_distributed_jitter_envelope_violation_locks() -> None:
    inputs = replace(
        _clean_inputs(),
        # Last node arrives 100 ms after the first — exceeds 10 ms envelope.
        timestamps_ns=[1_000_000_000, 1_000_001_000, 1_100_000_000],
    )
    out = _run(inputs)
    assert out.fail_reason == "jitter_envelope"
    assert out.jitter_violation
    assert out.safety_lock_distributed
    assert out.base.final_potential == out.base.initial_potential


# ---------------------------------------------------------------------------
# Failure mode 2 — staleness gate
# ---------------------------------------------------------------------------


def test_distributed_staleness_gate_locks_on_old_update() -> None:
    inputs = replace(
        _clean_inputs(),
        # ``now_ns`` is 100 ms after the youngest update — exceeds 50 ms staleness.
        now_ns=1_100_000_000,
    )
    out = _run(inputs)
    assert out.fail_reason == "staleness"
    assert out.stale_indices == (0, 1, 2)
    assert out.safety_lock_distributed


# ---------------------------------------------------------------------------
# Failure mode 3 — concurrency / out-of-order sequences
# ---------------------------------------------------------------------------


def test_distributed_concurrency_guard_rejects_replayed_seq() -> None:
    inputs = replace(
        _clean_inputs(),
        # Node 1's new seq (5) is below the last accepted (10) — replay attack.
        node_seqs=[10, 5, 12],
        last_seqs={0: 9, 1: 10, 2: 11},
    )
    out = _run(inputs)
    assert out.fail_reason == "concurrency"
    assert 1 in out.concurrency_violations
    assert out.safety_lock_distributed


def test_concurrency_guard_pure_function_accepts_clean() -> None:
    accepts, rejected = ConcurrencyGuard.accepts([10, 11, 12], {0: 9, 1: 10, 2: 11})
    assert accepts
    assert rejected == ()


def test_concurrency_guard_pure_function_rejects_equal_seq() -> None:
    accepts, rejected = ConcurrencyGuard.accepts([10, 10, 12], {0: 9, 1: 10, 2: 11})
    assert not accepts
    assert 1 in rejected


# ---------------------------------------------------------------------------
# Failure mode 4 — partial node failure
# ---------------------------------------------------------------------------


def test_distributed_partial_failure_detected() -> None:
    inputs = replace(
        _clean_inputs(),
        # Only node 0 and node 2 delivered — node 1 missing.
        active_indices=[0, 2],
    )
    out = _run(inputs)
    assert out.fail_reason == "partial_failure"
    assert 1 in out.missing_indices
    assert out.safety_lock_distributed


def test_partial_failure_detector_pure_function() -> None:
    assert PartialFailureDetector.missing([0, 2], 3) == (1,)
    assert PartialFailureDetector.missing([0, 1, 2], 3) == ()
    assert PartialFailureDetector.missing([], 3) == (0, 1, 2)


# ---------------------------------------------------------------------------
# Failure mode 5 — discontinuity (re-entry / adversarial sequence)
# ---------------------------------------------------------------------------


def test_distributed_discontinuity_monitor_flags_re_entry() -> None:
    inputs = replace(
        _clean_inputs(),
        # Adversarial: node phases jumped *away* from baseline since prev_phases.
        prev_phases=[0.01, -0.01, 0.01],
    )
    out = _run(inputs)
    assert out.fail_reason == "discontinuity"
    assert out.discontinuity_flagged
    assert out.safety_lock_distributed
    # Critical: under lock, V must be exactly preserved.
    assert out.base.final_potential == out.base.initial_potential


def test_discontinuity_monitor_pure_function_clean() -> None:
    monitor = DiscontinuityMonitor()
    flagged = monitor.discontinuity(
        prev_phases=[0.2, -0.2],
        new_phases=[0.05, -0.05],
        baseline_phases=[0.0, 0.0],
    )
    assert not flagged


def test_discontinuity_monitor_pure_function_adversarial() -> None:
    monitor = DiscontinuityMonitor()
    flagged = monitor.discontinuity(
        prev_phases=[0.05, -0.05],
        new_phases=[0.5, -0.5],
        baseline_phases=[0.0, 0.0],
    )
    assert flagged


# ---------------------------------------------------------------------------
# Determinism — same async input ⇒ same output
# ---------------------------------------------------------------------------


def test_distributed_adapter_is_deterministic() -> None:
    a = _run(_clean_inputs())
    b = _run(_clean_inputs())
    assert a == b


# ---------------------------------------------------------------------------
# Contract validation — input shape
# ---------------------------------------------------------------------------


def test_distributed_adapter_rejects_mismatched_lengths() -> None:
    inputs = replace(_clean_inputs(), timestamps_ns=[1_000_000_000])
    with pytest.raises(ValueError, match="timestamps_ns"):
        _run(inputs)


def test_distributed_adapter_rejects_mismatched_seqs() -> None:
    inputs = replace(_clean_inputs(), node_seqs=[10, 11])
    with pytest.raises(ValueError, match="node_seqs"):
        _run(inputs)


def test_distributed_adapter_rejects_mismatched_prev_phases() -> None:
    inputs = replace(_clean_inputs(), prev_phases=[0.01])
    with pytest.raises(ValueError, match="prev_phases"):
        _run(inputs)
