"""Tests for runtime shim entrypoints used by the new container pipeline."""

from __future__ import annotations

from types import ModuleType
from typing import Callable

import importlib
import runpy
import sys

import pytest


@pytest.fixture(name="server_run")
def _server_run(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    calls: list[None] = []

    def _run() -> None:
        calls.append(None)

    server_module = importlib.import_module("application.runtime.server")
    monkeypatch.setattr(server_module, "run", _run, raising=False)
    app_main = importlib.import_module("app.main")
    monkeypatch.setattr(app_main, "run", _run, raising=False)
    yield _run
    assert calls, "expected application.runtime.server.run to be invoked"


def test_app_main_invokes_legacy_runtime(server_run: Callable[[], None]) -> None:
    module = importlib.import_module("app.main")
    module.main()


def test_app_dunder_main_executes(server_run: Callable[[], None]) -> None:
    runpy.run_module("app.__main__", run_name="__main__")


def test_healthcheck_passes_when_import_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "application.runtime.server", ModuleType("application.runtime.server"))
    module = importlib.import_module("healthcheck")
    assert module.main() == 0


def test_healthcheck_fails_when_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("healthcheck")

    def _import(name: str, package: str | None = None):
        raise RuntimeError("boom")

    monkeypatch.setattr(importlib, "import_module", _import)
    assert module.main() == 1
