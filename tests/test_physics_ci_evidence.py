# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "physics_ci_evidence.py"

# The recorded copied evidence executed against #1220's merge SHA.
BOUND_SHA = "a6558ea3"
UNRELATED_SHA = "0" * 40


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("physics_ci_evidence", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sha_bound_evidence_records_required_green_gates() -> None:
    # Evidence IS bound to the scored commit -> required physics gates count.
    module = load_module()
    evidence = module.load_evidence()
    result = module.validate_evidence(evidence, head_sha=BOUND_SHA)
    assert result["all_required_physics_gates_green"] is True
    assert result["missing_required_workflows"] == []
    assert result["scored_commit_sha"] == BOUND_SHA
    assert "Physics Invariants" in result["successful_required_workflows"]
    assert "Physics Reliability Gate" in result["successful_required_workflows"]


def test_stale_evidence_is_fail_closed_against_unrelated_commit() -> None:
    # BLOCK-CI-001: evidence copied from another PR (different head_sha) must NOT
    # mark the physics gates green for an unrelated scored commit.
    module = load_module()
    evidence = module.load_evidence()
    result = module.validate_evidence(evidence, head_sha=UNRELATED_SHA)
    assert result["all_required_physics_gates_green"] is False
    assert result["successful_required_workflows"] == []
    assert "ci_evidence_not_bound_to_scored_commit" in result["blockers"]


def test_unresolved_head_sha_is_fail_closed() -> None:
    module = load_module()
    evidence = module.load_evidence()
    result = module.validate_evidence(evidence, head_sha="")
    assert result["all_required_physics_gates_green"] is False
    assert "head_sha_unresolved" in result["blockers"]


def test_physics_ci_evidence_does_not_promote_release_readiness() -> None:
    module = load_module()
    evidence = module.load_evidence()
    result = module.validate_evidence(evidence, head_sha=BOUND_SHA)
    assert result["full_pr_gate_green"] is False
    assert "full_pr_gate_not_green" in result["blockers"]
    assert evidence["score_implication"]["may_claim_final_physics_validation"] is False
    assert evidence["score_implication"]["may_claim_target_interval"] is False
