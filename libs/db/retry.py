# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configurable retry strategy for transient database failures."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_random,
    wait_random_exponential,
)

from .exceptions import RetryableDatabaseError

__all__ = ["RetryPolicy", "run_with_retry"]


class RetryPolicy(BaseModel):
    """Retry configuration with exponential backoff and jitter."""

    attempts: PositiveInt = Field(
        5, description="Maximum number of attempts before surfacing the error."
    )
    initial_backoff: PositiveFloat = Field(
        0.05,
        description="Initial backoff interval in seconds before the first retry.",
    )
    max_backoff: PositiveFloat = Field(
        2.0,
        description="Upper bound for the exponential backoff window.",
    )
    max_jitter: PositiveFloat = Field(
        0.1,
        description="Additional random jitter applied on top of the exponential backoff.",
    )

    def build(self, *, logger: logging.Logger) -> Retrying:
        """Return a configured :class:`~tenacity.Retrying` instance."""

        wait = wait_random_exponential(multiplier=self.initial_backoff, max=self.max_backoff)
        if self.max_jitter > 0:
            wait = wait + wait_random(0, self.max_jitter)
        return Retrying(
            stop=stop_after_attempt(int(self.attempts)),
            wait=wait,
            retry=retry_if_exception(self._is_retryable),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        if isinstance(error, RetryableDatabaseError):
            return True
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True
        if isinstance(error, (DisconnectionError, OperationalError, InterfaceError)):
            return True
        if isinstance(error, DBAPIError):
            return bool(getattr(error, "connection_invalidated", False))
        return False


def run_with_retry(
    policy: RetryPolicy, logger: logging.Logger, operation: Callable[[], object]
) -> object:
    """Execute *operation* applying the supplied retry policy."""

    retrying = policy.build(logger=logger)
    for attempt in retrying:
        with attempt:
            return operation()
    raise RuntimeError("Retrying loop exited unexpectedly")
