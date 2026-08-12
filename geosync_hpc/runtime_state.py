# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed, versioned, checksummed snapshot / restore envelope.

Replaces the "pickle a dict" pattern that makes cross-process /
cross-commit restore a coin toss. Every snapshot carries:

1. An **envelope version** — the format of the wrapper itself; the
   reader refuses to parse an envelope it was not written against.
2. A **schema version** — the caller's declaration of the payload
   layout; the reader refuses to deserialise a payload whose schema
   it was not compiled to understand.
3. A **SHA-256 checksum** — computed over the canonical JSON encoding
   of the payload (sort_keys, no whitespace, strict int/float). Any
   silent corruption between write and read trips the load path.
4. A **creation timestamp** — UTC, ISO 8601, for forensic ordering of
   historical snapshots.

This module does *not* implement pickle-based load. Pickle restores
arbitrary Python objects from a byte stream, cannot verify schema, and
is a recurring source of supply-chain and schema-drift incidents.
Callers that need to serialise a domain object map it to a JSON-safe
``Mapping[str, Any]`` at the boundary; the envelope is intentionally
format-neutral below that boundary.

Fail-closed behaviour:

* non-int versions, empty payload, non-mapping payload → ``TypeError``
  / ``ValueError`` at dump;
* unknown envelope version → :class:`UnsupportedEnvelopeVersion`;
* schema mismatch against the caller's expectation →
  :class:`SchemaVersionMismatch`;
* checksum recomputation disagrees with stored hex →
  :class:`ChecksumMismatch`;
* NaN / Inf / unsupported Python types in payload → ``ValueError``.

This is a primitive. It does not yet know about ``BacktesterCAL``
internals; the caller builds the payload. A follow-up PR wires the
component snapshot / restore into the backtest harness, one component
at a time.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Final, Mapping

ENVELOPE_VERSION: Final[int] = 1
"""Format version of the envelope wrapper itself. Bump only on
envelope-level breaking changes (e.g. changing the set of top-level
fields). Schema-level changes use ``schema_version`` instead.
"""


class EnvelopeError(Exception):
    """Base class for snapshot / restore failures."""


class UnsupportedEnvelopeVersion(EnvelopeError):
    """Envelope was written against a version this reader does not know."""


class SchemaVersionMismatch(EnvelopeError):
    """Payload schema version differs from the caller's expectation."""


class ChecksumMismatch(EnvelopeError):
    """Stored checksum disagrees with the recomputed checksum — the file
    has been altered since it was written."""


@dataclass(frozen=True)
class RuntimeStateEnvelope:
    """Immutable snapshot wrapper. Construct via :func:`dump_envelope`
    or :func:`load_envelope`; do not instantiate by hand — doing so
    bypasses the checksum computation."""

    envelope_version: int
    schema_version: int
    created_utc: str
    payload_sha256: str
    payload: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Canonical encoding
# ---------------------------------------------------------------------------


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Deterministic JSON encoding of ``payload``.

    Guarantees byte-identity across CPython builds for the same Python
    object by:

    * ``sort_keys=True`` — dict iteration order does not matter;
    * ``separators=(",", ":")`` — no whitespace variation;
    * ``allow_nan=False`` — NaN / ±Inf would be non-canonical JSON and
      are refused (a runtime state should never contain them).

    ``ensure_ascii=False`` preserves UTF-8 strings verbatim; the encoded
    bytes are then the SHA-256 input.
    """
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError as exc:
        # json.dumps raises ValueError on NaN/Inf under allow_nan=False,
        # and on non-serialisable types (with TypeError wrapped by us).
        raise ValueError(f"payload is not canonical-JSON-serialisable: {exc}") from exc
    except TypeError as exc:
        raise ValueError(
            f"payload contains an unsupported type (expect only "
            f"int / float / str / bool / None / list / dict): {exc}"
        ) from exc
    return text.encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    """SHA-256 over ``data``, lowercase hex — reproducible across
    architectures and locales."""
    return hashlib.sha256(data).hexdigest()


def _validate_finite(payload: Mapping[str, Any]) -> None:
    """Reject NaN / ±Inf anywhere in the payload tree.

    ``json.dumps(allow_nan=False)`` already blocks this at encode time;
    the explicit pre-check gives a cleaner error message and lets
    callers catch it without a wrapped ``json.JSONDecodeError``.
    """

    def _walk(node: Any) -> None:
        if isinstance(node, float):
            if not math.isfinite(node):
                raise ValueError(
                    f"payload contains non-finite float: {node!r} "
                    f"(NaN / ±Inf are not admissible in a snapshot)"
                )
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(payload)


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def dump_envelope(
    path: Path | str,
    payload: Mapping[str, Any],
    *,
    schema_version: int,
    clock: Callable[[], datetime] = _default_clock,
) -> RuntimeStateEnvelope:
    """Write a snapshot to ``path`` and return the in-memory envelope.

    Parameters
    ----------
    path
        Destination file. Parent directories are NOT created implicitly —
        the caller owns the directory layout.
    payload
        JSON-safe mapping: ``int``, ``float``, ``bool``, ``None``, ``str``,
        ``list``, ``dict`` only. NaN / ±Inf are refused.
    schema_version
        Non-negative int. The reader must request the same value via
        ``load_envelope(..., expected_schema_version=...)``.
    clock
        Injectable UTC clock for deterministic tests.

    Raises
    ------
    TypeError
        ``payload`` is not a ``Mapping``, ``schema_version`` is not an int.
    ValueError
        ``schema_version`` is negative; payload contains non-finite
        floats or unsupported types; ``path`` parent does not exist.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(f"payload must be a Mapping, got {type(payload).__name__}")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise TypeError(f"schema_version must be int, got {type(schema_version).__name__}")
    if schema_version < 0:
        raise ValueError(f"schema_version must be >= 0, got {schema_version}")

    _validate_finite(payload)

    payload_bytes = _canonical_json(payload)
    payload_sha256 = _sha256_hex(payload_bytes)
    created_utc = clock().replace(microsecond=0).isoformat().replace("+00:00", "Z")

    envelope = RuntimeStateEnvelope(
        envelope_version=ENVELOPE_VERSION,
        schema_version=schema_version,
        created_utc=created_utc,
        payload_sha256=payload_sha256,
        payload=dict(payload),
    )

    wrapper = {
        "envelope_version": envelope.envelope_version,
        "schema_version": envelope.schema_version,
        "created_utc": envelope.created_utc,
        "payload_sha256": envelope.payload_sha256,
        "payload": envelope.payload,
    }
    dest = Path(path)
    if not dest.parent.exists():
        raise ValueError(
            f"parent directory does not exist: {dest.parent} "
            f"(dump_envelope does not create directories implicitly)"
        )
    dest.write_bytes(
        json.dumps(
            wrapper,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    )
    return envelope


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_envelope(
    path: Path | str,
    *,
    expected_schema_version: int,
) -> RuntimeStateEnvelope:
    """Read a snapshot from ``path`` and verify every integrity claim.

    Parameters
    ----------
    path
        Source file previously written by :func:`dump_envelope`.
    expected_schema_version
        The payload schema this caller was compiled against. Mismatch
        raises :class:`SchemaVersionMismatch`.

    Raises
    ------
    UnsupportedEnvelopeVersion
        Stored envelope version is not :data:`ENVELOPE_VERSION`.
    SchemaVersionMismatch
        Stored schema version ≠ ``expected_schema_version``.
    ChecksumMismatch
        Recomputed SHA-256 of the payload differs from the stored value.
    EnvelopeError
        Any other structural problem (missing fields, wrong types).
    FileNotFoundError
        ``path`` does not exist.
    """
    src = Path(path)
    raw = src.read_bytes()
    try:
        wrapper = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EnvelopeError(f"envelope is not valid JSON: {exc}") from exc

    if not isinstance(wrapper, dict):
        raise EnvelopeError(f"envelope must be a JSON object, got {type(wrapper).__name__}")

    required = {
        "envelope_version",
        "schema_version",
        "created_utc",
        "payload_sha256",
        "payload",
    }
    missing = required - set(wrapper.keys())
    if missing:
        raise EnvelopeError(f"envelope missing required fields: {sorted(missing)}")

    envelope_version = wrapper["envelope_version"]
    if envelope_version != ENVELOPE_VERSION:
        raise UnsupportedEnvelopeVersion(
            f"envelope_version={envelope_version!r} unsupported; "
            f"this reader handles only {ENVELOPE_VERSION}"
        )

    schema_version = wrapper["schema_version"]
    if schema_version != expected_schema_version:
        raise SchemaVersionMismatch(
            f"schema_version={schema_version!r} != expected={expected_schema_version!r}"
        )

    payload = wrapper["payload"]
    if not isinstance(payload, dict):
        raise EnvelopeError(f"payload must be a JSON object, got {type(payload).__name__}")

    stored_sha = wrapper["payload_sha256"]
    if not isinstance(stored_sha, str):
        raise EnvelopeError("payload_sha256 must be a string")

    recomputed_sha = _sha256_hex(_canonical_json(payload))
    if recomputed_sha != stored_sha:
        raise ChecksumMismatch(
            f"payload checksum mismatch: stored={stored_sha}, "
            f"recomputed={recomputed_sha} — envelope has been altered "
            f"since write."
        )

    created_utc = wrapper["created_utc"]
    if not isinstance(created_utc, str):
        raise EnvelopeError("created_utc must be a string")

    return RuntimeStateEnvelope(
        envelope_version=envelope_version,
        schema_version=schema_version,
        created_utc=created_utc,
        payload_sha256=stored_sha,
        payload=payload,
    )
