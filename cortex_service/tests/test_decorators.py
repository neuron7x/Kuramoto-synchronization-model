# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for decorator functionality."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cortex_service.app.decorators import transactional, with_retry
from cortex_service.app.errors import DatabaseError


def _create_test_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionFactory()


class TestWithRetryDecorator:
    """Test retry decorator functionality."""

    def test_retry_succeeds_on_first_attempt(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_succeeds_after_failures(self):
        call_count = 0

        @with_retry(max_attempts=4, initial_delay=0.01, max_delay=0.05)
        def eventually_successful():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OperationalError("Temporary error", None, None)
            return "success"

        result = eventually_successful()
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted_raises_database_error(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        def always_failing():
            nonlocal call_count
            call_count += 1
            raise OperationalError("Persistent error", None, None)

        with pytest.raises(DatabaseError, match="after 3 attempts"):
            always_failing()
        assert call_count == 3

    def test_retry_non_retryable_error_raises_immediately(self):
        call_count = 0

        @with_retry(max_attempts=3, initial_delay=0.01)
        def non_retryable_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a DB error")

        with pytest.raises(ValueError):
            non_retryable_error()
        assert call_count == 1  # Should not retry


class TestTransactionalDecorator:
    """Test transactional decorator functionality."""

    def test_transactional_commits_on_success(self):
        session = _create_test_session()
        committed = False
        original_commit = session.commit

        def mock_commit():
            nonlocal committed
            committed = True
            return original_commit()

        session.commit = mock_commit

        @transactional
        def successful_operation(sess: Session):
            return "success"

        result = successful_operation(session)
        assert result == "success"
        assert committed

    def test_transactional_rolls_back_on_sqlalchemy_error(self):
        session = _create_test_session()
        rolled_back = False
        original_rollback = session.rollback

        def mock_rollback():
            nonlocal rolled_back
            rolled_back = True
            return original_rollback()

        session.rollback = mock_rollback

        @transactional
        def failing_operation(sess: Session):
            raise SQLAlchemyError("Database error")

        with pytest.raises(DatabaseError, match="Transaction failed"):
            failing_operation(session)
        assert rolled_back

    def test_transactional_rolls_back_on_generic_error(self):
        session = _create_test_session()
        rolled_back = False
        original_rollback = session.rollback

        def mock_rollback():
            nonlocal rolled_back
            rolled_back = True
            return original_rollback()

        session.rollback = mock_rollback

        @transactional
        def failing_with_generic_error(sess: Session):
            raise RuntimeError("Generic error")

        with pytest.raises(RuntimeError):
            failing_with_generic_error(session)
        assert rolled_back

    def test_transactional_requires_session(self):
        @transactional
        def no_session_provided():
            return "should fail"

        with pytest.raises(TypeError, match="requires a Session"):
            no_session_provided()

    def test_transactional_with_session_kwarg(self):
        session = _create_test_session()
        committed = False
        original_commit = session.commit

        def mock_commit():
            nonlocal committed
            committed = True
            return original_commit()

        session.commit = mock_commit

        @transactional
        def operation_with_kwarg(*, session: Session):
            return "success"

        result = operation_with_kwarg(session=session)
        assert result == "success"
        assert committed
