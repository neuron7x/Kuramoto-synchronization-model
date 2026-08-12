# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Database utilities for the cortex service."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import ConfigurationError, CortexSettings


class Base(DeclarativeBase):
    """Declarative base shared across cortex models."""


SessionFactory = sessionmaker(expire_on_commit=False, class_=Session)


def create_db_engine(settings: CortexSettings) -> Engine:
    """Create the SQLAlchemy engine using application settings."""

    url = settings.database.url
    if url.startswith("sqlite"):
        return create_engine(
            url,
            echo=settings.database.echo,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    connect_kwargs: dict[str, object] = {
        "echo": settings.database.echo,
        "pool_size": settings.database.pool_size,
        "pool_timeout": settings.database.pool_timeout,
        "future": True,
    }
    parsed = urlparse(url)
    if parsed.scheme.startswith("postgres"):
        tls = settings.database.tls
        if tls is None:
            raise ConfigurationError("PostgreSQL connections require TLS credentials")
        params = parse_qs(parsed.query, keep_blank_values=True)
        sslmode_list = params.get("sslmode", [])
        sslmode = sslmode_list[-1] if sslmode_list else None
        if sslmode not in {"verify-full", "verify-ca"}:
            raise ConfigurationError(
                "PostgreSQL connections must set sslmode to verify-full or verify-ca"
            )
        connect_kwargs["connect_args"] = {
            "sslmode": sslmode,
            "sslrootcert": str(tls.ca_file),
            "sslcert": str(tls.cert_file),
            "sslkey": str(tls.key_file),
        }
    return create_engine(url, **connect_kwargs)


def configure_session_factory(engine: Engine) -> None:
    """Bind the global session factory to the provided engine."""

    SessionFactory.configure(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope for database operations."""

    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - exception propagation path
        session.rollback()
        raise
    finally:
        session.close()


Dependency = Callable[[], Iterator[Session]]


def session_dependency() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    with session_scope() as session:
        yield session


__all__ = [
    "Base",
    "SessionFactory",
    "configure_session_factory",
    "create_db_engine",
    "session_dependency",
    "session_scope",
]
