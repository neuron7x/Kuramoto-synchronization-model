# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Wire protocol for the cognitive bridge.

The protocol is intentionally minimal:

* ``AdvisoryRequest``  — host -> sidecar, carries the current agent state
  snapshot (state machine node, market regime label, kill-switch flag) and
  a free-form ``question`` for the LLM.
* ``AdvisoryResponse`` — sidecar -> host, carries an evidence-tiered
  recommendation and a structured rationale.

Determinism guarantees:

* Both messages are Pydantic v2 models with frozen ``model_config``.
* Each request gets a deterministic ``correlation_id`` derived from a
  sha256 over the canonical JSON payload, so replays produce the same id
  and out-of-order delivery is detectable.
* ``status`` is a closed enum; any wire value outside it is rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION: str = "cb-1.0.0"


class EvidenceTier(str, Enum):
    """Inference Discipline Protocol v1.0 §7 tier labels.

    The cognitive bridge defaults to SPECULATIVE for any LLM-derived
    advisory because the sidecar is a free-form generator, not a
    contract-bound deterministic component.
    """

    ANCHORED = "anchored"
    EXTRAPOLATED = "extrapolated"
    SPECULATIVE = "speculative"
    UNKNOWN = "unknown"


class AdvisoryStatus(str, Enum):
    """Outcome of a single advisory exchange."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"
    DISABLED = "disabled"


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdvisoryRequest(BaseModel):
    """Host snapshot sent to the cognitive sidecar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: str = Field(default=PROTOCOL_VERSION)
    issued_at: datetime = Field(default_factory=_utc_now)
    agent_state: str = Field(min_length=1, max_length=64)
    coherence: float = Field(ge=0.0, le=1.0)
    kill_switch_active: bool
    stressed_state: bool
    question: str = Field(min_length=1, max_length=8192)
    context: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("protocol_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != PROTOCOL_VERSION:
            raise ValueError(
                f"unsupported protocol_version={value!r}; expected {PROTOCOL_VERSION!r}"
            )
        return value

    def correlation_id(self) -> str:
        """Deterministic sha256 over the canonical payload."""
        payload = self.model_dump(mode="json")
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class AdvisoryResponse(BaseModel):
    """Sidecar reply. ``recommendation`` is advisory-only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: str = Field(default=PROTOCOL_VERSION)
    correlation_id: str = Field(min_length=64, max_length=64)
    status: AdvisoryStatus
    tier: EvidenceTier = EvidenceTier.SPECULATIVE
    recommendation: str = Field(default="", max_length=8192)
    rationale: str = Field(default="", max_length=16384)
    received_at: datetime = Field(default_factory=_utc_now)

    @field_validator("protocol_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value != PROTOCOL_VERSION:
            raise ValueError(
                f"unsupported protocol_version={value!r}; expected {PROTOCOL_VERSION!r}"
            )
        return value

    @field_validator("correlation_id")
    @classmethod
    def _check_hex(cls, value: str) -> str:
        try:
            int(value, 16)
        except ValueError as exc:
            raise ValueError("correlation_id must be hex") from exc
        return value

    @classmethod
    def unavailable(cls, *, correlation_id: str, reason: str) -> "AdvisoryResponse":
        return cls(
            correlation_id=correlation_id,
            status=AdvisoryStatus.UNAVAILABLE,
            tier=EvidenceTier.UNKNOWN,
            recommendation="",
            rationale=reason,
        )

    @classmethod
    def disabled(cls, *, correlation_id: str, reason: str) -> "AdvisoryResponse":
        return cls(
            correlation_id=correlation_id,
            status=AdvisoryStatus.DISABLED,
            tier=EvidenceTier.UNKNOWN,
            recommendation="",
            rationale=reason,
        )


__all__ = [
    "AdvisoryRequest",
    "AdvisoryResponse",
    "AdvisoryStatus",
    "EvidenceTier",
    "PROTOCOL_VERSION",
]
