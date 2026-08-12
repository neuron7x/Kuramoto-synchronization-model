# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""KnowledgeNode + status classification tests."""

from __future__ import annotations

import pytest

from runtime.cognitive_bridge.knowledge_node import (
    DEFAULT_THRESHOLDS,
    KnowledgeNode,
    KnowledgeStatus,
    KnowledgeThresholds,
)
from runtime.cognitive_bridge.value_function import GvCondition


def _gv(*, fc: bool = True, ve: bool = True, audit: bool = True) -> GvCondition:
    return GvCondition(
        has_falsification_contract=fc,
        has_verification_evidence=ve,
        completed_audit=audit,
    )


def test_failing_gv_yields_rejected() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.99, gv=_gv(fc=False))
    assert status is KnowledgeStatus.REJECTED


def test_high_value_with_full_gv_yields_core_fact() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.50, gv=_gv())
    assert status is KnowledgeStatus.CORE_FACT


def test_mid_value_yields_working_hypothesis() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.35, gv=_gv())
    assert status is KnowledgeStatus.WORKING_HYPOTHESIS


def test_low_value_yields_contextual_tool() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.20, gv=_gv())
    assert status is KnowledgeStatus.CONTEXTUAL_TOOL


def test_below_floor_with_audit_yields_archived_error() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.05, gv=_gv())
    assert status is KnowledgeStatus.ARCHIVED_ERROR


def test_below_floor_without_audit_yields_rejected() -> None:
    status = DEFAULT_THRESHOLDS.classify(value=0.05, gv=_gv(audit=False))
    assert status is KnowledgeStatus.REJECTED


def test_thresholds_must_be_in_range() -> None:
    with pytest.raises(Exception):
        KnowledgeThresholds(core_fact=1.5)


def test_knowledge_node_is_frozen() -> None:
    node = KnowledgeNode(
        cycle_id="abc",
        status=KnowledgeStatus.CORE_FACT,
        value_score=0.5,
        falsification_contract="if R drops below 3/√N for K=0.1·K_c, INV-K2 fails",
        verification_evidence="tests/unit/physics/test_T22.py passes",
        summary="Kuramoto subcritical R bound",
    )
    with pytest.raises(Exception):
        node.value_score = 0.0  # type: ignore[misc]
