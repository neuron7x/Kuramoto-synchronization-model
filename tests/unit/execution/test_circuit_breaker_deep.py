# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deep coverage tests for execution.resilience.circuit_breaker module."""

from __future__ import annotations

import threading
import time

import pytest

from execution.resilience.circuit_breaker import (
    AdaptiveThrottler,
    Bulkhead,
    CachedDataFallback,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    DegradedModeFallback,
    ExchangeResilienceManager,
    HealthMetrics,
    LeakyBucketRateLimiter,
    TokenBucketRateLimiter,
    default_resilience_profile,
)

# ---------------------------------------------------------------------------
# CircuitBreaker core
# ---------------------------------------------------------------------------


class TestCircuitBreakerStates:
    def test_starts_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.state is CircuitBreakerState.CLOSED

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitBreakerState.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN

    def test_open_rejects_requests(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999))
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01))
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state is CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01))
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # transitions to half-open
        cb.record_success()
        assert cb.state is CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01))
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN

    def test_half_open_max_calls_limit(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=2)
        )
        cb.record_failure()
        time.sleep(0.02)
        assert cb.allow_request() is True  # call 1
        assert cb.allow_request() is True  # call 2
        assert cb.allow_request() is False  # over limit

    def test_success_resets_consecutive_failures(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state is CircuitBreakerState.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999))
        cb.record_failure()
        assert cb.state is CircuitBreakerState.OPEN
        cb.reset()
        assert cb.state is CircuitBreakerState.CLOSED


class TestCircuitBreakerFailureRate:
    def test_no_outcomes_returns_zero(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.failure_rate() == 0.0

    def test_all_failures(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=100))
        for _ in range(10):
            cb.record_failure()
        assert cb.failure_rate() == 1.0

    def test_all_successes(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        for _ in range(10):
            cb.record_success()
        assert cb.failure_rate() == 0.0

    def test_mixed(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=100))
        for _ in range(5):
            cb.record_success()
        for _ in range(5):
            cb.record_failure()
        assert abs(cb.failure_rate() - 0.5) < 0.01


class TestCircuitBreakerRiskBreach:
    def test_record_risk_breach(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        cb.record_risk_breach("max_drawdown")
        assert cb.get_last_trip_reason() == "max_drawdown"

    def test_old_breaches_cleaned(self):
        config = CircuitBreakerConfig(breaches_window_seconds=0.01)
        cb = CircuitBreaker(config)
        cb.record_risk_breach("old_breach")
        time.sleep(0.02)
        cb.record_risk_breach("new_breach")
        assert len(cb._risk_breaches) == 1


class TestCircuitBreakerCanExecute:
    def test_closed_allows(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.can_execute() is True

    def test_open_blocks(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=999))
        cb.record_failure()
        assert cb.can_execute() is False

    def test_open_transitions_to_half_open_on_can_execute(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01))
        cb.record_failure()
        time.sleep(0.02)
        assert cb.can_execute() is True
        assert cb.state is CircuitBreakerState.HALF_OPEN


class TestCircuitBreakerRecoveryTime:
    def test_not_open_returns_zero(self):
        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.get_time_until_recovery() == 0.0

    def test_open_returns_positive(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=1, recovery_timeout=10.0))
        cb.record_failure()
        remaining = cb.get_time_until_recovery()
        assert 0 < remaining <= 10.0


class TestCircuitBreakerConcurrency:
    def test_concurrent_failures(self):
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=50, rolling_window=200))
        errors = []

        def fail_many():
            try:
                for _ in range(20):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(cb._recent_outcomes) == 100


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter
# ---------------------------------------------------------------------------


class TestTokenBucket:
    def test_allows_within_capacity(self):
        tb = TokenBucketRateLimiter(capacity=10, refill_rate_per_sec=100)
        for _ in range(10):
            assert tb.allow() is True

    def test_rejects_over_capacity(self):
        tb = TokenBucketRateLimiter(capacity=2, refill_rate_per_sec=0)
        assert tb.allow() is True
        assert tb.allow() is True
        assert tb.allow() is False

    def test_refills_over_time(self):
        tb = TokenBucketRateLimiter(capacity=1, refill_rate_per_sec=1000)
        tb.allow()
        time.sleep(0.01)
        assert tb.allow() is True

    def test_utilization(self):
        tb = TokenBucketRateLimiter(capacity=10, refill_rate_per_sec=0)
        assert tb.get_utilization() == 0.0
        for _ in range(5):
            tb.allow()
        assert abs(tb.get_utilization() - 0.5) < 0.01

    def test_multi_token_request(self):
        tb = TokenBucketRateLimiter(capacity=10, refill_rate_per_sec=0)
        assert tb.allow(tokens=5.0) is True
        assert tb.allow(tokens=6.0) is False


# ---------------------------------------------------------------------------
# LeakyBucketRateLimiter
# ---------------------------------------------------------------------------


class TestLeakyBucket:
    def test_allows_within_capacity(self):
        lb = LeakyBucketRateLimiter(capacity=5, leak_rate_per_sec=100)
        for _ in range(5):
            assert lb.allow() is True

    def test_rejects_over_capacity(self):
        lb = LeakyBucketRateLimiter(capacity=2, leak_rate_per_sec=0)
        assert lb.allow() is True
        assert lb.allow() is True
        assert lb.allow() is False

    def test_non_unit_tokens_raises(self):
        lb = LeakyBucketRateLimiter(capacity=5, leak_rate_per_sec=1)
        with pytest.raises(ValueError, match="unit tokens"):
            lb.allow(tokens=2.0)

    def test_utilization(self):
        lb = LeakyBucketRateLimiter(capacity=10, leak_rate_per_sec=0)
        assert lb.get_utilization() == 0.0
        for _ in range(5):
            lb.allow()
        assert abs(lb.get_utilization() - 0.5) < 0.01

    def test_leaks_over_time(self):
        lb = LeakyBucketRateLimiter(capacity=1, leak_rate_per_sec=1000)
        lb.allow()
        time.sleep(0.01)
        assert lb.allow() is True


# ---------------------------------------------------------------------------
# AdaptiveThrottler
# ---------------------------------------------------------------------------


class TestAdaptiveThrottler:
    def test_default_multiplier(self):
        at = AdaptiveThrottler()
        assert at.throttle_factor() == 1.0

    def test_low_latency_reduces_multiplier(self):
        at = AdaptiveThrottler(target_p95_ms=100.0, smoothing=1.0)
        for _ in range(20):
            at.record_latency(50.0)
        assert at.throttle_factor() < 1.0

    def test_high_latency_increases_multiplier(self):
        at = AdaptiveThrottler(target_p95_ms=100.0, smoothing=1.0)
        for _ in range(20):
            at.record_latency(200.0)
        assert at.throttle_factor() > 1.0

    def test_multiplier_clamped(self):
        at = AdaptiveThrottler(
            target_p95_ms=1.0, smoothing=1.0, min_multiplier=0.5, max_multiplier=2.5
        )
        for _ in range(100):
            at.record_latency(10000.0)
        assert at.throttle_factor() <= 2.5

    def test_window_size_maintained(self):
        at = AdaptiveThrottler(window_size=10)
        for i in range(20):
            at.record_latency(float(i))
        assert len(at._recent_latencies) == 10


# ---------------------------------------------------------------------------
# CachedDataFallback / DegradedModeFallback
# ---------------------------------------------------------------------------


class TestFallbacks:
    def test_cached_fallback_returns_data(self):
        fb = CachedDataFallback(cache_provider=lambda ex, op: {"cached": True})
        assert fb.can_handle("binance", "fetch") is True
        assert fb.execute("binance", "fetch") == {"cached": True}

    def test_cached_fallback_no_data_raises(self):
        fb = CachedDataFallback(cache_provider=lambda ex, op: None)
        with pytest.raises(RuntimeError, match="No cached data"):
            fb.execute("binance", "fetch")

    def test_degraded_fallback(self):
        fb = DegradedModeFallback(message_factory=lambda ex, op: f"degraded:{ex}:{op}")
        assert fb.can_handle("kraken", "place") is True
        assert fb.execute("kraken", "place") == "degraded:kraken:place"


# ---------------------------------------------------------------------------
# HealthMetrics
# ---------------------------------------------------------------------------


class TestHealthMetrics:
    def test_snapshot(self):
        hm = HealthMetrics(total_requests=10, failures=2, successful_requests=8)
        snap = hm.snapshot()
        assert snap["total_requests"] == 10
        assert snap["failures"] == 2


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------


class TestBulkhead:
    def test_acquire_and_release(self):
        bh = Bulkhead(max_concurrency=2)
        assert bh.acquire(timeout=0) is True
        assert bh.acquire(timeout=0) is True
        assert bh.acquire(timeout=0) is False
        bh.release()
        assert bh.acquire(timeout=0) is True

    def test_utilization(self):
        bh = Bulkhead(max_concurrency=4)
        assert bh.utilization() == 0.0
        bh.acquire(timeout=0)
        bh.acquire(timeout=0)
        assert abs(bh.utilization() - 0.5) < 0.01

    def test_utilization_zero_max(self):
        bh = Bulkhead(max_concurrency=0)
        assert bh.utilization() == 1.0

    def test_release_without_acquire(self):
        bh = Bulkhead(max_concurrency=2)
        # Should not decrement _in_use below 0
        bh.release()
        assert bh._in_use == 0


# ---------------------------------------------------------------------------
# ExchangeResilienceProfile
# ---------------------------------------------------------------------------


class TestExchangeResilienceProfile:
    def _make_profile(self, **kwargs):
        return default_resilience_profile(**kwargs)

    def test_allow_request_happy_path(self):
        p = self._make_profile()
        assert p.allow_request() is True

    def test_release_success(self):
        p = self._make_profile()
        p.allow_request()
        p.release(success=True, latency_ms=10.0)
        assert p.health.successful_requests == 1

    def test_release_failure(self):
        p = self._make_profile()
        p.allow_request()
        exc = RuntimeError("fail")
        p.release(success=False, latency_ms=10.0, error=exc)
        assert p.health.failures == 1
        assert p.health.last_error == "fail"

    def test_circuit_breaker_rejection(self):
        p = self._make_profile(failure_threshold=1, recovery_timeout=999)
        p.circuit_breaker.record_failure()
        assert p.allow_request() is False
        assert p.health.rejected_requests == 1

    def test_execute_with_fallback_primary_success(self):
        p = self._make_profile(cache_provider=lambda e, o: "cached")
        result = p.execute_with_fallback("b", "op", lambda: "primary")
        assert result == "primary"

    def test_execute_with_fallback_uses_fallback(self):
        p = self._make_profile(cache_provider=lambda e, o: "cached")
        result = p.execute_with_fallback(
            "b", "op", lambda: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        assert result == "cached"

    def test_execute_with_fallback_all_fail(self):
        def bad_cache(e, o):
            raise RuntimeError("cache fail")

        p = self._make_profile(cache_provider=bad_cache)
        with pytest.raises(RuntimeError, match="fail"):
            p.execute_with_fallback("b", "op", lambda: (_ for _ in ()).throw(RuntimeError("fail")))


# ---------------------------------------------------------------------------
# ExchangeResilienceManager
# ---------------------------------------------------------------------------


class TestExchangeResilienceManager:
    def test_get_profile_and_health_report(self):
        p = default_resilience_profile()
        mgr = ExchangeResilienceManager({"binance": p})
        assert mgr.get_profile("binance") is p
        report = mgr.health_report()
        assert "binance" in report

    def test_unknown_profile_raises(self):
        mgr = ExchangeResilienceManager({})
        with pytest.raises(KeyError):
            mgr.get_profile("unknown")


# ---------------------------------------------------------------------------
# default_resilience_profile factory
# ---------------------------------------------------------------------------


class TestDefaultResilienceProfile:
    def test_no_fallbacks(self):
        p = default_resilience_profile()
        assert len(p.fallbacks) == 0

    def test_with_cache_fallback(self):
        p = default_resilience_profile(cache_provider=lambda e, o: None)
        assert len(p.fallbacks) == 1

    def test_with_both_fallbacks(self):
        p = default_resilience_profile(
            cache_provider=lambda e, o: None,
            degraded_factory=lambda e, o: "degraded",
        )
        assert len(p.fallbacks) == 2
