# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging

import pytest

from src.audit.audit_logger import AuditLogger


def test_audit_logger_redacts_sensitive_values_from_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_details = {
        "api_key": "s3cr3t-token",
        "nested": {"refreshToken": "refresh-123"},
        "safe": "ok",
        "list": [
            {"clientSecret": "top-secret"},
            "regular value",
        ],
    }

    with caplog.at_level(logging.INFO, logger="geosync.audit"):
        audit = AuditLogger(secret="unit-secret-value")
        record = audit.log_event(
            event_type="test",
            actor="tester",
            ip_address="127.0.0.1",
            details=sensitive_details,
        )

    assert record.details["api_key"] == "s3cr3t-token"
    assert record.details["nested"]["refreshToken"] == "refresh-123"
    assert "s3cr3t-token" not in caplog.text
    assert "refresh-123" not in caplog.text
    assert "top-secret" not in caplog.text

    record_entry = caplog.records[0]
    redacted_details = record_entry.audit["details"]

    assert redacted_details["api_key"] == "[REDACTED]"
    assert redacted_details["nested"]["refreshToken"] == "[REDACTED]"
    assert redacted_details["safe"] == "ok"
    assert redacted_details["list"][0]["clientSecret"] == "[REDACTED]"
