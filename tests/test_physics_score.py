# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _load_physics_score() -> Any:
    path = Path(__file__).resolve().parents[1] / "tools" / "physics_score.py"
    spec = importlib.util.spec_from_file_location("physics_score", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec so @dataclass can resolve module globals under
    # `from __future__ import annotations` (py3.12 looks up sys.modules[__module__]).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_physics_score_weights_sum_to_one() -> None:
    module = _load_physics_score()
    score = module.build_score()
    assert score["weights_sum"] == 1.0


def test_physics_score_has_required_metric_ids() -> None:
    module = _load_physics_score()
    metric_ids = {metric["id"] for metric in module.build_score()["metrics"]}
    assert metric_ids == {
        "S_math_object",
        "S_dimensional_consistency",
        "S_numerical_stability",
        "S_invariant_preservation",
        "S_falsifiability",
        "S_baseline_models",
        "S_UQ",
        "S_reproducibility",
        "S_interface_contracts",
        "S_traceability",
    }


def test_physics_score_remains_below_target_while_high_gates_exist() -> None:
    module = _load_physics_score()
    score = module.build_score()
    assert score["S_total"] < 88.0
    assert score["verdict"] == "FAIL_BELOW_TARGET_BLOCKED_FOR_VALIDATION"
    high_blockers = [b for b in score["blockers"] if b["severity"] == "HIGH"]
    assert high_blockers, "a below-target physics score must expose HIGH blockers"


def test_physics_score_is_schema_shaped() -> None:
    module = _load_physics_score()
    score = module.build_score()
    for key in {
        "schema_version",
        "status",
        "score_type",
        "commit",
        "branch",
        "target_interval",
        "S_total",
        "weights_sum",
        "metrics",
        "blockers",
        "verdict",
    }:
        assert key in score
