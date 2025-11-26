"""Repository abstractions built on top of SQLAlchemy sessions."""

from __future__ import annotations

import logging
from typing import Callable, Generic, Optional, TypeVar, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .exceptions import DatabaseError
from .models import Base, KillSwitchState
from .retry import RetryPolicy, run_with_retry
from .session import SessionManager

__all__ = ["SqlAlchemyRepository", "KillSwitchStateRepository"]

T = TypeVar("T")


class SqlAlchemyRepository(Generic[T]):
    """Base repository with retry and read/write routing support."""

    def __init__(
        self,
        session_manager: SessionManager,
        *,
        retry_policy: RetryPolicy | None = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._session_manager = session_manager
        self._retry_policy = retry_policy or RetryPolicy()
        self._logger = logger or logging.getLogger(self.__class__.__name__)

    def _execute(self, func: Callable[[Session], T], *, read_only: bool) -> T:
        def operation() -> T:
            with self._session_manager.session(read_only=read_only) as session:
                return func(session)

        return cast(T, run_with_retry(self._retry_policy, self._logger, operation))


class KillSwitchStateRepository(SqlAlchemyRepository[KillSwitchState]):
    """Persistence adapter for the global kill-switch state."""

    def load(self) -> KillSwitchState | None:
        def _load(session: Session) -> KillSwitchState | None:
            stmt = select(KillSwitchState).where(KillSwitchState.id == 1)
            result = session.execute(stmt)
            return result.scalar_one_or_none()

        return self._execute(_load, read_only=True)

    def upsert(self, *, engaged: bool, reason: str) -> KillSwitchState:
        def _upsert(session: Session) -> KillSwitchState:
            stmt = (
                insert(KillSwitchState)
                .values(id=1, engaged=engaged, reason=reason)
                .on_conflict_do_update(
                    index_elements=[KillSwitchState.id],
                    set_={
                        "engaged": engaged,
                        "reason": reason,
                        "updated_at": func.now(),
                    },
                )
                .returning(KillSwitchState)
            )
            return session.execute(stmt).scalar_one()

        return self._execute(_upsert, read_only=False)

    def ensure_schema(self) -> None:
        try:
            Base.metadata.create_all(
                self._session_manager.writer_engine, tables=[KillSwitchState.__table__]
            )
        except Exception as exc:  # pragma: no cover - defensive guard for engine issues
            raise DatabaseError(
                "Failed to initialise kill_switch_state schema"
            ) from exc
