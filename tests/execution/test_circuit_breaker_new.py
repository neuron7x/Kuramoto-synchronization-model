# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.resilience.circuit_breaker module."""

from __future__ import annotations

import time

import pytest

from execution.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cfg = CircuitBreakerConfig()
        assert cfg.failure_threshold == 5
        assert cfg.recovery_timeout == 30.0
        assert cfg.half_open_max_calls == 3
        assert cfg.rolling_window == 50

    def test_custom(self):
        cfg = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=5.0)
        assert cfg.failure_threshold == 3
        assert cfg.recovery_timeout == 5.0


class TestCircuitBreakerState:
    def test_values(self):
        assert CircuitBreakerState.CLOSED.value == "closed"
        assert CircuitBreakerState.OPEN.value == "open"
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"


class TestCircuitBreaker:
    def _make(self, **kwargs):
        return CircuitBreaker(CircuitBreakerConfig(**kwargs))

    def test_initial_state_closed(self):
        cb = self._make()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_allow_request_when_closed(self):
        cb = self._make()
        assert cb.allow_request() is True

    def test_record_success(self):
        cb = self._make()
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_record_failure_below_threshold(self):
        cb = self._make(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_record_failure_trips_to_open(self):
        cb = self._make(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_open_blocks_requests(self):
        cb = self._make(failure_threshold=1, recovery_timeout=100.0)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.allow_request() is False

    def test_failure_rate_empty(self):
        cb = self._make()
        assert cb.failure_rate() == 0.0

    def test_failure_rate_calculation(self):
        cb = self._make(failure_threshold=100)
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_rate() == pytest.approx(0.5)

    def test_reset(self):
        cb = self._make(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_recovery_to_half_open(self):
        cb = self._make(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_max_calls_limit(self):
        cb = self._make(failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=2)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.allow_request() is True
        # Third call in half-open should be blocked
        assert cb.allow_request() is False

    def test_half_open_success_returns_to_closed(self):
        cb = self._make(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # transition to half_open
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_returns_to_open(self):
        cb = self._make(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # transition to half_open
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_success_resets_consecutive_failures(self):
        cb = self._make(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        # Only 2 consecutive failures now
        assert cb.state == CircuitBreakerState.CLOSED
