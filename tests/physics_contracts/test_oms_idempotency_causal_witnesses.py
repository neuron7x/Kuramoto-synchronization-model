# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the two OMS lifecycle laws in the catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the pure platform primitives that implement the same physics,
without importing the forbidden ``execution/`` path (the catalog ``source`` is
``execution/oms.py``, but the law itself is a property of the idempotency and
causal-ordering machinery the platform exposes purely). Two previously-
unwitnessed catalog laws gain witnesses:

* ``oms.idempotency`` (INV-OMS2; Bernstein & Newcomer, exactly-once messaging) —
  ``apply(o, o, ..., o) ≡ apply(o)``: a deduplicated operation collapses to one
  record. Witnessed on ``core.idempotency`` — the same dedupe fields yield the
  same ``IdempotencyKey`` and replaying that key through an
  ``IdempotencyCoordinator`` returns the cached outcome with no second record.
* ``oms.causal_order`` (INV-OMS3; Lamport 1978, happens-before) — per-episode
  event records carry a strictly increasing sequence and an intact hash chain,
  so a consumer can always reconstruct the causal timeline ``t_{k+1} > t_k``.
  Witnessed on ``geosync_hpc.control.control_episode`` — the pure, append-only,
  monotonic-seq, hash-chained event log.

Nothing here is a market claim. These are exactly-once / causal-ordering facts
about the deterministic platform primitives.
"""

from __future__ import annotations

import random

from core.idempotency.keys import IdempotencyKeyFactory
from core.idempotency.operations import IdempotencyCoordinator
from geosync_hpc.control import (
    ExpectedResultModel,
    ObservedActionResult,
    compute_error,
    dispatch_action,
    persist_memory,
    receive_afferentation,
    render_decision,
    seal_model,
    start_episode,
    verify_chain,
)
from physics_contracts.law import law

# Determinism anchors. Replay counts and ordering comparisons are exact integers,
# so the witnessed bounds are strict — no numerical tolerance is admissible.
N_ORDERS = 200
N_REPLAYS = 5
N_PHASES = 7
SEED = 0


def _frozen_clock() -> float:
    """A constant monotonic reading so no TTL purge perturbs the replay proof."""
    return 0.0


@law("oms.idempotency", n_orders=N_ORDERS, n_replays=N_REPLAYS, seed=SEED)
def test_duplicate_operation_key_applies_exactly_once() -> None:
    """INV-OMS2: replaying one idempotency key changes state exactly once.

    For each of many independent orders the dedupe fields are turned into an
    ``IdempotencyKey`` and registered, completed, then replayed ``n_replays``
    times. The same fields must yield the same key; the first registration must
    not be cached while every replay must be served from cache with the identical
    operation id and result — ``apply(o, o, ..., o) ≡ apply(o)``. The witness
    counts any non-deterministic key, any replay that is not cached, and finally
    requires the coordinator to hold exactly one record per order (no
    double-booking).
    """
    factory = IdempotencyKeyFactory()
    coordinator: IdempotencyCoordinator[dict[str, int]] = IdempotencyCoordinator(
        clock=_frozen_clock
    )
    rng = random.Random(SEED)
    nondeterministic_keys = 0
    uncached_replays = 0
    for index in range(N_ORDERS):
        dedupe_fields = {"order_id": index, "symbol": f"INSTR-{index % 7}", "qty": rng.randint(1, 1000)}
        key = factory.build(service="oms", operation="submit", dedupe_fields=dedupe_fields)
        rebuilt = factory.build(service="oms", operation="submit", dedupe_fields=dedupe_fields)
        if rebuilt.operation_id != key.operation_id or rebuilt.fingerprint != key.fingerprint:
            nondeterministic_keys += 1
        first = coordinator.register_attempt(key)
        coordinator.complete_success(key, {"booked": index})
        if first.from_cache:
            uncached_replays += 1
        for _ in range(N_REPLAYS - 1):
            replay = coordinator.register_attempt(key)
            if not replay.from_cache or replay.operation_id != first.operation_id:
                uncached_replays += 1
    distinct_records = coordinator.metrics()["active_operations"]
    assert nondeterministic_keys == 0, (
        "INV-OMS2 violated: observed nondeterministic keys = "
        f"{nondeterministic_keys} must be 0 over n_orders={N_ORDERS} with seed={SEED}; "
        "identical dedupe fields must build the same idempotency key for replay safety"
    )
    assert uncached_replays == 0, (
        "INV-OMS2 violated: observed uncached/divergent replays = "
        f"{uncached_replays} must be 0 over n_orders={N_ORDERS} with n_replays={N_REPLAYS}, "
        f"seed={SEED}; every replay of one key must return the cached outcome unchanged"
    )
    assert distinct_records == N_ORDERS, (
        "INV-OMS2 violated: observed distinct coordinator records = "
        f"{distinct_records} must equal n_orders={N_ORDERS} with n_replays={N_REPLAYS}, "
        f"seed={SEED}; a duplicated key must collapse to one record, not double-book"
    )


@law("oms.causal_order", n_orders=N_ORDERS, n_phases=N_PHASES, seed=SEED)
def test_episode_event_log_is_causally_ordered() -> None:
    """INV-OMS3: per-episode event sequence is strictly increasing and chained.

    For each of many independent episodes the full seven-phase control chain is
    driven with strictly increasing, randomly spaced sequence numbers. The
    witness requires that within every episode the recorded sequence is strictly
    increasing and the hash chain verifies — the happens-before relation
    ``t_{k+1} > t_k`` a consumer relies on to reconstruct event order. It counts
    any sequence regression and any broken chain.
    """
    rng = random.Random(SEED)
    sequence_regressions = 0
    broken_chains = 0
    for index in range(N_ORDERS):
        cursor = 0
        seqs = []
        for _ in range(N_PHASES):
            cursor += rng.randint(1, 3)
            seqs.append(cursor)
        intent_seq, model_seq, action_seq, observed_seq, error_seq, decision_seq, memory_seq = seqs
        expected = ExpectedResultModel(
            action_id=f"a-{index}",
            action_type="trade",
            expected_result=(1.0, 0.0),
            expected_result_variance=None,
            context_signature=(0.5, 0.5),
            model_created_seq=model_seq,
            action_started_seq=action_seq,
            error_threshold=0.1,
            rollback_threshold=0.5,
        )
        observed = ObservedActionResult(
            action_id=f"a-{index}",
            observed_seq=observed_seq,
            observed_result=(1.0, 0.0),
        )
        episode = start_episode(f"ep-{index:04d}", b"intent", intent_seq)
        episode = seal_model(episode, expected, model_seq)
        episode = dispatch_action(episode, b"action", action_seq)
        episode = receive_afferentation(episode, observed, observed_seq)
        episode = compute_error(episode, error_seq)
        episode = render_decision(episode, decision_seq)
        episode = persist_memory(episode, memory_seq)
        records = episode.records
        for position in range(len(records) - 1):
            if records[position + 1].seq <= records[position].seq:
                sequence_regressions += 1
        if not verify_chain(episode):
            broken_chains += 1
    assert sequence_regressions == 0, (
        "INV-OMS3 violated: observed sequence regressions = "
        f"{sequence_regressions} must be 0 over n_orders={N_ORDERS} with "
        f"n_phases={N_PHASES}, seed={SEED}; per-episode event sequence must be "
        "strictly increasing so causal order t_{k+1} > t_k holds"
    )
    assert broken_chains == 0, (
        "INV-OMS3 violated: observed broken hash chains = "
        f"{broken_chains} must be 0 over n_orders={N_ORDERS} with n_phases={N_PHASES}, "
        f"seed={SEED}; the event hash chain must verify so event order is tamper-evident"
    )
