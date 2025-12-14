# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for the structured logging utilities."""
from __future__ import annotations

import io
import json
import logging

import pytest

from core.utils.logging import JSONFormatter, StructuredLogger, configure_logging


def _make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="tradepulse.tests",
        level=logging.ERROR,
        pathname=__file__,
        lineno=42,
        msg="problem occurred",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_extras_and_exception() -> None:
    formatter = JSONFormatter()

    try:
        raise ValueError("boom")
    except ValueError as exc:
        record = _make_record(
            correlation_id="cid-123",
            extra_fields={"action": "compute"},
            exc_info=(ValueError, exc, exc.__traceback__),
        )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "ERROR"
    assert payload["correlation_id"] == "cid-123"
    assert payload["action"] == "compute"
    assert "ValueError: boom" in payload["exception"]


def test_structured_logger_operation_success_emits_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    logger = StructuredLogger("tradepulse.ops", correlation_id="cid-success")
    with logger.operation("sync_data", asset="BTC-USDT") as ctx:
        ctx["result_value"] = 42

    start_record, end_record = caplog.records[-2:]

    assert start_record.message == "Starting operation: sync_data"
    assert start_record.correlation_id == "cid-success"
    assert start_record.extra_fields["operation"] == "sync_data"
    assert start_record.extra_fields["asset"] == "BTC-USDT"

    assert end_record.levelno == logging.INFO
    assert end_record.message == "Completed operation: sync_data"
    assert end_record.correlation_id == "cid-success"
    assert end_record.extra_fields["status"] == "success"
    assert end_record.extra_fields["result_value"] == 42
    assert end_record.extra_fields["asset"] == "BTC-USDT"
    assert end_record.extra_fields["operation"] == "sync_data"
    assert "duration_seconds" in end_record.extra_fields


def test_structured_logger_operation_failure_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    logger = StructuredLogger("tradepulse.ops", correlation_id="cid-failure")

    with pytest.raises(RuntimeError):
        with logger.operation("rebalance", portfolio="alpha"):
            raise RuntimeError("unable to rebalance")

    start_record, error_record = caplog.records[-2:]

    assert start_record.message == "Starting operation: rebalance"
    assert start_record.correlation_id == "cid-failure"

    assert error_record.levelno == logging.ERROR
    assert error_record.message == "Failed operation: rebalance"
    assert error_record.correlation_id == "cid-failure"
    assert error_record.extra_fields["status"] == "failure"
    assert error_record.extra_fields["error_type"] == "RuntimeError"
    assert error_record.extra_fields["error_message"] == "unable to rebalance"
    assert error_record.extra_fields["portfolio"] == "alpha"


def test_structured_logger_operation_can_disable_success_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    logger = StructuredLogger("tradepulse.ops", correlation_id="cid-quiet")
    with logger.operation(
        "fast_path",
        level=logging.DEBUG,
        emit_start=False,
        emit_success=False,
        window="5m",
    ):
        pass

    assert caplog.records == []


def test_structured_logger_operation_failure_still_logs_when_suppressed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)

    logger = StructuredLogger("tradepulse.ops", correlation_id="cid-error")

    with pytest.raises(ValueError):
        with logger.operation(
            "fast_path",
            level=logging.DEBUG,
            emit_start=False,
            emit_success=False,
        ):
            raise ValueError("boom")

    (error_record,) = caplog.records

    assert error_record.levelno == logging.ERROR
    assert error_record.message == "Failed operation: fast_path"
    assert error_record.extra_fields["status"] == "failure"
    assert error_record.extra_fields["error_type"] == "ValueError"
    assert error_record.extra_fields["error_message"] == "boom"
    assert error_record.extra_fields["operation"] == "fast_path"


def test_structured_logger_preserves_exc_info(caplog: pytest.LogCaptureFixture) -> None:
    """Structured logger should forward exc_info instead of serialising it."""

    caplog.set_level(logging.WARNING)

    logger = StructuredLogger("tradepulse.ops", correlation_id="cid-warning")
    exc = RuntimeError("stream failure")

    logger.warning("Async stream terminated with error", stream="FLAKY", exc_info=exc)

    (record,) = caplog.records[-1:]

    assert record.message == "Async stream terminated with error"
    assert record.correlation_id == "cid-warning"
    assert record.extra_fields["stream"] == "FLAKY"
    assert "exc_info" not in record.extra_fields
    assert record.exc_info is not None
    assert record.exc_info[1] is exc


def test_configure_logging_emits_json_payload() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", use_json=True, stream=stream)

    logging.getLogger("tradepulse.tests").info("hello world")

    output = stream.getvalue().strip()
    assert output

    payload = json.loads(output)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "tradepulse.tests"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload


def test_configure_logging_accepts_numeric_level() -> None:
    stream = io.StringIO()

    configure_logging(level=logging.DEBUG, use_json=False, stream=stream)
    logging.getLogger("tradepulse.tests").debug("debug message")

    assert logging.getLogger().level == logging.DEBUG
    assert "debug message" in stream.getvalue()


def test_configure_logging_accepts_numeric_level_string() -> None:
    stream = io.StringIO()

    configure_logging(level="10", use_json=False, stream=stream)
    logging.getLogger("tradepulse.tests").debug("debug message")

    assert logging.getLogger().level == 10
    assert "debug message" in stream.getvalue()


def test_configure_logging_accepts_case_insensitive_level() -> None:
    stream = io.StringIO()

    configure_logging(level="info", use_json=False, stream=stream)
    logging.getLogger("tradepulse.tests").info("hello lower")

    assert logging.getLogger().level == logging.INFO
    assert "hello lower" in stream.getvalue()


def test_configure_logging_rejects_invalid_level() -> None:
    with pytest.raises(ValueError):
        configure_logging(level="not-a-level")


def test_configure_logging_rejects_boolean_level() -> None:
    with pytest.raises(ValueError):
        configure_logging(level=True)

    with pytest.raises(ValueError):
        configure_logging(level=False)
