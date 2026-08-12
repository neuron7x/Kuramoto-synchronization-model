"""Tests for the Physics-2026 source-pack validator.

Three contracts:

1. The shipping pack `docs/research/physics_2026/source_pack.yaml`
   validates clean: 6 sources, 6 stable IDs, no errors.

2. Each documented failure mode is detected on a synthetic pack:
   - missing forbidden_overclaim entry
   - duplicate source_id
   - forbidden phrase in verified_fact / allowed_translation / title
   - bad source_id shape
   - missing required key
   - empty evidence list
   - unsupported schema_version

3. The CLI writes deterministic JSON and returns the right exit code.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "tools" / "research" / "validate_physics_2026_sources.py"
SHIPPING_PACK = REPO_ROOT / "docs" / "research" / "physics_2026" / "source_pack.yaml"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vps", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vps"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vps() -> ModuleType:
    return _load()


def _good_source(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_id": "S99_FAKE",
        "title": "Test source",
        "url": "https://example.org/test",
        "verified_fact": ["it is a fact"],
        "allowed_translation": ["abstract pattern"],
        "forbidden_overclaim": ["do not overclaim"],
    }
    base.update(overrides)
    return base


def _write_pack(path: Path, sources: list[dict[str, object]]) -> Path:
    path.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "sources": sources},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Contract 1 — shipping pack validates clean
# ---------------------------------------------------------------------------


def test_shipping_pack_validates_clean(vps: ModuleType) -> None:
    report = vps.validate_pack(SHIPPING_PACK)
    assert report.valid, "shipping pack errors:\n  - " + "\n  - ".join(
        str(e) for e in report.errors
    )
    assert report.source_count == 10
    assert len(report.source_ids) == 10
    assert sorted(report.source_ids) == [
        "S10_LOGICAL_GAUGING_LOCAL_SYMMETRY",
        "S1_GWTC4",
        "S2_PAIR_INSTABILITY_GAP",
        "S3_DESI_2026",
        "S4_KITAEV_PARITY_READOUT",
        "S5_HELIUM_MOTIONAL_BELL",
        "S6_LHCB_DOUBLY_CHARMED_BARYON",
        "S7_KPZ_2D_UNIVERSALITY",
        "S8_ACTIVE_COARSENING_NON_SELFSIMILAR",
        "S9_NOISE_INDUCED_SHALLOW_CIRCUITS",
    ]


# ---------------------------------------------------------------------------
# Contract 2 — each documented failure mode is detected
# ---------------------------------------------------------------------------


def test_missing_forbidden_overclaim_fails(vps: ModuleType, tmp_path: Path) -> None:
    bad = _good_source()
    del bad["forbidden_overclaim"]
    pack = _write_pack(tmp_path / "pack.yaml", [bad])
    report = vps.validate_pack(pack)
    assert not report.valid
    rules = {e.rule for e in report.errors}
    assert "MISSING_KEY" in rules


def test_empty_forbidden_overclaim_list_fails(vps: ModuleType, tmp_path: Path) -> None:
    bad = _good_source(forbidden_overclaim=[])
    pack = _write_pack(tmp_path / "pack.yaml", [bad])
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(e.rule == "EMPTY_EVIDENCE_LIST" for e in report.errors)


def test_duplicate_source_id_fails(vps: ModuleType, tmp_path: Path) -> None:
    a = _good_source(source_id="S99_FAKE")
    b = _good_source(source_id="S99_FAKE", title="Different title")
    pack = _write_pack(tmp_path / "pack.yaml", [a, b])
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(e.rule == "DUPLICATE_SOURCE_ID" for e in report.errors)


@pytest.mark.parametrize(
    "phrase,key",
    [
        ("proves market", "verified_fact"),
        ("quantum market", "allowed_translation"),
        ("predicts returns", "verified_fact"),
        ("universal law", "allowed_translation"),
        ("physical equivalence", "verified_fact"),
    ],
)
def test_forbidden_phrase_in_inspected_field_fails(
    vps: ModuleType, tmp_path: Path, phrase: str, key: str
) -> None:
    bad = _good_source(**{key: [f"this entry {phrase} sneakily"]})
    pack = _write_pack(tmp_path / "pack.yaml", [bad])
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(
        e.rule == "FORBIDDEN_PHRASE" and phrase in e.detail for e in report.errors
    ), report.errors


def test_forbidden_phrase_inside_forbidden_overclaim_passes(
    vps: ModuleType, tmp_path: Path
) -> None:
    """An entry that *forbids* the phrasing must not be flagged for it."""
    good = _good_source(
        forbidden_overclaim=["Do not claim physical equivalence between markets and physics."]
    )
    pack = _write_pack(tmp_path / "pack.yaml", [good])
    report = vps.validate_pack(pack)
    assert report.valid, [str(e) for e in report.errors]


@pytest.mark.parametrize(
    "bad_id",
    [
        "lowercase",
        "S",
        "S99",
        "S99-FAKE",
        "X1_FAKE",
        "",
    ],
)
def test_bad_source_id_shape_fails(vps: ModuleType, tmp_path: Path, bad_id: str) -> None:
    bad = _good_source(source_id=bad_id)
    pack = _write_pack(tmp_path / "pack.yaml", [bad])
    report = vps.validate_pack(pack)
    assert not report.valid
    rules = {e.rule for e in report.errors}
    assert {"BAD_SOURCE_ID", "BAD_SOURCE_ID_SHAPE"} & rules, rules


def test_missing_required_key_fails(vps: ModuleType, tmp_path: Path) -> None:
    bad = _good_source()
    del bad["url"]
    pack = _write_pack(tmp_path / "pack.yaml", [bad])
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(e.rule == "MISSING_KEY" and "url" in e.detail for e in report.errors)


def test_unsupported_schema_version_fails(vps: ModuleType, tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    pack.write_text(
        yaml.safe_dump({"schema_version": 99, "sources": []}),
        encoding="utf-8",
    )
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(e.rule == "SCHEMA_VERSION" for e in report.errors)


def test_yaml_parse_error_returns_clean_diagnostic(vps: ModuleType, tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    pack.write_text(
        dedent("""
            schema_version: 1
            sources:
              - source_id: S1_BAD
                : oops
            """),
        encoding="utf-8",
    )
    report = vps.validate_pack(pack)
    assert not report.valid
    assert any(e.rule == "YAML_PARSE_ERROR" for e in report.errors)


def test_missing_pack_file_fails(vps: ModuleType, tmp_path: Path) -> None:
    report = vps.validate_pack(tmp_path / "absent.yaml")
    assert not report.valid
    assert any(e.rule == "PACK_NOT_FOUND" for e in report.errors)


# ---------------------------------------------------------------------------
# Contract 3 — CLI / deterministic JSON
# ---------------------------------------------------------------------------


def test_main_writes_json_and_exits_zero_on_clean_pack(vps: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    rc = vps.main(["--pack", str(SHIPPING_PACK), "--output", str(out)])
    assert rc == 0
    assert out.exists()
    decoded = json.loads(out.read_text(encoding="utf-8"))
    assert decoded["valid"] is True
    assert decoded["source_count"] == 10


def test_main_exits_nonzero_and_records_errors_on_bad_pack(vps: ModuleType, tmp_path: Path) -> None:
    pack = _write_pack(tmp_path / "pack.yaml", [_good_source(source_id="bad")])
    out = tmp_path / "report.json"
    rc = vps.main(["--pack", str(pack), "--output", str(out)])
    assert rc == 1
    decoded = json.loads(out.read_text(encoding="utf-8"))
    assert decoded["valid"] is False
    assert decoded["errors"]


def test_validate_pack_is_deterministic(vps: ModuleType) -> None:
    a = vps.validate_pack(SHIPPING_PACK).to_dict()
    b = vps.validate_pack(SHIPPING_PACK).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
