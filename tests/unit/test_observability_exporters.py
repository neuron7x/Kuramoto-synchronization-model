# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from multiprocessing import Event
from types import SimpleNamespace

import pytest

from observability import exporters


def test_start_prometheus_exporter_requires_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exporters, "_PROM_AVAILABLE", False, raising=False)
    with pytest.raises(RuntimeError, match="prometheus_client is not installed"):
        exporters.start_prometheus_exporter_process()


def test_start_prometheus_exporter_sets_ready_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Event] = []

    def fake_run(port: int, addr: str, ready: Event) -> None:
        events.append(ready)
        ready.set()

    class DummyProcess:
        def __init__(self, **kwargs) -> None:
            self._target = kwargs["target"]
            self._args = kwargs["args"]
            self.daemon = kwargs.get("daemon", False)
            self.name = kwargs.get("name")
            self.started = False

        def start(self) -> None:
            self.started = True
            self._target(*self._args)

        def join(self, timeout: float | None = None) -> None:  # pragma: no cover - noop
            return None

        def terminate(self) -> None:  # pragma: no cover - noop
            return None

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(
        exporters,
        "multiprocessing",
        SimpleNamespace(Event=Event, Process=lambda **kwargs: DummyProcess(**kwargs)),
    )
    monkeypatch.setattr(exporters, "_PROM_AVAILABLE", True, raising=False)
    monkeypatch.setattr(exporters, "_run_prometheus_exporter", fake_run, raising=False)

    process = exporters.start_prometheus_exporter_process(port=9100, addr="127.0.0.1")
    assert process.started is True
    assert events and events[0].is_set()


def test_stop_exporter_process_handles_alive_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.joined = False

        def is_alive(self) -> bool:
            return True

        def terminate(self) -> None:
            self.terminated = True

        def join(self, timeout: float | None = None) -> None:
            self.joined = True

    proc = FakeProcess()
    exporters.stop_exporter_process(proc, timeout=0.1)
    assert proc.terminated is True
    assert proc.joined is True


def test_stop_exporter_process_ignores_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:  # pragma: no cover - not invoked
            raise AssertionError("should not terminate")

        def join(self, timeout: float | None = None) -> None:  # pragma: no cover - not invoked
            raise AssertionError("should not join")

    exporters.stop_exporter_process(FakeProcess())
    exporters.stop_exporter_process(None)
