# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage tests for core.utils.secure_errors."""

from __future__ import annotations

import logging

import pytest

from core.utils.secure_errors import (
    AuthenticationError,
    AuthorizationError,
    DataValidationError,
    RateLimitError,
    SecureError,
    TradingError,
    handle_exception,
    safe_str,
    sanitize_error_message,
)


class TestSecureError:
    def test_basic_message_only(self) -> None:
        err = SecureError("Something went wrong")
        assert err.public_message == "Something went wrong"
        # detail_message defaults to public_message when not provided.
        assert err.detail_message == "Something went wrong"
        assert err.error_code is None
        assert err.context == {}
        assert str(err) == "Something went wrong"

    def test_detail_and_code(self) -> None:
        err = SecureError(
            "Public",
            detail_message="Internal detail",
            error_code="X1",
        )
        assert err.detail_message == "Internal detail"
        assert err.error_code == "X1"

    def test_context_sanitization_redacts_sensitive_keys(self) -> None:
        err = SecureError(
            "boom",
            password="hunter2",  # pragma: allowlist secret
            api_key="sk_live",  # pragma: allowlist secret
            user_token="abc",
            username="alice",
        )
        assert err.context["password"] == "***REDACTED***"
        assert err.context["api_key"] == "***REDACTED***"
        # substring match: user_token contains "token"
        assert err.context["user_token"] == "***REDACTED***"
        # non-sensitive preserved verbatim
        assert err.context["username"] == "alice"

    def test_to_dict_minimal(self) -> None:
        err = SecureError("Public")
        assert err.to_dict() == {"error": "Public"}

    def test_to_dict_with_code_no_details(self) -> None:
        err = SecureError("Public", error_code="E1")
        result = err.to_dict()
        assert result == {"error": "Public", "error_code": "E1"}

    def test_to_dict_include_details_with_context(self) -> None:
        err = SecureError(
            "Public",
            detail_message="Detail",
            error_code="E1",
            account="123",
        )
        result = err.to_dict(include_details=True)
        assert result["error"] == "Public"
        assert result["error_code"] == "E1"
        assert result["detail"] == "Detail"
        assert result["context"] == {"account": "123"}

    def test_to_dict_include_details_empty_context(self) -> None:
        err = SecureError("Public", detail_message="Detail")
        result = err.to_dict(include_details=True)
        assert result["detail"] == "Detail"
        # No context key when context is empty.
        assert "context" not in result

    def test_log_emits_record(self, caplog: pytest.LogCaptureFixture) -> None:
        err = SecureError("Public", detail_message="Detail", error_code="E1", foo="bar")
        with caplog.at_level(logging.ERROR, logger="core.utils.secure_errors"):
            err.log()
        assert "Public" in caplog.text
        assert "Detail" in caplog.text

    def test_log_custom_level_and_no_code(self, caplog: pytest.LogCaptureFixture) -> None:
        err = SecureError("Public")
        with caplog.at_level(logging.WARNING, logger="core.utils.secure_errors"):
            err.log(level=logging.WARNING)
        # error_code None renders as N/A via the "or" branch.
        assert "N/A" in caplog.text


class TestSubclasses:
    def test_trading_and_data_validation_are_secure_errors(self) -> None:
        assert issubclass(TradingError, SecureError)
        assert issubclass(DataValidationError, SecureError)
        te = TradingError("trade failed")
        assert te.public_message == "trade failed"

    def test_authentication_error_generic_public_message(self) -> None:
        err = AuthenticationError(detail_message="user bob not found", ip="1.2.3.4")
        assert err.public_message == "Authentication failed"
        assert err.detail_message == "user bob not found"
        assert err.error_code == "AUTH_FAILED"
        assert err.context["ip"] == "1.2.3.4"

    def test_authentication_error_default_detail(self) -> None:
        err = AuthenticationError()
        # detail defaults to public message via SecureError.__init__
        assert err.detail_message == "Authentication failed"

    def test_authorization_error_with_resource(self) -> None:
        err = AuthorizationError(resource="/admin", user="carol")
        assert err.public_message == "Access denied"
        assert err.detail_message == "Access denied to resource: /admin"
        assert err.error_code == "ACCESS_DENIED"

    def test_authorization_error_without_resource(self) -> None:
        err = AuthorizationError()
        assert err.detail_message == "Access denied"

    def test_rate_limit_error_with_retry_after(self) -> None:
        err = RateLimitError(retry_after=30)
        assert err.public_message == "Rate limit exceeded. Retry after 30 seconds"
        assert err.error_code == "RATE_LIMIT_EXCEEDED"
        assert err.context["retry_after"] == 30

    def test_rate_limit_error_without_retry_after(self) -> None:
        err = RateLimitError(detail_message="too many")
        assert err.public_message == "Rate limit exceeded"
        assert err.detail_message == "too many"
        assert err.context["retry_after"] is None

    def test_rate_limit_error_default_detail(self) -> None:
        err = RateLimitError(retry_after=5)
        assert err.detail_message == "Rate limit exceeded. Retry after 5 seconds"


class TestSanitizeErrorMessage:
    def test_secure_error_returns_public_message(self) -> None:
        err = SecureError("safe public", detail_message="secret detail")
        assert sanitize_error_message(err) == "safe public"

    def test_redacts_password(self) -> None:
        out = sanitize_error_message(ValueError("password=hunter2"), include_type=False)
        assert "hunter2" not in out
        assert "password=***" in out

    def test_redacts_api_key_and_type_prefix(self) -> None:
        out = sanitize_error_message(ValueError("api_key: sk_live_123"))
        assert "sk_live_123" not in out
        assert out.startswith("ValueError:")

    def test_redacts_token_secret_email_ip(self) -> None:
        msg = "token=abc secret=xyz user@example.com from 192.168.1.1"
        out = sanitize_error_message(RuntimeError(msg), include_type=False)
        assert "abc" not in out
        assert "xyz" not in out
        assert "user@example.com" not in out
        assert "192.168.1.1" not in out
        assert "***@***.***" in out
        assert "***.***.***.***" in out

    def test_include_type_false_omits_prefix(self) -> None:
        out = sanitize_error_message(KeyError("plain"), include_type=False)
        # KeyError str adds quotes; ensure no "KeyError:" prefix.
        assert not out.startswith("KeyError:")


class TestHandleException:
    def test_passthrough_secure_error_logs_and_returns_same(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        original = SecureError("already secure")
        with caplog.at_level(logging.ERROR, logger="core.utils.secure_errors"):
            result = handle_exception(original)
        assert result is original

    def test_value_error_mapping(self) -> None:
        result = handle_exception(ValueError("bad"), log_traceback=False)
        assert result.public_message == "Invalid input provided"

    def test_key_error_mapping(self) -> None:
        result = handle_exception(KeyError("missing"), log_traceback=False)
        assert result.public_message == "Required field missing"

    def test_file_not_found_mapping(self) -> None:
        result = handle_exception(FileNotFoundError("nope"), log_traceback=False)
        assert result.public_message == "Resource not found"

    def test_permission_error_mapping(self) -> None:
        result = handle_exception(PermissionError("denied"), log_traceback=False)
        assert result.public_message == "Access denied"

    def test_timeout_error_mapping(self) -> None:
        result = handle_exception(TimeoutError("slow"), log_traceback=False)
        assert result.public_message == "Operation timed out"

    def test_generic_error_mapping(self) -> None:
        result = handle_exception(RuntimeError("weird"), log_traceback=False)
        assert result.public_message == "An error occurred while processing your request"

    def test_context_is_passed_and_sanitized(self) -> None:
        result = handle_exception(
            ValueError("x"),
            context={"password": "p", "ok": "v"},
            log_traceback=False,
        )
        assert result.context["password"] == "***REDACTED***"
        assert result.context["ok"] == "v"

    def test_log_traceback_true_emits(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.ERROR, logger="core.utils.secure_errors"):
            handle_exception(ValueError("boom"), log_traceback=True)
        assert "Exception caught" in caplog.text


class TestSafeStr:
    def test_short_string_unchanged(self) -> None:
        assert safe_str("hello") == "hello"

    def test_truncation(self) -> None:
        out = safe_str("x" * 200, max_length=10)
        assert len(out) == 10
        assert out.endswith("...")

    def test_exact_boundary_not_truncated(self) -> None:
        s = "a" * 100
        assert safe_str(s) == s

    def test_exception_on_str_returns_fallback(self) -> None:
        class Bad:
            def __str__(self) -> str:
                raise RuntimeError("cannot stringify")

        out = safe_str(Bad())
        assert out == "<Bad object>"


def test_error_context_is_preserved_not_dropped() -> None:
    """`self.context or {}` / `context or {}` must KEEP supplied context, defaulting only when empty.

    Under `Or -> And` a non-empty context collapses to `{}`, so the diagnostic context is
    silently dropped from exactly the errors that carried it -- the log loses the very fields
    that make an error triageable.
    """
    err = SecureError("public", detail_message="internal", request_id="abc-123", attempt=2)
    assert err.context.get("request_id") == "abc-123"
    assert err.context.get("attempt") == 2

    empty = SecureError("public")
    assert empty.context == {}


def test_log_carries_real_context_not_empty(caplog) -> None:
    """`self.context or {}` -- a populated context is logged, not blanked.

    Under Or->And a non-empty context collapses to {} (`x and {}` == {}), so the
    audit log loses the very detail it exists to carry.
    """
    caplog.set_level(logging.ERROR)
    SecureError("public", region="eu-west").log()
    assert caplog.records[-1].args[-1] == {"region": "eu-west"}


def test_handle_exception_logs_real_context_not_empty(caplog) -> None:
    """`extra={"context": context or {}}` -- the caller's context is logged.

    Under Or->And a populated context becomes {} in the structured log record.
    """
    caplog.set_level(logging.ERROR)
    handle_exception(ValueError("boom"), context={"trace_key": "trace_value"})
    logged = [getattr(r, "context", None) for r in caplog.records]
    assert {"trace_key": "trace_value"} in logged
