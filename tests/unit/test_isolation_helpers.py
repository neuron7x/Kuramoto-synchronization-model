# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the X-axis scoped isolation helpers.

Asserts that ``IsolatedEnv`` / ``IsolatedModules`` leave ``os.environ``
and ``sys.modules`` in their pre-test state regardless of whether the
overridden keys existed beforehand.
"""

from __future__ import annotations

import os
import sys
import types

from tests.fixtures.isolation import (
    IsolatedEnv,
    IsolatedModules,
    env_overrides,
)


class TestIsolatedEnv:
    def test_sets_and_restores_absent_key(self) -> None:
        key = "GEOSYNC_ISO_TEST_ABSENT"
        assert key not in os.environ
        with IsolatedEnv({key: "yes"}):
            assert os.environ[key] == "yes"
        assert key not in os.environ

    def test_sets_and_restores_existing_key(self) -> None:
        key = "GEOSYNC_ISO_TEST_EXISTING"
        os.environ[key] = "before"
        try:
            with IsolatedEnv({key: "during"}):
                assert os.environ[key] == "during"
            assert os.environ[key] == "before"
        finally:
            os.environ.pop(key, None)

    def test_override_with_none_pops_key(self) -> None:
        key = "GEOSYNC_ISO_TEST_POP"
        os.environ[key] = "will-be-popped"
        try:
            with IsolatedEnv({key: None}):
                assert key not in os.environ
            assert os.environ[key] == "will-be-popped"
        finally:
            os.environ.pop(key, None)

    def test_env_overrides_shorthand(self) -> None:
        key = "GEOSYNC_ISO_SHORTHAND"
        with env_overrides(GEOSYNC_ISO_SHORTHAND="1"):
            assert os.environ[key] == "1"
        assert key not in os.environ


class TestIsolatedModules:
    def test_registers_and_restores_absent_module(self) -> None:
        name = "geosync_iso_fake_module"
        assert name not in sys.modules
        fake = types.ModuleType(name)
        with IsolatedModules({name: fake}):
            assert sys.modules[name] is fake
        assert name not in sys.modules

    def test_overrides_existing_module_and_restores(self) -> None:
        # Use a module that we know is always importable.

        original = sys.modules["math"]
        shim = types.ModuleType("math_shim")
        with IsolatedModules({"math": shim}):
            assert sys.modules["math"] is shim
        assert sys.modules["math"] is original

    def test_none_override_removes_module(self) -> None:
        name = "geosync_iso_pop_module"
        placeholder = types.ModuleType(name)
        sys.modules[name] = placeholder
        try:
            with IsolatedModules({name: None}):
                assert name not in sys.modules
            assert sys.modules[name] is placeholder
        finally:
            sys.modules.pop(name, None)


class TestFixtureForms:
    def test_fixture_form_env(self, isolated_env) -> None:
        isolated_env({"GEOSYNC_FIXTURE_FORM": "abc"})
        assert os.environ["GEOSYNC_FIXTURE_FORM"] == "abc"

    def test_env_fixture_restores_after_test(self, isolated_env) -> None:
        """Subtle: this test alone cannot prove post-test cleanup, but
        the fixture teardown is exercised by pytest's test sequencing
        — a leak would show up in other tests in this module."""
        isolated_env({"GEOSYNC_FIXTURE_RESTORED": "once"})
        assert "GEOSYNC_FIXTURE_RESTORED" in os.environ

    def test_fixture_form_modules(self, isolated_modules) -> None:
        name = "geosync_iso_fixture_form_mod"
        fake = types.ModuleType(name)
        isolated_modules({name: fake})
        assert sys.modules[name] is fake


def test_restore_visible_after_fixture_scope() -> None:
    """This function-scope test runs AFTER the earlier fixture-form
    tests. If cleanup is broken, ``GEOSYNC_FIXTURE_RESTORED`` would
    still leak here."""
    assert "GEOSYNC_FIXTURE_RESTORED" not in os.environ
    assert "geosync_iso_fixture_form_mod" not in sys.modules
