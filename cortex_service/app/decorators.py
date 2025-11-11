"""Decorators for resilience and transaction management."""

from __future__ import annotations

import functools
import time
from typing import Callable, ParamSpec, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from .constants import (
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_INITIAL_DELAY,
    RETRY_MAX_DELAY,
)
from .errors import DatabaseError
from .logger import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def with_retry(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    initial_delay: float = RETRY_INITIAL_DELAY,
    max_delay: float = RETRY_MAX_DELAY,
    backoff_multiplier: float = RETRY_BACKOFF_MULTIPLIER,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry decorator for transient database errors.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff

    Returns:
        Decorator function

    Example:
        >>> @with_retry(max_attempts=3)
        ... def fetch_data():
        ...     return db.query(...)
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            attempt = 0
            delay = initial_delay

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (OperationalError, DBAPIError) as exc:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(
                            "Database operation failed after %d attempts",
                            max_attempts,
                            exc_info=True,
                        )
                        raise DatabaseError(
                            f"Database operation failed after {max_attempts} attempts: {exc}",
                            details={"attempts": attempt, "original_error": str(exc)},
                        ) from exc

                    logger.warning(
                        "Database operation failed (attempt %d/%d), retrying after %.2fs",
                        attempt,
                        max_attempts,
                        delay,
                        extra={"error": str(exc)},
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_multiplier, max_delay)

            # This should never be reached, but satisfies type checker
            raise DatabaseError("Maximum retry attempts reached")

        return wrapper

    return decorator


def transactional(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator to manage database transactions.

    Automatically commits on success and rolls back on failure.
    Expects the first argument to be a SQLAlchemy Session.

    Args:
        func: Function to wrap with transaction management

    Returns:
        Wrapped function with transaction management

    Example:
        >>> @transactional
        ... def create_user(session: Session, name: str):
        ...     user = User(name=name)
        ...     session.add(user)
        ...     return user
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # Get session from first argument or kwargs
        session: Session | None = None
        if args:
            first_arg: object = args[0]
            if isinstance(first_arg, Session):
                session = first_arg
        if session is None and "session" in kwargs:
            session_kwarg: object = kwargs["session"]
            if isinstance(session_kwarg, Session):
                session = session_kwarg

        if session is None:
            raise TypeError(
                f"Function {func.__name__} requires a Session as first argument or 'session' kwarg"
            )

        try:
            result = func(*args, **kwargs)
            session.commit()
            return result
        except SQLAlchemyError as exc:
            session.rollback()
            logger.error("Transaction rolled back due to error", exc_info=True)
            raise DatabaseError(
                f"Transaction failed: {exc}", details={"original_error": str(exc)}
            ) from exc
        except Exception:
            session.rollback()
            raise

    return wrapper


__all__ = ["with_retry", "transactional"]
