# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the claim-to-artifact graph gate.

The gate proves that a research line's declared state/tier is actually backed by
an artifact whose hashes and falsification status earn it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_claim_artifact_graph.py"
)
spec = importlib.util.spec_from_file_location("check_claim_artifact_graph", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

ZERO64 = "0" * 64
ZERO40 = "0" * 40
REAL64 = "a" * 64
REAL64B = "b" * 64
REAL40 = "c" * 40


def _artifact(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "run_id": "RFC-2026-MARKET-RICCI-V1",
        "git_sha": ZERO40,
        "git_dirty": False,
        "data_sha256": ZERO64,
        "config_sha256": "1" * 64,
        "seed": 1337,
        "timestamp_utc": "2026-05-31T20:27:00Z",
        "input_window_sec": 30,
        "score": 0.0,
        "uncertainty": 0.0,
        "decision": "OBSERVE",
        "claim_tier": "HYPOTHESIS",
        "falsification_status": "NOT_RUN",
        "artifact_role": "placeholder",
    }
    doc.update(overrides)
    return doc


def _build(root: Path, *, state: str, tier: str, artifact: dict[str, object],
           falsifier: bool = True, nulls: bool = True) -> None:
    line = root / "research_lines" / "demo_line"
    line.mkdir(parents=True)
    schema = root / "schemas" / "research" / "demo.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}", encoding="utf-8")
    art_path = root / "artifacts" / "runs" / "demo_line" / "example.json"
    art_path.parent.mkdir(parents=True)
    art_path.write_text(json.dumps(artifact), encoding="utf-8")
    claim: dict[str, object] = {"tier": tier, "status": "x"}
    if falsifier:
        claim["falsifier"] = "reject on null superiority"
    contract: dict[str, object] = {
        "schema_version": "research-line-contract.v1",
        "line_id": "demo_line",
        "state": state,
        "claim": claim,
        "inference_contract": {"canonical_schema": "schemas/research/demo.schema.json"},
        "artifact": {"example": "artifacts/runs/demo_line/example.json"},
    }
    if nulls:
        contract["falsification"] = {"required_nulls": ["permutation_null"]}
    (line / "contract.yaml").write_text(yaml.safe_dump(contract), encoding="utf-8")


class GraphGateRejections(unittest.TestCase):
    def test_evidence_state_with_zero_data_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="TESTED_REAL_SINGLE", tier="LIMITED_EMPIRICAL",
                   artifact=_artifact())  # zero hashes
            v = gate.check(root)
            self.assertTrue(any("asserts evidence" in e and "zero data_sha256" in e for e in v), v)

    def test_empirical_tier_zero_git_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="INSTRUMENTED", tier="LIMITED_EMPIRICAL",
                   artifact=_artifact(data_sha256=REAL64, config_sha256=REAL64B,
                                      git_sha=ZERO40, claim_tier="LIMITED_EMPIRICAL"))
            v = gate.check(root)
            self.assertTrue(any("non-zero git_sha" in e for e in v), v)

    def test_hypothesis_line_with_pass_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="HYPOTHESIS", tier="HYPOTHESIS",
                   artifact=_artifact(data_sha256=REAL64, config_sha256=REAL64B,
                                      git_sha=REAL40, score=0.3, claim_tier="HYPOTHESIS",
                                      falsification_status="PASS", artifact_role="evidence"))
            v = gate.check(root)
            self.assertTrue(any("cannot ship a PASS artifact" in e for e in v), v)

    def test_pass_without_falsifier_or_null_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="MEASURED_SINGLE", tier="MEASURED_SINGLE",
                   artifact=_artifact(data_sha256=REAL64, config_sha256=REAL64B, git_sha=REAL40,
                                      score=0.3, claim_tier="MEASURED_SINGLE",
                                      falsification_status="PASS", artifact_role="evidence"),
                   falsifier=False, nulls=False)
            v = gate.check(root)
            self.assertTrue(any("neither a falsifier nor required null" in e for e in v), v)

    def test_missing_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            line = root / "research_lines" / "demo_line"
            line.mkdir(parents=True)
            (line / "contract.yaml").write_text(
                "line_id: demo_line\nstate: HYPOTHESIS\nclaim:\n  tier: HYPOTHESIS\n"
                "inference_contract:\n  canonical_schema: schemas/x.json\n"
                "artifact:\n  example: artifacts/runs/demo_line/missing.json\n",
                encoding="utf-8",
            )
            v = gate.check(root)
            self.assertTrue(any("artifact not found" in e for e in v), v)


class GraphGateAcceptance(unittest.TestCase):
    def test_honest_hypothesis_placeholder_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="INSTRUMENTED", tier="HYPOTHESIS",
                   artifact=_artifact(), falsifier=True, nulls=True)
            self.assertEqual(gate.check(root), [])

    def test_real_evidence_line_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build(root, state="TESTED_REAL_SINGLE", tier="MEASURED_SINGLE",
                   artifact=_artifact(data_sha256=REAL64, config_sha256=REAL64B, git_sha=REAL40,
                                      score=0.31, uncertainty=0.02, decision="OBSERVE",
                                      claim_tier="MEASURED_SINGLE", falsification_status="PASS",
                                      artifact_role="evidence", score_source="computed",
                                      method_version="ricci-ollivier-v1.0",
                                      baseline="permutation_null_v1",
                                      replay_command="geosync-research run --line x --data d --out o",
                                      env_sha256="e" * 64, output_sha256="f" * 64,
                                      agent="ci:research-integrity-gate@" + ("a" * 40)))
            self.assertEqual(gate.check(root), [])


class GraphGateRealRepo(unittest.TestCase):
    def test_repository_graph_is_consistent(self) -> None:
        # The live repository must pass its own claim-artifact graph gate.
        self.assertEqual(gate.check(gate.ROOT), [])


if __name__ == "__main__":
    unittest.main()
