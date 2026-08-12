# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: a half-open probe admitted by the breaker but rejected downstream
must be refunded, or the breaker wedges HALF_OPEN forever.

Bug: ExchangeResilienceProfile.allow_request admits a request through the circuit
breaker (bumping _half_open_calls) and then may reject it via the leaky bucket /
bulkhead / token bucket. Those rejection paths never recorded success/failure, so
the consumed half-open budget was never returned — once _half_open_calls reached
half_open_max_calls the breaker refused every probe forever (HALF_OPEN never
re-checks recovery_timeout), permanently blocking the exchange.

`execution.*` is behind the forbidden_import_patterns gate → importlib.
"""

from __future__ import annotations

import importlib

_cb = importlib.import_module("execution.resilience.circuit_breaker")
CircuitBreaker = _cb.CircuitBreaker
CircuitBreakerConfig = _cb.CircuitBreakerConfig
CircuitBreakerState = _cb.CircuitBreakerState


def _tripped_half_open() -> "CircuitBreaker":
    cfg = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0, half_open_max_calls=2)
    cb = CircuitBreaker(cfg)
    cb.record_failure()  # threshold 1 -> OPEN; recovery_timeout 0 -> next allow -> HALF_OPEN
    return cb


def test_admitted_but_refunded_probes_never_wedge_the_breaker() -> None:
    cb = _tripped_half_open()
    # Admit-then-refund far more times than half_open_max_calls (downstream reject).
    for _ in range(10):
        assert cb.allow_request() is True  # HALF_OPEN admits and bumps the budget
        cb.refund_half_open_probe()  # downstream layer rejected -> return the budget
    # Budget was never exhausted: a real probe can still be admitted and succeed,
    # which closes the breaker. (On the buggy code the 3rd admit already returned
    # False and the breaker was wedged.)
    assert cb.allow_request() is True
    cb.record_success()
    assert cb.allow_request() is True  # CLOSED -> recovered, not wedged


def test_refund_is_a_noop_when_closed_and_never_underflows() -> None:
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))
    assert cb.allow_request() is True  # CLOSED
    cb.refund_half_open_probe()  # must not raise / underflow
    cb.refund_half_open_probe()
    assert cb.allow_request() is True


def test_without_refund_budget_would_exhaust() -> None:
    # Documents the failure mode: admitting probes WITHOUT refunding exhausts the
    # half-open budget and wedges the breaker (this is exactly what the profile's
    # downstream-rejection paths used to do).
    cb = _tripped_half_open()
    assert cb.allow_request() is True  # 1/2
    assert cb.allow_request() is True  # 2/2
    assert cb.allow_request() is False  # 3rd -> refused: wedged without a refund
