# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the generic data access layer helpers."""

from __future__ import annotations

import pytest

from libs.db.access import DataAccessLayer


class FakeCursor:
    """Collect executed queries and expose canned fetch results."""

    def __init__(
        self,
        *,
        fetchone_result: object | None = None,
        fetchall_result: list[object] | None = None,
    ) -> None:
        self.fetchone_result = fetchone_result
        self.fetchall_result = fetchall_result or []
        self.closed = False
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 0

    def execute(self, query: str, params: object = None) -> None:
        self.executed.append((query, params))
        # Simulate drivers reporting the amount of affected rows.
        if self.fetchall_result:
            self.rowcount = len(self.fetchall_result)
        else:
            self.rowcount = 1

    def fetchone(self) -> object | None:
        return self.fetchone_result

    def fetchall(self) -> list[object]:
        return list(self.fetchall_result)

    def close(self) -> None:
        self.closed = True


class ErrorCursor(FakeCursor):
    """Cursor that fails when executing a statement."""

    def execute(
        self, query: str, params: object = None
    ) -> None:  # pragma: no cover - simple delegation
        super().execute(query, params)
        raise RuntimeError("boom")


class FakeConnection:
    """Tiny stub mimicking the psycopg connection surface."""

    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class RecordingFactory:
    """Connection factory storing produced connections for inspection."""

    def __init__(
        self,
        cursor_factory: type[FakeCursor] | None = None,
        *,
        fetchone: object | None = None,
        fetchall: list[object] | None = None,
    ) -> None:
        self.cursor_factory = cursor_factory or FakeCursor
        self.fetchone = fetchone
        self.fetchall = fetchall
        self.connections: list[FakeConnection] = []

    def __call__(self) -> FakeConnection:
        cursor = self.cursor_factory(fetchone_result=self.fetchone, fetchall_result=self.fetchall)
        connection = FakeConnection(cursor)
        self.connections.append(connection)
        return connection


def test_execute_commits_and_returns_rowcount() -> None:
    factory = RecordingFactory()
    dal = DataAccessLayer(factory)

    affected = dal.execute("UPDATE foo SET bar = 1 WHERE id = %s", params=(1,))

    connection = factory.connections[-1]
    assert affected == 1
    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.cursor_instance.closed is True
    assert connection.closed is True


def test_fetch_all_returns_rows_without_committing() -> None:
    rows = [{"id": 1}, {"id": 2}]
    factory = RecordingFactory(fetchall=rows)
    dal = DataAccessLayer(factory)

    result = dal.fetch_all("SELECT * FROM foo")

    connection = factory.connections[-1]
    assert result == rows
    assert connection.committed is False
    assert connection.rolled_back is False


def test_execute_rolls_back_on_error() -> None:
    factory = RecordingFactory(cursor_factory=ErrorCursor)
    dal = DataAccessLayer(factory)

    with pytest.raises(RuntimeError):
        dal.execute("DELETE FROM foo")

    connection = factory.connections[-1]
    assert connection.committed is False
    assert connection.rolled_back is True


def test_transaction_context_manages_commit_and_rollback() -> None:
    factory = RecordingFactory()
    dal = DataAccessLayer(factory)

    with dal.transaction() as connection:
        assert connection is factory.connections[-1]

    connection = factory.connections[-1]
    assert connection.committed is True
    assert connection.rolled_back is False

    with pytest.raises(ValueError):
        with dal.transaction() as connection:
            raise ValueError("fail")

    connection = factory.connections[-1]
    assert connection.committed is False
    assert connection.rolled_back is True
