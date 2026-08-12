# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Acceptance tests for the neuro-physics contradiction ledger (Assurance-Case v2).

The ledger is a Toulmin-structured, PROV-attributed, executably-falsifiable
assurance case. Beyond schema/vocab conformance, the critical test EXECUTES every
entry's falsifier against live source and requires exit 0 — making the ledger
self-verifying: a code change that invalidates an entry breaks CI until the
ledger is updated (anti-staleness; no fake closure).

Critical acceptance invariants run in pure Python. Full JSON-Schema conformance
runs where ``jsonschema`` is importable.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LEDGER = _ROOT / "data" / "audit" / "neuro_physics_contradiction_ledger.json"
_SCHEMA = _ROOT / "schemas" / "audit" / "contradiction_ledger.schema.json"
_DOC = _ROOT / "docs" / "audit" / "neuro_physics_contradiction_ledger.md"

_STATUS_VOCAB = {"VERIFIED", "PLAUSIBLE", "UNSUPPORTED", "CONTRADICTED"}
_SEVERITY_VOCAB = {"HIGH", "MEDIUM", "LOW"}
_RESOLUTION_VOCAB = {"OPEN", "IN_PROGRESS", "RESOLVED", "WONTFIX"}

_KNOWN_LANES = {
    "lane-1-contradiction-ledger",
    "lane-2-energy-contract",
    "lane-3-neuromodulator-semantics",
    "lane-4-tacl-delta-f",
    "lane-5-kuramoto-ricci-structure",
    "lane-6-orchestrator-boundary",
    "lane-7-neuro-physics-scorecard",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ledger() -> dict[str, Any]:
    data: dict[str, Any] = _load(_LEDGER)
    return data


def test_ledger_and_schema_are_valid_json() -> None:
    assert isinstance(_load(_LEDGER), dict)
    assert isinstance(_load(_SCHEMA), dict)


def test_methodology_declares_assurance_standard(ledger: dict[str, Any]) -> None:
    meth = ledger["methodology"]
    assert "Toulmin" in meth["argument_model"]
    assert "PROV" in meth["provenance_model"]
    assert len(meth["verification"]) >= 8
    assert ledger["version"] >= 2


def test_doc_exists_and_references_every_id(ledger: dict[str, Any]) -> None:
    text = _DOC.read_text(encoding="utf-8")
    for entry in ledger["contradictions"]:
        assert entry["id"] in text, f"{entry['id']} missing from human-readable ledger"


def test_every_claim_has_status_in_vocab(ledger: dict[str, Any]) -> None:
    for entry in ledger["contradictions"]:
        assert entry["claim_status"] in _STATUS_VOCAB, entry["id"]


def test_every_high_or_medium_has_owner_lane(ledger: dict[str, Any]) -> None:
    for entry in ledger["contradictions"]:
        if entry["severity"] in {"HIGH", "MEDIUM"}:
            assert entry["owner_lane"].strip(), f"{entry['id']} HIGH/MEDIUM without owner lane"


def test_no_fake_closure(ledger: dict[str, Any]) -> None:
    for entry in ledger["contradictions"]:
        if entry["resolution_state"] == "RESOLVED":
            assert entry.get("resolution_ref", "").strip(), f"{entry['id']} RESOLVED without ref"
            assert entry["evidence"].strip(), f"{entry['id']} RESOLVED without evidence"


def test_ids_are_unique_and_well_formed(ledger: dict[str, Any]) -> None:
    import re

    ids = [e["id"] for e in ledger["contradictions"]]
    assert len(ids) == len(set(ids)), "duplicate contradiction ids"
    for cid in ids:
        assert re.fullmatch(r"C-[A-Z0-9]+-\d{3}", cid), cid


def test_every_entry_has_source_and_evidence(ledger: dict[str, Any]) -> None:
    for entry in ledger["contradictions"]:
        assert entry["source_path"].strip(), entry["id"]
        assert len(entry["evidence"].strip()) >= 8, entry["id"]
        assert entry["resolution_state"] in _RESOLUTION_VOCAB, entry["id"]
        assert entry["severity"] in _SEVERITY_VOCAB, entry["id"]


def test_every_entry_has_full_toulmin_argument(ledger: dict[str, Any]) -> None:
    """Toulmin: every claim defended with warrant + backing + rebuttal."""
    for entry in ledger["contradictions"]:
        arg = entry["argument"]
        assert len(arg["warrant"].strip()) >= 16, f"{entry['id']} weak/empty warrant"
        assert len(arg["backing"].strip()) >= 8, f"{entry['id']} no backing authority"
        assert len(arg["rebuttal"].strip()) >= 16, f"{entry['id']} no rebuttal condition"


def test_every_entry_has_provenance(ledger: dict[str, Any]) -> None:
    """W3C-PROV: every assertion attributed (who / when / how)."""
    import re

    for entry in ledger["contradictions"]:
        prov = entry["provenance"]
        assert prov["asserted_by"].strip(), entry["id"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", prov["asserted_on"]), entry["id"]
        assert len(prov["method"].strip()) >= 8, entry["id"]


def test_source_paths_resolve_on_disk(ledger: dict[str, Any]) -> None:
    """Grounds must point at a real file (or a package dir) — no phantom evidence."""
    for entry in ledger["contradictions"]:
        target = _ROOT / entry["source_path"]
        assert target.exists(), f"{entry['id']} source_path does not exist: {entry['source_path']}"


def test_every_falsifier_confirms_its_claim_against_live_source(ledger: dict[str, Any]) -> None:
    """The crown invariant: each falsifier must exit 0 against the live tree.

    This makes the ledger self-verifying. If a later code change invalidates an
    entry (e.g. the dead invariant gets wired, or a metaphor gets renamed), its
    falsifier stops returning 0 and THIS test fails — forcing a ledger update
    rather than silently going stale.
    """
    for entry in ledger["contradictions"]:
        fz = entry["falsifier"]
        proc = subprocess.run(
            fz["command"],
            shell=True,
            cwd=str(_ROOT),
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == fz["expect_exit"], (
            f"LEDGER STALE: {entry['id']} falsifier returned {proc.returncode}, "
            f"expected {fz['expect_exit']}. The ledger's stated position is no longer "
            f"true against live source. {fz['interpretation']} "
            f"Command: {fz['command']!r}"
        )


def test_vocab_arrays_match_canonical_sets(ledger: dict[str, Any]) -> None:
    assert set(ledger["claim_status_vocab"]) == _STATUS_VOCAB
    assert set(ledger["severity_vocab"]) == _SEVERITY_VOCAB
    assert set(ledger["resolution_vocab"]) == _RESOLUTION_VOCAB


def test_owner_lanes_are_known(ledger: dict[str, Any]) -> None:
    for entry in ledger["contradictions"]:
        assert entry["owner_lane"] in _KNOWN_LANES, (
            f"{entry['id']} -> unknown lane {entry['owner_lane']}"
        )


def test_jsonschema_conformance(ledger: dict[str, Any]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(instance=ledger, schema=_load(_SCHEMA))


def test_jsonschema_rejects_fake_closure() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load(_SCHEMA)
    bad = _load(_LEDGER)
    # Flip an OPEN entry to RESOLVED without a resolution_ref -> must be rejected.
    target = next(e for e in bad["contradictions"] if e["resolution_state"] == "OPEN")
    target["resolution_state"] = "RESOLVED"
    target.pop("resolution_ref", None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_jsonschema_rejects_missing_falsifier() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = _load(_SCHEMA)
    bad = _load(_LEDGER)
    bad["contradictions"][0].pop("falsifier", None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)
