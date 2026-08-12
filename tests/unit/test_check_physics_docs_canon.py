# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tests for the physics-documentation canon gate.

These tests lock the machine-checkable guarantees of the canon:

* every catalog law and every registry invariant is classified into exactly
  one domain (completeness — nothing silently dropped or double-counted);
* the committed manifest matches the substrates (drift detection);
* an unmapped registry section or unclassified law fails closed;
* the overclaim scanner catches forecast/alpha/predictor prose but exempts
  quoted/negated lines;
* the documentation index rejects unknown roles/domains and dangling paths.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_physics_docs_canon", _ROOT / "scripts" / "ci" / "check_physics_docs_canon.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_m = _load()


# --- completeness -----------------------------------------------------------


def test_committed_manifest_is_in_sync() -> None:
    # The whole gate must pass on the committed tree.
    assert _m.main([]) == 0


def test_every_law_and_invariant_is_classified() -> None:
    manifest = _m.build_manifest()
    law_ids = _m.load_law_ids()
    sections = _m.load_invariant_sections()
    total_inv = sum(len(v) for v in sections.values())

    classified_laws = sum(len(d["laws"]) for d in manifest["domains"].values())
    classified_inv = sum(len(d["invariants"]) for d in manifest["domains"].values())
    assert classified_laws == len(law_ids)
    assert classified_inv == total_inv
    assert manifest["totals"] == {"laws": len(law_ids), "invariants": total_inv}


def test_no_id_is_double_counted() -> None:
    manifest = _m.build_manifest()
    seen_laws: list[str] = []
    seen_inv: list[str] = []
    for d in manifest["domains"].values():
        seen_laws.extend(d["laws"])
        seen_inv.extend(d["invariants"])
    assert len(seen_laws) == len(set(seen_laws))
    assert len(seen_inv) == len(set(seen_inv))


def test_every_registry_section_maps_to_a_bucket() -> None:
    sections = _m.load_invariant_sections()
    for section in sections:
        assert section in _m.SECTION_TO_BUCKET, f"unmapped section {section}"


def test_unknown_law_prefix_is_unclassified() -> None:
    assert _m.classify_law("totally_new_module.some_law") is None
    assert _m.classify_law("ricci.something") == "graph_geometry"


# --- ontology / neuro are non-claim -----------------------------------------


def test_ontology_and_neuro_domains_are_non_claim() -> None:
    manifest = _m.build_manifest()
    assert manifest["domains"]["personal_research_ontology"]["maturity"] == "NON_CLAIM_ANALOGY"
    assert manifest["domains"]["neuro_symbolic_analogy"]["maturity"] == "NON_CLAIM_ANALOGY"
    # The gradient-ontology axiom must live in the ontology bucket, never physics.
    assert "INV-YV1" in manifest["domains"]["personal_research_ontology"]["invariants"]


# --- overclaim scanner ------------------------------------------------------


def test_overclaim_scanner_flags_and_exempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "PHYSICS_CANON.md"
    bad.write_text("This is a proven predictor of returns.\n", encoding="utf-8")
    monkeypatch.setattr(_m, "CANON_DOCS", (bad,))
    errors = _m.check_canon_docs()
    assert any("overclaim" in e for e in errors)

    good = tmp_path / "PHYSICS_CANON.md"
    good.write_text("This is NOT a proven predictor; no market law is claimed.\n", encoding="utf-8")
    monkeypatch.setattr(_m, "CANON_DOCS", (good,))
    assert _m.check_canon_docs() == []


def test_missing_canon_doc_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_m, "CANON_DOCS", (tmp_path / "does_not_exist.md",))
    assert any("missing" in e for e in _m.check_canon_docs())


# --- documentation index ----------------------------------------------------


def test_doc_index_rejects_unknown_role(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = tmp_path / "DOCUMENTATION_INDEX.manifest.json"
    idx.write_text(
        json.dumps(
            {"entries": [{"path": "README.md", "role": "bogus", "domain": "physics", "claim_bearing": True}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_m, "DOC_INDEX", idx)
    monkeypatch.setattr(_m, "ROOT", tmp_path)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert any("unknown role" in e for e in _m.check_doc_index())


def test_doc_index_rejects_dangling_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    idx = tmp_path / "DOCUMENTATION_INDEX.manifest.json"
    idx.write_text(
        json.dumps(
            {"entries": [{"path": "nope.md", "role": "general", "domain": "general", "claim_bearing": False}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_m, "DOC_INDEX", idx)
    monkeypatch.setattr(_m, "ROOT", tmp_path)
    assert any("does not exist" in e for e in _m.check_doc_index())
