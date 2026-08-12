# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Static checks for the AAR-PRO-V1 machine-readable invariant registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REGISTRY = Path("docs/operations/aar_pro_v1_invariants.yaml")


def _registry() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def test_aar_pro_invariants_registry_is_complete() -> None:
    data = _registry()

    assert data["schema_version"] == "AAR-PRO-V1-INVARIANTS"
    assert "post-factum prediction synthesis" in data["problem_statement"]
    assert "precision_weighted_error" in data["formulas"]
    assert "variational_energy_surrogate" in data["formulas"]
    assert "chronology_hash" in data["formulas"]

    invariants = data["invariants"]
    ids = {item["id"] for item in invariants}
    assert ids == {
        "AAR-PRO-SEQ-001",
        "AAR-PRO-NODEFAULT-002",
        "AAR-PRO-PRECISION-003",
        "AAR-PRO-EVIDENCE-004",
        "AAR-PRO-CHRONOLOGY-005",
        "AAR-PRO-ENERGY-006",
        "AAR-PRO-SELFHEAL-007",
        "AAR-PRO-FORMAL-008",
    }


def test_aar_pro_invariants_registry_paths_exist() -> None:
    data = _registry()

    for item in data["invariants"]:
        enforcement = item["enforcement"]
        for path in enforcement["code"]:
            assert Path(path).exists(), f"missing code path for {item['id']}: {path}"
        for test_ref in enforcement["tests"]:
            test_path = test_ref.split("::", 1)[0]
            if test_path.endswith(".py"):
                assert Path(test_path).exists(), f"missing test path for {item['id']}: {test_path}"

    for evidence in data["evidence"]:
        assert Path(evidence["path"]).exists(), f"missing evidence path: {evidence['path']}"


def test_aar_pro_invariants_registry_binds_product_commands() -> None:
    commands = _registry()["readiness_commands"]

    assert "test_14b_precision_inversion_is_falsifiable" in commands["falsifier"]
    assert "test_dro_ara_ara_state_keeps_bounded_energy_window" in commands["falsifier"]
    assert commands["smoke"] == "python scripts/aar_pro_smoke.py"
    assert commands["readiness"] == "python scripts/aar_pro_readiness.py"
