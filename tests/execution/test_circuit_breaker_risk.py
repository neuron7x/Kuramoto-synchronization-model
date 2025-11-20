"""Tests for circuit breaker risk breach tracking."""

from __future__ import annotations

import time

from execution.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


class TestCircuitBreakerRiskTracking:
    """Test suite for circuit breaker risk breach tracking."""

    def test_record_risk_breach(self):
        """Test recording risk breaches."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)

        breaker.record_risk_breach("max_notional_exceeded")

        assert breaker.get_last_trip_reason() == "max_notional_exceeded"

    def test_can_execute_when_closed(self):
        """Test can_execute returns True when circuit is closed."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)

        assert breaker.can_execute()
        assert breaker.state == CircuitBreakerState.CLOSED

    def test_can_execute_when_open(self):
        """Test can_execute returns False when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=1.0)
        breaker = CircuitBreaker(config)

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitBreakerState.OPEN
        assert not breaker.can_execute()

    def test_can_execute_after_recovery(self):
        """Test can_execute returns True after recovery timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        breaker = CircuitBreaker(config)

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitBreakerState.OPEN
        assert not breaker.can_execute()

        time.sleep(0.15)

        assert breaker.can_execute()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_get_time_until_recovery(self):
        """Test time until recovery calculation."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=10.0)
        breaker = CircuitBreaker(config)

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitBreakerState.OPEN

        ttl = breaker.get_time_until_recovery()
        assert 9.5 < ttl <= 10.0

    def test_get_time_until_recovery_when_closed(self):
        """Test time until recovery is 0 when circuit is closed."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)

        ttl = breaker.get_time_until_recovery()
        assert ttl == 0.0

    def test_multiple_risk_breaches(self):
        """Test recording multiple risk breaches."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)

        breaker.record_risk_breach("max_notional_exceeded")
        breaker.record_risk_breach("max_gross_exposure_exceeded")
        breaker.record_risk_breach("daily_drawdown_exceeded")

        assert breaker.get_last_trip_reason() == "daily_drawdown_exceeded"

    def test_breach_window_cleanup(self):
        """Test that old breaches are cleaned up."""
        config = CircuitBreakerConfig(breaches_window_seconds=0.2)
        breaker = CircuitBreaker(config)

        breaker.record_risk_breach("breach_1")
        time.sleep(0.1)
        breaker.record_risk_breach("breach_2")
        time.sleep(0.15)

        breaker.record_risk_breach("breach_3")

        assert breaker.get_last_trip_reason() == "breach_3"
