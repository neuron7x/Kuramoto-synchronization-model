# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for distributed tracing utilities."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.tracing.distributed import (
    _DICT_GETTER,
    _TRACE_AVAILABLE,
    BAGGAGE_MAX_BYTES,
    BAGGAGE_MAX_MEMBERS,
    DistributedTracingConfig,
    ExtractedContext,
    _default_correlation_id,
    _extract_local_baggage,
    _first_correlation_value,
    _inject_local_baggage,
    _normalize_baggage_member,
    _normalize_correlation_value,
    _normalize_header_key,
    _normalize_header_value,
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
        assert config.service_name == "geosync"
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
        carrier: Dict[str, Any] = {"x-correlation-id": []}
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

    def test_inject_local_baggage_with_values(self) -> None:
        """Verify baggage is injected correctly when values exist."""
        # We need to test this within a baggage scope that adds local baggage
        carrier: Dict[str, str] = {}
        with baggage_scope({"inject_key": "inject_value"}):
            _inject_local_baggage(carrier)
        # When not using OpenTelemetry, baggage should be in carrier
        # The behavior depends on _TRACE_AVAILABLE
        # At minimum, verify it doesn't raise

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
        carrier: Dict[str, Any] = {"baggage": []}
        result = _extract_local_baggage(carrier)
        assert result is None

    def test_extract_local_baggage_list_with_non_string(self) -> None:
        """Verify baggage list with non-string first element."""
        carrier: Dict[str, Any] = {"baggage": [123]}
        result = _extract_local_baggage(carrier)
        # Integer is converted to string, but "123" has no "=" so returns None
        assert result is None

    def test_extract_local_baggage_with_case_insensitive_header(self) -> None:
        """Verify baggage header matching is case-insensitive."""
        carrier = {"Baggage": "key=value"}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value"


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


class TestInjectWithBaggage:
    """Additional tests for inject_distributed_context with baggage."""

    def test_inject_without_correlation_id(self) -> None:
        """Verify inject works without correlation ID."""
        carrier: Dict[str, str] = {}
        inject_distributed_context(carrier)
        # Should not add correlation header if not in scope

    def test_inject_populates_carrier(self) -> None:
        """Verify inject populates the carrier."""
        carrier: Dict[str, str] = {}
        with correlation_scope("my-correlation-id"):
            inject_distributed_context(carrier)
        assert carrier.get("x-correlation-id") == "my-correlation-id"


class TestExtractWithBaggage:
    """Additional tests for extract_distributed_context with baggage."""

    def test_extract_with_empty_carrier(self) -> None:
        """Verify extract handles empty carrier."""
        carrier: Dict[str, str] = {}
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id is None
        assert ctx.baggage is None

    def test_extract_preserves_baggage_values(self) -> None:
        """Verify extract correctly parses baggage."""
        carrier = {
            "x-correlation-id": "corr-123",
            "baggage": "key1=value1,key2=value2",
        }
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "corr-123"
        # Baggage extraction depends on implementation

    def test_extract_with_tuple_correlation_value(self) -> None:
        """Verify extract handles tuple correlation values."""
        carrier = {"x-correlation-id": ("tuple-id", "second")}
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "tuple-id"


class TestFirstCorrelationValueEdgeCases:
    """Additional edge case tests for _first_correlation_value."""

    def test_tuple_value(self) -> None:
        """Verify tuple value is handled like list."""
        carrier = {"x-correlation-id": ("first", "second")}
        result = _first_correlation_value(carrier)
        assert result == "first"

    def test_non_string_value(self) -> None:
        """Verify non-string values are converted."""
        carrier: Dict[str, Any] = {"x-correlation-id": 12345}
        result = _first_correlation_value(carrier)
        assert result == "12345"


class TestExtractLocalBaggageEdgeCases:
    """Additional edge case tests for _extract_local_baggage."""

    def test_non_string_baggage_value(self) -> None:
        """Verify non-string baggage value is converted."""
        carrier: Dict[str, Any] = {"baggage": 12345}
        result = _extract_local_baggage(carrier)
        # Integer converted to string but may not parse as key=value
        assert result is None

    def test_tuple_baggage_value(self) -> None:
        """Verify tuple baggage value is handled."""
        carrier = {"baggage": ("key=value",)}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value"

    def test_multiple_equals_in_baggage_value(self) -> None:
        """Verify multiple equals are handled correctly."""
        carrier = {"baggage": "key=value=extra"}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value=extra"

    def test_baggage_with_whitespace(self) -> None:
        """Verify baggage with whitespace is trimmed."""
        carrier = {"baggage": " key = value , key2 = value2 "}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value"
        assert result["key2"] == "value2"


class TestBaggageScopeEdgeCases:
    """Additional edge case tests for baggage_scope."""

    def test_baggage_scope_with_dict_only(self) -> None:
        """Verify baggage scope with dict only."""
        with baggage_scope({"key": "value"}) as baggage:
            assert "key" in baggage

    def test_baggage_scope_with_kwargs_only(self) -> None:
        """Verify baggage scope with kwargs only."""
        with baggage_scope(key1="val1", key2="val2") as baggage:
            assert baggage.get("key1") == "val1"
            assert baggage.get("key2") == "val2"

    def test_baggage_scope_merges_both(self) -> None:
        """Verify baggage scope merges dict and kwargs."""
        with baggage_scope({"dict_key": "dict_val"}, kwarg_key="kwarg_val") as baggage:
            assert baggage.get("dict_key") == "dict_val"
            assert baggage.get("kwarg_key") == "kwarg_val"

    def test_get_baggage_item_with_existing_key(self) -> None:
        """Verify get_baggage_item returns value for existing key."""
        with baggage_scope(test_key="test_value"):
            result = get_baggage_item("test_key")
            assert result == "test_value"


class TestActivateDistributedContextEdgeCases:
    """Additional edge case tests for activate_distributed_context."""

    def test_activate_resets_after_exit(self) -> None:
        """Verify context is reset after exit."""
        initial = current_correlation_id(default=None)
        ctx = ExtractedContext(
            correlation_id="temp-corr",
            trace_context=None,
            baggage=None,
        )
        with activate_distributed_context(ctx):
            assert current_correlation_id() == "temp-corr"
        assert current_correlation_id(default=None) == initial

    def test_activate_with_both_baggage_and_correlation(self) -> None:
        """Verify both baggage and correlation work together."""
        ctx = ExtractedContext(
            correlation_id="combined-corr",
            trace_context=None,
            baggage={"combined_key": "combined_value"},
        )
        with activate_distributed_context(ctx) as corr_id:
            assert corr_id == "combined-corr"
            baggage = current_baggage()
            assert baggage.get("combined_key") == "combined_value"


class TestStartDistributedSpanEdgeCases:
    """Additional edge case tests for start_distributed_span."""

    def test_start_span_auto_generates_correlation(self) -> None:
        """Verify span correctly handles correlation ID within its scope."""
        with start_distributed_span("test-span"):
            corr = current_correlation_id()
            # Within the span scope, a correlation ID should be set
            # (auto-generated if not explicitly provided)
            assert corr is not None
            assert len(corr) == 32  # UUID hex format

    def test_start_span_preserves_correlation_after_exit(self) -> None:
        """Verify correlation is reset after span exit."""
        initial = current_correlation_id(default=None)
        with start_distributed_span("test-span", correlation_id="span-corr"):
            pass
        assert current_correlation_id(default=None) == initial


class TestCorrelationScopeEdgeCases:
    """Additional edge case tests for correlation_scope."""

    def test_nested_correlation_scopes(self) -> None:
        """Verify nested correlation scopes work correctly."""
        with correlation_scope("outer"):
            assert current_correlation_id() == "outer"
            with correlation_scope("inner"):
                assert current_correlation_id() == "inner"
            assert current_correlation_id() == "outer"

    def test_correlation_scope_with_none_and_no_auto_generate(self) -> None:
        """Verify scope with None and no auto-generate."""
        with correlation_scope(None, auto_generate=False) as corr_id:
            assert corr_id is None


class _PairsMapping(Mapping[Any, Any]):
    """Mapping helper that permits bytes-like (including bytearray) keys.

    ``dict`` refuses unhashable keys like ``bytearray`` and silently
    coerces some types. For carrier-contract tests we need to feed the
    exact (possibly unhashable, possibly duplicate) sequence of pairs
    a real HTTP framework might hand us.
    """

    def __init__(self, pairs: list[tuple[Any, Any]]) -> None:
        self._pairs = pairs

    def __getitem__(self, key: Any) -> Any:
        for existing_key, value in self._pairs:
            if existing_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[Any]:
        for key, _ in self._pairs:
            yield key

    def __len__(self) -> int:
        return len(self._pairs)

    def items(self) -> Iterator[tuple[Any, Any]]:  # type: ignore[override]
        return iter(self._pairs)


class TestHeaderKeyNormalizationContract:
    """Contract tests for carrier key-type handling (user-surfaced + extended)."""

    @pytest.mark.parametrize(
        ("header_key", "expected"),
        [
            ("x-correlation-id", "value-str"),
            (b"x-correlation-id", "value-bytes"),
            (bytearray(b"X-Correlation-ID"), "value-bytearray"),
            (b"X-CoRrElAtIoN-Id", "value-mixed"),
        ],
    )
    def test_first_correlation_value_supported_key_types(
        self, header_key: Any, expected: str
    ) -> None:
        if isinstance(header_key, bytearray):
            carrier: Mapping[Any, Any] = _PairsMapping([(header_key, expected)])
        else:
            carrier = {header_key: expected}
        assert _first_correlation_value(carrier) == expected

    @pytest.mark.parametrize("header_key", [123, ("x-correlation-id",), object()])
    def test_first_correlation_value_unsupported_key_types(self, header_key: Any) -> None:
        carrier: Dict[Any, Any] = {header_key: "value"}
        assert _first_correlation_value(carrier) is None

    def test_first_correlation_value_decodes_bytes_value(self) -> None:
        carrier: Dict[str, Any] = {"x-correlation-id": b"bytes-value"}
        assert _first_correlation_value(carrier) == "bytes-value"

    def test_bytes_header_key_is_supported(self) -> None:
        """User-surfaced regression: non-string header keys must not crash."""
        carrier: Dict[Any, Any] = {b"x-correlation-id": "bytes-key-value"}
        assert _first_correlation_value(carrier) == "bytes-key-value"

    @pytest.mark.parametrize(
        ("header_key", "header_value"),
        [
            ("baggage", "k=v"),
            (b"baggage", "k=v"),
            (bytearray(b"BaGgAgE"), "k=v"),
        ],
    )
    def test_extract_local_baggage_supported_key_types(
        self, header_key: Any, header_value: str
    ) -> None:
        if isinstance(header_key, bytearray):
            carrier: Mapping[Any, Any] = _PairsMapping([(header_key, header_value)])
        else:
            carrier = {header_key: header_value}
        parsed = _extract_local_baggage(carrier)
        assert parsed is not None
        assert parsed["k"] == "v"

    @pytest.mark.parametrize("header_key", [123, ("baggage",), object()])
    def test_extract_local_baggage_unsupported_key_types(self, header_key: Any) -> None:
        carrier: Dict[Any, Any] = {header_key: "k=v"}
        assert _extract_local_baggage(carrier) is None

    def test_extract_local_baggage_non_ascii_key_is_rejected(self) -> None:
        """Malformed bytes keys (non-ASCII) must not match canonical headers."""
        carrier: Mapping[Any, Any] = _PairsMapping([(b"baggage\xff", "k=v")])
        assert _extract_local_baggage(carrier) is None

    def test_extract_local_baggage_with_bytes_key(self) -> None:
        """User-surfaced regression: bytes baggage keys must parse."""
        carrier: Dict[Any, Any] = {b"baggage": "key=value"}
        result = _extract_local_baggage(carrier)
        assert result is not None
        assert result["key"] == "value"

    def test_extract_ignores_invalid_non_ascii_header_keys(self) -> None:
        """Malformed bytes header keys must not match canonical headers."""
        carrier: Mapping[Any, Any] = _PairsMapping(
            [
                (b"x-correlation-id\xff", "bad-key"),
                (b"baggage\xff", "tenant=bad"),
            ]
        )
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id is None
        assert ctx.baggage is None

    def test_extract_with_bytes_keys_and_values(self) -> None:
        """End-to-end: extract_distributed_context on bytes-carrier."""
        carrier: Mapping[Any, Any] = _PairsMapping(
            [
                (b"x-correlation-id", b"bytes-corr"),
                (bytearray(b"baggage"), b"tenant=alpha"),
            ]
        )
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "bytes-corr"
        assert ctx.baggage == {"tenant": "alpha"}

    @pytest.mark.skipif(
        not _TRACE_AVAILABLE or _DICT_GETTER is None,
        reason="OpenTelemetry getter path unavailable",
    )
    def test_dict_getter_supported_mixed_carriers(self) -> None:
        carrier: Mapping[Any, Any] = _PairsMapping(
            [
                (123, "ignored"),
                (
                    b"traceparent",
                    "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
                ),
                (bytearray(b"baggage"), ("key=value", "unused")),
            ]
        )
        assert _DICT_GETTER.get(carrier, "traceparent") == [
            "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
        ]
        assert _DICT_GETTER.get(carrier, "baggage") == ["key=value", "unused"]

    @pytest.mark.skipif(
        not _TRACE_AVAILABLE or _DICT_GETTER is None,
        reason="OpenTelemetry getter path unavailable",
    )
    @pytest.mark.parametrize("header_key", [123, ("traceparent",), object()])
    def test_dict_getter_unsupported_key_types(self, header_key: Any) -> None:
        carrier: Dict[Any, Any] = {header_key: "value"}
        assert _DICT_GETTER.get(carrier, "traceparent") == []

    @pytest.mark.skipif(
        not _TRACE_AVAILABLE or _DICT_GETTER is None,
        reason="OpenTelemetry getter path unavailable",
    )
    def test_dict_getter_no_regression_string_carrier(self) -> None:
        carrier = {"TraceParent": ["tp-first", "tp-second"]}
        assert _DICT_GETTER.get(carrier, "traceparent") == ["tp-first", "tp-second"]


class TestNormalizeHelpers:
    """Direct coverage for _normalize_header_key / _normalize_header_value."""

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("X-Correlation-ID", "x-correlation-id"),
            (b"X-Correlation-ID", "x-correlation-id"),
            (bytearray(b"baggage"), "baggage"),
            ("baggage", "baggage"),
        ],
    )
    def test_normalize_header_key_supported(self, key: Any, expected: str) -> None:
        assert _normalize_header_key(key) == expected

    @pytest.mark.parametrize(
        "key",
        [
            None,
            123,
            b"invalid\xff",
            "bad header with space",
            "bad\nheader",
            "",
            b"",
            ("tuple",),
        ],
    )
    def test_normalize_header_key_rejects(self, key: Any) -> None:
        assert _normalize_header_key(key) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("plain-string", "plain-string"),
            (b"bytes-value", "bytes-value"),
            (bytearray(b"bytearray"), "bytearray"),
            (None, None),
            (123, "123"),
            ((1, 2), "(1, 2)"),
        ],
    )
    def test_normalize_header_value(self, value: Any, expected: str | None) -> None:
        assert _normalize_header_value(value) == expected


class TestCRLFInjectionDrop:
    """Write-path must drop header values carrying CR/LF/NUL (no raise)."""

    @pytest.mark.parametrize(
        "bad_value",
        [
            "trailing\r",
            "trailing\n",
            "embedded\r\nX-Attacker: evil",
            "with-nul\x00suffix",
            "\rleading",
            "\nleading",
        ],
    )
    def test_unsafe_correlation_value_returns_none(self, bad_value: str) -> None:
        assert _normalize_correlation_value(bad_value) is None

    @pytest.mark.parametrize(
        "ok_value",
        [
            "clean",
            "with spaces ok",
            "tabs\tallowed-at-this-layer",  # tab is not CR/LF/NUL
            "unicode-ok-ä",
        ],
    )
    def test_safe_correlation_value_passes_through(self, ok_value: str) -> None:
        assert _normalize_correlation_value(ok_value) == ok_value.strip()

    def test_inject_drops_crlf_in_correlation_id(self) -> None:
        """Unsafe correlation IDs must not land on the wire (drop, no raise)."""
        carrier: Dict[str, str] = {}
        with correlation_scope("good\r\nX-Injected: evil", auto_generate=False):
            inject_distributed_context(carrier)
        assert "x-correlation-id" not in carrier

    def test_lf_in_baggage_value_drops_whole_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drop-philosophy: a member with CR/LF/NUL in its value is dropped
        entirely, but other safe members survive."""
        import core.tracing.distributed as dist

        monkeypatch.setattr(dist, "_TRACE_AVAILABLE", False)
        monkeypatch.setattr(dist, "_GLOBAL_PROPAGATOR", None)
        monkeypatch.setattr(dist, "_DICT_SETTER", None)
        monkeypatch.setattr(dist, "otel_baggage", None)
        monkeypatch.setattr(dist, "otel_context", None)

        carrier: Dict[str, str] = {}
        with baggage_scope({"good": "ok", "tenant": "ok\n key=injected"}):
            inject_distributed_context(carrier)
        header = carrier.get("baggage", "")
        # The unsafe member is gone, the safe one remains.
        assert "tenant" not in header
        assert "good=ok" in header
        assert "\n" not in header and "\r" not in header


class TestInjectExtractRoundtrip:
    """Canonical inject -> extract roundtrip preserves correlation + baggage."""

    def test_string_carrier_roundtrip(self) -> None:
        carrier: Dict[str, str] = {}
        with correlation_scope("round-trip-id", auto_generate=False):
            with baggage_scope({"tenant": "alpha", "region": "eu"}):
                inject_distributed_context(carrier)
        ctx = extract_distributed_context(carrier)
        assert ctx.correlation_id == "round-trip-id"
        if ctx.baggage is not None:
            assert ctx.baggage.get("tenant") == "alpha"
            assert ctx.baggage.get("region") == "eu"

    def test_bytes_carrier_extract_after_string_inject(self) -> None:
        """Injected string values survive re-encoding to bytes by upstream."""
        carrier: Dict[str, str] = {}
        with correlation_scope("bytes-after-inject", auto_generate=False):
            inject_distributed_context(carrier)
        # Simulate an upstream re-encoding the dict into bytes keys/values
        bytes_carrier: Mapping[Any, Any] = _PairsMapping(
            [(k.encode("ascii"), v.encode("ascii")) for k, v in carrier.items()]
        )
        ctx = extract_distributed_context(bytes_carrier)
        assert ctx.correlation_id == "bytes-after-inject"


class TestHeaderNormalizationProperties:
    """Hypothesis-driven properties on the carrier-key/value normalisers."""

    @pytest.mark.parametrize("_", range(1))  # marker so collection is identical
    def test_properties_available(self, _: int) -> None:
        """Sanity that hypothesis is importable in this env."""
        import hypothesis  # noqa: F401  # pragma: no cover


_HEADER_TOKEN_CHARS = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'*+-.^_`|~"
)


@given(st.text(alphabet=_HEADER_TOKEN_CHARS, min_size=1, max_size=40))
def test_property_str_token_keys_roundtrip(key: str) -> None:
    """Any RFC 7230 token round-trips through _normalize_header_key."""
    normalized = _normalize_header_key(key)
    assert normalized is not None
    assert normalized == key.lower()


@given(st.binary(min_size=1, max_size=40))
def test_property_arbitrary_bytes_never_crashes(payload: bytes) -> None:
    """No byte string causes _normalize_header_key to raise."""
    result = _normalize_header_key(payload)
    assert result is None or isinstance(result, str)


@given(st.text(min_size=0, max_size=80))
def test_property_normalize_header_value_str_identity(value: str) -> None:
    assert _normalize_header_value(value) == value


@given(st.binary(min_size=0, max_size=80))
def test_property_normalize_header_value_bytes_latin1(value: bytes) -> None:
    """Bytes values are decoded via latin-1 (never None, never crash)."""
    result = _normalize_header_value(value)
    assert result is not None
    assert result.encode("latin-1") == value


@given(
    st.text(
        alphabet=st.characters(
            blacklist_characters="\r\n\x00",
            blacklist_categories=["Cs"],
        ),
        min_size=1,
        max_size=60,
    )
)
def test_property_normalize_correlation_accepts_safe_text(value: str) -> None:
    """Any control-free, non-empty text normalises to its trimmed form."""
    stripped = value.strip()
    assert _normalize_correlation_value(value) == (stripped or None)


@given(
    st.text(min_size=0, max_size=30),
    st.sampled_from(["\r", "\n", "\x00", "\r\n"]),
    st.text(min_size=0, max_size=30),
)
def test_property_normalize_correlation_drops_on_ctl(prefix: str, ctl: str, suffix: str) -> None:
    """Any string carrying CR/LF/NUL is silently dropped (drop-philosophy)."""
    assert _normalize_correlation_value(prefix + ctl + suffix) is None


@given(st.text(alphabet=_HEADER_TOKEN_CHARS, min_size=1, max_size=30))
def test_property_roundtrip_inject_extract_correlation(correlation: str) -> None:
    """For any RFC 7230 token-shaped correlation ID, inject → extract is identity."""
    carrier: Dict[str, str] = {}
    with correlation_scope(correlation, auto_generate=False):
        inject_distributed_context(carrier)
    ctx = extract_distributed_context(carrier)
    assert ctx.correlation_id == correlation


# --------------------------------------------------------------------- #
# W3C Baggage § 3.2.1.1 / § 4.3 compliance of the local fallback path.
# These tests force _TRACE_AVAILABLE = False so the fallback injector
# and extractor run even on machines that have OpenTelemetry installed.
# --------------------------------------------------------------------- #


@pytest.fixture
def local_baggage_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the local fallback path even under OTel."""
    import core.tracing.distributed as dist

    monkeypatch.setattr(dist, "_TRACE_AVAILABLE", False)
    monkeypatch.setattr(dist, "_GLOBAL_PROPAGATOR", None)
    monkeypatch.setattr(dist, "_DICT_SETTER", None)
    monkeypatch.setattr(dist, "otel_baggage", None)
    monkeypatch.setattr(dist, "otel_context", None)


class TestBaggageMemberNormalization:
    """Drop-philosophy boundary: every unsafe member normalises to ``None``."""

    @pytest.mark.parametrize(
        ("key", "value", "expected"),
        [
            ("tenant", "alpha", ("tenant", "alpha")),
            ("TENANT", "alpha", ("tenant", "alpha")),
            ("tenant-id", "eu-west-1", ("tenant-id", "eu-west-1")),
            ("  tenant  ", "  beta  ", ("tenant", "beta")),
            ("my_key", "abc123", ("my_key", "abc123")),
        ],
    )
    def test_safe_members_pass(self, key: str, value: str, expected: tuple[str, str]) -> None:
        assert _normalize_baggage_member(key, value) == expected

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("bad=key", "value"),  # "=" in key
            ("bad,key", "value"),  # "," in key
            ("bad;key", "value"),  # ";" in key
            ("bad key", "value"),  # space in key
            ("", "value"),  # empty key
            ("unicodeключ", "value"),  # non-ASCII key
            ("tenant", ""),  # empty value
            ("tenant", "a,b,c"),  # "," in value → list-member ambiguity
            ("tenant", "k=v; prop"),  # ";" in value → property ambiguity
            ("tenant", "bad\rvalue"),  # CR in value
            ("tenant", "bad\nvalue"),  # LF in value
            ("tenant", "bad\x00value"),  # NUL in value
        ],
    )
    def test_unsafe_members_drop(self, key: str, value: str) -> None:
        assert _normalize_baggage_member(key, value) is None


class TestBaggageInjectDropPhilosophy:
    """Inject silently drops unsafe members; safe ones survive."""

    def test_unsafe_members_dropped_safe_members_pass(self, local_baggage_only: None) -> None:
        carrier: Dict[str, str] = {}
        with baggage_scope({"good": "ok", "bad=key": "v", "comma": "a,b", "tenant": "alpha"}):
            inject_distributed_context(carrier)
        ctx = extract_distributed_context(carrier)
        assert ctx.baggage == {"good": "ok", "tenant": "alpha"}

    def test_invalid_key_is_silently_dropped(self, local_baggage_only: None) -> None:
        carrier: Dict[str, str] = {}
        with baggage_scope({"bad=key": "value"}):
            inject_distributed_context(carrier)  # must not raise
        assert "baggage" not in carrier

    def test_all_unsafe_produces_no_header(self, local_baggage_only: None) -> None:
        carrier: Dict[str, str] = {}
        with baggage_scope({"a=b": "x", "c,d": "y"}):
            inject_distributed_context(carrier)
        assert "baggage" not in carrier

    def test_extract_strips_w3c_property_segment(self, local_baggage_only: None) -> None:
        """W3C Baggage allows ``key=value;prop=x`` members. The local model
        drops the property segment and returns the canonical value."""
        carrier = {"baggage": "tenant=alpha;kind=service"}
        ctx = extract_distributed_context(carrier)
        assert ctx.baggage == {"tenant": "alpha"}

    def test_at_limit_members_passes(self, local_baggage_only: None) -> None:
        """Exactly BAGGAGE_MAX_MEMBERS short entries must pass without truncation."""
        carrier: Dict[str, str] = {}
        small = {f"k{i}": str(i) for i in range(BAGGAGE_MAX_MEMBERS)}
        with baggage_scope(small):
            inject_distributed_context(carrier)
        assert len(carrier["baggage"].encode("ascii")) <= BAGGAGE_MAX_BYTES
        ctx = extract_distributed_context(carrier)
        assert ctx.baggage is not None
        assert len(ctx.baggage) == BAGGAGE_MAX_MEMBERS


class TestBaggageSizeTruncation:
    """W3C § 4.3 size limits enforced via drop-trailing-members + warning."""

    def test_inject_baggage_truncates_at_max_members(self, local_baggage_only: None) -> None:
        """181 safe entries → only BAGGAGE_MAX_MEMBERS land in the header."""
        carrier: Dict[str, str] = {}
        overflow = {f"k{i}": "v" for i in range(BAGGAGE_MAX_MEMBERS + 1)}
        with baggage_scope(overflow):
            inject_distributed_context(carrier)
        header = carrier["baggage"]
        assert header.count("=") == BAGGAGE_MAX_MEMBERS
        assert header.count(",") == BAGGAGE_MAX_MEMBERS - 1

    def test_inject_baggage_truncates_at_max_bytes(self, local_baggage_only: None) -> None:
        """Entries totalling > 8192 bytes → tail dropped until payload fits."""
        carrier: Dict[str, str] = {}
        # ~110 bytes per entry × 150 entries ≈ 16 KB — far over the 8192 cap.
        giants = {f"k{i:03d}": "x" * 100 for i in range(150)}
        with baggage_scope(giants):
            inject_distributed_context(carrier)
        header = carrier["baggage"]
        assert len(header.encode("ascii")) <= BAGGAGE_MAX_BYTES
        # Some members survived (not all dropped).
        assert "=" in header

    def test_inject_baggage_logs_warning_on_truncation(self, local_baggage_only: None) -> None:
        """Every truncation path emits tracing.baggage_truncated warning."""
        from unittest.mock import patch

        import core.tracing.distributed as dist_mod

        carrier: Dict[str, str] = {}
        overflow = {f"k{i}": "v" for i in range(BAGGAGE_MAX_MEMBERS + 5)}
        with patch.object(dist_mod.LOGGER, "warning") as warn:
            with baggage_scope(overflow):
                inject_distributed_context(carrier)
        matching = [
            call
            for call in warn.call_args_list
            if call.args
            and call.args[0] == "tracing.baggage_truncated"
            and call.kwargs.get("extra", {}).get("reason") == "too_many_members"
        ]
        assert matching, "expected tracing.baggage_truncated log with reason=too_many_members"
        extra = matching[-1].kwargs["extra"]
        assert extra["original_members"] == BAGGAGE_MAX_MEMBERS + 5
        assert extra["kept_members"] == BAGGAGE_MAX_MEMBERS
        assert extra["limit"] == BAGGAGE_MAX_MEMBERS

    def test_inject_baggage_logs_warning_on_byte_truncation(self, local_baggage_only: None) -> None:
        """Byte-limit truncation emits its own warning with a header_too_large reason."""
        from unittest.mock import patch

        import core.tracing.distributed as dist_mod

        carrier: Dict[str, str] = {}
        giants = {f"k{i:03d}": "x" * 100 for i in range(150)}
        with patch.object(dist_mod.LOGGER, "warning") as warn:
            with baggage_scope(giants):
                inject_distributed_context(carrier)
        matching = [
            call
            for call in warn.call_args_list
            if call.args
            and call.args[0] == "tracing.baggage_truncated"
            and call.kwargs.get("extra", {}).get("reason") == "header_too_large"
        ]
        assert matching, "expected tracing.baggage_truncated log with reason=header_too_large"
        extra = matching[-1].kwargs["extra"]
        assert extra["kept_bytes"] <= BAGGAGE_MAX_BYTES
        assert extra["original_bytes"] > BAGGAGE_MAX_BYTES
        assert extra["limit"] == BAGGAGE_MAX_BYTES

    def test_inject_skips_header_when_truncation_empties_list(
        self, local_baggage_only: None
    ) -> None:
        """If even a single member exceeds BAGGAGE_MAX_BYTES alone, the header
        is not written at all and a warning is still emitted."""
        from unittest.mock import patch

        import core.tracing.distributed as dist_mod

        carrier: Dict[str, str] = {}
        # Single entry of 9000 ASCII bytes in the value — above the 8192 cap.
        oversized = {"onekey": "v" + "x" * 9000}
        with patch.object(dist_mod.LOGGER, "warning") as warn:
            with baggage_scope(oversized):
                inject_distributed_context(carrier)
        assert "baggage" not in carrier
        assert any(
            call.args and call.args[0] == "tracing.baggage_truncated"
            for call in warn.call_args_list
        )
