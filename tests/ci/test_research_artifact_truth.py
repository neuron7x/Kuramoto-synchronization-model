# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the semantic research-artifact truth gate.

Schema validity proves shape; this gate proves truth. These tests pin the
exact lies it must reject and the honest shapes it must accept.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "ci"
    / "check_research_artifact_truth.py"
)
spec = importlib.util.spec_from_file_location("check_research_artifact_truth", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

ZERO64 = "0" * 64
ZERO40 = "0" * 40
NONZERO64 = "a" * 64
NONZERO64B = "b" * 64
NONZERO40 = "c" * 40

ARTIFACT_PATH = Path("artifacts/runs/ricci_microstructure_v1/artifact.json")
PLACEHOLDER_PATH = Path("artifacts/runs/ricci_microstructure_v1/example_placeholder.json")


def _real_evidence(**overrides: object) -> dict[str, object]:
    """A semantically honest evidence-bearing artifact."""
    doc: dict[str, object] = {
        "run_id": "RFC-2026-MARKET-RICCI-V1",
        "git_sha": NONZERO40,
        "git_dirty": False,
        "data_sha256": NONZERO64,
        "config_sha256": NONZERO64B,
        "seed": 1337,
        "timestamp_utc": "2026-05-31T20:27:00Z",
        "input_window_sec": 30,
        "score": 0.31,
        "uncertainty": 0.02,
        "decision": "OBSERVE",
        "claim_tier": "MEASURED_SINGLE",
        "falsification_status": "PASS",
        "method_version": "ricci-ollivier-v1.0",
        "score_source": "computed",
        "baseline": "permutation_null_v1",
        "replay_command": "geosync-research run --line ricci_microstructure_v1 --config c --data d --out o",
        "env_sha256": "e" * 64,
        "output_sha256": "f" * 64,
        "agent": "ci:research-integrity-gate@" + ("a" * 40),
    }
    doc.update(overrides)
    return doc


def _placeholder(**overrides: object) -> dict[str, object]:
    """The honest zero-data placeholder shape."""
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


class TruthGateRejections(unittest.TestCase):
    def test_rejects_zero_data_sha_with_pass(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(data_sha256=ZERO64))
        self.assertTrue(any("zero data_sha256" in e and "PASS" in e for e in errs), errs)

    def test_rejects_zero_git_sha_with_pass(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(git_sha=ZERO40))
        self.assertTrue(any("git_sha" in e for e in errs), errs)

    def test_rejects_hypothesis_with_pass(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(claim_tier="HYPOTHESIS"))
        self.assertTrue(any("HYPOTHESIS" in e for e in errs), errs)

    def test_rejects_placeholder_score_with_pass(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(score=0.742))
        self.assertTrue(any("placeholder score" in e for e in errs), errs)

    def test_pass_requires_replay_command(self) -> None:
        doc = _real_evidence()
        del doc["replay_command"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("replay_command" in e for e in errs), errs)

    def test_pass_requires_baseline(self) -> None:
        doc = _real_evidence()
        del doc["baseline"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("baseline" in e for e in errs), errs)

    def test_pass_requires_computed_score_source(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(score_source="external"))
        self.assertTrue(any("score_source=computed" in e for e in errs), errs)

    def test_placeholder_cannot_claim_computed(self) -> None:
        errs = gate.evaluate_artifact(PLACEHOLDER_PATH, _placeholder(score_source="computed"))
        self.assertTrue(any("score_source=computed contradicts" in e for e in errs), errs)

    def test_pass_requires_env_sha256(self) -> None:
        doc = _real_evidence()
        del doc["env_sha256"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("env_sha256" in e for e in errs), errs)

    def test_pass_requires_output_sha256(self) -> None:
        doc = _real_evidence()
        del doc["output_sha256"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("output_sha256" in e for e in errs), errs)

    def test_pass_requires_agent(self) -> None:
        doc = _real_evidence()
        del doc["agent"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("agent attribution" in e for e in errs), errs)

    def test_tier_status_matrix_rejects_instrumented_pass(self) -> None:
        # INSTRUMENTED may only carry NOT_APPLICABLE/NOT_RUN, never an evidence status.
        errs = gate.evaluate_artifact(
            ARTIFACT_PATH, _real_evidence(claim_tier="INSTRUMENTED")
        )
        self.assertTrue(any("incompatible with" in e for e in errs), errs)

    def test_tier_status_matrix_rejects_rejected_with_pass(self) -> None:
        errs = gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence(claim_tier="REJECTED"))
        self.assertTrue(any("incompatible with" in e for e in errs), errs)

    def test_rejects_zero_data_not_marked_placeholder(self) -> None:
        # HYPOTHESIS + NOT_RUN + zero hashes, but NOT marked placeholder → reject.
        doc = _placeholder()
        del doc["artifact_role"]
        errs = gate.evaluate_artifact(ARTIFACT_PATH, doc)
        self.assertTrue(any("must be explicitly marked placeholder" in e for e in errs), errs)

    def test_rejects_zero_data_with_trade_decision(self) -> None:
        errs = gate.evaluate_artifact(PLACEHOLDER_PATH, _placeholder(decision="ABSTAIN"))
        self.assertTrue(any("decision in" in e for e in errs), errs)


class TruthGateAcceptances(unittest.TestCase):
    def test_accepts_zero_hashes_only_if_explicit_placeholder(self) -> None:
        # Field-marked placeholder is accepted.
        self.assertEqual(gate.evaluate_artifact(ARTIFACT_PATH, _placeholder()), [])
        # Filename-marked placeholder (no field) is accepted too.
        doc = _placeholder()
        del doc["artifact_role"]
        self.assertEqual(gate.evaluate_artifact(PLACEHOLDER_PATH, doc), [])

    def test_accepts_real_evidence_with_full_lineage(self) -> None:
        self.assertEqual(gate.evaluate_artifact(ARTIFACT_PATH, _real_evidence()), [])

    def test_non_placeholder_requires_real_hashes(self) -> None:
        # A non-placeholder artifact with real hashes and NOT_RUN is fine (provenance
        # run): data is loaded but inference has not run, so score is not computed.
        doc = _real_evidence(
            falsification_status="NOT_RUN",
            claim_tier="INSTRUMENTED",
            score=0.0,
            score_source="placeholder",
        )
        self.assertEqual(gate.evaluate_artifact(ARTIFACT_PATH, doc), [])


class TruthGateRepoScan(unittest.TestCase):
    def test_check_scans_and_rejects_fake_artifact(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "artifacts" / "runs" / "fake"
            run_dir.mkdir(parents=True)
            (run_dir / "artifact.json").write_text(
                json.dumps(_real_evidence(data_sha256=ZERO64, claim_tier="HYPOTHESIS")),
                encoding="utf-8",
            )
            violations = gate.check(root)
            self.assertTrue(violations)

    def test_check_passes_on_clean_placeholder(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "artifacts" / "runs" / "clean"
            run_dir.mkdir(parents=True)
            (run_dir / "example_placeholder.json").write_text(
                json.dumps(_placeholder()), encoding="utf-8"
            )
            self.assertEqual(gate.check(root), [])


if __name__ == "__main__":
    unittest.main()
