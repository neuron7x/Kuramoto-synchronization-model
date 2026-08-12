# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Sprint 3 — witnesses that the conftest session-isolation fixtures do
what they claim.

These tests cannot prove the post-session restore (we are *inside* the
session when they run), but they prove (a) that the defaults the fixture
promises are actually visible to every test, and (b) that the conftest
does not crash under pytest-randomly ordering.
"""

from __future__ import annotations

import os
import sys


def test_environment_defaults_are_visible() -> None:
    """``_test_env`` must have injected the Sprint-3 defaults before collection."""
    assert os.environ.get("GEOSYNC_TWO_FACTOR_SECRET") == "JBSWY3DPEHPK3PXP"
    assert os.environ.get("THERMO_DUAL_SECRET") == "test-secret"


def test_audit_trail_module_shim_is_registered() -> None:
    """Collection-time ``sys.modules`` wiring must still be in place."""
    assert "geosync_observability_audit_trail" in sys.modules
    assert "geosync_tests_fixtures" in sys.modules


def test_rerunning_same_assertions_is_stable() -> None:
    """Regression guard — same expectations twice, no hidden per-test
    mutation on env / sys.modules keys we watch."""
    assert os.environ.get("GEOSYNC_TWO_FACTOR_SECRET") == "JBSWY3DPEHPK3PXP"
    assert "geosync_observability_audit_trail" in sys.modules
