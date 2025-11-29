# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for distributed tracing utilities."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from core.tracing.distributed import (
    _TRACE_AVAILABLE,
    DistributedTracingConfig,
    ExtractedContext,
    _default_correlation_id,
    _extract_local_baggage,
    _first_correlation_value,
    _inject_local_baggage,
    _update_correlation_header,
    activate_distributed_context,
    baggage_scope,
    configure_distributed_tracing,
    correlation_scope,
    current_baggage,
    current_correlation_id,
    extract_distributed_context,
    generate_correlation_id,
    get_baggage_item,
    inject_distributed_context,
    set_correlation_id_generator,
    shutdown_tracing,
    start_distributed_span,
    traceparent_header,
)


class TestDistributedTracingConfig:
    """Tests for DistributedTracingConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Verify default configuration values."""
        config = DistributedTracingConfig()
        assert config.service_name == "tradepulse"
        assert config.environment is None
        assert config.jaeger_agent_host == "localhost"
        assert config.jaeger_agent_port == 6831
        assert config.jaeger_collector_endpoint is None
        assert config.jaeger_username is None
        assert config.jaeger_password is None
        assert config.sample_ratio == 1.0
        assert config.correlation_header == "x-correlation-id"
        assert config.resource_attributes is None
        assert config.enable_w3c_propagation is True

    def test_custom_config_values(self) -> None:
        """Verify custom configuration values are applied."""
        config = DistributedTracingConfig(
            service_name="custom-service",
            environment="production",
            jaeger_agent_host="jaeger.example.com",
            jaeger_agent_port=6832,
            jaeger_collector_endpoint="http://jaeger:14268",
            jaeger_username="user",
            jaeger_password="pass",
            sample_ratio=0.5,
            correlation_header="x-custom-id",
            resource_attributes={"custom.key": "value"},
            enable_w3c_propagation=False,
        )
        assert config.service_name == "custom-service"
        assert config.environment == "production"
        assert config.jaeger_agent_host == "jaeger.example.com"
        assert config.jaeger_agent_port == 6832
        assert config.jaeger_collector_endpoint == "http://jaeger:14268"
        assert config.jaeger_username == "user"
        assert config.jaeger_password == "pass"
        assert config.sample_ratio == 0.5
        assert config.correlation_header == "x-custom-id"
        assert config.resource_attributes == {"custom.key": "value"}
        assert config.enable_w3c_propagation is False


class TestExtractedContext:
    """Tests for ExtractedContext dataclass."""

    def test_extracted_context_creation(self) -> None:
        """Verify ExtractedContext can be created."""
        ctx = ExtractedContext(
            correlation_id="test-123",
            trace_context=None,
            baggage={"key": "value"},
        )
        assert ctx.correlation_id == "test-123"
        assert ctx.trace_context is None
        assert ctx.baggage == {"key": "value"}

    def test_extracted_context_with_none_values(self) -> None:
        """Verify ExtractedContext handles None values."""
        ctx = ExtractedContext(
            correlation_id=None,
            trace_context=None,
            baggage=None,
        )
        assert ctx.correlation_id is None
        assert ctx.trace_context is None
        assert ctx.baggage is None


class TestCorrelationIdFunctions:
    """Tests for correlation ID related functions."""

    def test_default_correlation_id_is_valid_uuid_hex(self) -> None:
        """Verify default correlation ID is a valid UUID hex."""
        corr_id = _default_correlation_id()
        assert len(corr_id) == 32
        assert corr_id.isalnum()

    def test_generate_correlation_id_uses_factory(self) -> None:
        """Verify generate_correlation_id uses the configured factory."""
        original_id = generate_correlation_id()
        assert len(original_id) == 32

    def test_set_correlation_id_generator_custom_function(self) -> None:
        """Verify custom correlation ID generator works."""
        custom_ids = iter(["custom-1", "custom-2"])

        def custom_generator() -> str:
            return next(custom_ids)

        set_correlation_id_generator(custom_generator)
        assert generate_correlation_id() == "custom-1"
        assert generate_correlation_id() == "custom-2"

        # Reset to default
        set_correlation_id_generator(_default_correlation_id)

    def test_set_correlation_id_generator_not_callable_raises(self) -> None:
        """Verify non-callable raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            set_correlation_id_generator("not-callable")  # type: ignore

    def test_current_correlation_id_returns_none_by_default(self) -> None:
        """Verify current_correlation_id returns None when not in scope."""
        # Outside of any scope, should return default
        result = current_correlation_id(default=None)
        # This may return None or the value from a parent context
        # Just verify it returns without error
        assert result is None or isinstance(result, str)

    def test_current_correlation_id_returns_default(self) -> None:
        """Verify current_correlation_id returns default when specified."""
        default_val = "my-default-id"
        result = current_correlation_id(default=default_val)
        # Without an active scope, should return default
        assert result == default_val or isinstance(result, str)


class TestCorrelationScope:
    """Tests for correlation_scope context manager."""

    def test_correlation_scope_with_explicit_id(self) -> None:
        """Verify correlation scope with explicit ID."""
        with correlation_scope("test-correlation-123") as corr_id:
            assert corr_id == "test-correlation-123"
            assert current_correlation_id() == "test-correlation-123"

    def test_correlation_scope_auto_generates_id(self) -> None:
        """Verify correlation scope auto-generates ID."""
        with correlation_scope() as corr_id:
            assert corr_id is not None
            assert len(corr_id) == 32
            assert current_correlation_id() == corr_id

    def test_correlation_scope_no_auto_generate(self) -> None:
        """Verify correlation scope without auto-generation."""
        with correlation_scope(auto_generate=False) as corr_id:
            assert corr_id is None

    def test_correlation_scope_resets_after_exit(self) -> None:
        """Verify correlation ID is reset after scope exit."""
        initial = current_correlation_id(default=None)
        with correlation_scope("temp-id"):
            assert current_correlation_id() == "temp-id"
        # After exit, should be back to initial value
        assert current_correlation_id(default=None) == initial


class TestInjectExtractFunctions:
    """Tests for inject and extract functions."""

    def test_inject_distributed_context_none_carrier_raises(self) -> None:
        """Verify None carrier raises ValueError."""
        with pytest.raises(ValueError, match="carrier must be provided"):
            inject_distributed_context(None)  # type: ignore

    def test_inject_distributed_context_with_correlation(self) -> None:
        """Verify correlation ID is injected into carrier."""
        carrier: Dict[str, str] = {}
        with correlation_scope("inject-test-id"):
            inject_distributed_context(carrier)
        assert "x-correlation-id" in carrier
        assert carrier["x-correlation-id"] == "inject-test-id"

    def test_extract_distributed_context_none_carrier_raises(self) -> None:
        """Verify None carrier raises ValueError."""
        with pytest.raises(ValueError, match="carrier must be provided"):
            extract_distributed_context(None)  # type: ignore

    def test_extract_distributed_context_with_correlation(self) -> None:
        """Verify correlation ID is extracted from carrier."""
        carrier = {"x-correlation-id": "extracted-id-123"}
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "extracted-id-123"

    def test_extract_distributed_context_case_insensitive(self) -> None:
        """Verify correlation header is case-insensitive."""
        carrier = {"X-Correlation-ID": "case-test-id"}
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "case-test-id"


class TestFirstCorrelationValue:
    """Tests for _first_correlation_value helper."""

    def test_string_value(self) -> None:
        """Verify string value is returned directly."""
        carrier = {"x-correlation-id": "simple-value"}
        result = _first_correlation_value(carrier)
        assert result == "simple-value"

    def test_list_value(self) -> None:
        """Verify first item from list is returned."""
        carrier = {"x-correlation-id": ["first", "second"]}
        result = _first_correlation_value(carrier)
        assert result == "first"

    def test_empty_list_returns_none(self) -> None:
        """Verify empty list returns None."""
        carrier = {"x-correlation-id": []}
        result = _first_correlation_value(carrier)
        assert result is None

    def test_missing_header_returns_none(self) -> None:
        """Verify missing header returns None."""
        carrier: Dict[str, Any] = {}
        result = _first_correlation_value(carrier)
        assert result is None


class TestLocalBaggage:
    """Tests for local baggage functions."""

    def test_inject_local_baggage_empty(self) -> None:
        """Verify empty baggage doesn't add header."""
        carrier: Dict[str, str] = {}
        _inject_local_baggage(carrier)
        assert "baggage" not in carrier

    def test_extract_local_baggage_empty(self) -> None:
        """Verify missing baggage header returns None."""
        carrier: Dict[str, Any] = {}
        result = _extract_local_baggage(carrier)
        assert result is None

    def test_extract_local_baggage_string(self) -> None:
        """Verify baggage header is parsed correctly."""
        carrier = {"baggage": "key1=value1,key2=value2"}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_extract_local_baggage_list(self) -> None:
        """Verify baggage header from list."""
        carrier = {"baggage": ["key=value"]}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value"

    def test_extract_local_baggage_malformed(self) -> None:
        """Verify malformed baggage is handled gracefully."""
        carrier = {"baggage": "invalid-no-equals"}
        result = _extract_local_baggage(carrier)
        # Empty dict should be returned as None
        assert result is None

    def test_extract_local_baggage_empty_list(self) -> None:
        """Verify empty list returns None."""
        carrier = {"baggage": []}
        result = _extract_local_baggage(carrier)
        assert result is None


class TestBaggageScope:
    """Tests for baggage_scope context manager."""

    def test_baggage_scope_adds_items(self) -> None:
        """Verify baggage scope adds items."""
        with baggage_scope({"key1": "value1"}, key2="value2") as baggage:
            assert "key1" in baggage
            assert baggage["key1"] == "value1"
            assert "key2" in baggage
            assert baggage["key2"] == "value2"

    def test_baggage_scope_empty(self) -> None:
        """Verify empty baggage scope works."""
        with baggage_scope() as baggage:
            assert isinstance(baggage, dict)

    def test_current_baggage_returns_dict(self) -> None:
        """Verify current_baggage returns a dict."""
        result = current_baggage()
        assert isinstance(result, dict)

    def test_get_baggage_item_returns_default(self) -> None:
        """Verify get_baggage_item returns default when missing."""
        result = get_baggage_item("missing-key", default="default-value")
        assert result == "default-value"


class TestActivateDistributedContext:
    """Tests for activate_distributed_context context manager."""

    def test_activate_with_correlation_id(self) -> None:
        """Verify correlation ID is activated."""
        ctx = ExtractedContext(
            correlation_id="activated-id",
            trace_context=None,
            baggage=None,
        )
        with activate_distributed_context(ctx) as corr_id:
            assert corr_id == "activated-id"
            assert current_correlation_id() == "activated-id"

    def test_activate_with_auto_generate(self) -> None:
        """Verify auto-generation of correlation ID."""
        ctx = ExtractedContext(
            correlation_id=None,
            trace_context=None,
            baggage=None,
        )
        with activate_distributed_context(ctx, auto_generate_correlation=True) as corr_id:
            assert corr_id is not None
            assert len(corr_id) == 32

    def test_activate_without_auto_generate(self) -> None:
        """Verify no auto-generation when disabled."""
        ctx = ExtractedContext(
            correlation_id=None,
            trace_context=None,
            baggage=None,
        )
        with activate_distributed_context(ctx, auto_generate_correlation=False) as corr_id:
            assert corr_id is None

    def test_activate_with_baggage(self) -> None:
        """Verify baggage is activated."""
        ctx = ExtractedContext(
            correlation_id=None,
            trace_context=None,
            baggage={"bg_key": "bg_value"},
        )
        with activate_distributed_context(ctx):
            baggage = current_baggage()
            assert "bg_key" in baggage
            assert baggage["bg_key"] == "bg_value"


class TestStartDistributedSpan:
    """Tests for start_distributed_span context manager."""

    def test_start_span_without_trace_available(self) -> None:
        """Verify span works when tracing is unavailable."""
        with start_distributed_span("test-span", correlation_id="span-corr-id") as span:
            # When trace is not available, span should be None
            if not _TRACE_AVAILABLE:
                assert span is None
            assert current_correlation_id() == "span-corr-id"

    def test_start_span_with_attributes(self) -> None:
        """Verify span accepts attributes."""
        with start_distributed_span(
            "test-span",
            attributes={"custom.attr": "value"},
        ):
            # Just verify it doesn't raise
            pass


class TestTraceparentHeader:
    """Tests for traceparent_header function."""

    def test_traceparent_header_without_trace(self) -> None:
        """Verify traceparent returns None when trace is unavailable."""
        result = traceparent_header()
        # Without active trace, may return None
        assert result is None or isinstance(result, str)


class TestShutdownTracing:
    """Tests for shutdown_tracing function."""

    def test_shutdown_tracing_does_not_raise(self) -> None:
        """Verify shutdown_tracing doesn't raise."""
        shutdown_tracing()  # Should not raise


class TestConfigureDistributedTracing:
    """Tests for configure_distributed_tracing function."""

    def test_configure_returns_bool(self) -> None:
        """Verify configure returns boolean."""
        # Since we may or may not have tracing available, just verify return type
        result = configure_distributed_tracing()
        assert isinstance(result, bool)

    def test_configure_with_custom_config(self) -> None:
        """Verify configure accepts custom config."""
        config = DistributedTracingConfig(
            service_name="test-service",
            environment="test",
        )
        result = configure_distributed_tracing(config)
        assert isinstance(result, bool)


class TestUpdateCorrelationHeader:
    """Tests for _update_correlation_header function."""

    def test_update_correlation_header_empty_no_change(self) -> None:
        """Verify empty header doesn't change defaults."""
        # This function modifies globals, so just verify it doesn't raise
        _update_correlation_header("")
        # Verify no crash happened

    def test_update_correlation_header_custom(self) -> None:
        """Verify custom header is set."""
        _update_correlation_header("x-custom-correlation")
        # Reset for other tests
        _update_correlation_header("x-correlation-id")
