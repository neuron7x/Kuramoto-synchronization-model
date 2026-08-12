# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative reproduction tests for the MFN capsule verifier (TASK 932).

The positive path (``--verify`` passes on the committed capsule) is exercised by
CI. These tests prove the *controlled failure* half: the verifier must fail
closed — and for the correct, named reason — when the capsule is corrupted in
each way a capsule can rot or be forged.

Each test runs against a sandbox COPY of the real capsule (monkeypatching the
module's path roots) so the committed artifact is never mutated. The generator
still runs from the real checkout, so reproduction is genuine.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "reproduce" / "mfn_capsule.py"
CAPSULE_REL = Path("artifacts/reproducible_capsules/mfn_integration_seed7_p256")


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mfn_capsule_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def capsule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """A monkeypatched module whose ROOT points at a sandbox copy of the capsule."""
    mod = _load_module()
    sandbox_capsule = tmp_path / CAPSULE_REL
    sandbox_capsule.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / CAPSULE_REL, sandbox_capsule)

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "CAPSULE_DIR", sandbox_capsule)
    monkeypatch.setattr(mod, "BUNDLE_DIR", sandbox_capsule / "bundle")
    monkeypatch.setattr(mod, "MANIFEST_PATH", sandbox_capsule / "manifest.json")
    return mod


def _read_manifest(mod: ModuleType) -> dict[str, Any]:
    return json.loads(Path(mod.MANIFEST_PATH).read_text(encoding="utf-8"))


def _write_manifest(mod: ModuleType, manifest: dict[str, Any]) -> None:
    Path(mod.MANIFEST_PATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _assert_fails(mod: ModuleType, capsys: pytest.CaptureFixture[str], needle: str) -> None:
    rc = mod.verify()
    err = capsys.readouterr().err
    assert rc == 1, f"expected verify() to fail, got rc={rc}"
    assert needle in err, f"expected {needle!r} in stderr, got:\n{err}"


def test_baseline_sandbox_passes(capsule: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    """Sanity: the untouched sandbox copy verifies, so failures below are real."""
    assert capsule.verify() == 0


def test_case01_manifest_missing(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    Path(capsule.MANIFEST_PATH).unlink()
    rc = capsule.verify()
    assert rc == 1
    assert "missing manifest" in capsys.readouterr().err


def test_case02_manifest_schema_invalid(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    manifest["evidence_class"] = "EMPIRICAL_EVIDENCE"
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "evidence_class must be")


def test_case03_artifact_absent(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    (Path(capsule.BUNDLE_DIR) / "report.json").unlink()
    _assert_fails(capsule, capsys, "missing on disk")


def test_case04_artifact_digest_differs(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    manifest["artifacts"][0]["sha256"] = "0" * 64
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "manifest digest stale")


def test_case05_regenerated_differs(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A different seed produces a different bundle than the committed one.
    monkeypatch.setattr(capsule, "SEED", capsule.SEED + 1)
    _assert_fails(capsule, capsys, "non-reproducible bundle file")


def test_case06_extra_untracked_artifact(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    (Path(capsule.BUNDLE_DIR) / "stowaway.json").write_text("{}\n", encoding="utf-8")
    _assert_fails(capsule, capsys, "untracked bundle file not in manifest")


def test_case07_source_date_epoch_absent(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    del manifest["source_date_epoch"]
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "missing required field: source_date_epoch")


def test_case08_git_sha_missing(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    del manifest["git_sha"]
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "missing required field: git_sha")


def test_case09_verify_command_empty(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    manifest["verify_command"] = "  "
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "verify_command must be a non-empty string")


def test_case10_claims_empirical_evidence(
    capsule: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _read_manifest(capsule)
    manifest["is_empirical_evidence"] = True
    _write_manifest(capsule, manifest)
    _assert_fails(capsule, capsys, "is_empirical_evidence must be false")


def test_reproduction_is_deterministic_across_runs(capsule: ModuleType) -> None:
    """Repeated verification of an untouched capsule is stable (no flakiness)."""
    assert capsule.verify() == 0
    assert capsule.verify() == 0
