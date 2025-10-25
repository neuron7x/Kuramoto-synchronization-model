"""Utilities for distributed tracing and correlation ID propagation.

This module wraps the OpenTelemetry SDK to expose a consistent
application-facing API for distributed tracing.  When the optional
``opentelemetry`` dependencies are not installed the helpers degrade to
no-ops while still providing correlation identifiers for structured
logging.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, Mapping, MutableMapping
from uuid import uuid4

LOGGER = logging.getLogger(__name__)


try:  # pragma: no cover - optional dependency import guarded at runtime
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.propagate import get_global_textmap, set_global_textmap
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    from opentelemetry.trace import Span, SpanKind
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    _TRACE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - the dependencies are optional
    LOGGER.debug(
        "OpenTelemetry instrumentation unavailable; distributed tracing disabled",
        exc_info=exc,
    )
    otel_context = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]
    JaegerExporter = None  # type: ignore[assignment]
    Resource = TracerProvider = BatchSpanProcessor = None  # type: ignore[assignment]
    TraceIdRatioBased = None  # type: ignore[assignment]
    Span = SpanKind = None  # type: ignore[assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment]
    get_global_textmap = set_global_textmap = None  # type: ignore[assignment]
    _TRACE_AVAILABLE = False


def _default_correlation_id() -> str:
    return uuid4().hex


_CORRELATION_ID_VAR: ContextVar[str | None] = ContextVar(
    "tradepulse_correlation_id", default=None
)

_CORRELATION_ID_FACTORY: Callable[[], str] = _default_correlation_id

_CORRELATION_HEADER_NAME = "x-correlation-id"
_CORRELATION_HEADER_LOWER = _CORRELATION_HEADER_NAME.lower()
_CORRELATION_ATTRIBUTE = "correlation.id"
_DEFAULT_TRACER_NAME = "tradepulse.distributed"


if _TRACE_AVAILABLE:

    class _DictSetter:
        """Setter helper compatible with OpenTelemetry propagators."""

        def set(self, carrier: MutableMapping[str, str], key: str, value: str) -> None:
            carrier[key] = value

    class _DictGetter:
        """Getter helper compatible with OpenTelemetry propagators."""

        def get(self, carrier: Mapping[str, str], key: str) -> list[str]:
            for existing_key, value in carrier.items():
                if existing_key.lower() != key.lower():
                    continue
                if isinstance(value, (list, tuple)):
                    return [str(item) for item in value]
                return [str(value)]
            return []

    _DICT_SETTER = _DictSetter()
    _DICT_GETTER = _DictGetter()
    _W3C_PROPAGATOR = TraceContextTextMapPropagator()
else:  # pragma: no cover - tracing stack unavailable
    _DICT_SETTER = _DICT_GETTER = None  # type: ignore[assignment]
    _W3C_PROPAGATOR = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DistributedTracingConfig:
    """Configuration for distributed tracing with Jaeger."""

    service_name: str = "tradepulse"
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
        "service.namespace": "tradepulse",
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
    if isinstance(current, TraceContextTextMapPropagator):
        return
    set_global_textmap(_W3C_PROPAGATOR)


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
    """Inject the current trace and correlation context into ``carrier``."""

    if carrier is None:
        raise ValueError("carrier must be provided")

    if _TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_SETTER:
        _W3C_PROPAGATOR.inject(carrier, setter=_DICT_SETTER)

    correlation_id = current_correlation_id()
    if correlation_id:
        carrier[_CORRELATION_HEADER_NAME] = correlation_id


def _first_correlation_value(carrier: Mapping[str, Any]) -> str | None:
    for key, value in carrier.items():
        if key.lower() != _CORRELATION_HEADER_LOWER:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            return str(value[0])
        return str(value)
    return None


def extract_distributed_context(carrier: Mapping[str, Any]) -> ExtractedContext:
    """Extract trace and correlation metadata from ``carrier``."""

    if carrier is None:
        raise ValueError("carrier must be provided")

    trace_context = None
    if _TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_GETTER:
        trace_context = _W3C_PROPAGATOR.extract(carrier, getter=_DICT_GETTER)

    correlation_id = _first_correlation_value(carrier)
    return ExtractedContext(correlation_id=correlation_id, trace_context=trace_context)


@contextmanager
def activate_distributed_context(
    context: ExtractedContext,
    *,
    auto_generate_correlation: bool = False,
) -> Iterator[str | None]:
    """Activate an extracted distributed context as the current one."""

    trace_token = None
    if (
        _TRACE_AVAILABLE
        and otel_context
        and context.trace_context is not None
    ):
        trace_token = otel_context.attach(context.trace_context)

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
    "configure_distributed_tracing",
    "correlation_scope",
    "current_correlation_id",
    "generate_correlation_id",
    "inject_distributed_context",
    "extract_distributed_context",
    "set_correlation_id_generator",
    "shutdown_tracing",
    "start_distributed_span",
    "traceparent_header",
]
