# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for causal_no_lookahead and provenance_identity laws."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.physics.causality import (
    CausalityError,
    _finite,
    assert_no_lookahead,
    assert_provenance_identity,
    causal_cone,
    provenance_hash,
    tombstone_violation,
)


def test_past_read_passes() -> None:
    """Positive witness: a read of a strictly-past source is admitted."""
    assert_no_lookahead(read_time=100.0, source_time=99.5) is None
    assert_no_lookahead(read_time=100.0, source_time=100.0) is None  # simultaneous allowed


def test_future_read_is_rejected() -> None:
    """Negative control: a read consuming a future source fails closed."""
    with pytest.raises(CausalityError, match="CAUSAL-LOOKAHEAD VIOLATED"):
        assert_no_lookahead(read_time=100.0, source_time=100.001)


def test_provenance_identity_holds() -> None:
    """Positive witness: identical bytes reproduce an identical provenance hash."""
    payload = b'{"bid": 1.2345, "ask": 1.2347}'
    expected = provenance_hash(payload)
    assert_provenance_identity(expected, payload) is None
    assert provenance_hash(payload) == expected  # deterministic


def test_rewritten_payload_breaks_provenance() -> None:
    """Negative control: a single rewritten byte breaks provenance identity."""
    payload = b'{"bid": 1.2345, "ask": 1.2347}'
    expected = provenance_hash(payload)
    rewritten = b'{"bid": 1.2399, "ask": 1.2347}'  # timestamp/price rewrite
    with pytest.raises(CausalityError, match="PROVENANCE VIOLATED"):
        assert_provenance_identity(expected, rewritten)


def test_causal_cone_selects_past_within_latency() -> None:
    """The past light-cone keeps only events in [t - max_latency, t]."""
    times = [90.0, 95.0, 99.0, 100.0, 101.0]
    cone = causal_cone(event_time=100.0, event_times=times, max_latency=5.0)
    assert cone == [1, 2, 3]  # 95, 99, 100 — not 90 (too old) nor 101 (future)


def test_violation_writes_tombstone_jsonl(tmp_path: Path) -> None:
    """A recorded violation appends a parseable JSONL tombstone record."""
    ledger = tmp_path / "tombstone_ledger.jsonl"
    tombstone_violation(
        ledger, law_id="causal_no_lookahead", detail="future read", context={"delta": 0.001}
    )
    tombstone_violation(ledger, law_id="provenance_identity", detail="byte rewrite")
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["law_id"] == "causal_no_lookahead"
    assert first["context"]["delta"] == 0.001


def test_negative_max_latency_is_rejected() -> None:
    """`not _finite(max_latency) or max_latency < 0.0` -- a finite negative fails.

    Rule-Zero note: this guards the LATENCY CONTRACT (a window cannot extend into
    negative time); it redefines no physical quantity. Under Or->And a finite but
    negative max_latency slips past and would build a backwards causal cone.
    """
    with pytest.raises(CausalityError, match="max_latency"):
        causal_cone(0.0, [0.0], max_latency=-1.0)


def test_lookahead_guard_rejects_a_single_non_finite_time() -> None:
    """`not _finite(read_time) or not _finite(source_time)` -- EITHER NaN fails.

    Under Or->And one finite time masks a NaN partner and the look-ahead check
    proceeds on a non-finite comparison.
    """
    import math

    with pytest.raises(CausalityError, match="finite"):
        assert_no_lookahead(math.nan, 0.0)
    with pytest.raises(CausalityError, match="finite"):
        assert_no_lookahead(0.0, math.nan)


def test_finite_helper_rejects_inf_and_nan() -> None:
    """`value == value and value not in (inf, -inf)` -- both halves required.

    Pins the finiteness primitive itself: NaN fails the first half, inf the
    second; under And->Or either would wrongly read as finite.
    """
    assert _finite(1.0) is True
    assert _finite(float("inf")) is False
    assert _finite(float("-inf")) is False
    assert _finite(float("nan")) is False
