"""Tests for the Physics-2026 translation-matrix validator.

Three contracts:

1. The shipping translation `.claude/research/PHYSICS_2026_TRANSLATION.yaml`
   validates clean against `docs/research/physics_2026/source_pack.yaml`:
   6 patterns, all references resolve, no errors.

2. Each documented failure mode is detected on a synthetic translation:
   - missing falsifier
   - invalid source_id reference
   - forbidden ENGINEERING_ANALOG phrasing
   - duplicate proposed_module path
   - duplicate pattern_id
   - REJECTED without rejection_reason
   - missing required key
   - unsupported schema_version

3. CLI returns the right exit code and writes deterministic JSON.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "tools" / "research" / "validate_physics_2026_translation.py"
SHIPPING_TRANSLATION = REPO_ROOT / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
SHIPPING_PACK = REPO_ROOT / "docs" / "research" / "physics_2026" / "source_pack.yaml"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vpt", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vpt"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vpt() -> ModuleType:
    return _load()


def _good_pattern(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "pattern_id": "PT_FAKE",
        "source_ids": ["S99_FAKE"],
        "source_fact_summary": "summary",
        "methodological_pattern": "abstract pattern",
        "geosync_operational_analog": "engineering analog body",
        "proposed_module": "geosync_hpc/fake/fake_module.py",
        "claim_tier": "ENGINEERING_ANALOG",
        "implementation_status": "PROPOSED",
        "measurable_inputs": ["x"],
        "output_witness": ["y"],
        "null_model": "the null is x = 0",
        "falsifier": "x != 0 fails",
        "deterministic_tests": ["x = 0 ⇒ y = 0"],
        "mutation_candidate": "drop the x check",
        "ledger_entry_required": True,
    }
    base.update(overrides)
    return base


def _write_translation(path: Path, patterns: list[dict[str, Any]]) -> Path:
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "patterns": patterns}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _write_pack(path: Path, source_ids: list[str]) -> Path:
    sources = [
        {
            "source_id": sid,
            "title": "stub",
            "url": "https://example.org",
            "verified_fact": ["fact"],
            "allowed_translation": ["pattern"],
            "forbidden_overclaim": ["do not overclaim"],
        }
        for sid in source_ids
    ]
    path.write_text(
        yaml.safe_dump({"schema_version": 1, "sources": sources}, sort_keys=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Contract 1 — shipping translation validates clean
# ---------------------------------------------------------------------------


def test_shipping_translation_validates_clean(vpt: ModuleType) -> None:
    report = vpt.validate_translation(SHIPPING_TRANSLATION, SHIPPING_PACK)
    assert report.valid, "shipping translation errors:\n  - " + "\n  - ".join(
        str(e) for e in report.errors
    )
    assert report.pattern_count == 10
    assert sorted(report.pattern_ids) == [
        "P10_CLAIM_GAUGE_WITNESS",
        "P1_POPULATION_EVENT_CATALOG",
        "P2_STRUCTURED_ABSENCE_INFERENCE",
        "P3_DYNAMIC_NULL_MODEL",
        "P4_GLOBAL_PARITY_WITNESS",
        "P5_MOTIONAL_CORRELATION_WITNESS",
        "P6_COMPOSITE_BINDING_STRUCTURE",
        "P7_REGIME_FRONT_ROUGHNESS",
        "P8_NON_SELFSIMILAR_CLUSTER_GROWTH",
        "P9_EFFECTIVE_DEPTH_GUARD",
    ]


def test_every_referenced_source_exists_in_shipping_pack(
    vpt: ModuleType,
) -> None:
    report = vpt.validate_translation(SHIPPING_TRANSLATION, SHIPPING_PACK)
    expected = {
        "S1_GWTC4",
        "S2_PAIR_INSTABILITY_GAP",
        "S3_DESI_2026",
        "S4_KITAEV_PARITY_READOUT",
        "S5_HELIUM_MOTIONAL_BELL",
        "S6_LHCB_DOUBLY_CHARMED_BARYON",
        "S7_KPZ_2D_UNIVERSALITY",
        "S8_ACTIVE_COARSENING_NON_SELFSIMILAR",
        "S9_NOISE_INDUCED_SHALLOW_CIRCUITS",
        "S10_LOGICAL_GAUGING_LOCAL_SYMMETRY",
    }
    assert set(report.referenced_source_ids) == expected


# ---------------------------------------------------------------------------
# Contract 2 — failure-mode injection
# ---------------------------------------------------------------------------


def test_missing_falsifier_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(falsifier="")
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "EMPTY_FALSIFIER" for e in report.errors)


def test_invalid_source_id_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(source_ids=["S77_DOES_NOT_EXIST"])
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "UNKNOWN_SOURCE_ID" for e in report.errors)


@pytest.mark.parametrize(
    "phrase,key",
    [
        ("physical equivalence", "geosync_operational_analog"),
        ("quantum market", "methodological_pattern"),
        ("universal", "null_model"),
        ("predicts returns", "falsifier"),
    ],
)
def test_forbidden_engineering_analog_phrase_fails(
    vpt: ModuleType, tmp_path: Path, phrase: str, key: str
) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(**{key: f"this is fine but {phrase} sneaks in"})
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "FORBIDDEN_ANALOG_PHRASE" and phrase in e.detail for e in report.errors)


def test_forbidden_phrase_in_source_fact_summary_passes(vpt: ModuleType, tmp_path: Path) -> None:
    """source_fact_summary may legitimately quote source phrasings (e.g.
    'universal' as it appears in a paper title). It is NOT scanned for
    forbidden analog phrases."""
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    good = _good_pattern(
        source_fact_summary=("The cited paper uses the word universal in its title.")
    )
    trans = _write_translation(tmp_path / "trans.yaml", [good])
    report = vpt.validate_translation(trans, pack)
    assert report.valid, [str(e) for e in report.errors]


def test_duplicate_module_path_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    a = _good_pattern(pattern_id="P_A")
    b = _good_pattern(pattern_id="P_B")
    trans = _write_translation(tmp_path / "trans.yaml", [a, b])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "DUPLICATE_MODULE_PATH" for e in report.errors)


def test_duplicate_pattern_id_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    a = _good_pattern(pattern_id="P_DUP", proposed_module="m/a.py")
    b = _good_pattern(pattern_id="P_DUP", proposed_module="m/b.py")
    trans = _write_translation(tmp_path / "trans.yaml", [a, b])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "DUPLICATE_PATTERN_ID" for e in report.errors)


def test_rejected_without_reason_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(claim_tier="REJECTED", implementation_status="REJECTED")
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "REJECTED_NO_REASON" for e in report.errors)


def test_rejected_with_reason_passes(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(
        claim_tier="REJECTED",
        implementation_status="REJECTED",
        rejection_reason="evidence gap: no measurable input",
    )
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert report.valid, [str(e) for e in report.errors]


def test_missing_required_key_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern()
    del bad["null_model"]
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "MISSING_KEY" and "null_model" in e.detail for e in report.errors)


def test_unknown_claim_tier_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(claim_tier="ASTROLOGICAL")
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "BAD_CLAIM_TIER" for e in report.errors)


def test_unsupported_schema_version_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    trans = tmp_path / "trans.yaml"
    trans.write_text(
        yaml.safe_dump({"schema_version": 99, "patterns": []}),
        encoding="utf-8",
    )
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "SCHEMA_VERSION" for e in report.errors)


def test_missing_translation_file_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    report = vpt.validate_translation(tmp_path / "absent.yaml", pack)
    assert not report.valid
    assert any(e.rule == "TRANSLATION_NOT_FOUND" for e in report.errors)


def test_empty_source_pack_fails(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", [])
    bad = _good_pattern()
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    report = vpt.validate_translation(trans, pack)
    assert not report.valid
    assert any(e.rule == "SOURCE_PACK_UNAVAILABLE" for e in report.errors)


# ---------------------------------------------------------------------------
# Contract 3 — CLI / determinism
# ---------------------------------------------------------------------------


def test_main_writes_json_and_exits_zero_on_clean(vpt: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    rc = vpt.main(
        [
            "--translation",
            str(SHIPPING_TRANSLATION),
            "--source-pack",
            str(SHIPPING_PACK),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    decoded = json.loads(out.read_text(encoding="utf-8"))
    assert decoded["valid"] is True
    assert decoded["pattern_count"] == 10


def test_main_exits_nonzero_on_bad_translation(vpt: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", ["S99_FAKE"])
    bad = _good_pattern(falsifier="")
    trans = _write_translation(tmp_path / "trans.yaml", [bad])
    out = tmp_path / "report.json"
    rc = vpt.main(
        [
            "--translation",
            str(trans),
            "--source-pack",
            str(pack),
            "--output",
            str(out),
        ]
    )
    assert rc == 1
    decoded = json.loads(out.read_text(encoding="utf-8"))
    assert decoded["valid"] is False
    assert decoded["errors"]


def test_validate_translation_is_deterministic(vpt: ModuleType) -> None:
    a = vpt.validate_translation(SHIPPING_TRANSLATION, SHIPPING_PACK).to_dict()
    b = vpt.validate_translation(SHIPPING_TRANSLATION, SHIPPING_PACK).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
