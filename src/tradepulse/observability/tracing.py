"""OpenTelemetry tracing utilities for TradePulse pipelines.

This module centralises the configuration of OpenTelemetry tracing and provides
helpers that make it easy to instrument the ingest → features → signals → orders
pipeline.  All helpers gracefully degrade to no-ops when the optional
``opentelemetry`` dependencies are not installed so that the rest of the code
base keeps functioning in lightweight environments.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, Mapping, MutableMapping, Sequence

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency import guarded at runtime
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.propagate import get_global_textmap, set_global_textmap
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
    from opentelemetry.sdk.trace.sampling import (
        Sampler,
        SamplingResult,
        TraceIdRatioBased,
    )
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    _TRACE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - the dependencies are optional
    LOGGER.debug(
        "OpenTelemetry instrumentation unavailable; tracing disabled",
        exc_info=exc,
    )
    otel_context = None  # type: ignore[assignment]
    trace = None  # type: ignore[assignment]
    Resource = TracerProvider = BatchSpanProcessor = OTLPSpanExporter = None  # type: ignore[assignment]
    SpanProcessor = None  # type: ignore[assignment]
    Sampler = SamplingResult = TraceIdRatioBased = None  # type: ignore[assignment]
    Status = StatusCode = None  # type: ignore[assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment]
    get_global_textmap = set_global_textmap = None  # type: ignore[assignment]
    _TRACE_AVAILABLE = False

_DEFAULT_TRACER_NAME = "tradepulse.pipeline"
_TRACEPARENT_HEADER = "traceparent"

_FAILOVER_ATTRIBUTE_KEYS = (
    "pipeline.failover",
    "routing.failover",
    "routing.failover_active",
    "resilience.failover",
    "failover.active",
)
_TRUTHY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "active",
    "failover",
}


def _is_truthy_signal(value: Any) -> bool:
    """Return ``True`` when ``value`` represents an enabled flag."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            return False
        return lowered in _TRUTHY_STRINGS
    return bool(value)


if _TRACE_AVAILABLE:

    class _DictSetter:
        """Setter helper compatible with OpenTelemetry propagators."""

        def set(self, carrier: MutableMapping[str, str], key: str, value: str) -> None:
            carrier[key] = value

    class _DictGetter:
        """Getter helper compatible with OpenTelemetry propagators."""

        def get(self, carrier: Mapping[str, str], key: str) -> Sequence[str]:
            value = carrier.get(key)
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                return list(value)
            return [value]

    _DICT_SETTER = _DictSetter()
    _DICT_GETTER = _DictGetter()
    _W3C_PROPAGATOR = TraceContextTextMapPropagator()
else:  # pragma: no cover - tracing stack unavailable
    _DICT_SETTER = _DICT_GETTER = None  # type: ignore[assignment]
    _W3C_PROPAGATOR = None  # type: ignore[assignment]


@dataclass(frozen=True)
class TracingConfig:
    """Container with tracing configuration options."""

    service_name: str = "tradepulse"
    environment: str | None = None
    exporter_endpoint: str | None = None
    exporter_insecure: bool = True
    resource_attributes: Mapping[str, Any] | None = None
    enable_w3c_propagation: bool = True
    pii_attributes: Sequence[str] = ()
    pii_patterns: Sequence[str] = ()
    pii_redaction: str = "[redacted]"
    hot_path_globs: Sequence[str] = ()
    hot_path_attribute: str = "pipeline.hot_path"
    default_sample_ratio: float = 1.0
    hot_path_sample_ratio: float = 1.0
    sampler: Any | None = field(default=None, repr=False, compare=False)


def configure_tracing(config: TracingConfig | None = None) -> bool:
    """Configure OpenTelemetry tracing using ``config``."""

    if not _TRACE_AVAILABLE:
        LOGGER.warning("OpenTelemetry not installed; tracing is disabled")
        return False

    cfg = config or TracingConfig()

    resource_attrs: Dict[str, Any] = {
        "service.name": cfg.service_name,
        "service.namespace": "tradepulse",
    }
    if cfg.environment:
        resource_attrs["deployment.environment"] = cfg.environment
    if cfg.resource_attributes:
        resource_attrs.update(dict(cfg.resource_attributes))

    endpoint = cfg.exporter_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    insecure_env = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE")
    insecure = (
        cfg.exporter_insecure
        if insecure_env is None
        else insecure_env.lower() == "true"
    )

    sampler = _build_sampler(cfg)
    provider = TracerProvider(resource=Resource.create(resource_attrs), sampler=sampler)

    exporter: OTLPSpanExporter | None
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    else:
        exporter = OTLPSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    _register_pii_filter(provider, cfg)

    trace.set_tracer_provider(provider)

    if cfg.enable_w3c_propagation:
        _ensure_w3c_propagator()

    LOGGER.info(
        "OpenTelemetry tracing configured",
        extra={
            "extra_fields": {
                "service_name": cfg.service_name,
                "environment": cfg.environment,
                "endpoint": endpoint,
                "insecure": insecure,
            }
        },
    )
    return True


def _build_sampler(config: TracingConfig):
    if not _TRACE_AVAILABLE:
        return None

    if config.sampler is not None:
        return config.sampler

    hot_ratio = max(0.0, min(1.0, float(config.hot_path_sample_ratio)))
    default_ratio = max(0.0, min(1.0, float(config.default_sample_ratio)))

    if (
        config.hot_path_globs
        or hot_ratio not in (0.0, 1.0)
        or default_ratio not in (0.0, 1.0)
    ):
        return SelectiveSampler(
            hot_path_globs=config.hot_path_globs,
            attribute_flag=config.hot_path_attribute,
            default_ratio=default_ratio,
            hot_ratio=hot_ratio,
        )

    if default_ratio not in (0.0, 1.0):
        return TraceIdRatioBased(default_ratio)

    return None


def _register_pii_filter(provider: TracerProvider, config: TracingConfig) -> None:
    if not _TRACE_AVAILABLE:
        return
    patterns = list(config.pii_patterns or ())
    attributes = list(config.pii_attributes or ())
    if not (patterns or attributes):
        return
    processor = PIIFilterSpanProcessor(
        denylist=attributes,
        pattern_denylist=patterns,
        redaction=config.pii_redaction,
    )
    provider.add_span_processor(processor)


def _ensure_w3c_propagator() -> None:
    if not _TRACE_AVAILABLE:
        return
    current = get_global_textmap()
    if isinstance(current, TraceContextTextMapPropagator):
        return
    set_global_textmap(_W3C_PROPAGATOR)


def get_tracer(name: str = _DEFAULT_TRACER_NAME):
    """Return the configured tracer or a no-op tracer when tracing is disabled."""

    if not _TRACE_AVAILABLE:
        return _NoOpTracer()
    return trace.get_tracer(name)


def inject_trace_context(carrier: MutableMapping[str, str]) -> None:
    """Inject the current span context into ``carrier`` using W3C TraceContext."""

    if not (_TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_SETTER):
        return
    _W3C_PROPAGATOR.inject(carrier, setter=_DICT_SETTER)


def extract_trace_context(carrier: Mapping[str, str]):
    """Extract a context from ``carrier`` using W3C TraceContext."""

    if not (_TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_GETTER):
        return None
    return _W3C_PROPAGATOR.extract(carrier, getter=_DICT_GETTER)


def current_traceparent() -> str | None:
    """Return the canonical traceparent header for the current span, if any."""

    if not (_TRACE_AVAILABLE and _W3C_PROPAGATOR and _DICT_SETTER):
        return None
    carrier: Dict[str, str] = {}
    _W3C_PROPAGATOR.inject(carrier, setter=_DICT_SETTER)
    return carrier.get(_TRACEPARENT_HEADER)


@contextmanager
def activate_traceparent(traceparent: str | None) -> Iterator[bool]:
    """Temporarily activate the provided ``traceparent`` header."""

    if not (
        _TRACE_AVAILABLE
        and traceparent
        and otel_context
        and _W3C_PROPAGATOR
        and _DICT_GETTER
    ):
        yield False
        return

    context = _W3C_PROPAGATOR.extract(
        {_TRACEPARENT_HEADER: traceparent}, getter=_DICT_GETTER
    )
    token = otel_context.attach(context)
    try:
        yield True
    finally:
        otel_context.detach(token)


@contextmanager
def pipeline_span(stage: str, **attributes: Any) -> Iterator[Any]:
    """Create a span representing one pipeline stage."""

    if not _TRACE_AVAILABLE:
        yield None
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(stage) as span:
        if attributes:
            span.set_attributes(attributes)
        try:
            yield span
        except Exception as exc:  # pragma: no cover - exercised via integration
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@contextmanager
def chaos_span(experiment: str, **attributes: Any) -> Iterator[Any]:
    """Instrument chaos engineering experiments with consistent metadata."""

    payload: dict[str, Any] = {"chaos.experiment": experiment}
    payload.update(attributes)
    stage_name = f"chaos.{experiment}"
    with pipeline_span(stage_name, **payload) as span:
        yield span


class _NoOpSpan:
    """Minimal span used when OpenTelemetry is not installed."""

    def set_attributes(
        self, _attrs: Mapping[str, Any]
    ) -> None:  # pragma: no cover - trivial
        return

    def record_exception(
        self, _exc: BaseException
    ) -> None:  # pragma: no cover - trivial
        return

    def set_status(self, _status: Any) -> None:  # pragma: no cover - trivial
        return


class _NoOpSpanContext:
    def __enter__(self) -> _NoOpSpan:  # pragma: no cover - trivial
        return _NoOpSpan()

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        return None


class _NoOpTracer:
    """Tracer compatible stub used when tracing is disabled."""

    def start_as_current_span(
        self, _name: str, **_kwargs: Any
    ) -> _NoOpSpanContext:  # pragma: no cover - trivial
        return _NoOpSpanContext()


if _TRACE_AVAILABLE:

    class SelectiveSampler(Sampler):
        """Sampler favouring hot paths while keeping defaults lightweight."""

        def __init__(
            self,
            *,
            hot_path_globs: Sequence[str] | None = None,
            attribute_flag: str = "pipeline.hot_path",
            default_ratio: float = 1.0,
            hot_ratio: float = 1.0,
        ) -> None:
            self._patterns = tuple(hot_path_globs or ())
            self._attribute_flag = attribute_flag
            self._default_sampler = TraceIdRatioBased(default_ratio)
            self._hot_sampler = TraceIdRatioBased(hot_ratio)

        def _is_hot(self, name: str, attributes: Mapping[str, Any] | None) -> bool:
            lowered_name = name.lower()
            if "failover" in lowered_name:
                return True

            if attributes:
                if self._attribute_flag in attributes and _is_truthy_signal(
                    attributes[self._attribute_flag]
                ):
                    return True

                for alias in _FAILOVER_ATTRIBUTE_KEYS:
                    if alias == self._attribute_flag:
                        continue
                    if alias in attributes and _is_truthy_signal(attributes[alias]):
                        return True

            for pattern in self._patterns:
                if fnmatch.fnmatch(name, pattern):
                    return True
            return False

        def should_sample(
            self,
            parent_context: Any,
            trace_id: int,
            name: str,
            kind: Any,
            attributes: Mapping[str, Any] | None,
            links: Iterable[Any] | None,
        ) -> SamplingResult:
            if self._is_hot(name, attributes):
                return self._hot_sampler.should_sample(
                    parent_context, trace_id, name, kind, attributes, links
                )
            return self._default_sampler.should_sample(
                parent_context, trace_id, name, kind, attributes, links
            )

        def get_description(self) -> str:
            return "SelectiveSampler"

    class PIIFilterSpanProcessor(SpanProcessor):
        """Scrub attributes/events that may contain PII before export."""

        def __init__(
            self,
            *,
            denylist: Sequence[str] | None = None,
            pattern_denylist: Sequence[str] | None = None,
            redaction: str = "[redacted]",
        ) -> None:
            super().__init__()
            self._denylist = {key.lower() for key in (denylist or ())}
            self._patterns = [
                re.compile(fnmatch.translate(pattern), re.IGNORECASE)
                for pattern in (pattern_denylist or [])
            ]
            self._redaction = redaction

        def _matches(self, key: str) -> bool:
            lowered = key.lower()
            if lowered in self._denylist:
                return True
            return any(pattern.match(key) for pattern in self._patterns)

        def on_start(
            self, span: Any, parent_context: Any
        ) -> None:  # pragma: no cover - no-op
            return None

        def on_end(self, span: Any) -> None:
            if not getattr(span, "attributes", None):
                return
            attributes = list(span.attributes.items())
            for key, _ in attributes:
                if self._matches(key):
                    span.set_attribute(key, self._redaction)
            if getattr(span, "events", None):
                for event in span.events:
                    if not getattr(event, "attributes", None):
                        continue
                    for key in list(event.attributes.keys()):
                        if self._matches(key):
                            event.attributes[key] = self._redaction

        def shutdown(self) -> None:  # pragma: no cover - interface requirement
            return None

        def force_flush(
            self, timeout_millis: int = 30000
        ) -> bool:  # pragma: no cover - interface requirement
            return True

else:  # pragma: no cover - optional dependency missing

    class SelectiveSampler:
        def __init__(self, **_: Any) -> None:
            return

    class PIIFilterSpanProcessor:
        def __init__(self, **_: Any) -> None:
            return


__all__ = [
    "TracingConfig",
    "configure_tracing",
    "get_tracer",
    "inject_trace_context",
    "extract_trace_context",
    "current_traceparent",
    "activate_traceparent",
    "pipeline_span",
    "SelectiveSampler",
    "PIIFilterSpanProcessor",
]
