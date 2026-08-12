# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from observability import exporters


class DummyEvent:
    def __init__(self) -> None:
        self.wait_calls = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return True

    def set(self):  # pragma: no cover - compatibility shim
        pass


class FakeProcess:
    def __init__(self, target=None, name=None, args=(), daemon=None, **kwargs):
        self.target = target
        self.name = name
        self.args = args
        self.daemon = daemon
        self.kwargs = kwargs
        self.start_called = False
        self.terminate_called = False
        self.join_calls = []
        self._alive = True

    def start(self):
        self.start_called = True

    def is_alive(self):
        return self._alive

    def terminate(self):
        self.terminate_called = True
        self._alive = False

    def join(self, timeout=None):
        self.join_calls.append(timeout)


@pytest.fixture
def fake_multiprocessing(monkeypatch):
    events = []

    def event_factory():
        event = DummyEvent()
        events.append(event)
        return event

    monkeypatch.setattr(exporters, "_PROM_AVAILABLE", True)
    monkeypatch.setattr(exporters.multiprocessing, "Event", event_factory)
    monkeypatch.setattr(exporters.multiprocessing, "Process", FakeProcess)
    return events


def test_start_prometheus_exporter_requires_prometheus(monkeypatch):
    monkeypatch.setattr(exporters, "_PROM_AVAILABLE", False)

    with pytest.raises(RuntimeError):
        exporters.start_prometheus_exporter_process()


def test_exporter_process_lifecycle(fake_multiprocessing):
    events = fake_multiprocessing

    process = exporters.start_prometheus_exporter_process(port=9100, addr="127.0.0.1")

    assert isinstance(process, FakeProcess)
    assert process.start_called is True
    assert process.name == "prometheus-exporter"
    assert process.args[0:2] == (9100, "127.0.0.1")

    ready_event = events[0]
    assert ready_event.wait_calls == [5]
    assert process.args[2] is ready_event

    exporters.stop_exporter_process(process, timeout=2.0)
    assert process.terminate_called is True
    assert process.join_calls == [2.0]
    assert process._alive is False

    exporters.stop_exporter_process(None)

    inactive = FakeProcess(target=None)
    inactive._alive = False
    exporters.stop_exporter_process(inactive)
    assert inactive.terminate_called is False
    assert inactive.join_calls == []
