# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-maturity registry gate — self-falsification proof.

``scripts/ci/check_claim_maturity.py`` must PASS on the shipped
``governance/CLAIM_MATURITY.yaml`` and FAIL CLOSED when a registered claim
declares a rung its cumulative evidence does not support (a skipped state /
silent promotion), launders a descriptor with promotion language, or carries
an out-of-vocabulary evidence token; and return 2 on a malformed registry.
The gate runs over the canonical ladder in analytics/signals/claim_maturity.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_claim_maturity.py"
REGISTRY_PATH = ROOT / "governance" / "CLAIM_MATURITY.yaml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_claim_maturity", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_claim_maturity"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load()


def _write(tmp_path: Path, claims: list[dict[str, Any]]) -> Path:
    p = tmp_path / "CLAIM_MATURITY.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 1, "claims": claims}, sort_keys=False), encoding="utf-8")
    return p


def _run(gate: Any, path: Path) -> int:
    return gate.main(["--registry", str(path)])


def test_live_registry_passes(gate: Any) -> None:
    assert _run(gate, REGISTRY_PATH) == 0


def test_skipped_state_fails(gate: Any, tmp_path: Path) -> None:
    bad = {
        "id": "overclaim",
        "maturity_state": "BOUNDED_CLAIM_ALLOWED",
        "evidence": ["observability", "synthetic_measurement"],
        "description": "structural",
    }
    assert _run(gate, _write(tmp_path, [bad])) == 1


def test_synthetic_to_real_promotion_fails(gate: Any, tmp_path: Path) -> None:
    bad = {
        "id": "synthetic-as-real",
        "maturity_state": "REAL_DATA_SINGLE_SESSION",
        # everything up to REPLAYABLE but no real_data_artifact/provenance
        "evidence": [
            "observability",
            "synthetic_measurement",
            "alternatives_enumerated",
            "discriminating_test",
            "falsifier_executed",
            "calibration_record",
            "integration_proof",
            "replay_digest",
        ],
        "description": "structural",
    }
    assert _run(gate, _write(tmp_path, [bad])) == 1


def test_forbidden_language_fails(gate: Any, tmp_path: Path) -> None:
    bad = {
        "id": "laundered",
        "maturity_state": "MEASURED_SYNTHETIC",
        "evidence": ["observability", "synthetic_measurement"],
        "description": "this is alpha and guaranteed outperformance",
    }
    assert _run(gate, _write(tmp_path, [bad])) == 1


def test_unknown_evidence_token_fails(gate: Any, tmp_path: Path) -> None:
    bad = {
        "id": "typo-token",
        "maturity_state": "MEASURED_SYNTHETIC",
        "evidence": ["observability", "synthetic_measuremnt"],  # typo
        "description": "structural",
    }
    assert _run(gate, _write(tmp_path, [bad])) == 1


def test_wrong_boundary_fails(gate: Any, tmp_path: Path) -> None:
    bad = {
        "id": "bad-boundary",
        "maturity_state": "MEASURED_SYNTHETIC",
        "evidence": ["observability", "synthetic_measurement"],
        "claim_boundary": "predictive_alpha",
        "description": "structural",
    }
    assert _run(gate, _write(tmp_path, [bad])) == 1


def test_missing_registry_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, tmp_path / "absent.yaml") == 2


def test_empty_claims_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, _write(tmp_path, [])) == 2
