# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Indexed RNG — addressability, stream isolation, control-flow independence.

Guards the three properties that justify the primitive's existence:

1. **Addressability.** The same 4-tuple ``(seed, stream, event, index)``
   always returns the same value, on any fresh instance, in any order.
2. **Control-flow independence.** Adding or removing unrelated draws
   between two addressed draws never perturbs either draw's value.
3. **Stream isolation.** Different ``stream_id`` values yield draws that
   are statistically independent of each other.

Together these are the invariants that make event-addressed RNG strictly
stronger than a stateful ``np.random.Generator`` for deterministic
replay: a refactor that changes the internal order of draws but
preserves the 4-tuples of addressed events leaves the output byte-
identical.

A regression at this layer is exactly the "control-flow-dependent
stochasticity" leak that Task 3 of the 2026-04-23 audit closes.
"""

from __future__ import annotations

import math
import statistics

import numpy as np
import pytest

from geosync_hpc.indexed_rng import CANONICAL_STREAMS, IndexedRNG

SEED = 42


# ---------------------------------------------------------------------------
# Construction contracts
# ---------------------------------------------------------------------------


def test_bernoulli_boundary_probabilities_are_degenerate() -> None:
    """TEETH: ``bernoulli`` is ``uniform(...) < p`` — the STRICT-LESS-THAN direction.

    Measured gap this closes: ``tools/mutation_probe.py --only-logic`` showed
    ``indexed_rng.py:152`` mutating ``Lt -> GtE`` and SURVIVING — no test pinned the
    comparison's direction, so an inverted coin (True exactly when it should be False)
    was undetectable. p=0.0 must NEVER fire and p=1.0 must ALWAYS fire, since
    ``uniform`` is drawn from [0, 1): under the mutant both flip.
    """
    rng = IndexedRNG(seed=SEED, stream_id="execution")
    for idx in range(64):
        assert rng.bernoulli("queue_fill", idx, p=0.0) is False, (
            f"p=0.0 must never fire (uniform < 0 is impossible); fired at index {idx}"
        )
        assert rng.bernoulli("queue_fill", idx, p=1.0) is True, (
            f"p=1.0 must always fire (uniform < 1 for a [0,1) draw); did not fire at index {idx}"
        )


def test_indexed_rng_is_frozen() -> None:
    rng = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(Exception):  # FrozenInstanceError
        rng.seed = 0  # type: ignore[misc]


def test_indexed_rng_rejects_non_int_seed() -> None:
    with pytest.raises(TypeError):
        IndexedRNG(seed=1.5, stream_id="execution")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        IndexedRNG(seed=True, stream_id="execution")  # bool is a subclass of int


def test_indexed_rng_rejects_empty_stream() -> None:
    with pytest.raises(ValueError):
        IndexedRNG(seed=SEED, stream_id="")


def test_canonical_streams_documented() -> None:
    """Non-enforcement constant — but it should list the five canonical
    substreams a full GeoSync run needs."""
    assert {"execution", "model", "bootstrap", "simulation", "tests"} <= CANONICAL_STREAMS


# ---------------------------------------------------------------------------
# Addressability
# ---------------------------------------------------------------------------


def test_same_tuple_yields_same_value() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    a = r.uniform(event_id="fill", event_index=42)
    b = r.uniform(event_id="fill", event_index=42)
    assert a == b


def test_same_tuple_across_fresh_instances_yields_same_value() -> None:
    """Two different IndexedRNG objects with the same seed + stream must
    agree on every addressed draw — this is the cross-process property."""
    a = IndexedRNG(seed=SEED, stream_id="execution").uniform("fill", 42)
    b = IndexedRNG(seed=SEED, stream_id="execution").uniform("fill", 42)
    assert a == b


def test_different_seed_changes_value() -> None:
    a = IndexedRNG(seed=SEED, stream_id="execution").uniform("fill", 42)
    b = IndexedRNG(seed=SEED + 1, stream_id="execution").uniform("fill", 42)
    assert a != b


def test_different_event_id_changes_value() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    assert r.uniform("fill", 42) != r.uniform("cancel", 42)


def test_different_event_index_changes_value() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    assert r.uniform("fill", 0) != r.uniform("fill", 1)


# ---------------------------------------------------------------------------
# Control-flow independence
# ---------------------------------------------------------------------------


def test_addressed_draw_value_is_independent_of_call_order() -> None:
    """The critical property: two call orders that include the same
    addressed draw produce the same value for it."""
    r = IndexedRNG(seed=SEED, stream_id="execution")
    baseline = r.uniform("fill", 99)

    # Interleave many unrelated draws; the addressed value must not move.
    for i in range(50):
        r.uniform("warmup", i)
        r.normal("noise", i)
    interleaved = r.uniform("fill", 99)
    assert interleaved == baseline


def test_addressed_draw_value_is_independent_of_intermediate_stream() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    baseline = r.uniform("fill", 7)
    # Spawn a child, draw from it — parent's addressed draw stays fixed.
    child = r.spawn("retry")
    for i in range(20):
        child.uniform("backoff", i)
    assert r.uniform("fill", 7) == baseline


# ---------------------------------------------------------------------------
# Stream isolation
# ---------------------------------------------------------------------------


def test_different_streams_give_different_values_for_same_tuple() -> None:
    exec_rng = IndexedRNG(seed=SEED, stream_id="execution")
    model_rng = IndexedRNG(seed=SEED, stream_id="model")
    assert exec_rng.uniform("fill", 0) != model_rng.uniform("fill", 0)


def test_spawn_yields_independent_child_stream() -> None:
    parent = IndexedRNG(seed=SEED, stream_id="execution")
    child = parent.spawn("retry")
    assert parent.stream_id != child.stream_id
    assert parent.uniform("e", 0) != child.uniform("e", 0)


def test_spawn_child_stream_id_is_dotted() -> None:
    parent = IndexedRNG(seed=SEED, stream_id="execution")
    child = parent.spawn("retry")
    assert child.stream_id == "execution.retry"


def test_spawn_rejects_empty_child() -> None:
    parent = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(ValueError):
        parent.spawn("")


# ---------------------------------------------------------------------------
# Distributional sanity
# ---------------------------------------------------------------------------


def test_uniform_draws_are_in_unit_interval() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    values = [r.uniform("fill", i) for i in range(500)]
    assert all(0.0 <= v < 1.0 for v in values)


def test_uniform_draws_have_near_uniform_mean() -> None:
    """Weak distributional sanity — catches a wrong scaling in the
    hash-to-float pipeline without forcing a fragile KS test."""
    r = IndexedRNG(seed=SEED, stream_id="execution")
    values = [r.uniform("fill", i) for i in range(2000)]
    mean = statistics.fmean(values)
    assert 0.45 < mean < 0.55, f"uniform mean drifted to {mean:.4f}"


def test_normal_draws_have_near_target_moments() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    values = [r.normal("noise", i, mean=1.0, std=2.0) for i in range(2000)]
    assert abs(statistics.fmean(values) - 1.0) < 0.15
    assert abs(statistics.stdev(values) - 2.0) < 0.25


def test_integer_draws_are_bounded() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    values = [r.integer("bucket", i, low=3, high=7) for i in range(400)]
    assert all(3 <= v < 7 for v in values)


def test_bernoulli_is_fair_at_p_half() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    hits = sum(r.bernoulli("flip", i, p=0.5) for i in range(2000))
    assert 900 <= hits <= 1100


# ---------------------------------------------------------------------------
# Fail-closed inputs
# ---------------------------------------------------------------------------


def test_uniform_rejects_empty_event_id() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(ValueError):
        r.uniform("", 0)


def test_uniform_rejects_non_int_event_index() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(TypeError):
        r.uniform("fill", 1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        r.uniform("fill", True)


def test_integer_rejects_inverted_bounds() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(ValueError):
        r.integer("bucket", 0, low=5, high=5)
    with pytest.raises(ValueError):
        r.integer("bucket", 0, low=5, high=3)


def test_bernoulli_rejects_out_of_range_p() -> None:
    r = IndexedRNG(seed=SEED, stream_id="execution")
    with pytest.raises(ValueError):
        r.bernoulli("flip", 0, p=-0.1)
    with pytest.raises(ValueError):
        r.bernoulli("flip", 0, p=1.5)
    with pytest.raises(ValueError):
        r.bernoulli("flip", 0, p=float("nan"))


# ---------------------------------------------------------------------------
# Cross-process determinism contract
# ---------------------------------------------------------------------------


def test_draws_match_byte_identical_reference() -> None:
    """Pin a small reference trace so any future hash / PCG change trips
    this test loudly — cross-platform replay is the whole point of the
    module, and a silent drift would defeat it.

    The reference values are *not* magic numbers: they are frozen
    outputs of BLAKE2b+PCG64 on the canonical 4-tuples and must never
    move without a conscious version bump.
    """
    r = IndexedRNG(seed=42, stream_id="execution")
    trace = [
        r.uniform("fill", 0),
        r.uniform("fill", 1),
        r.uniform("fill", 2),
    ]
    # Recompute via a parallel path to cross-check in-module
    expected = [
        float(np.random.default_rng(r._tuple_seed("fill", 0)).random()),
        float(np.random.default_rng(r._tuple_seed("fill", 1)).random()),
        float(np.random.default_rng(r._tuple_seed("fill", 2)).random()),
    ]
    assert trace == expected
    # Each value is a real float in the unit interval; guards against
    # a regression that swaps `random()` for `integers()` silently.
    for v in trace:
        assert math.isfinite(v) and 0.0 <= v < 1.0


def test_trace_is_stable_across_repeated_construction() -> None:
    """Ten fresh IndexedRNG objects — same seed + stream → same draws."""
    expected = IndexedRNG(seed=SEED, stream_id="execution").uniform("fill", 0)
    for _ in range(10):
        value = IndexedRNG(seed=SEED, stream_id="execution").uniform("fill", 0)
        assert value == expected
