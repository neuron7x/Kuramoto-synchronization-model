# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for the transient-database retry strategy.

Every test here is written so that a *plausible defect* in ``libs/db/retry.py``
flips it red: swapping ``reraise=True`` for ``False``, widening the retryable
set to swallow programming errors, dropping the ``stop_after_attempt`` cap,
losing the exponential-backoff bound, or muting the ``before_sleep`` log line.
"""

from __future__ import annotations

import logging
import random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)

from libs.db.exceptions import DatabaseError, RetryableDatabaseError
from libs.db.retry import RetryPolicy, run_with_retry

_FAST = {
    "attempts": 3,
    "initial_backoff": 0.001,
    "max_backoff": 0.002,
    "max_jitter": 0.001,
}


def _logger() -> logging.Logger:
    log = logging.getLogger("test.retry")
    log.setLevel(logging.WARNING)
    return log


def test_retry_stops_after_max_attempts_and_reraises_final() -> None:
    policy = RetryPolicy(**_FAST)
    calls = {"n": 0}

    def op() -> object:
        calls["n"] += 1
        raise RetryableDatabaseError("transient")

    with pytest.raises(RetryableDatabaseError):
        run_with_retry(policy, _logger(), op)
    # Defect guard: a dropped stop() would loop forever / exceed the cap.
    assert calls["n"] == 3


def test_final_exception_is_not_swallowed() -> None:
    policy = RetryPolicy(**_FAST)
    sentinel = RetryableDatabaseError("boom-42")

    def op() -> object:
        raise sentinel

    with pytest.raises(RetryableDatabaseError) as excinfo:
        run_with_retry(policy, _logger(), op)
    # reraise=True must surface the ORIGINAL error, not a RetryError wrapper.
    assert excinfo.value is sentinel


def test_non_retryable_error_is_not_retried() -> None:
    policy = RetryPolicy(**_FAST)
    calls = {"n": 0}

    def op() -> object:
        calls["n"] += 1
        raise ValueError("programming error")

    with pytest.raises(ValueError):
        run_with_retry(policy, _logger(), op)
    # A non-retryable error must fail on the first attempt (no masking).
    assert calls["n"] == 1


def test_retryable_error_is_retried_then_succeeds() -> None:
    policy = RetryPolicy(**_FAST)
    calls = {"n": 0}

    def op() -> object:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableDatabaseError("transient")
        return "recovered"

    assert run_with_retry(policy, _logger(), op) == "recovered"
    assert calls["n"] == 3


def test_keyboard_interrupt_is_not_swallowed() -> None:
    policy = RetryPolicy(**_FAST)
    calls = {"n": 0}

    def op() -> object:
        calls["n"] += 1
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_with_retry(policy, _logger(), op)
    # KeyboardInterrupt must propagate immediately, never be retried.
    assert calls["n"] == 1


def test_before_sleep_logs_one_warning_per_retry_without_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = RetryPolicy(**_FAST)

    def op() -> object:
        raise RetryableDatabaseError("transient-only")

    with caplog.at_level(logging.WARNING, logger="test.retry"):
        with pytest.raises(RetryableDatabaseError):
            run_with_retry(policy, _logger(), op)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    # before_sleep fires once per *retry*, i.e. attempts - 1 times.
    assert len(warnings) == policy.attempts - 1
    # The retry logger has no access to a DSN, so no credential can leak.
    joined = "\n".join(r.getMessage() for r in warnings)
    assert "password" not in joined.lower()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RetryableDatabaseError("x"), True),
        (TimeoutError(), True),
        (ConnectionError(), True),
        (OSError(), True),
        (DisconnectionError(), True),
        (OperationalError("stmt", {}, Exception("orig")), True),
        (InterfaceError("stmt", {}, Exception("orig")), True),
        (ValueError("nope"), False),
        (DatabaseError("generic non-retryable"), False),
        (KeyboardInterrupt(), False),
    ],
)
def test_is_retryable_classification(error: BaseException, expected: bool) -> None:
    assert RetryPolicy._is_retryable(error) is expected


def test_dbapi_error_retryable_only_when_connection_invalidated() -> None:
    invalidated = DBAPIError("stmt", {}, Exception("orig"), connection_invalidated=True)
    intact = DBAPIError("stmt", {}, Exception("orig"), connection_invalidated=False)
    assert RetryPolicy._is_retryable(invalidated) is True
    assert RetryPolicy._is_retryable(intact) is False


def test_backoff_is_bounded_and_monotonic_upper_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RetryPolicy(attempts=8, initial_backoff=0.01, max_backoff=1.0, max_jitter=0.25)
    # Force the random components to their upper bound so we observe the
    # deterministic ceiling of the wait strategy: exp = min(max_backoff,
    # initial * 2**(n-1)); jitter = max_jitter.
    monkeypatch.setattr(random, "uniform", lambda _lo, hi: hi)
    monkeypatch.setattr(random, "random", lambda: 1.0)
    wait = policy.build(logger=_logger()).wait

    ceiling = policy.max_backoff + policy.max_jitter
    previous = -1.0
    for attempt in range(1, policy.attempts + 1):
        value = wait(SimpleNamespace(attempt_number=attempt))
        assert 0.0 <= value <= ceiling + 1e-12
        # Upper-bound of exponential backoff is monotonically non-decreasing.
        assert value >= previous - 1e-12
        previous = value
    # Once capped, the ceiling must actually be reached (bound is tight).
    assert previous == pytest.approx(ceiling)


@pytest.mark.parametrize("field", ["attempts", "initial_backoff", "max_backoff", "max_jitter"])
def test_non_positive_policy_values_rejected(field: str) -> None:
    kwargs = dict(_FAST)
    kwargs[field] = 0 if field == "attempts" else 0.0
    with pytest.raises(ValidationError):
        RetryPolicy(**kwargs)


def test_run_with_retry_returns_operation_result() -> None:
    policy = RetryPolicy(**_FAST)
    assert run_with_retry(policy, _logger(), lambda: 7) == 7
