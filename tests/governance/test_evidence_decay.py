# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/governance/evidence_decay.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tools.governance.evidence_decay import (
    POLICY_BY_CLASS,
    DecayClass,
    DecayStatus,
    EvidenceRecord,
    assess_decay,
)


def _record(
    *,
    decay_class: DecayClass = DecayClass.SECURITY_HIGH_DECAY,
    last_verified_at: datetime | None = None,
) -> EvidenceRecord:
    if last_verified_at is None:
        last_verified_at = datetime(2026, 4, 27, tzinfo=timezone.utc)
    return EvidenceRecord(
        evidence_id="ev-1",
        evidence_type="security-advisory",
        last_verified_at=last_verified_at,
        decay_class=decay_class,
        revalidate_command="python tools/research/validate_physics_2026_sources.py",
    )


def test_fresh_security_evidence_is_valid() -> None:
    record = _record(last_verified_at=datetime(2026, 4, 27, tzinfo=timezone.utc))
    witness = assess_decay(record, now=datetime(2026, 4, 28, tzinfo=timezone.utc))
    assert witness.status is DecayStatus.VALID


def test_security_evidence_eight_days_old_is_stale() -> None:
    """SECURITY_HIGH_DECAY: stale_after = 7d.

    This is the test the falsifier must break.
    """
    record = _record(last_verified_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    witness = assess_decay(record, now=datetime(2026, 4, 9, tzinfo=timezone.utc))
    assert witness.status is DecayStatus.STALE


def test_security_evidence_thirty_one_days_old_is_expired() -> None:
    """SECURITY_HIGH_DECAY: expired_after = 30d."""
    record = _record(last_verified_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    witness = assess_decay(record, now=datetime(2026, 5, 2, tzinfo=timezone.utc))
    assert witness.status is DecayStatus.EXPIRED


def test_market_data_one_day_old_is_valid_two_days_stale_eight_days_expired() -> None:
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    record = _record(
        decay_class=DecayClass.MARKET_DATA_HIGH_DECAY,
        last_verified_at=base,
    )
    assert assess_decay(record, now=base + timedelta(hours=12)).status is DecayStatus.VALID
    assert assess_decay(record, now=base + timedelta(days=2)).status is DecayStatus.STALE
    assert assess_decay(record, now=base + timedelta(days=8)).status is DecayStatus.EXPIRED


def test_ci_state_immediate_decay_thresholds() -> None:
    base = datetime(2026, 4, 27, 12, tzinfo=timezone.utc)
    record = _record(
        decay_class=DecayClass.CI_STATE_IMMEDIATE_DECAY,
        last_verified_at=base,
    )
    assert assess_decay(record, now=base + timedelta(minutes=30)).status is DecayStatus.VALID
    assert assess_decay(record, now=base + timedelta(hours=2)).status is DecayStatus.STALE
    assert assess_decay(record, now=base + timedelta(hours=25)).status is DecayStatus.EXPIRED


def test_static_low_decay_long_thresholds() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    record = _record(
        decay_class=DecayClass.STATIC_LOW_DECAY,
        last_verified_at=base,
    )
    assert assess_decay(record, now=base + timedelta(days=100)).status is DecayStatus.VALID
    assert assess_decay(record, now=base + timedelta(days=200)).status is DecayStatus.STALE
    assert assess_decay(record, now=base + timedelta(days=800)).status is DecayStatus.EXPIRED


def test_dependency_medium_decay_thresholds() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    record = _record(
        decay_class=DecayClass.DEPENDENCY_MEDIUM_DECAY,
        last_verified_at=base,
    )
    assert assess_decay(record, now=base + timedelta(days=10)).status is DecayStatus.VALID
    assert assess_decay(record, now=base + timedelta(days=45)).status is DecayStatus.STALE
    assert assess_decay(record, now=base + timedelta(days=120)).status is DecayStatus.EXPIRED


def test_future_last_verified_returns_revalidation_required() -> None:
    """Clock-drift defence: last_verified_at in the future → revalidate."""
    record = _record(last_verified_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    witness = assess_decay(record, now=datetime(2026, 4, 27, tzinfo=timezone.utc))
    assert witness.status is DecayStatus.REVALIDATION_REQUIRED


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceRecord(
            evidence_id="x",
            evidence_type="t",
            last_verified_at=datetime(2026, 4, 27),  # naive
            decay_class=DecayClass.STATIC_LOW_DECAY,
            revalidate_command="echo refresh",
        )


def test_naive_now_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_decay(_record(), now=datetime(2026, 4, 27))  # naive


def test_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="evidence_id"):
        EvidenceRecord(
            evidence_id="",
            evidence_type="t",
            last_verified_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
            decay_class=DecayClass.STATIC_LOW_DECAY,
            revalidate_command="echo refresh",
        )


def test_empty_revalidate_command_rejected() -> None:
    with pytest.raises(ValueError, match="revalidate_command"):
        EvidenceRecord(
            evidence_id="x",
            evidence_type="t",
            last_verified_at=datetime(2026, 4, 27, tzinfo=timezone.utc),
            decay_class=DecayClass.STATIC_LOW_DECAY,
            revalidate_command="",
        )


def test_policy_invariant_expired_greater_than_stale() -> None:
    for cls, policy in POLICY_BY_CLASS.items():
        assert policy.expired_after > policy.stale_after, cls


def test_witness_is_frozen() -> None:
    record = _record()
    witness = assess_decay(record, now=datetime(2026, 4, 28, tzinfo=timezone.utc))
    with pytest.raises(Exception):  # noqa: B017
        witness.status = DecayStatus.EXPIRED  # type: ignore[misc]


def test_witness_evidence_fields_immutable() -> None:
    from collections.abc import Mapping

    record = _record()
    witness = assess_decay(record, now=datetime(2026, 4, 28, tzinfo=timezone.utc))
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_falsifier_text_present() -> None:
    record = _record()
    witness = assess_decay(record, now=datetime(2026, 4, 28, tzinfo=timezone.utc))
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


def test_witness_carries_no_prediction_class_field() -> None:
    from tools.governance.evidence_decay import DecayWitness

    forbidden = {"prediction", "signal", "forecast", "score", "confidence"}
    fields = set(DecayWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_deterministic_at_same_inputs() -> None:
    record = _record()
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    a = assess_decay(record, now=now)
    b = assess_decay(record, now=now)
    assert a == b
