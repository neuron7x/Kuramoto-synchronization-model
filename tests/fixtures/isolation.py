# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Scoped isolation helpers for the GeoSync test suite — X-axis Phase 3.

The remediation protocol demands every test-time mutation of
``os.environ`` or ``sys.modules`` to be scope-bounded and auto-restored.
The baseline count (48 ``os.environ`` + 39 ``sys.modules`` sites)
cannot be migrated in one pass, but every *new* test landing after
Sprint 3 should prefer these helpers over direct mutation.

Usage
-----

.. code-block:: python

    from tests.fixtures.isolation import isolated_env, isolated_modules

    def test_config_reload(isolated_env):
        isolated_env({"MY_FLAG": "1"})
        # ...
        # env vars restored automatically at test teardown.

    def test_adapter_stub(isolated_modules):
        fake = types.ModuleType("my.fake.adapter")
        isolated_modules({"my.fake.adapter": fake})
        # ...
        # sys.modules entries restored automatically.

These helpers are context-manager-compatible when a test cannot use the
fixture form (e.g. inside a parametrized class):

    with IsolatedEnv({"X": "1"}):
        ...
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import ModuleType

import pytest

__all__ = [
    "IsolatedEnv",
    "IsolatedModules",
    "isolated_env",
    "isolated_modules",
]


class IsolatedEnv:
    """Context manager: set env vars, restore previous values on exit."""

    def __init__(self, overrides: Mapping[str, str | None]) -> None:
        self._overrides = dict(overrides)
        self._previous: dict[str, str | None] = {}

    def __enter__(self) -> IsolatedEnv:
        for key, value in self._overrides.items():
            self._previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *_: object) -> None:
        for key, original in self._previous.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


class IsolatedModules:
    """Context manager: install ``sys.modules`` stubs, restore on exit."""

    def __init__(self, overrides: Mapping[str, ModuleType | None]) -> None:
        self._overrides = dict(overrides)
        self._previous: dict[str, ModuleType | None] = {}

    def __enter__(self) -> IsolatedModules:
        for name, module in self._overrides.items():
            self._previous[name] = sys.modules.get(name)
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        return self

    def __exit__(self, *_: object) -> None:
        for name, previous in self._previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


@pytest.fixture
def isolated_env() -> Iterator[object]:
    """Function-scoped helper: call it with a mapping to override env.

    Returns a callable that takes ``{key: value_or_None}`` and installs
    it. All overrides are restored when the test exits.
    """
    active: list[IsolatedEnv] = []

    def _apply(overrides: Mapping[str, str | None]) -> None:
        box = IsolatedEnv(overrides)
        box.__enter__()
        active.append(box)

    yield _apply
    for box in reversed(active):
        box.__exit__(None, None, None)


@pytest.fixture
def isolated_modules() -> Iterator[object]:
    """Function-scoped helper: call it with a mapping to override sys.modules."""
    active: list[IsolatedModules] = []

    def _apply(overrides: Mapping[str, ModuleType | None]) -> None:
        box = IsolatedModules(overrides)
        box.__enter__()
        active.append(box)

    yield _apply
    for box in reversed(active):
        box.__exit__(None, None, None)


@contextmanager
def env_overrides(**overrides: str | None) -> Iterator[None]:
    """Shorthand: ``with env_overrides(MY_FLAG="1"): ...``."""
    with IsolatedEnv(overrides):
        yield
