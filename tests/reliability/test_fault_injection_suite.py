"""TST-015 — fault-injection / negative-path suite for the safety surfaces.

Every test INJECTS the failure the surface exists to contain and asserts the surface
fails CLOSED (denies, halts, or surfaces the error) — never fail-open. A protective
control that does not deny under fault is theatre; these are its teeth.

Covers: execution/resilience/circuit_breaker.py (breaker trip + recovery budget) and
geosync/risk/kill_switch.py (protective-callback aggregation). The kill-switch corrupt-
state latch and the OMS concurrent-idempotency path have their own teeth suites
(test_killswitch_failclosed_teeth.py, test_oms_concurrent_idempotency_teeth.py); this
file adds the breaker and multi-callback fault paths.
"""
from __future__ import annotations

import pytest

from execution.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)
from geosync.risk.kill_switch import KillSwitchCallbackError, SafetyController


# ---------------------------------------------------------------- circuit breaker

def test_breaker_trips_open_after_threshold_and_denies() -> None:
    """N consecutive failures → OPEN, and OPEN denies requests (fail-closed)."""
    cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3, recovery_timeout=1e9))
    assert cb.allow_request() is True  # healthy: closed lets traffic through
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitBreakerState.OPEN
    # while OPEN and inside recovery_timeout, every request is DENIED
    assert cb.allow_request() is False
    assert cb.allow_request() is False


def test_breaker_recovers_to_half_open_then_limits_probes() -> None:
    """After recovery_timeout the breaker half-opens but caps concurrent probes."""
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.0, half_open_max_calls=2)
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitBreakerState.OPEN
    # recovery_timeout=0 → next allow_request transitions OPEN → HALF_OPEN
    assert cb.allow_request() is True
    assert cb.state is CircuitBreakerState.HALF_OPEN
    assert cb.allow_request() is True  # 2nd probe (budget = 2)
    # budget exhausted → further probes denied (does not flood the recovering dependency)
    assert cb.allow_request() is False


def test_breaker_probe_refund_prevents_half_open_wedge() -> None:
    """A never-executed probe can be refunded so recovery is not wedged forever."""
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0, half_open_max_calls=1)
    )
    cb.record_failure()
    assert cb.allow_request() is True           # consumes the only probe
    assert cb.allow_request() is False          # wedged: no budget
    cb.refund_half_open_probe()                 # caller never executed the probe
    assert cb.allow_request() is True           # budget restored → recovery can proceed


def test_breaker_success_in_half_open_closes_circuit() -> None:
    """A successful probe in HALF_OPEN restores CLOSED (recovery completes)."""
    cb = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0, half_open_max_calls=2)
    )
    cb.record_failure()
    assert cb.allow_request() is True
    assert cb.state is CircuitBreakerState.HALF_OPEN
    cb.record_success()
    assert cb.state is CircuitBreakerState.CLOSED


# ---------------------------------------------------------------- kill switch

def test_every_failing_protective_callback_is_aggregated_not_swallowed() -> None:
    """Multiple raising protective callbacks all surface; good ones still run; switch stays active."""
    sc = SafetyController()
    ran = {"good": 0}

    def bad_flatten(state: object) -> None:
        raise RuntimeError("flatten failed")

    def bad_disconnect(state: object) -> None:
        raise RuntimeError("disconnect failed")

    def good(state: object) -> None:
        ran["good"] += 1

    sc.register_callback(bad_flatten)
    sc.register_callback(good)
    sc.register_callback(bad_disconnect)

    with pytest.raises(KillSwitchCallbackError):
        sc.activate_kill_switch(reason="fault-injection", source="TST-015")

    # fail-closed: state committed HALTED before notify, the healthy callback ran,
    # and the failures were NOT silently swallowed (a swallow would report success).
    assert sc.is_kill_switch_active() is True
    assert ran["good"] == 1
