# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the non-vacuous manifest hash gate.

A pass over zero artifacts is not proof. Proof mode (``--min-artifacts``)
must fail honestly when there is nothing to verify.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_manifest_hashes.py"
)
spec = importlib.util.spec_from_file_location("check_manifest_hashes", MODULE_PATH)
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)


class ManifestGateBehaviour(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_root = gate.ROOT
        self._orig_discover = gate._discover_manifest_paths

    def tearDown(self) -> None:
        gate.ROOT = self._orig_root
        gate._discover_manifest_paths = self._orig_discover

    def _seed_manifest(self, tmp: Path, n_artifacts: int) -> Path:
        gate.ROOT = tmp
        artifacts = []
        for i in range(n_artifacts):
            payload = f"artifact-{i}".encode()
            (tmp / f"a{i}.bin").write_bytes(payload)
            artifacts.append(
                {"path": f"a{i}.bin", "sha256": hashlib.sha256(payload).hexdigest()}
            )
        manifest = tmp / "manifest.json"
        manifest.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
        gate._discover_manifest_paths = lambda: [manifest]
        return manifest

    def test_default_mode_allows_zero_artifacts(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gate.ROOT = Path(tmp)
            gate._discover_manifest_paths = list
            self.assertEqual(gate.main([]), 0)

    def test_min_artifacts_fails_when_zero(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gate.ROOT = Path(tmp)
            gate._discover_manifest_paths = list
            self.assertEqual(gate.main(["--min-artifacts", "1"]), 1)

    def test_require_artifacts_alias_fails_when_zero(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gate.ROOT = Path(tmp)
            gate._discover_manifest_paths = list
            self.assertEqual(gate.main(["--require-artifacts"]), 1)

    def test_min_artifacts_passes_when_present_and_valid(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self._seed_manifest(Path(tmp), 2)
            self.assertEqual(gate.main(["--min-artifacts", "1"]), 0)

    def test_checksum_mismatch_fails(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_manifest(root, 1)
            (root / "a0.bin").write_bytes(b"tampered")  # corrupt the artifact
            self.assertEqual(gate.main(["--min-artifacts", "1"]), 1)

    def test_evidence_freshness_manifest_schema_is_skipped(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.ROOT = root
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "evidence_artifact_freshness.v1",
                        "artifacts": [
                            {"path": "missing.json", "sha256": "0" * 64}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            gate._discover_manifest_paths = lambda: [manifest]
            self.assertEqual(gate.main([]), 0)

    def test_contract_manifest_missing_artifact_fails(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.ROOT = root
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "contract_manifest.v1",
                        "artifacts": [
                            {"path": "missing.json", "sha256": "0" * 64}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            gate._discover_manifest_paths = lambda: [manifest]
            self.assertEqual(gate.main([]), 1)


if __name__ == "__main__":
    unittest.main()
