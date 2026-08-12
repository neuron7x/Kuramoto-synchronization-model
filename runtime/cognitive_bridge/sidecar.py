# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cognitive sidecar orchestrator.

Wraps a ``Transport`` with the CB-INV-1..7 fail-closed contracts. The
host obtains advisories by calling :py:meth:`CognitiveSidecar.advise`;
the orchestrator handles short-circuits, schema validation, correlation
checks, and timeout normalization so the caller never has to.

Audit log: every exchange is appended to a bounded deque so the host
can prove what was asked, when, and how it resolved. The log only
stores correlation ids and statuses, never the free-form question or
recommendation, to keep PII out of post-mortems.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock

from pydantic import ValidationError

from runtime.cognitive_bridge.errors import (
    BridgeInvariantError,
    BridgeTimeoutError,
    BridgeTransportError,
)
from runtime.cognitive_bridge.invariants import InvariantId
from runtime.cognitive_bridge.protocol import (
    PROTOCOL_VERSION,
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
    EvidenceTier,
)
from runtime.cognitive_bridge.transport import Transport


@dataclass(frozen=True)
class SidecarConfig:
    """Configuration knobs for ``CognitiveSidecar``.

    Defaults are chosen so that the bridge collapses gracefully if the
    sidecar is missing: ``enabled=True`` by default, but a single
    timeout or transport failure becomes UNAVAILABLE rather than an
    exception bubbling to the host.
    """

    timeout_s: float = 5.0
    enabled: bool = True
    audit_log_size: int = 256

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.audit_log_size <= 0:
            raise ValueError("audit_log_size must be positive")


@dataclass(frozen=True)
class AuditEntry:
    ts: datetime
    correlation_id: str
    status: AdvisoryStatus
    invariant: InvariantId | None = None
    note: str = ""


@dataclass
class _State:
    audit: deque[AuditEntry] = field(default_factory=lambda: deque(maxlen=256))


class CognitiveSidecar:
    """Fail-closed wrapper around a ``Transport``.

    Usage::

        sidecar = CognitiveSidecar(transport=InMemoryTransport(handler))
        response = sidecar.advise(request)
        if response.status is AdvisoryStatus.OK:
            ...  # treat as Layer-2 advisory only (CB-INV-3)

    The deterministic state machine remains authoritative; this class
    only exposes the LLM as a side-channel hint.
    """

    def __init__(
        self,
        *,
        transport: Transport,
        config: SidecarConfig | None = None,
    ) -> None:
        self._transport = transport
        self._config = config or SidecarConfig()
        self._lock = RLock()
        self._state = _State(
            audit=deque(maxlen=self._config.audit_log_size),
        )

    @property
    def config(self) -> SidecarConfig:
        return self._config

    def audit_log(self) -> tuple[AuditEntry, ...]:
        with self._lock:
            return tuple(self._state.audit)

    def advise(self, request: AdvisoryRequest) -> AdvisoryResponse:
        correlation_id = request.correlation_id()

        if not self._config.enabled:
            return self._record_disabled(
                correlation_id, "sidecar disabled by config", InvariantId.CB_INV_5_KILL_SWITCH
            )
        if request.kill_switch_active:
            return self._record_disabled(
                correlation_id, "kill switch active", InvariantId.CB_INV_5_KILL_SWITCH
            )
        if request.stressed_state:
            return self._record_disabled(
                correlation_id, "stressed state", InvariantId.CB_INV_6_STRESSED
            )

        try:
            response = self._transport.exchange(request, timeout_s=self._config.timeout_s)
        except (BridgeTimeoutError, BridgeTransportError) as exc:
            return self._record_unavailable(
                correlation_id, f"transport: {exc}", InvariantId.CB_INV_2_TIMEOUT
            )
        except ValidationError as exc:
            return self._record_unavailable(
                correlation_id, f"schema: {exc}", InvariantId.CB_INV_1_SCHEMA
            )
        except Exception as exc:
            return self._record_unavailable(
                correlation_id,
                f"unexpected: {exc.__class__.__name__}",
                InvariantId.CB_INV_2_TIMEOUT,
            )

        validated = self._validate(request, correlation_id, response)
        self._append_audit(
            AuditEntry(
                ts=_utc_now(),
                correlation_id=correlation_id,
                status=validated.status,
            )
        )
        return validated

    def _validate(
        self,
        request: AdvisoryRequest,
        correlation_id: str,
        response: AdvisoryResponse,
    ) -> AdvisoryResponse:
        if response.protocol_version != PROTOCOL_VERSION:
            raise BridgeInvariantError(
                InvariantId.CB_INV_7_VERSION.value,
                f"protocol mismatch: request={PROTOCOL_VERSION!r} "
                f"response={response.protocol_version!r}",
            )
        if response.correlation_id != correlation_id:
            raise BridgeInvariantError(
                InvariantId.CB_INV_4_CORRELATION.value,
                f"correlation mismatch: expected={correlation_id} got={response.correlation_id}",
            )
        # CB-INV-3: any tier above SPECULATIVE on free-form output is downgraded
        # at the host boundary. We keep the tier as reported but the host
        # contract guarantees deterministic state remains authoritative.
        del request  # state-machine reconciliation is the host's job, not ours
        return response

    def _record_disabled(
        self,
        correlation_id: str,
        reason: str,
        invariant: InvariantId,
    ) -> AdvisoryResponse:
        response = AdvisoryResponse.disabled(correlation_id=correlation_id, reason=reason)
        self._append_audit(
            AuditEntry(
                ts=_utc_now(),
                correlation_id=correlation_id,
                status=AdvisoryStatus.DISABLED,
                invariant=invariant,
                note=reason,
            )
        )
        return response

    def _record_unavailable(
        self,
        correlation_id: str,
        reason: str,
        invariant: InvariantId,
    ) -> AdvisoryResponse:
        response = AdvisoryResponse.unavailable(correlation_id=correlation_id, reason=reason)
        self._append_audit(
            AuditEntry(
                ts=_utc_now(),
                correlation_id=correlation_id,
                status=AdvisoryStatus.UNAVAILABLE,
                invariant=invariant,
                note=reason,
            )
        )
        return response

    def _append_audit(self, entry: AuditEntry) -> None:
        with self._lock:
            self._state.audit.append(entry)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["AuditEntry", "CognitiveSidecar", "EvidenceTier", "SidecarConfig"]
