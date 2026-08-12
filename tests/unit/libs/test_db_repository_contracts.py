# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for the SQLAlchemy repository layer.

CRUD round-trips run against a real in-memory SQLite backend; postgres-only
upsert semantics are asserted via dialect compilation; read/write routing and
retry wiring are asserted with a mocked session manager. Each test flips red on
a plausible defect: wrong routing, string-interpolated parameters, a missing
not-found path, or a commit that survives a mid-transaction failure.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from libs.db.access import DataAccessLayer
from libs.db.exceptions import DatabaseError
from libs.db.models import Base, KillSwitchState
from libs.db.repository import KillSwitchStateRepository, SqlAlchemyRepository
from libs.db.retry import RetryPolicy
from libs.db.session import SessionManager


def _sqlite_manager() -> SessionManager:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng, tables=[KillSwitchState.__table__])
    return SessionManager(eng, monitoring_interval_seconds=None)


def _fast_repo(manager: SessionManager) -> KillSwitchStateRepository:
    return KillSwitchStateRepository(
        manager,
        retry_policy=RetryPolicy(attempts=1, initial_backoff=0.001, max_backoff=0.002, max_jitter=0.001),
    )


# ---------------------------------------------------------------------------
# Real SQLite CRUD semantics
# ---------------------------------------------------------------------------


def test_load_returns_typed_none_when_absent() -> None:
    mgr = _sqlite_manager()
    try:
        repo = _fast_repo(mgr)
        assert repo.load() is None  # missing record -> typed not-found, not an error.
    finally:
        mgr.close()


def test_crud_round_trip() -> None:
    mgr = _sqlite_manager()
    try:
        repo = _fast_repo(mgr)
        with mgr.session() as s:
            s.add(KillSwitchState(id=1, engaged=True, reason="tripped"))
        # repo.load() proves the row round-tripped: identity is captured in the
        # instance state (no DB refresh) even after the read-only session closes.
        loaded = repo.load()
        assert loaded is not None
        assert inspect(loaded).identity == (1,)
        # Field values are read while a session is still live.
        with mgr.session(read_only=True) as s:
            row = s.get(KillSwitchState, 1)
            assert row is not None
            assert row.engaged is True and row.reason == "tripped"
    finally:
        mgr.close()


def test_duplicate_primary_key_raises_deterministic_conflict() -> None:
    mgr = _sqlite_manager()
    try:
        with mgr.session() as s:
            s.add(KillSwitchState(id=1, engaged=True, reason="first"))
        with pytest.raises(IntegrityError):
            with mgr.session() as s:
                s.add(KillSwitchState(id=1, engaged=False, reason="dup"))
    finally:
        mgr.close()


def test_invalid_model_fails_before_write() -> None:
    mgr = _sqlite_manager()
    try:
        with pytest.raises(IntegrityError):
            with mgr.session() as s:
                # engaged is NOT NULL — the row must be rejected at flush time.
                # Build via **kwargs so the omitted NOT-NULL column is a runtime
                # IntegrityError, not a static call-arg error to suppress.
                incomplete_row: dict[str, object] = {"id": 1, "reason": "missing-engaged"}
                s.add(KillSwitchState(**incomplete_row))
        with mgr.session(read_only=True) as s:
            assert s.get(KillSwitchState, 1) is None
    finally:
        mgr.close()


def test_partial_update_preserves_unspecified_fields() -> None:
    mgr = _sqlite_manager()
    try:
        with mgr.session() as s:
            s.add(KillSwitchState(id=1, engaged=True, reason="keep-me"))
        with mgr.session() as s:
            row = s.get(KillSwitchState, 1)
            assert row is not None
            row.engaged = False  # update only one column
        with mgr.session(read_only=True) as s:
            row = s.get(KillSwitchState, 1)
            assert row is not None
            assert row.engaged is False
            assert row.reason == "keep-me"  # untouched field survives
    finally:
        mgr.close()


def test_transaction_rollback_prevents_partial_write() -> None:
    mgr = _sqlite_manager()
    try:
        repo = SqlAlchemyRepository(
            mgr,
            retry_policy=RetryPolicy(attempts=1, initial_backoff=0.001, max_backoff=0.002, max_jitter=0.001),
        )

        def _write_then_fail(session: Session) -> None:
            session.add(KillSwitchState(id=1, engaged=True, reason="doomed"))
            session.flush()
            raise RuntimeError("explode mid-transaction")

        with pytest.raises(RuntimeError):
            repo._execute(_write_then_fail, read_only=False)
        assert _fast_repo(mgr).load() is None
    finally:
        mgr.close()


# ---------------------------------------------------------------------------
# Parameter binding & postgres upsert dialect
# ---------------------------------------------------------------------------


def test_select_uses_bound_parameters_not_interpolation() -> None:
    stmt = select(KillSwitchState).where(KillSwitchState.id == 1)
    compiled = stmt.compile()
    # The literal value lives in bound params, never spliced into SQL text.
    assert 1 in compiled.params.values()
    assert " 1" not in str(compiled)


def test_upsert_compiles_to_on_conflict_with_bound_params() -> None:
    stmt = (
        insert(KillSwitchState)
        .values(id=1, engaged=True, reason="reason")
        .on_conflict_do_update(
            index_elements=[KillSwitchState.id],
            set_={"engaged": True, "reason": "reason"},
        )
    )
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT" in str(compiled)
    # The reason string is a bound parameter, not inline SQL text.
    assert "reason" in compiled.params.values()
    assert "'reason'" not in str(compiled)


# ---------------------------------------------------------------------------
# Routing & retry wiring (mocked session manager)
# ---------------------------------------------------------------------------


def _mock_manager_with_session(result_row: object) -> tuple[MagicMock, dict[str, object]]:
    captured: dict[str, object] = {}
    fake_session = MagicMock(name="session")
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = result_row
    fake_session.execute.return_value = exec_result

    @contextmanager
    def _session(*, read_only: bool) -> Iterator[MagicMock]:
        captured["read_only"] = read_only
        yield fake_session

    manager = MagicMock(spec=SessionManager)
    manager.session.side_effect = _session
    return manager, captured


def test_load_routes_to_reader() -> None:
    manager, captured = _mock_manager_with_session(result_row=None)
    repo = KillSwitchStateRepository(
        manager,
        retry_policy=RetryPolicy(attempts=1, initial_backoff=0.001, max_backoff=0.002, max_jitter=0.001),
    )
    assert repo.load() is None
    assert captured["read_only"] is True  # reads must go to a replica.


def test_upsert_routes_to_writer_and_returns_row() -> None:
    sentinel = KillSwitchState(id=1, engaged=True, reason="written")
    captured: dict[str, object] = {}
    fake_session = MagicMock(name="session")
    exec_result = MagicMock()
    exec_result.scalar_one.return_value = sentinel
    fake_session.execute.return_value = exec_result

    @contextmanager
    def _session(*, read_only: bool) -> Iterator[MagicMock]:
        captured["read_only"] = read_only
        yield fake_session

    manager = MagicMock(spec=SessionManager)
    manager.session.side_effect = _session
    repo = KillSwitchStateRepository(
        manager,
        retry_policy=RetryPolicy(attempts=1, initial_backoff=0.001, max_backoff=0.002, max_jitter=0.001),
    )
    assert repo.upsert(engaged=True, reason="written") is sentinel
    assert captured["read_only"] is False  # writes must route to the primary.


def test_ensure_schema_wraps_engine_failure_in_database_error() -> None:
    manager = MagicMock(spec=SessionManager)
    engine = MagicMock()
    engine.dispose.return_value = None
    manager.writer_engine = engine
    repo = KillSwitchStateRepository(manager)
    # Force metadata.create_all to fail by giving a non-engine bindable.
    manager.writer_engine = object()
    with pytest.raises(DatabaseError):
        repo.ensure_schema()


# ---------------------------------------------------------------------------
# DataAccessLayer transaction commit/rollback semantics
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_transaction_commits_and_closes_on_success() -> None:
    conn = _FakeConn()
    dal = DataAccessLayer(connection_factory=lambda: conn)
    with dal.transaction() as active:
        assert active is conn
    assert conn.committed and conn.closed and not conn.rolled_back


def test_transaction_rolls_back_and_closes_on_error() -> None:
    conn = _FakeConn()
    dal = DataAccessLayer(connection_factory=lambda: conn)
    with pytest.raises(ValueError):
        with dal.transaction():
            raise ValueError("boom")
    assert conn.rolled_back and conn.closed and not conn.committed
