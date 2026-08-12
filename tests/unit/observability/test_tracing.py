# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import importlib
import sys
import types
from unittest import mock

import pytest


class _FakeSamplingResult:
    def __init__(self, source: str) -> None:
        self.source = source


def _install_stub_opentelemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(sys.modules):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            sys.modules.pop(name)

    context_mod = types.ModuleType("opentelemetry.context")
    context_mod._current = None  # type: ignore[attr-defined]

    def attach(ctx):  # type: ignore[no-redef]
        token = context_mod._current  # type: ignore[attr-defined]
        context_mod._current = ctx  # type: ignore[attr-defined]
        return token

    def detach(token):  # type: ignore[no-redef]
        context_mod._current = token  # type: ignore[attr-defined]

    def get_current():
        return context_mod._current  # type: ignore[attr-defined]

    context_mod.attach = attach  # type: ignore[attr-defined]
    context_mod.detach = detach  # type: ignore[attr-defined]
    context_mod.get_current = get_current  # type: ignore[attr-defined]
    sys.modules["opentelemetry.context"] = context_mod

    class StatusCode:
        OK = "OK"
        ERROR = "ERROR"

    class Status:
        def __init__(self, status_code, description="") -> None:
            self.status_code = status_code
            self.description = description

    class _Span:
        def __init__(self, name: str) -> None:
            self.name = name
            self.attributes = {}
            self.events = []
            self.status = None

        def set_attributes(self, attrs):
            self.attributes.update(attrs)

        def set_attribute(self, key, value):
            self.attributes[key] = value

        def record_exception(self, exc):
            self.events.append({"exception": repr(exc)})

        def set_status(self, status):
            self.status = status

    class _SpanContext:
        def __init__(self, span: _Span) -> None:
            self._span = span

        def __enter__(self):
            return self._span

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Tracer:
        def __init__(self, name: str) -> None:
            self.name = name

        def start_as_current_span(self, name, **_):
            span = _Span(name)
            return _SpanContext(span)

    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.Status = Status
    trace_mod.StatusCode = StatusCode
    trace_mod._provider = None

    def set_tracer_provider(provider):
        trace_mod._provider = provider

    def get_tracer(name):
        return _Tracer(name)

    trace_mod.set_tracer_provider = set_tracer_provider
    trace_mod.get_tracer = get_tracer
    sys.modules["opentelemetry.trace"] = trace_mod

    propagate_mod = types.ModuleType("opentelemetry.propagate")
    propagate_state = {"propagator": object()}

    def get_global_textmap():
        return propagate_state["propagator"]

    def set_global_textmap(value):
        propagate_state["propagator"] = value

    propagate_mod.get_global_textmap = get_global_textmap
    propagate_mod.set_global_textmap = set_global_textmap
    sys.modules["opentelemetry.propagate"] = propagate_mod

    class TraceContextTextMapPropagator:
        def inject(self, carrier, setter):
            context = context_mod.get_current()
            if not context:
                return
            traceparent = context.get("traceparent")
            if traceparent:
                setter.set(carrier, "traceparent", traceparent)

        def extract(self, carrier, getter):
            values = getter.get(carrier, "traceparent")
            traceparent = values[0] if values else None
            if traceparent:
                return {"traceparent": traceparent}
            return {}

    tracecontext_mod = types.ModuleType("opentelemetry.trace.propagation.tracecontext")
    tracecontext_mod.TraceContextTextMapPropagator = TraceContextTextMapPropagator
    sys.modules["opentelemetry.trace.propagation.tracecontext"] = tracecontext_mod

    class Resource:
        def __init__(self, attributes):
            self.attributes = attributes

        @classmethod
        def create(cls, attributes):
            return cls(attributes)

    resources_mod = types.ModuleType("opentelemetry.sdk.resources")
    resources_mod.Resource = Resource
    sys.modules["opentelemetry.sdk.resources"] = resources_mod

    class SpanProcessor:
        def __init__(self):
            self.shutdown_called = False

        def shutdown(self):  # pragma: no cover - interface
            self.shutdown_called = True

    class BatchSpanProcessor(SpanProcessor):
        def __init__(self, exporter):
            super().__init__()
            self.exporter = exporter

    class TracerProvider:
        instances = []

        def __init__(self, resource, sampler=None):
            self.resource = resource
            self.sampler = sampler
            self.processors = []
            TracerProvider.instances.append(self)

        def add_span_processor(self, processor):
            self.processors.append(processor)

    trace_sdk_mod = types.ModuleType("opentelemetry.sdk.trace")
    trace_sdk_mod.TracerProvider = TracerProvider
    sys.modules["opentelemetry.sdk.trace"] = trace_sdk_mod

    export_mod = types.ModuleType("opentelemetry.sdk.trace.export")
    export_mod.BatchSpanProcessor = BatchSpanProcessor
    export_mod.SpanProcessor = SpanProcessor
    sys.modules["opentelemetry.sdk.trace.export"] = export_mod

    class Sampler:
        pass

    class TraceIdRatioBased(Sampler):
        def __init__(self, ratio):
            self.ratio = ratio
            self.calls = []

        def should_sample(self, parent_context, trace_id, name, kind, attributes, links):
            self.calls.append(
                {
                    "parent_context": parent_context,
                    "trace_id": trace_id,
                    "name": name,
                    "attributes": attributes,
                }
            )
            return _FakeSamplingResult(f"ratio:{self.ratio}")

    class SamplingResult:
        def __init__(self, decision):
            self.decision = decision

    sampling_mod = types.ModuleType("opentelemetry.sdk.trace.sampling")
    sampling_mod.Sampler = Sampler
    sampling_mod.TraceIdRatioBased = TraceIdRatioBased
    sampling_mod.SamplingResult = SamplingResult
    sys.modules["opentelemetry.sdk.trace.sampling"] = sampling_mod

    class OTLPSpanExporter:
        instances = []

        def __init__(self, endpoint="default", insecure=True):
            self.endpoint = endpoint
            self.insecure = insecure
            OTLPSpanExporter.instances.append(self)

    exporter_mod = types.ModuleType("opentelemetry.exporter")
    otlp_mod = types.ModuleType("opentelemetry.exporter.otlp")
    proto_mod = types.ModuleType("opentelemetry.exporter.otlp.proto")
    grpc_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc")
    trace_exporter_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    trace_exporter_mod.OTLPSpanExporter = OTLPSpanExporter
    sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = trace_exporter_mod
    sys.modules["opentelemetry.exporter.otlp.proto.grpc"] = grpc_mod
    sys.modules["opentelemetry.exporter.otlp.proto"] = proto_mod
    sys.modules["opentelemetry.exporter.otlp"] = otlp_mod
    sys.modules["opentelemetry.exporter"] = exporter_mod

    otel_module = types.ModuleType("opentelemetry")
    otel_module.context = context_mod
    otel_module.trace = trace_mod
    sys.modules["opentelemetry"] = otel_module


@pytest.fixture
def tracing_module(monkeypatch: pytest.MonkeyPatch):
    _install_stub_opentelemetry(monkeypatch)
    import observability.tracing as tracing

    tracing = importlib.reload(tracing)
    yield tracing


def test_selective_sampler_routes_hot_spans(tracing_module):
    sampler = tracing_module.SelectiveSampler(
        hot_path_globs=("signals.*",),
        attribute_flag="pipeline.hot_path",
        default_ratio=0.1,
        hot_ratio=0.9,
    )

    sampler.should_sample(None, 1, "signals.order", None, {"pipeline.hot_path": True}, None)
    sampler.should_sample(None, 2, "signals.cool", None, {"pipeline.hot_path": "true"}, None)
    sampler.should_sample(None, 3, "features.calc", None, {"pipeline.hot_path": False}, None)
    sampler.should_sample(None, 4, "warm.path", None, {}, None)

    assert len(sampler._hot_sampler.calls) == 2
    assert len(sampler._default_sampler.calls) == 2
    hot_names = {call["name"] for call in sampler._hot_sampler.calls}
    assert hot_names == {"signals.order", "signals.cool"}


def test_pii_filter_redacts_attributes_and_events(tracing_module):
    processor = tracing_module.PIIFilterSpanProcessor(
        denylist=["user.email"],
        pattern_denylist=["*secret"],
        redaction="***",
    )

    class FakeEvent:
        def __init__(self, attributes):
            self.attributes = attributes

    class FakeSpan:
        def __init__(self):
            self.attributes = {
                "user.email": "a@example.com",
                "session.id": "abc",
            }
            self.events = [
                FakeEvent({"api.secret": "value", "ok": "1"}),
                FakeEvent({}),
            ]
            self.set_calls = []

        def set_attribute(self, key, value):
            self.attributes[key] = value
            self.set_calls.append((key, value))

    span = FakeSpan()
    processor.on_end(span)

    assert span.attributes["user.email"] == "***"
    assert span.attributes["session.id"] == "abc"
    assert ("user.email", "***") in span.set_calls
    assert span.events[0].attributes["api.secret"] == "***"
    assert span.events[0].attributes["ok"] == "1"


def test_configure_tracing_sets_up_provider(tracing_module, monkeypatch):
    ensure_mock = mock.Mock()
    monkeypatch.setattr(tracing_module, "_ensure_w3c_propagator", ensure_mock)

    config = tracing_module.TracingConfig(
        service_name="geosync",
        exporter_endpoint="grpc://collector",
        exporter_insecure=False,
        pii_attributes=("user.email",),
        enable_w3c_propagation=True,
        default_sample_ratio=0.5,
    )

    result = tracing_module.configure_tracing(config)

    assert result is True
    provider = tracing_module.TracerProvider.instances[-1]
    assert provider.resource.attributes["service.name"] == "geosync"
    assert isinstance(provider.processors[0], tracing_module.BatchSpanProcessor)
    assert any(
        isinstance(proc, tracing_module.PIIFilterSpanProcessor) for proc in provider.processors
    )
    exporter = provider.processors[0].exporter
    assert exporter.endpoint == "grpc://collector"
    assert exporter.insecure is False
    ensure_mock.assert_called_once()


def test_trace_context_helpers_roundtrip(tracing_module):
    carrier = {}
    tracing_module.inject_trace_context(carrier)
    assert carrier == {}

    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    with tracing_module.activate_traceparent(traceparent) as activated:
        assert activated is True
        extracted = tracing_module.extract_trace_context({"traceparent": traceparent})
        assert extracted == {"traceparent": traceparent}
        header = tracing_module.current_traceparent()
        assert header == traceparent
        injected = {}
        tracing_module.inject_trace_context(injected)
        assert injected["traceparent"] == traceparent

    assert tracing_module.current_traceparent() is None
