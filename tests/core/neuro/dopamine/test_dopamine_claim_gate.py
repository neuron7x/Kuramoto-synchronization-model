from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]


def test_claim_gate_requires_terminal_pass(monkeypatch: Any, tmp_path: Path) -> None:
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")
    claim_file = tmp_path / "CLAIMS.md"
    claim_file.write_text(
        "Dopamine remains structural and research-gated with bounded telemetry.\n",
        encoding="utf-8",
    )
    artifact = tmp_path / "CLAIM_PROMOTION_VERDICT.json"
    monkeypatch.setattr(module, "CLAIM_FILES", [claim_file])
    monkeypatch.setattr(module, "ARTIFACT", artifact)
    monkeypatch.setattr(module, "EVAL", tmp_path / "EVAL_SUMMARY.json")
    monkeypatch.setattr(module, "MANIFEST", tmp_path / "ARTIFACT_MANIFEST.sha256")

    assert module.main() == 0
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_claim_evaluator_blocks_unsupported_dopamine_promotion() -> None:
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")
    reasons = module.evaluate_text(
        "Dopamine produces market edge and biological dopamine replication.",
        eval_exists=False,
        manifest_exists=False,
    )
    assert any("market edge" in reason for reason in reasons)
    assert any("biological dopamine replication" in reason for reason in reasons)


def test_claim_evaluator_ignores_unrelated_governance_words() -> None:
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")
    text = (
        "General claim is anchored and tested.\n\n"
        "Dopamine remains structural and research-gated."
    )
    reasons = module.evaluate_text(text, eval_exists=False, manifest_exists=False)
    assert reasons == []


def test_claim_evaluator_allows_structural_research_boundary() -> None:
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")
    reasons = module.evaluate_text(
        "Dopamine remains structural and research-gated with bounded telemetry.",
        eval_exists=False,
        manifest_exists=False,
    )
    assert reasons == []


def test_zero_byte_manifest_is_not_evidence(tmp_path: Path) -> None:
    # DEFECT 4: existence != integrity. A zero-byte or garbage manifest must NOT
    # satisfy the evidence condition that greenlights "extrapolated" wording.
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")

    empty = tmp_path / "ARTIFACT_MANIFEST.sha256"
    empty.write_text("", encoding="utf-8")
    assert empty.exists() and module.manifest_present(empty) is False

    garbage = tmp_path / "garbage.sha256"
    garbage.write_text("not a sha256 manifest\n", encoding="utf-8")
    assert module.manifest_present(garbage) is False

    valid = tmp_path / "valid.sha256"
    valid.write_text(f"{'a' * 64}  CLAIM_PROMOTION_VERDICT.json\n", encoding="utf-8")
    assert module.manifest_present(valid) is True


def test_zero_byte_manifest_does_not_promote_extrapolated_claim(tmp_path: Path) -> None:
    # Wiring: an "extrapolated" dopamine claim must be blocked when the only
    # manifest present is zero-byte. Before the fix `manifest_exists` came from
    # MANIFEST.exists() (True for a zero-byte file) and the claim passed.
    module: Any = importlib.import_module("scripts.ci.check_dopamine_claim_promotion")
    manifest = tmp_path / "ARTIFACT_MANIFEST.sha256"
    manifest.write_text("", encoding="utf-8")  # exists() is True, integrity is False

    reasons = module.evaluate_text(
        "Dopamine extrapolated performance is claimed here.",
        eval_exists=False,
        manifest_exists=module.manifest_present(manifest),
    )
    assert any("extrapolated" in reason for reason in reasons)
