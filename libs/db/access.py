# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generic data access layer for relational databases.

This module provides a small abstraction for executing SQL queries in a
transactionally safe manner.  The :class:`DataAccessLayer` class accepts a
callable that yields raw database connections (for example a psycopg
connection factory) and exposes a higher level API for common operations.  The
goals of the abstraction are the following:

* ensure every connection is properly closed after use;
* automatically commit on success and roll back on failure when mutating
  queries are executed;
* provide thin helper methods for fetching single rows or full result sets
  without leaking cursor management to the callers.

The implementation intentionally stays minimal so that it can operate with any
DB-API 2.0 compatible driver.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

Params = Mapping[str, Any] | Sequence[Any] | None
RowT = TypeVar("RowT")

__all__ = ["DataAccessLayer"]


class SupportsCursor(Protocol):
    """Protocol representing the minimum surface of a DB connection."""

    def cursor(self) -> Any:  # pragma: no cover - runtime duck typing
        """Return a cursor object."""

    def commit(self) -> None:  # pragma: no cover - runtime duck typing
        """Commit the current transaction."""

    def rollback(self) -> None:  # pragma: no cover - runtime duck typing
        """Rollback the current transaction."""

    def close(self) -> None:  # pragma: no cover - runtime duck typing
        """Close the connection and release the underlying resources."""


@runtime_checkable
class SupportsCursorClose(Protocol):
    """Protocol for cursor objects that can be closed."""

    def close(self) -> None:  # pragma: no cover - runtime duck typing
        """Close the cursor."""

    def execute(
        self, query: str, params: Params = None
    ) -> Any:  # pragma: no cover - runtime duck typing
        """Execute a SQL query."""

    def fetchone(self) -> RowT | None:  # pragma: no cover - runtime duck typing
        """Return a single row from the result set, if available."""

    def fetchall(self) -> list[RowT]:  # pragma: no cover - runtime duck typing
        """Return all rows from the result set."""

    @property
    def rowcount(self) -> int:  # pragma: no cover - runtime duck typing
        """Expose the amount of rows affected by the last command."""


ConnectionFactory = Callable[[], SupportsCursor]


@dataclass(slots=True)
class DataAccessLayer:
    """High level wrapper around a connection factory.

    Parameters
    ----------
    connection_factory:
        Callable returning a new database connection each time it is invoked.
    """

    connection_factory: ConnectionFactory

    # ------------------------------------------------------------------
    # Public helpers
    def execute(self, query: str, params: Params = None) -> int:
        """Execute a statement and commit the transaction.

        The method returns the amount of rows affected as reported by the
        driver.  On failure the transaction is rolled back and the exception is
        propagated to the caller.
        """

        def _command(cursor: SupportsCursorClose) -> int:
            cursor.execute(query, params)
            return int(getattr(cursor, "rowcount", -1))

        return self._run(_command, commit_on_success=True)

    def fetch_one(self, query: str, params: Params = None) -> RowT | None:
        """Execute *query* and return the first row from the result set."""

        def _command(cursor: SupportsCursorClose) -> RowT | None:
            cursor.execute(query, params)
            return cursor.fetchone()

        return self._run(_command, commit_on_success=False)

    def fetch_all(self, query: str, params: Params = None) -> list[RowT]:
        """Execute *query* and return all rows."""

        def _command(cursor: SupportsCursorClose) -> list[RowT]:
            cursor.execute(query, params)
            return cursor.fetchall()

        return self._run(_command, commit_on_success=False)

    @contextmanager
    def transaction(self) -> Iterator[SupportsCursor]:
        """Yield a raw connection guarded by commit/rollback handlers."""

        connection = self.connection_factory()
        try:
            yield connection
        except Exception:  # pragma: no cover - defensive guard
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Internal helpers
    def _run(
        self, command: Callable[[SupportsCursorClose], RowT], *, commit_on_success: bool
    ) -> RowT:
        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            try:
                result = command(cursor)
            except Exception:
                connection.rollback()
                raise
            else:
                if commit_on_success:
                    connection.commit()
                return result
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
        finally:
            connection.close()
