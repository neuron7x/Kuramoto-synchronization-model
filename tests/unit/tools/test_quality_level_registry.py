# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from pathlib import Path

import pytest

from tests._helpers import quality_levels as ql


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("tests/unit/core/test_scheduler.py", "l1"),
        ("tests/contracts/test_openapi_contracts.py", "l2"),
        ("tests/core/orchestrator/test_mode_orchestrator.py", "l3"),
        ("tests/e2e/test_full_pipeline.py", "l4"),
        ("tests/chaos/test_risk_spikes.py", "l5"),
    ],
)
def test_resolve_level_assigns_expected_marker(candidate: str, expected: str) -> None:
    assert ql.resolve_level(Path(candidate)) == expected


def test_resolve_level_exact_match_file() -> None:
    assert ql.resolve_level(Path("tests/test_energy.py")) == "l5"


def test_resolve_level_unknown_path_raises_usage_error() -> None:
    with pytest.raises(pytest.UsageError):
        ql.resolve_level(Path("tests/unmapped/test_unknown.py"))


def test_level_rules_document_all_known_markers() -> None:
    marker_set = {rule.marker for rule in ql.iter_rules()}
    assert marker_set.issubset(set(ql.known_markers()))
