from __future__ import annotations

import json
from pathlib import Path

from tools.research.validate_ricci_artifact_schema import (
    validate_artifact,
    validate_artifact_semantics,
)

SCHEMA = Path("schemas/research/research_inference_artifact.schema.json")


def test_example_ricci_artifact_satisfies_schema() -> None:
    # INV-RC1 / INV-DET1: canonical Ricci evidence artifacts must be schema-valid.
    errors = validate_artifact(
        schema_path=Path("schemas/research/research_inference_artifact.schema.json"),
        artifact_path=Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json"),
    )

    assert errors == []


def test_schema_rejects_synthetic_promotion_without_required_fields(tmp_path) -> None:
    # INV-NFD1 / INV-DET1: malformed artifacts cannot promote claim state.
    artifact = tmp_path / "bad.json"
    artifact.write_text(
        json.dumps(
            {
                "run_id": "RFC-2026-MARKET-RICCI-V1",
                "git_sha": "not-a-sha",
                "git_dirty": False,
                "data_sha256": "0" * 64,
                "config_sha256": "1" * 64,
                "seed": 1337,
                "timestamp_utc": "2026-05-31T20:27:00Z",
                "input_window_sec": 30,
                "score": 0.742,
                "uncertainty": 0.031,
                "decision": "TRADE",
                "claim_tier": "MEASURED_SINGLE",
                "falsification_status": "PASS",
            }
        ),
        encoding="utf-8",
    )

    errors = validate_artifact(
        schema_path=Path("schemas/research/research_inference_artifact.schema.json"),
        artifact_path=artifact,
    )

    assert any("git_sha" in error for error in errors)
    assert any("decision" in error for error in errors)


def test_schema_validator_fallback_works_without_jsonschema(monkeypatch) -> None:
    # INV-BOOT1: clean installs must validate canonical artifacts without optional deps.
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def no_jsonschema(name: str, *args: object, **kwargs: object):
        if name == "jsonschema":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", no_jsonschema)

    errors = validate_artifact(
        schema_path=Path("schemas/research/research_inference_artifact.schema.json"),
        artifact_path=Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json"),
    )

    assert errors == []


def test_schema_validator_fallback_rejects_missing_critical_field(monkeypatch, tmp_path: Path) -> None:
    # Fallback validation must fail closed on critical contract fields when jsonschema is unavailable.
    import importlib.util

    real_find_spec = importlib.util.find_spec

    def no_jsonschema(name: str, *args: object, **kwargs: object):
        if name == "jsonschema":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", no_jsonschema)
    source = json.loads(Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json").read_text(encoding="utf-8"))
    del source["data_sha256"]
    artifact = tmp_path / "missing-critical.json"
    artifact.write_text(json.dumps(source), encoding="utf-8")

    errors = validate_artifact(
        schema_path=Path("schemas/research/research_inference_artifact.schema.json"),
        artifact_path=artifact,
    )

    assert any("data_sha256" in error and "critical property" in error for error in errors)


def _fake_evidence() -> dict[str, object]:
    """The original lie: zero hashes + hand-typed score + PASS, schema-valid."""
    return {
        "conforms_to": (
            "https://schemas.neuron7xlab.org/research/research_inference_artifact.schema.json"
        ),
        "schema_version": "1.0.0",
        "research_line": "ricci_microstructure",
        "run_id": "RFC-2026-MARKET-RICCI-V1",
        "git_sha": "0" * 40,
        "git_dirty": False,
        "data_sha256": "0" * 64,
        "config_sha256": "1" * 64,
        "seed": 1337,
        "timestamp_utc": "2026-05-31T20:27:00Z",
        "input_window_sec": 30,
        "score": 0.742,
        "uncertainty": 0.031,
        "decision": "ABSTAIN",
        "claim_tier": "HYPOTHESIS",
        "falsification_status": "PASS",
    }


def test_semantics_reject_schema_valid_fake_evidence(tmp_path) -> None:
    # A schema-valid artifact can still be a lie. Semantic validation must catch it.
    fake = tmp_path / "fake.json"
    fake.write_text(json.dumps(_fake_evidence()), encoding="utf-8")

    schema_errors = validate_artifact(schema_path=SCHEMA, artifact_path=fake)
    semantic_errors = validate_artifact_semantics(schema_path=SCHEMA, artifact_path=fake)

    assert schema_errors == []  # shape is valid …
    assert semantic_errors  # … but truth is not
    assert any("PASS" in e and "zero data_sha256" in e for e in semantic_errors)


def test_semantics_accept_honest_placeholder() -> None:
    # The committed example is an explicit NOT_RUN placeholder: schema-valid AND honest.
    errors = validate_artifact_semantics(
        schema_path=SCHEMA,
        artifact_path=Path("artifacts/runs/ricci_microstructure_v1/example_artifact.json"),
    )
    assert errors == []


def test_semantics_reject_zero_hash_evidence_bearing(tmp_path) -> None:
    # Provenance-only (NOT_RUN) zero-hash artifact must be marked placeholder.
    doc = _fake_evidence()
    doc["falsification_status"] = "NOT_RUN"
    doc["decision"] = "OBSERVE"
    doc["score"] = 0.0
    # no artifact_role → not a placeholder → zero data is a latent lie
    art = tmp_path / "provenance.json"
    art.write_text(json.dumps(doc), encoding="utf-8")
    errors = validate_artifact_semantics(schema_path=SCHEMA, artifact_path=art)
    assert any("must be explicitly marked placeholder" in e for e in errors)
