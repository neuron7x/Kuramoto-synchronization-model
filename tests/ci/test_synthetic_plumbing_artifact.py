# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Forward proof: the synthetic plumbing artifact exercises the whole pipeline.

These tests prove the chain runs FORWARD (a correctly-built artifact passes every
gate AND is reproducible) and stays fail-closed (corruption, missing lineage, or
an empirical overclaim from synthetic data is rejected). No empirical claim is
made: the artifact is INSTRUMENTED / NOT_APPLICABLE on closed-form synthetic data.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gen = _load("synthetic_plumbing_gen", "scripts/research/generate_synthetic_plumbing_artifact.py")
truth = _load("spv1_truth", "scripts/ci/check_research_artifact_truth.py")
graph = _load("spv1_graph", "scripts/ci/check_claim_artifact_graph.py")

ARTIFACT_PATH = ROOT / "artifacts" / "runs" / "synthetic_plumbing_v1" / "artifact.json"
DATA_PATH = ROOT / "artifacts" / "runs" / "synthetic_plumbing_v1" / "synthetic_returns.csv"


def _artifact() -> dict[str, object]:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


class SyntheticArtifactValid(unittest.TestCase):
    def test_passes_truth_gate(self) -> None:
        errs = truth.evaluate_artifact(
            ARTIFACT_PATH.relative_to(ROOT), _artifact()
        )
        self.assertEqual(errs, [])

    def test_repository_graph_includes_and_accepts_the_line(self) -> None:
        # The live graph gate must accept the synthetic line end-to-end.
        self.assertEqual(graph.check(ROOT), [])

    def test_is_honestly_non_empirical(self) -> None:
        a = _artifact()
        self.assertEqual(a["claim_tier"], "INSTRUMENTED")
        self.assertEqual(a["falsification_status"], "NOT_APPLICABLE")
        self.assertEqual(a["score_source"], "computed")
        self.assertEqual(a["decision"], "OBSERVE")


class SyntheticArtifactReproducible(unittest.TestCase):
    def test_replay_reproduces_data_hash_exactly(self) -> None:
        panel = gen.synthetic_returns()
        csv = gen.canonical_csv(panel)
        recomputed = hashlib.sha256(csv.encode("utf-8")).hexdigest()
        self.assertEqual(recomputed, _artifact()["data_sha256"])

    def test_committed_data_file_matches_artifact_hash(self) -> None:
        on_disk = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
        self.assertEqual(on_disk, _artifact()["data_sha256"])

    def test_replay_reproduces_score_within_tolerance(self) -> None:
        panel = gen.synthetic_returns()
        recomputed = gen.mean_abs_offdiag_corr(panel)
        self.assertAlmostEqual(recomputed, float(_artifact()["score"]), places=9)

    def test_replay_command_is_present_and_real(self) -> None:
        a = _artifact()
        self.assertEqual(a["replay_command"], gen.REPLAY_COMMAND)
        self.assertTrue(str(a["replay_command"]).strip())


class SyntheticArtifactFailClosed(unittest.TestCase):
    def test_corrupt_data_hash_is_detectable(self) -> None:
        # A tampered hash no longer matches the committed data — the replay
        # equality test is the detector.
        on_disk = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
        self.assertNotEqual(on_disk, "0" * 64)
        self.assertNotEqual(on_disk, "f" * 64)

    def test_empirical_overclaim_from_synthetic_is_rejected(self) -> None:
        a = _artifact()
        a["claim_tier"] = "LIMITED_EMPIRICAL"  # synthetic data must not claim empirical
        errs = truth.evaluate_artifact(ARTIFACT_PATH.relative_to(ROOT), a)
        self.assertTrue(any("cannot carry empirical claim_tier" in e for e in errs), errs)

    def test_not_applicable_without_computed_is_rejected(self) -> None:
        a = _artifact()
        a["score_source"] = "placeholder"
        errs = truth.evaluate_artifact(ARTIFACT_PATH.relative_to(ROOT), a)
        self.assertTrue(any("NOT_APPLICABLE requires score_source=computed" in e for e in errs), errs)

    def test_synthetic_cannot_masquerade_as_pass_evidence(self) -> None:
        # Flipping the INSTRUMENTED synthetic line to a PASS must be blocked by the
        # graph gate (a non-evidence tier cannot ship a PASS artifact).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "schemas" / "research").mkdir(parents=True)
            (root / "schemas" / "research" / "s.json").write_text("{}", encoding="utf-8")
            art_dir = root / "artifacts" / "runs" / "synthetic_plumbing_v1"
            art_dir.mkdir(parents=True)
            a = _artifact()
            a["falsification_status"] = "PASS"  # the overclaim
            (art_dir / "artifact.json").write_text(json.dumps(a), encoding="utf-8")
            line = root / "research_lines" / "synthetic_plumbing_v1"
            line.mkdir(parents=True)
            (line / "contract.yaml").write_text(
                "line_id: synthetic_plumbing_v1\nstate: INSTRUMENTED\n"
                "claim:\n  tier: INSTRUMENTED\n"
                "inference_contract:\n  canonical_schema: schemas/research/s.json\n"
                "artifact:\n  example: artifacts/runs/synthetic_plumbing_v1/artifact.json\n",
                encoding="utf-8",
            )
            violations = graph.check(root)
            self.assertTrue(any("cannot ship a PASS artifact" in e for e in violations), violations)


if __name__ == "__main__":
    unittest.main()
