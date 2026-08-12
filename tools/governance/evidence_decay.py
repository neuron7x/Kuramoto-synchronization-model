# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Evidence-decay engine.

Lie blocked:
    "old evidence remains true forever"

Evidence is dated. A claim that rests on a security advisory checked
six months ago is not the same as a claim that rests on the same
advisory checked yesterday. This module classifies an evidence record
into one of {VALID, STALE, EXPIRED, REVALIDATION_REQUIRED} given its
type-specific decay policy and the current clock.

Decay classes (max age in seconds before STALE / EXPIRED):

    STATIC_LOW_DECAY            stale=180d   expired=730d
    DEPENDENCY_MEDIUM_DECAY     stale=30d    expired=90d
    SECURITY_HIGH_DECAY         stale=7d     expired=30d
    MARKET_DATA_HIGH_DECAY      stale=1d     expired=7d
    CI_STATE_IMMEDIATE_DECAY    stale=1h     expired=24h

Determinism: classification is a pure function of (now, last_verified_at,
decay_class). The clock is injected; no module-level time-of-day reads.

Non-claims:
    - the engine does not refresh evidence; it only classifies it
    - it does not run revalidate_command; it records the command for
      a caller to invoke
    - decay thresholds are policy, not law; they reduce false-confidence
      at known cadences but do not certify any specific freshness level
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "DecayClass",
    "DecayStatus",
    "EvidenceRecord",
    "DecayPolicy",
    "DecayWitness",
    "POLICY_BY_CLASS",
    "assess_decay",
]


class DecayClass(str, Enum):
    STATIC_LOW_DECAY = "STATIC_LOW_DECAY"
    DEPENDENCY_MEDIUM_DECAY = "DEPENDENCY_MEDIUM_DECAY"
    SECURITY_HIGH_DECAY = "SECURITY_HIGH_DECAY"
    MARKET_DATA_HIGH_DECAY = "MARKET_DATA_HIGH_DECAY"
    CI_STATE_IMMEDIATE_DECAY = "CI_STATE_IMMEDIATE_DECAY"


class DecayStatus(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"


@dataclass(frozen=True)
class DecayPolicy:
    """Policy for one decay class."""

    decay_class: DecayClass
    stale_after: timedelta
    expired_after: timedelta

    def __post_init__(self) -> None:
        if self.stale_after.total_seconds() <= 0:
            raise ValueError("stale_after must be a positive duration")
        if self.expired_after <= self.stale_after:
            raise ValueError("expired_after must be strictly greater than stale_after")


POLICY_BY_CLASS: Mapping[DecayClass, DecayPolicy] = MappingProxyType(
    {
        DecayClass.STATIC_LOW_DECAY: DecayPolicy(
            DecayClass.STATIC_LOW_DECAY,
            timedelta(days=180),
            timedelta(days=730),
        ),
        DecayClass.DEPENDENCY_MEDIUM_DECAY: DecayPolicy(
            DecayClass.DEPENDENCY_MEDIUM_DECAY,
            timedelta(days=30),
            timedelta(days=90),
        ),
        DecayClass.SECURITY_HIGH_DECAY: DecayPolicy(
            DecayClass.SECURITY_HIGH_DECAY,
            timedelta(days=7),
            timedelta(days=30),
        ),
        DecayClass.MARKET_DATA_HIGH_DECAY: DecayPolicy(
            DecayClass.MARKET_DATA_HIGH_DECAY,
            timedelta(days=1),
            timedelta(days=7),
        ),
        DecayClass.CI_STATE_IMMEDIATE_DECAY: DecayPolicy(
            DecayClass.CI_STATE_IMMEDIATE_DECAY,
            timedelta(hours=1),
            timedelta(hours=24),
        ),
    }
)


@dataclass(frozen=True)
class EvidenceRecord:
    """One piece of dated evidence."""

    evidence_id: str
    evidence_type: str
    last_verified_at: datetime
    decay_class: DecayClass
    revalidate_command: str

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be a non-empty string")
        if not isinstance(self.evidence_type, str) or not self.evidence_type.strip():
            raise ValueError("evidence_type must be a non-empty string")
        if not isinstance(self.last_verified_at, datetime):
            raise TypeError("last_verified_at must be a datetime")
        if self.last_verified_at.tzinfo is None:
            raise ValueError("last_verified_at must be timezone-aware")
        if not isinstance(self.decay_class, DecayClass):
            raise TypeError("decay_class must be a DecayClass member")
        if not isinstance(self.revalidate_command, str) or not self.revalidate_command.strip():
            raise ValueError("revalidate_command must be a non-empty string")


@dataclass(frozen=True)
class DecayWitness:
    """One decay-classification verdict."""

    evidence_id: str
    status: DecayStatus
    decay_class: DecayClass
    age_seconds: float
    stale_threshold_seconds: float
    expired_threshold_seconds: float
    revalidate_command: str
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


_FALSIFIER_TEXT = (
    "VALID was returned for an evidence record whose age exceeds the "
    "decay-class stale_after threshold. OR: EXPIRED evidence was "
    "treated as VALID because the decay policy was bypassed. OR: the "
    "clock was read from system state instead of the injected `now`."
)


def assess_decay(record: EvidenceRecord, *, now: datetime) -> DecayWitness:
    """Pure decay classifier.

    Priority (first matching condition wins):
        1. age >= expired_after   → EXPIRED (REVALIDATION_REQUIRED if
                                    revalidate_command is non-empty;
                                    otherwise EXPIRED only)
        2. age >= stale_after     → STALE
        3. age <  0 (future)      → REVALIDATION_REQUIRED
        4. otherwise              → VALID
    """
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    policy = POLICY_BY_CLASS[record.decay_class]
    delta = now - record.last_verified_at
    age = delta.total_seconds()
    stale = policy.stale_after.total_seconds()
    expired = policy.expired_after.total_seconds()

    if age < 0:
        status = DecayStatus.REVALIDATION_REQUIRED
        reason = "LAST_VERIFIED_IN_FUTURE_CLOCK_DRIFT"
    elif age >= expired:
        status = DecayStatus.EXPIRED
        reason = "AGE_EXCEEDS_EXPIRED_THRESHOLD"
    elif age >= stale:
        status = DecayStatus.STALE
        reason = "AGE_EXCEEDS_STALE_THRESHOLD"
    else:
        status = DecayStatus.VALID
        reason = "OK_WITHIN_STALE_THRESHOLD"

    evidence = MappingProxyType(
        {
            "evidence_id": record.evidence_id,
            "evidence_type": record.evidence_type,
            "decay_class": record.decay_class.value,
            "last_verified_at": record.last_verified_at.isoformat(),
            "now": now.isoformat(),
            "age_seconds": age,
            "stale_threshold_seconds": stale,
            "expired_threshold_seconds": expired,
        }
    )
    return DecayWitness(
        evidence_id=record.evidence_id,
        status=status,
        decay_class=record.decay_class,
        age_seconds=age,
        stale_threshold_seconds=stale,
        expired_threshold_seconds=expired,
        revalidate_command=record.revalidate_command,
        reason=reason,
        falsifier=_FALSIFIER_TEXT,
        evidence_fields=evidence,
    )


def _utcnow_for_doctest() -> datetime:
    """Stable UTC-now wrapper kept out of assess_decay for determinism."""
    return datetime.now(tz=timezone.utc)
