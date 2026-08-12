# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.oms module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from execution.oms import OMSConfig, QueuedOrder


class TestOMSConfig:
    def test_defaults(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state")
        assert cfg.auto_persist is True
        assert cfg.max_retries == 3
        assert cfg.backoff_seconds == 0.0
        assert isinstance(cfg.state_path, Path)

    def test_string_state_path_coerced(self, tmp_path):
        cfg = OMSConfig(state_path=str(tmp_path / "state"))
        assert isinstance(cfg.state_path, Path)

    def test_max_retries_minimum(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", max_retries=0)
        assert cfg.max_retries == 1

    def test_negative_backoff_clamped(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", backoff_seconds=-1.0)
        assert cfg.backoff_seconds == 0.0

    def test_invalid_request_timeout_clamped(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", request_timeout=-1.0)
        assert cfg.request_timeout is None

    def test_zero_request_timeout_clamped(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", request_timeout=0)
        assert cfg.request_timeout is None

    def test_valid_request_timeout(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", request_timeout=5.0)
        assert cfg.request_timeout == 5.0

    def test_pre_trade_timeout_none_when_zero(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state", pre_trade_timeout=0)
        assert cfg.pre_trade_timeout is None

    def test_pre_trade_timeout_default(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "state")
        assert cfg.pre_trade_timeout == 0.25

    def test_ledger_path_derived(self, tmp_path):
        cfg = OMSConfig(state_path=tmp_path / "oms_state")
        assert cfg.ledger_path is not None
        assert "ledger" in str(cfg.ledger_path)

    def test_custom_ledger_path(self, tmp_path):
        custom = tmp_path / "custom_ledger.jsonl"
        cfg = OMSConfig(state_path=tmp_path / "state", ledger_path=custom)
        assert cfg.ledger_path == custom


class TestQueuedOrder:
    def test_creation(self):
        order = MagicMock()
        q = QueuedOrder(correlation_id="c1", order=order)
        assert q.correlation_id == "c1"
        assert q.attempts == 0
        assert q.last_error is None

    def test_with_attempts(self):
        order = MagicMock()
        q = QueuedOrder(correlation_id="c1", order=order, attempts=3, last_error="timeout")
        assert q.attempts == 3
        assert q.last_error == "timeout"
