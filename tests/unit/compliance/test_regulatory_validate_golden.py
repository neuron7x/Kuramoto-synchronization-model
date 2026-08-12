# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization (golden) battery for RegulatoryComplianceValidator.validate.

validate() is a 374-LOC, cyclomatic-complexity-~61 sequence of ~13 independent
compliance checks. This battery freezes its observable behaviour on a corpus
that exercises every check branch (compliant baseline + one targeted violation
per check + nested-lookup forms + empty), so the function can be decomposed
into per-check methods with zero behaviour change. Each case locks the
``(compliant, sorted issues, metadata_view)`` triple.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.compliance.regulatory import RegulatoryComplianceValidator

_GOLDEN = json.loads((Path(__file__).with_name("regulatory_validate_golden.json")).read_text())


def _capture(report: Any) -> dict[str, Any]:
    return {
        "compliant": report.compliant,
        "issues": sorted(f"{i.severity}:{i.message}" for i in report.issues),
        "metadata_view": dict(report.metadata),
    }


@pytest.mark.parametrize("case", sorted(_GOLDEN))
def test_validate_matches_golden(case: str) -> None:
    entry = _GOLDEN[case]
    report = RegulatoryComplianceValidator().validate(entry["input"])
    assert _capture(report) == entry["output"], (
        f"validate() output changed for case '{case}' — the decomposition must be "
        f"behaviour-preserving. If a compliance-rule change is intended, regenerate "
        f"the golden corpus deliberately."
    )


def test_corpus_exercises_violations() -> None:
    # guard the guard: the corpus must keep covering real violations, not drift
    # into an all-compliant set that would make the golden vacuous.
    noncompliant = sum(1 for c in _GOLDEN.values() if not c["output"]["compliant"])
    assert noncompliant >= 15, "characterization corpus lost its violation coverage"
