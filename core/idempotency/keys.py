# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for producing stable idempotency keys across services."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from datetime import time as dtime
from decimal import Decimal
from hashlib import blake2b
from typing import Any, Iterable, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

_CANONICAL_NAMESPACE = uuid5(NAMESPACE_URL, "https://geosync/idempotency")


def _canonical_temporal(value: datetime | date | dtime) -> str:
    """UTC-normalised ISO-8601 string for a datetime/date/time value."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
    elif isinstance(value, date):
        value = datetime.combine(value, dtime.min, tzinfo=timezone.utc)
    elif value.tzinfo is None:  # dtime
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _canonical_float(value: float) -> float:
    """Collapse -0.0 to +0.0 and reject non-finite floats (fail-closed).

    Logically-identical dedupe payloads must share one key: a signed-zero
    numeric field must not fingerprint differently, and NaN/Inf have no valid
    canonical JSON representation.
    """
    if not math.isfinite(value):
        raise ValueError(f"non-finite float is not a valid idempotency payload: {value!r}")
    return 0.0 if value == 0.0 else value


def _normalise(value: Any) -> Any:
    """Normalise arbitrary structures into JSON-compatible primitives."""

    if isinstance(value, Mapping):
        return {
            str(key): _normalise(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_normalise(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    if isinstance(value, (datetime, date, dtime)):
        return _canonical_temporal(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float):
        return _canonical_float(value)
    return value


def canonical_dumps(payload: Any) -> str:
    """Return a canonical JSON representation for hashing purposes."""

    normalised = _normalise(payload)
    return json.dumps(
        normalised, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False
    )


def fingerprint_payload(payload: Any, *, digest_size: int = 16) -> str:
    """Produce a deterministic fingerprint for the supplied payload."""

    representation = canonical_dumps(payload)
    digest = blake2b(representation.encode("utf-8"), digest_size=digest_size)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Compound identifier encapsulating request and operation identifiers."""

    service: str
    operation: str
    request_id: str
    operation_id: str
    fingerprint: str

    def composite(self) -> str:
        """Return the composite identifier for storage systems."""

        return f"{self.service}:{self.operation}:{self.fingerprint}"


class IdempotencyKeyFactory:
    """Factory responsible for generating stable request and operation identifiers."""

    def __init__(self, *, namespace: UUID | None = None) -> None:
        self._namespace = namespace or _CANONICAL_NAMESPACE

    def build(
        self,
        *,
        service: str,
        operation: str,
        dedupe_fields: Any,
        attempt: int | None = None,
        nonce: str | None = None,
    ) -> IdempotencyKey:
        if not service or not operation:
            raise ValueError("service and operation must be provided")
        fingerprint = fingerprint_payload(dedupe_fields)
        service_namespace = uuid5(self._namespace, service)
        request_uuid = uuid5(service_namespace, f"{operation}:{fingerprint}")
        attempt_source: str | None
        if nonce is not None:
            attempt_source = (
                f"nonce:{nonce}" if attempt is None else f"nonce:{nonce}:attempt:{attempt}"
            )
        elif attempt is not None:
            attempt_source = f"attempt:{attempt}"
        else:
            attempt_source = None
        operation_uuid = (
            uuid5(request_uuid, attempt_source) if attempt_source is not None else request_uuid
        )
        return IdempotencyKey(
            service=service,
            operation=operation,
            request_id=str(request_uuid),
            operation_id=str(operation_uuid),
            fingerprint=fingerprint,
        )

    def bulk(
        self,
        *,
        service: str,
        operation: str,
        dedupe_items: Iterable[Any],
    ) -> list[IdempotencyKey]:
        """Generate idempotency keys for a batch of items."""

        return [
            self.build(service=service, operation=operation, dedupe_fields=item, attempt=index)
            for index, item in enumerate(dedupe_items)
        ]


__all__ = [
    "IdempotencyKey",
    "IdempotencyKeyFactory",
    "canonical_dumps",
    "fingerprint_payload",
]
