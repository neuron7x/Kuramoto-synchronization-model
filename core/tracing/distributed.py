# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for distributed tracing and correlation ID propagation.

This module wraps the OpenTelemetry SDK to expose a consistent
application-facing API for distributed tracing.  When the optional
``opentelemetry`` dependencies are not installed the helpers degrade to
no-ops while still providing correlation identifiers for structured
logging.

Carrier-key contract
--------------------

Extraction paths (:func:`extract_distributed_context`,
:func:`_first_correlation_value`, :func:`_extract_local_baggage`,
:class:`_DictGetter`) are **read-tolerant** over the carrier:

* Supported key types: ``str``, ``bytes``, ``bytearray``.
* Keys are ASCII-decoded when byte-shaped, lower-cased, and validated
  against the RFC 7230 § 3.2.6 *token* grammar. Keys that fail the
  grammar are silently ignored rather than coerced via ``str(key)`` —
  this prevents non-header-like objects (integers, tuples, arbitrary
  class instances) from spuriously matching canonical header names.
* Values are normalised via :func:`_normalize_header_value`: ``str``
  passes through, ``bytes``/``bytearray`` decode via latin-1, and other
  types fall back to ``str()`` so legacy carriers do not crash the read
  path.

Injection paths (:func:`inject_distributed_context`,
:class:`_DictSetter`, :func:`_inject_local_baggage`) are
**write-canonical**:

* Only ``str`` keys and ``str`` values are emitted — never bytes.
* Every outgoing value is passed through :func:`_reject_crlf`, which
  refuses CR/LF/NUL forbidden by RFC 7230 § 3.2 for header field values.
  This forecloses header-splitting attacks where an attacker-supplied
  correlation ID or baggage value could be smuggled into a downstream
  HTTP/1.1 proxy that is not Unicode-strict.

The asymmetry (tolerant read, canonical write) is deliberate: upstream
carriers come from WSGI, ASGI, gRPC metadata, Jaeger wire bytes, etc.
and may present bytes keys; downstream propagators and HTTP clients
expect ``str`` on their setter contract, so we never expose them to
anything else.

W3C Baggage fallback (drop-truncate-log)
----------------------------------------

When OpenTelemetry is not installed, :func:`_inject_local_baggage` is
the W3C-Baggage emitter and :func:`_extract_local_baggage` is its
reader. Philosophy: **drop-truncate-log**, not raise.

* Unsafe members (non-token key, CR/LF/NUL in value, ``,`` or ``;``
  in value) are silently dropped via
  :func:`_normalize_baggage_member`. Callers never see a runtime
  exception from the tracing layer because of a bad baggage entry.
* W3C § 4.3 size limits are enforced by truncation:
  :data:`BAGGAGE_MAX_MEMBERS` (180) caps the member count; the tail
  is dropped if more are present. :data:`BAGGAGE_MAX_BYTES` (8192)
  caps the encoded payload; trailing members are dropped iteratively
  until the remaining payload fits. If no members survive, no header
  is written at all.
* Every truncation emits
  ``LOGGER.warning('tracing.baggage_truncated', extra={reason, ...})``
  so operators can alert on the event without the inject path raising.

The correlation write path follows the same philosophy: unsafe
correlation values (CR/LF/NUL) are dropped at inject via
:func:`_normalize_correlation_value`, never injected on the wire.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Callable, Dict, Final, Iterator, Mapping, MutableMapping
from uuid import uuid4

LOGGER = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency import guarded at runtime
    from opentelemetry import baggage as otel_baggage
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.propagate import get_global_textmap, set_global_textmap
    from opentelemetry.propagators.baggage import BaggagePropagator
    from opentelemetry.propagators.composite import CompositeTextMapPropagator
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    from opentelemetry.trace import Span, SpanKind
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _TRACE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - the dependencies are optional
    LOGGER.debug(
        "OpenTelemetry instrumentation unavailable; distributed tracing disabled",
        exc_info=exc,
    )
    otel_context = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]
    otel_baggage = None  # type: ignore[assignment]
    JaegerExporter = None
    Resource = TracerProvider = BatchSpanProcessor = None  # type: ignore[assignment]
    TraceIdRatioBased = None  # type: ignore[assignment]
    Span = SpanKind = None  # type: ignore[assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment]
    CompositeTextMapPropagator = None
    BaggagePropagator = None
    get_global_textmap = set_global_textmap = None  # type: ignore[assignment]
    _TRACE_AVAILABLE = False


def _default_correlation_id() -> str:
    return uuid4().hex


_CORRELATION_ID_VAR: ContextVar[str | None] = ContextVar("geosync_correlation_id", default=None)

_CORRELATION_ID_FACTORY: Callable[[], str] = _default_correlation_id

_CORRELATION_HEADER_NAME = "x-correlation-id"
_CORRELATION_HEADER_LOWER = _CORRELATION_HEADER_NAME.lower()
_CORRELATION_ATTRIBUTE = "correlation.id"
_BAGGAGE_HEADER_NAME = "baggage"
_BAGGAGE_HEADER_LOWER = _BAGGAGE_HEADER_NAME.lower()
_DEFAULT_TRACER_NAME = "geosync.distributed"
# RFC 7230 § 3.2.6 token grammar. Carrier keys must be case-insensitively
# comparable against canonical lower-cased header names; any key that
# cannot survive a round-trip through this grammar after ASCII-decoding
# is rejected outright rather than matched via ``str(key)`` (which would
# let bytes/other types leak into header space).
_HEADER_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9a-z]+$")
# Same grammar, case-preserving, for validating *baggage* keys on the
# write path — W3C Baggage § 3.2.1.1 pins keys to RFC 7230 tokens.
_BAGGAGE_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
# RFC 7230 § 3.2 forbids CR/LF and NUL inside header field values; we
# also refuse any other C0 control byte to prevent header-splitting
# attacks on downstream HTTP/1.1 hops that may not be Unicode-strict.
_FORBIDDEN_HEADER_VALUE_CHARS: Final[tuple[str, ...]] = ("\r", "\n", "\x00")
# W3C Baggage (https://www.w3.org/TR/baggage/, § 4.3) hard limits on the
# wire representation of the `baggage` header. We enforce BEFORE emission
# — a baggage header that would exceed either bound is rejected at
# inject time with a clear ValueError, never silently truncated.
BAGGAGE_MAX_MEMBERS: Final[int] = 180
BAGGAGE_MAX_BYTES: Final[int] = 8192
# Percent-encoding safe-set for baggage VALUES. W3C Baggage defers to
# RFC 3986 § 2.3 `unreserved` (ALPHA / DIGIT / "-" / "." / "_" / "~").
# Everything else — including "=" "," ";" space and non-ASCII — must be
# percent-encoded on the wire so the CSV/list-member parser cannot be
# confused by values that happen to contain delimiter characters.
_BAGGAGE_VALUE_SAFE = ""  # empty => quote everything outside unreserved


_LOCAL_BAGGAGE: ContextVar[Mapping[str, str] | None] = ContextVar(
    "geosync_local_baggage", default=None
)


def _normalize_header_key(key: object) -> str | None:
    """Normalize carrier header keys for case-insensitive matching.

    Only ``str`` and bytes-like keys are supported because those are the
    canonical wire/header representations. Unsupported key types return
    ``None`` and are silently ignored rather than matched through
    implicit ``str(key)`` coercion (which would allow non-header-like
    objects to accidentally satisfy the header-name comparison).
    """

    if isinstance(key, str):
        normalized = key.lower()
    elif isinstance(key, (bytes, bytearray)):
        try:
            normalized = bytes(key).decode("ascii").lower()
        except UnicodeDecodeError:
            return None
    else:
        return None

    if not _HEADER_TOKEN_RE.fullmatch(normalized):
        return None
    return normalized


def _header_key_matches(key: object, expected_lower: str) -> bool:
    """Return ``True`` when a carrier key matches ``expected_lower``."""

    normalized = _normalize_header_key(key)
    return normalized == expected_lower if normalized is not None else False


def _normalize_header_value(value: object) -> str | None:
    """Normalize header values without turning bytes into ``b'...'`` strings.

    ``str`` passes through. ``bytes``/``bytearray`` decode via latin-1 —
    the canonical HTTP surrogate for opaque octets. ``None`` stays
    ``None``. Other types are coerced via ``str()`` as a last resort so
    accidental integer/tuple carriers do not crash the reader path, but
    the write path in :class:`_DictSetter` remains canonical ``str``.
    """

    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("latin-1")
    if value is None:
        return None
    return str(value)


def _current_local_baggage() -> dict[str, str]:
    """Return a fresh copy of the active local-baggage snapshot.

    The :data:`_LOCAL_BAGGAGE` :class:`ContextVar` defaults to ``None``
    so we never mutate or expose a shared default-instance dict; every
    caller gets its own copy.
    """

    baggage = _LOCAL_BAGGAGE.get()
    return dict(baggage) if baggage else {}


def _is_safe_header_text(value: str) -> bool:
    """Return ``True`` when header text has no CR/LF/NUL separators."""

    return all(char not in value for char in _FORBIDDEN_HEADER_VALUE_CHARS)


def _normalize_correlation_value(value: object) -> str | None:
    """Normalize a transport value for correlation-id extraction.

    ``str`` is trimmed; ``bytes``/``bytearray`` decode via latin-1; other
    types are ignored. Values that carry CR/LF/NUL are dropped so a
    corrupted upstream cannot turn into a header-split vector when the
    value is re-injected downstream.
    """

    normalized = _normalize_header_value(value)
    if normalized is None:
        return None
    if not _is_safe_header_text(normalized):
        return None
    stripped = normalized.strip()
    return stripped or None


def _normalize_baggage_header_value(value: object) -> str | None:
    """Normalize the raw `baggage` header value for extraction.

    Same tolerance profile as :func:`_normalize_correlation_value`
    without the strip — list-member whitespace is handled by the
    downstream parser.
    """

    normalized = _normalize_header_value(value)
    if normalized is None:
        return None
    if not _is_safe_header_text(normalized):
        return None
    return normalized


def _normalize_baggage_member(key: object, value: object) -> tuple[str, str] | None:
    """Normalize a single baggage (key, value) pair.

    W3C Baggage § 3.2.1.1 pins keys to RFC 7230 tokens. Values that
    carry list/member delimiters (``,`` or ``;``) cannot be emitted
    unambiguously as plain list-members, so they are silently dropped.
    Control bytes (CR/LF/NUL) are dropped for header-splitting safety.
    The function returns ``None`` for any unsafe pair, which the inject
    path treats as "skip this member".
    """

    if not isinstance(key, str):
        key = str(key)
    if not isinstance(value, str):
        value = str(value)

    normalized_key = key.strip().lower()
    normalized_value = value.strip()
    if not normalized_key or not normalized_value:
        return None
    if not _BAGGAGE_TOKEN_RE.fullmatch(normalized_key):
        return None
    if not _is_safe_header_text(normalized_value):
        return None
    if any(sep in normalized_value for sep in (",", ";")):
        return None
    return normalized_key, normalized_value


if _TRACE_AVAILABLE:

    class _DictSetter:
        """Setter helper compatible with OpenTelemetry propagators.

        Write path is canonical: emit ``str`` keys and ``str`` values
        only. Values here come from OpenTelemetry's own tracecontext /
        baggage propagators which already produce safe ASCII payloads,
        so we do not re-validate on the setter side.
        """

        def set(self, carrier: MutableMapping[str, str], key: str, value: str) -> None:
            carrier[key] = value

    class _DictGetter:
        """Getter helper compatible with OpenTelemetry propagators.

        Read path is tolerant — accepts ``str`` and bytes-like keys
        (including ``bytearray``), ignores malformed or non-header-shaped
        keys rather than matching them, and decodes bytes-like values via
        latin-1 so propagators never see ``b'...'`` repr strings.
        """

        def get(self, carrier: Mapping[Any, Any], key: str) -> list[str]:
            expected_lower = key.lower()
            for existing_key, value in carrier.items():
                if not _header_key_matches(existing_key, expected_lower):
                    continue
                if isinstance(value, (list, tuple)):
                    return [
                        item_str
                        for item in value
                        if (item_str := _normalize_header_value(item)) is not None
                    ]
                item_str = _normalize_header_value(value)
                return [item_str] if item_str is not None else []
            return []

    _DICT_SETTER = _DictSetter()
    _DICT_GETTER = _DictGetter()
    _W3C_PROPAGATOR = TraceContextTextMapPropagator()
    _BAGGAGE_PROPAGATOR = BaggagePropagator()
    _GLOBAL_PROPAGATOR = CompositeTextMapPropagator(
        [
            _W3C_PROPAGATOR,
            _BAGGAGE_PROPAGATOR,
        ]
    )
else:  # pragma: no cover - tracing stack unavailable
    _DICT_SETTER = _DICT_GETTER = None  # type: ignore[assignment]
    _W3C_PROPAGATOR = None  # type: ignore[assignment]
    _BAGGAGE_PROPAGATOR = None
    _GLOBAL_PROPAGATOR = None


@dataclass(frozen=True)
class DistributedTracingConfig:
    """Configuration for distributed tracing with Jaeger."""

    service_name: str = "geosync"
    environment: str | None = None
    jaeger_agent_host: str = "localhost"
    jaeger_agent_port: int = 6831
    jaeger_collector_endpoint: str | None = None
    jaeger_username: str | None = None
    jaeger_password: str | None = None
    sample_ratio: float = 1.0
    correlation_header: str = _CORRELATION_HEADER_NAME
    resource_attributes: Mapping[str, Any] | None = None
    enable_w3c_propagation: bool = True


@dataclass(frozen=True)
class ExtractedContext:
    """Container for distributed context extracted from a carrier."""

    correlation_id: str | None
    trace_context: Any | None
    baggage: Mapping[str, str] | None


def configure_distributed_tracing(
    config: DistributedTracingConfig | None = None,
) -> bool:
    """Configure OpenTelemetry tracing with a Jaeger exporter."""

    if not _TRACE_AVAILABLE:
        LOGGER.warning("OpenTelemetry not installed; distributed tracing disabled")
        return False

    cfg = config or DistributedTracingConfig()

    _update_correlation_header(cfg.correlation_header)

    resource_attrs: Dict[str, Any] = {
        "service.name": cfg.service_name,
        "service.namespace": "geosync",
    }
    if cfg.environment:
        resource_attrs["deployment.environment"] = cfg.environment
    if cfg.resource_attributes:
        resource_attrs.update(dict(cfg.resource_attributes))

    sampler = _build_sampler(cfg.sample_ratio)
    provider_kwargs: Dict[str, Any] = {"resource": Resource.create(resource_attrs)}
    if sampler is not None:
        provider_kwargs["sampler"] = sampler

    provider = TracerProvider(**provider_kwargs)

    exporter = _build_jaeger_exporter(cfg)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    if cfg.enable_w3c_propagation:
        _ensure_w3c_propagator()

    LOGGER.info(
        "Distributed tracing configured",
        extra={
            "extra_fields": {
                "service_name": cfg.service_name,
                "environment": cfg.environment,
                "jaeger_agent": f"{cfg.jaeger_agent_host}:{cfg.jaeger_agent_port}",
                "jaeger_collector": cfg.jaeger_collector_endpoint,
                "sample_ratio": cfg.sample_ratio,
            }
        },
    )
    return True


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider if one is configured."""

    if not _TRACE_AVAILABLE:
        return

    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()


def _build_sampler(sample_ratio: float):
    if not _TRACE_AVAILABLE:
        return None

    try:
        ratio = float(sample_ratio)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid sample ratio %r; defaulting to 1.0", sample_ratio)
        ratio = 1.0

    ratio = max(0.0, min(1.0, ratio))

    if ratio >= 1.0:
        return None
    return TraceIdRatioBased(ratio)


def _build_jaeger_exporter(config: DistributedTracingConfig):
    if config.jaeger_collector_endpoint:
        username = config.jaeger_username or os.environ.get("JAEGER_USERNAME")
        password = config.jaeger_password or os.environ.get("JAEGER_PASSWORD")
        return JaegerExporter(
            collector_endpoint=config.jaeger_collector_endpoint,
            username=username,
            password=password,
        )
    return JaegerExporter(
        agent_host_name=config.jaeger_agent_host,
        agent_port=config.jaeger_agent_port,
    )


def _ensure_w3c_propagator() -> None:
    if not (_TRACE_AVAILABLE and get_global_textmap and set_global_textmap):
        return
    current = get_global_textmap()
    if current is _GLOBAL_PROPAGATOR:
        return
    set_global_textmap(_GLOBAL_PROPAGATOR)


def _update_correlation_header(header_name: str) -> None:
    global _CORRELATION_HEADER_NAME, _CORRELATION_HEADER_LOWER
    if not header_name:
        return
    _CORRELATION_HEADER_NAME = header_name
    _CORRELATION_HEADER_LOWER = header_name.lower()


def set_correlation_id_generator(generator: Callable[[], str]) -> None:
    """Set a custom generator used for correlation identifiers."""

    global _CORRELATION_ID_FACTORY
    if not callable(generator):
        raise TypeError("generator must be callable")
    _CORRELATION_ID_FACTORY = generator


def generate_correlation_id() -> str:
    """Return a new correlation identifier."""

    try:
        return _CORRELATION_ID_FACTORY()
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.error("Correlation ID generator failed; using uuid4", exc_info=exc)
        return _default_correlation_id()


def current_correlation_id(default: str | None = None) -> str | None:
    """Return the correlation identifier bound to the current context."""

    correlation = _CORRELATION_ID_VAR.get()
    if correlation:
        return correlation
    return default


@contextmanager
def correlation_scope(
    correlation_id: str | None = None,
    *,
    auto_generate: bool = True,
) -> Iterator[str | None]:
    """Context manager that binds a correlation ID to the current task."""

    token: Token | None = None
    new_id = correlation_id
    if new_id is None and auto_generate:
        new_id = generate_correlation_id()
    if new_id is not None:
        token = _CORRELATION_ID_VAR.set(new_id)
    try:
        yield new_id
    finally:
        if token is not None:
            _CORRELATION_ID_VAR.reset(token)


def inject_distributed_context(carrier: MutableMapping[str, str]) -> None:
    """Inject the current trace and correlation context into ``carrier``.

    The write path is canonical: ``str`` keys/values only. Unsafe
    correlation values (CR/LF/NUL) are silently dropped rather than
    injected — aligned with the drop-and-continue philosophy of
    :func:`_inject_local_baggage`.
    """

    if carrier is None:
        raise ValueError("carrier must be provided")

    if _TRACE_AVAILABLE and _GLOBAL_PROPAGATOR and _DICT_SETTER:
        _GLOBAL_PROPAGATOR.inject(carrier, setter=_DICT_SETTER)
    else:
        _inject_local_baggage(carrier)

    correlation_id = current_correlation_id()
    normalized_correlation = (
        _normalize_correlation_value(correlation_id) if correlation_id else None
    )
    if normalized_correlation:
        carrier[_CORRELATION_HEADER_NAME] = normalized_correlation


def _first_correlation_value(carrier: Mapping[Any, Any]) -> str | None:
    for key, value in carrier.items():
        if not _header_key_matches(key, _CORRELATION_HEADER_LOWER):
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            return _normalize_correlation_value(value[0])
        return _normalize_correlation_value(value)
    return None


def _inject_local_baggage(carrier: MutableMapping[str, str]) -> None:
    """Emit a W3C Baggage-compliant header when OpenTelemetry is unavailable.

    Philosophy: **drop + truncate + log**. Unsafe members are silently
    dropped; oversized membership lists or header payloads are truncated
    at the W3C § 4.3 limits; every truncation emits a structured
    ``LOGGER.warning('tracing.baggage_truncated', ...)`` so operators can
    alert on the event without the inject path raising at runtime.

    * Keys and values that fail :func:`_normalize_baggage_member`
      (non-token keys, control bytes, delimiter chars in values) are
      dropped before the member list is assembled.
    * Member count is capped at :data:`BAGGAGE_MAX_MEMBERS` (180): if
      more than 180 safe members are present, the tail is dropped.
    * Total wire-encoded length is capped at :data:`BAGGAGE_MAX_BYTES`
      (8192): trailing members are dropped one by one until the
      remaining payload fits.
    * If zero members survive truncation, no header is set.
    """

    baggage = _current_local_baggage()
    if not baggage:
        return

    safe_items: list[tuple[str, str]] = []
    for key, value in baggage.items():
        normalized = _normalize_baggage_member(key, value)
        if normalized is not None:
            safe_items.append(normalized)
    if not safe_items:
        return

    # W3C § 4.3 member-count ceiling.
    if len(safe_items) > BAGGAGE_MAX_MEMBERS:
        LOGGER.warning(
            "tracing.baggage_truncated",
            extra={
                "event": "tracing.baggage_truncated",
                "reason": "too_many_members",
                "original_members": len(safe_items),
                "kept_members": BAGGAGE_MAX_MEMBERS,
                "limit": BAGGAGE_MAX_MEMBERS,
            },
        )
        safe_items = safe_items[:BAGGAGE_MAX_MEMBERS]

    # W3C § 4.3 byte-length ceiling; drop tail members until the payload fits.
    header_value = ",".join(f"{k}={v}" for k, v in safe_items)
    original_byte_len = len(header_value.encode("ascii"))
    if original_byte_len > BAGGAGE_MAX_BYTES:
        original_members = len(safe_items)
        while safe_items:
            header_value = ",".join(f"{k}={v}" for k, v in safe_items)
            if len(header_value.encode("ascii")) <= BAGGAGE_MAX_BYTES:
                break
            safe_items = safe_items[:-1]
        else:
            header_value = ""
        LOGGER.warning(
            "tracing.baggage_truncated",
            extra={
                "event": "tracing.baggage_truncated",
                "reason": "header_too_large",
                "original_bytes": original_byte_len,
                "kept_bytes": len(header_value.encode("ascii")),
                "original_members": original_members,
                "kept_members": len(safe_items),
                "limit": BAGGAGE_MAX_BYTES,
            },
        )

    if not header_value:
        return
    carrier[_BAGGAGE_HEADER_NAME] = header_value


def _extract_local_baggage(carrier: Mapping[Any, Any]) -> Mapping[str, str] | None:
    """Parse the `baggage` header from a carrier using the drop-philosophy.

    An unsafe baggage header (CR/LF/NUL anywhere in the payload) is
    rejected wholesale so a single injected split cannot leak partial
    state to the caller. Individual malformed members — those that fail
    :func:`_normalize_baggage_member` — are dropped; the remaining safe
    members are returned.
    """

    baggage_header: str | None = None
    for key, value in carrier.items():
        if not _header_key_matches(key, _BAGGAGE_HEADER_LOWER):
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                baggage_header = None
            else:
                baggage_header = _normalize_baggage_header_value(value[0])
        else:
            baggage_header = _normalize_baggage_header_value(value)
        break
    if not baggage_header:
        return None
    parsed: dict[str, str] = {}
    for part in baggage_header.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        raw_key, raw_value = part.split("=", 1)
        # W3C Baggage § 3.2.1.1: members may carry ``;property`` segments
        # after the value. Drop them for the simplified local model.
        value_bare = raw_value.split(";", 1)[0].strip()
        normalized = _normalize_baggage_member(raw_key, value_bare)
        if normalized is None:
            continue
        safe_key, safe_value = normalized
        parsed[safe_key] = safe_value
    return parsed or None


def current_baggage() -> Mapping[str, str]:
    """Return a shallow copy of baggage items bound to the active context."""

    if _TRACE_AVAILABLE and otel_baggage is not None and otel_context is not None:
        context = otel_context.get_current()
        values = otel_baggage.get_all(context=context) or {}
        return dict(values)
    return _current_local_baggage()


def get_baggage_item(key: str, default: str | None = None) -> str | None:
    """Return a single baggage entry, falling back to ``default`` when missing."""

    return current_baggage().get(key, default)


@contextmanager
def baggage_scope(
    baggage: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> Iterator[Mapping[str, str]]:
    """Context manager that temporarily augments the active baggage set."""

    updates = {str(key): str(value) for key, value in (baggage or {}).items()}
    updates.update({str(key): str(value) for key, value in kwargs.items()})
    if not updates:
        yield current_baggage()
        return

    if _TRACE_AVAILABLE and otel_baggage is not None and otel_context is not None:
        current = otel_context.get_current()
        updated_context = current
        for key, value in updates.items():
            updated_context = otel_baggage.set_baggage(key, value, context=updated_context)
        token = otel_context.attach(updated_context)
        try:
            yield current_baggage()
        finally:
            otel_context.detach(token)
        return

    token = _LOCAL_BAGGAGE.set({**_current_local_baggage(), **updates})
    try:
        yield current_baggage()
    finally:
        _LOCAL_BAGGAGE.reset(token)


def extract_distributed_context(carrier: Mapping[Any, Any]) -> ExtractedContext:
    """Extract trace and correlation metadata from ``carrier``."""

    if carrier is None:
        raise ValueError("carrier must be provided")

    trace_context = None
    baggage_values: Mapping[str, str] | None = None
    if _TRACE_AVAILABLE and _GLOBAL_PROPAGATOR and _DICT_GETTER:
        trace_context = _GLOBAL_PROPAGATOR.extract(carrier, getter=_DICT_GETTER)
        if otel_baggage is not None:
            baggage_values = otel_baggage.get_all(context=trace_context) or None
    else:
        baggage_values = _extract_local_baggage(carrier)

    correlation_id = _first_correlation_value(carrier)
    return ExtractedContext(
        correlation_id=correlation_id,
        trace_context=trace_context,
        baggage=baggage_values,
    )


@contextmanager
def activate_distributed_context(
    context: ExtractedContext,
    *,
    auto_generate_correlation: bool = False,
) -> Iterator[str | None]:
    """Activate an extracted distributed context as the current one."""

    trace_token = None
    baggage_token: Token | None = None
    if _TRACE_AVAILABLE and otel_context and context.trace_context is not None:
        trace_token = otel_context.attach(context.trace_context)
    if context.baggage and (not _TRACE_AVAILABLE or context.trace_context is None):
        baggage_token = _LOCAL_BAGGAGE.set(dict(context.baggage))

    correlation_token: Token | None = None
    correlation = context.correlation_id
    if correlation is None and auto_generate_correlation:
        correlation = generate_correlation_id()
    if correlation is not None:
        correlation_token = _CORRELATION_ID_VAR.set(correlation)

    try:
        yield correlation
    finally:
        if trace_token is not None and otel_context is not None:
            otel_context.detach(trace_token)
        if baggage_token is not None:
            _LOCAL_BAGGAGE.reset(baggage_token)
        if correlation_token is not None:
            _CORRELATION_ID_VAR.reset(correlation_token)


@contextmanager
def start_distributed_span(
    name: str,
    *,
    correlation_id: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind | None = None,
) -> Iterator[Any]:
    """Start a span that also binds the correlation ID to the context."""

    with correlation_scope(correlation_id) as correlation:
        if not _TRACE_AVAILABLE or trace is None:
            yield None
            return

        span_kwargs: Dict[str, Any] = {}
        if kind is not None:
            span_kwargs["kind"] = kind

        tracer = trace.get_tracer(_DEFAULT_TRACER_NAME)
        with tracer.start_as_current_span(name, **span_kwargs) as span:
            if span and correlation:
                try:
                    span.set_attribute(_CORRELATION_ATTRIBUTE, correlation)
                except Exception:  # pragma: no cover - defensive guard
                    LOGGER.debug("Failed to set correlation attribute on span", exc_info=True)
            if span and attributes:
                try:
                    span.set_attributes(dict(attributes))
                except Exception:  # pragma: no cover - defensive guard
                    LOGGER.debug("Failed to set span attributes", exc_info=True)
            yield span


def traceparent_header() -> str | None:
    """Return the canonical ``traceparent`` header for the active span."""

    if not (_TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_SETTER):
        return None
    carrier: Dict[str, str] = {}
    _W3C_PROPAGATOR.inject(carrier, setter=_DICT_SETTER)
    return carrier.get("traceparent")


__all__ = [
    "DistributedTracingConfig",
    "ExtractedContext",
    "activate_distributed_context",
    "baggage_scope",
    "configure_distributed_tracing",
    "correlation_scope",
    "current_correlation_id",
    "current_baggage",
    "generate_correlation_id",
    "get_baggage_item",
    "inject_distributed_context",
    "extract_distributed_context",
    "set_correlation_id_generator",
    "shutdown_tracing",
    "start_distributed_span",
    "traceparent_header",
]
