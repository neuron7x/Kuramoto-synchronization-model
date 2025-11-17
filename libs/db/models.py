"""SQLAlchemy ORM models used by the shared data access layer."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "KillSwitchState"]


class Base(DeclarativeBase):
    """Declarative base for TradePulse ORM models."""


class KillSwitchState(Base):
    """Singleton row storing the current kill-switch status."""

    __tablename__ = "kill_switch_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    engaged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(length=2048), nullable=False, server_default=""
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_kill_switch_state_singleton"),
        Index("idx_kill_switch_state_updated_at", "updated_at"),
    )
