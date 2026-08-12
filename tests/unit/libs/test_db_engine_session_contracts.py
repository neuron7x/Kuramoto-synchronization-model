# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed contracts for engine construction and session orchestration.

The SQLAlchemy engine is mocked where a live server would otherwise be needed,
so these tests assert *wiring* invariants: engines are pool-hardened and NOT
eager-connecting, sessions commit only on a clean exit, roll back and re-raise
on error, honour read-only routing, and dispose owned engines exactly once.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool, StaticPool

from core.config.cli_models import PostgresTLSConfig
from libs.db import engine as engine_mod
from libs.db import session as session_mod
from libs.db.config import DatabasePoolConfig, DatabaseRuntimeConfig
from libs.db.engine import _build_connect_args, create_engine_from_config, warm_pool
from libs.db.models import Base, KillSwitchState
from libs.db.session import SessionManager

# ---------------------------------------------------------------------------
# engine.py
# ---------------------------------------------------------------------------


def _pool() -> DatabasePoolConfig:
    return DatabasePoolConfig(size=7, max_overflow=3, timeout=4.0, recycle=900.0, use_lifo=False)


def _runtime() -> DatabaseRuntimeConfig:
    return DatabaseRuntimeConfig(
        application_name="unit-app",
        connect_timeout_seconds=2.5,
        statement_timeout_ms=1234,
    )


def test_create_engine_uses_hardened_queue_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = MagicMock(name="engine")
    fake_engine.execution_options.return_value = fake_engine
    created = MagicMock(return_value=fake_engine)
    monkeypatch.setattr(engine_mod, "create_engine", created)
    monkeypatch.setattr(engine_mod, "instrument_engine_metrics", MagicMock())

    result = create_engine_from_config(
        "postgresql://u@h/db?sslmode=verify-full",
        tls=None,
        pool=_pool(),
        runtime=_runtime(),
    )

    assert result is fake_engine
    _, kwargs = created.call_args
    assert kwargs["poolclass"] is QueuePool
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 3
    assert kwargs["pool_timeout"] == 4.0
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["future"] is True
    # Streaming results must be enabled for the shared read path.
    fake_engine.execution_options.assert_called_once()
    assert fake_engine.execution_options.call_args.kwargs["stream_results"] is True


def test_create_engine_does_not_connect_eagerly(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = MagicMock(name="engine")
    fake_engine.execution_options.return_value = fake_engine
    monkeypatch.setattr(engine_mod, "create_engine", MagicMock(return_value=fake_engine))
    monkeypatch.setattr(engine_mod, "instrument_engine_metrics", MagicMock())

    create_engine_from_config(
        "postgresql://u@h/db?sslmode=verify-full",
        tls=None,
        pool=_pool(),
        runtime=_runtime(),
    )
    fake_engine.connect.assert_not_called()


def test_pool_timeout_none_maps_to_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = MagicMock(name="engine")
    fake_engine.execution_options.return_value = fake_engine
    created = MagicMock(return_value=fake_engine)
    monkeypatch.setattr(engine_mod, "create_engine", created)
    monkeypatch.setattr(engine_mod, "instrument_engine_metrics", MagicMock())

    create_engine_from_config(
        "sqlite:///x.db",
        tls=None,
        pool=DatabasePoolConfig(timeout=None),
        runtime=_runtime(),
    )
    assert created.call_args.kwargs["pool_timeout"] is None


def test_build_connect_args_encodes_runtime_and_tls() -> None:
    tls = PostgresTLSConfig(ca_file="/tls/ca", cert_file="/tls/cert", key_file="/tls/key")
    args = _build_connect_args(tls, _runtime())
    assert args["connect_timeout"] == 2.5
    assert args["application_name"] == "unit-app"
    assert "statement_timeout=1234" in args["options"]
    assert "timezone=UTC" in args["options"]
    assert args["sslrootcert"] == "/tls/ca"
    assert args["sslcert"] == "/tls/cert"
    assert args["sslkey"] == "/tls/key"


def test_build_connect_args_without_tls_omits_ssl_keys() -> None:
    args = _build_connect_args(None, _runtime())
    assert "sslrootcert" not in args
    assert "target_session_attrs" not in args


def test_build_connect_args_includes_target_session_attrs_when_set() -> None:
    runtime = DatabaseRuntimeConfig(target_session_attrs="read-write")
    args = _build_connect_args(None, runtime)
    assert args["target_session_attrs"] == "read-write"


def test_warm_pool_opens_and_closes_requested_connections() -> None:
    conns = [MagicMock(name=f"c{i}") for i in range(3)]
    fake_engine = MagicMock()
    fake_engine.connect.side_effect = conns
    warm_pool(fake_engine, target_size=3)
    assert fake_engine.connect.call_count == 3
    for conn in conns:
        conn.close.assert_called_once()


def test_warm_pool_noop_on_non_positive_target() -> None:
    fake_engine = MagicMock()
    warm_pool(fake_engine, target_size=0)
    fake_engine.connect.assert_not_called()


def test_warm_pool_closes_even_when_a_later_connect_fails() -> None:
    good = MagicMock(name="good")
    fake_engine = MagicMock()
    fake_engine.connect.side_effect = [good, RuntimeError("pool exhausted")]
    with pytest.raises(RuntimeError):
        warm_pool(fake_engine, target_size=3)
    # The already-opened connection must still be released.
    good.close.assert_called_once()


# ---------------------------------------------------------------------------
# session.py — mocked-factory wiring invariants
# ---------------------------------------------------------------------------


def _manager_with_mock_session(monkeypatch: pytest.MonkeyPatch) -> tuple[SessionManager, MagicMock]:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    monkeypatch.setattr(session_mod, "DatabaseMonitor", MagicMock())
    mgr = SessionManager(MagicMock(name="writer"), monitoring_interval_seconds=None)
    fake_session = MagicMock(name="session")
    mgr._writer_factory = MagicMock(return_value=fake_session)
    return mgr, fake_session


def test_session_commits_and_closes_on_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr, fake_session = _manager_with_mock_session(monkeypatch)
    with mgr.session() as s:
        assert s is fake_session
    fake_session.commit.assert_called_once()
    fake_session.rollback.assert_not_called()
    fake_session.close.assert_called_once()


def test_session_rolls_back_and_reraises_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr, fake_session = _manager_with_mock_session(monkeypatch)
    with pytest.raises(ValueError):
        with mgr.session():
            raise ValueError("boom")
    fake_session.rollback.assert_called_once()
    fake_session.commit.assert_not_called()
    fake_session.close.assert_called_once()


def test_read_only_session_rolls_back_never_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr, fake_session = _manager_with_mock_session(monkeypatch)
    with mgr.session(read_only=True):
        pass
    fake_session.rollback.assert_called_once()
    fake_session.commit.assert_not_called()
    fake_session.close.assert_called_once()


def test_read_only_routing_cycles_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    monkeypatch.setattr(session_mod, "DatabaseMonitor", MagicMock())
    r1, r2 = MagicMock(name="r1"), MagicMock(name="r2")
    mgr = SessionManager(
        MagicMock(name="writer"), reader_engines=[r1, r2], monitoring_interval_seconds=None
    )
    writer_factory = mgr._writer_factory
    reader_factories = mgr._reader_factories
    # read-only requests round-robin across the reader factories.
    picks = [mgr._select_factory(read_only=True) for _ in range(4)]
    assert picks == [
        reader_factories[0],
        reader_factories[1],
        reader_factories[0],
        reader_factories[1],
    ]
    # writes always route to the writer factory.
    assert mgr._select_factory(read_only=False) is writer_factory


def test_read_only_without_readers_uses_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr, _ = _manager_with_mock_session(monkeypatch)
    assert mgr._select_factory(read_only=True) is mgr._writer_factory


def test_close_disposes_owned_engines_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    monkeypatch.setattr(session_mod, "DatabaseMonitor", MagicMock())
    writer, reader = MagicMock(name="w"), MagicMock(name="r")
    mgr = SessionManager(writer, reader_engines=[reader], monitoring_interval_seconds=None)
    mgr.close()
    mgr.close()  # idempotent
    writer.dispose.assert_called_once()
    reader.dispose.assert_called_once()


def test_close_does_not_dispose_when_not_owning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    monkeypatch.setattr(session_mod, "DatabaseMonitor", MagicMock())
    writer = MagicMock(name="w")
    mgr = SessionManager(writer, owns_engines=False, monitoring_interval_seconds=None)
    mgr.close()
    writer.dispose.assert_not_called()


def test_warmup_primes_writer_and_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    monkeypatch.setattr(session_mod, "DatabaseMonitor", MagicMock())
    warm = MagicMock()
    monkeypatch.setattr(session_mod, "warm_pool", warm)
    writer, reader = MagicMock(name="w"), MagicMock(name="r")
    mgr = SessionManager(writer, reader_engines=[reader], monitoring_interval_seconds=None)
    mgr.warmup(writer_connections=2, reader_connections=1)
    assert call(writer, target_size=2) in warm.call_args_list
    assert call(reader, target_size=1) in warm.call_args_list


def test_non_positive_monitoring_interval_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "instrument_engine_metrics", MagicMock())
    with pytest.raises(ValueError):
        SessionManager(MagicMock(name="w"), monitoring_interval_seconds=0.0)


# ---------------------------------------------------------------------------
# session.py — real in-memory SQLite persistence semantics
# ---------------------------------------------------------------------------


def _sqlite_manager() -> SessionManager:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng, tables=[KillSwitchState.__table__])
    return SessionManager(eng, monitoring_interval_seconds=None)


def test_clean_exit_persists_writes() -> None:
    mgr = _sqlite_manager()
    try:
        with mgr.session() as s:
            s.add(KillSwitchState(id=1, engaged=True, reason="engaged"))
        with mgr.session(read_only=True) as s:
            row = s.get(KillSwitchState, 1)
            assert row is not None and row.engaged is True
    finally:
        mgr.close()


def test_exception_rolls_back_partial_write() -> None:
    mgr = _sqlite_manager()
    try:
        with pytest.raises(RuntimeError):
            with mgr.session() as s:
                s.add(KillSwitchState(id=1, engaged=True, reason="doomed"))
                s.flush()
                raise RuntimeError("abort after write")
        with mgr.session(read_only=True) as s:
            assert s.get(KillSwitchState, 1) is None
    finally:
        mgr.close()


def test_read_only_session_discards_writes() -> None:
    mgr = _sqlite_manager()
    try:
        with mgr.session(read_only=True) as s:
            s.add(KillSwitchState(id=2, engaged=False, reason="ro"))
        with mgr.session(read_only=True) as s:
            assert s.get(KillSwitchState, 2) is None
    finally:
        mgr.close()


def test_monitor_lifecycle_starts_and_stops_cleanly() -> None:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng, tables=[KillSwitchState.__table__])
    # A positive interval spins up a background monitor per engine; close() must
    # stop the thread and dispose the engine without leaking either.
    mgr = SessionManager(eng, monitoring_interval_seconds=0.05)
    monitors = list(mgr._monitors)
    assert monitors, "a monitor thread must be started for a positive interval"
    mgr.close()
    # close() must stop every monitor thread (no leaked daemon threads).
    assert all(monitor._thread is None for monitor in monitors)
