# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Centralised mapping between test paths and mandatory quality levels.

The TradePulse test mandate requires every pytest to declare an explicit
quality level marker (``l1``–``l7`` or ``l5`` for stability suites).  Touching
every historical test to sprinkle the correct marker would be brittle and easy
to forget, so we apply the mapping programmatically during collection.

This module exposes two helpers:

``resolve_level``
    Given a test file path, return the expected pytest marker name.  The rules
    intentionally operate on POSIX paths so the same behaviour works on Linux
    and Windows runners.

``LEVEL_RULES``
    Structured mapping that can be inspected by tooling and unit tests to
    ensure the taxonomy stays aligned with repository layout changes.

The implementation is deliberately declarative – extending the taxonomy is as
simple as appending a new ``LevelRule`` entry and adding a regression test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pytest

__all__ = ["LEVEL_MARKERS", "LEVEL_RULES", "LevelRule", "resolve_level"]


LEVEL_MARKERS: tuple[str, ...] = ("l1", "l2", "l3", "l4", "l5", "l6", "l7")


@dataclass(frozen=True)
class LevelRule:
    """Declare how a test file path should map to a pytest marker."""

    marker: str
    patterns: tuple[str, ...]
    description: str

    def matches(self, file_path: Path) -> bool:
        """Return ``True`` when *file_path* is governed by this rule."""

        posix_path = file_path.as_posix()
        for pattern in self.patterns:
            if not pattern:
                continue
            if pattern.endswith("/") and posix_path.startswith(pattern):
                return True
            if posix_path == pattern:
                return True
        return False


def _rules() -> list[LevelRule]:
    """Build the ordered level rules for the repository."""

    return [
        LevelRule(
            marker="l5",
            patterns=(
                "tests/chaos/",
                "tests/performance/",
                "tests/security/",
                "tests/tacl/",
                "tests/fuzz/",
                "tests/nightly/",
                "tests/e2e/test_progressive_rollout.py",
                "tests/test_energy.py",
                "tests/test_link_activator.py",
                "tests/test_recovery_agent.py",
                "tests/test_thermo_audit.py",
                "tests/test_thermo_fallback.py",
                "tests/test_thermo_manual_override.py",
            ),
            description=(
                "Thermodynamic stability, chaos, and degradation guards must run at L5 "
                "before rollout decisions are taken."
            ),
        ),
        LevelRule(
            marker="l4",
            patterns=("tests/e2e/", "tests/smoke/"),
            description="End-to-end trading lifecycle regressions.",
        ),
        LevelRule(
            marker="l2",
            patterns=(
                "tests/contracts/",
                "tests/api/",
                "tests/interfaces/",
                "tests/protocol/",
                "tests/sdk/test_sdk_contract.py",
            ),
            description="Contract, schema, RBAC, and SDK surface enforcement suites.",
        ),
        LevelRule(
            marker="l1",
            patterns=(
                "tests/unit/",
                "tests/utils/",
                "tests/data/",
                "tests/analysis/",
                "tests/analytics/",
                "tests/property/",
                "tests/neuro/",
                "tests/neuropro/",
                "tests/hydrobrain_v2/",
                "tests/generated/",
                "tests/test_composite.py",
                "tests/test_conformal.py",
                "tests/test_conformal_online.py",
                "tests/test_cv.py",
                "tests/test_drift.py",
                "tests/test_metric_validations.py",
                "tests/test_fairness.py",
                "tests/test_nlca_core.py",
            ),
            description="Pure unit suites without external side effects.",
        ),
        LevelRule(
            marker="l3",
            patterns=(
                "tests/integration/",
                "tests/core/",
                "tests/execution/",
                "tests/strategies/",
                "tests/workflows/",
                "tests/scripts/",
                "tests/sandbox/",
                "tests/observability/",
                "tests/markets/",
                "tests/admin/",
                "tests/evolution/",
                "tests/analytics/signals/",
                "tests/analytics/etl/",
                "tests/analytics/pipelines/",
                "tests/tools/",
                "tests/test_execution.py",
                "tests/test_policy.py",
                "tests/test_polygon_integration.py",
                "tests/test_scan_assets.py",
            ),
            description="Cross-module integration scenarios for the analytics core.",
        ),
    ]


LEVEL_RULES: tuple[LevelRule, ...] = tuple(_rules())


def resolve_level(file_path: Path) -> str:
    """Return the pytest marker name for *file_path* or raise ``UsageError``."""

    for rule in LEVEL_RULES:
        if rule.matches(file_path):
            return rule.marker
    raise pytest.UsageError(
        "No quality level mapping found for test file. Update `tests/_helpers/quality_levels.py` "
        f"to classify {file_path.as_posix()}"
    )


def iter_rules() -> Iterable[LevelRule]:
    """Expose the ordered rules for inspection (mainly for testing)."""

    return iter(LEVEL_RULES)


def known_markers() -> Sequence[str]:
    """Return the tuple of supported quality level markers."""

    return LEVEL_MARKERS

