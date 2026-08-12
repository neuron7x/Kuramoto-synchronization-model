# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""N4 — adversarial soundness of the No-Ungrounded-Act apex.

An adversary tries to make FORBIDDEN look ADMISSIBLE by forging a committed
artifact. The apex resists because it does not trust verdict fields: it re-checks
the numeric homeostasis grounds (H1/H3), rejects report-only runs, and RE-DERIVES
H4 by re-running the aggregator over the substrate — so a forged final verdict
that hides a FAIL/missing substrate is caught.

Honest boundary: substrate DATA artifacts (coverage, etc.) are trusted-as-data
here, protected by the manifest-hash / commit-acceptor gates, not re-derived.
Each test seeds a tmp root from the real artifacts, tampers ONE thing, and asserts
the apex fails closed.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_no_ungrounded_act.py"
_HOMEO = "artifacts/neuro/homeostasis_contract.json"
_FINAL = "artifacts/inference/final_inference_verdict.json"
_CONCURRENCY = "artifacts/concurrency/concurrency_matrix.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("nua_adv", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


nua = _load_tool()


@pytest.fixture()
def honest_root(tmp_path: Path) -> Path:
    # Seed a tmp root from the real committed artifacts -> honest ADMISSIBLE.
    shutil.copytree(ROOT / "artifacts", tmp_path / "artifacts")
    return tmp_path


def _patch(root: Path, rel: str, **changes: object) -> None:
    path = root / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_honest_root_is_admissible(honest_root: Path) -> None:
    assert nua.build_apex(honest_root)["gate"] == "ADMISSIBLE"


def test_forged_h1_numeric_is_ignored(honest_root: Path) -> None:
    # G2 hardening: the apex re-derives H1 from the real controllers, so a forged
    # allostatic-load number in the artifact is inert — the gate reflects reality
    # (ADMISSIBLE), never the forged file value.
    _patch(honest_root, _HOMEO, worst_allostatic_load=99.0)
    report = nua.build_apex(honest_root)
    assert report["gate"] == "ADMISSIBLE"
    assert next(g for g in report["grounds"] if g["id"] == "H1")["holds"] is True


def test_forged_h3_coherence_is_ignored(honest_root: Path) -> None:
    # Likewise H3: a forged coherence number cannot decide the apex.
    _patch(honest_root, _HOMEO, coherence_locked=0.0)
    report = nua.build_apex(honest_root)
    assert report["gate"] == "ADMISSIBLE"
    assert next(g for g in report["grounds"] if g["id"] == "H3")["holds"] is True


def test_report_only_homeostasis_is_still_defeated(honest_root: Path) -> None:
    # A forged report_only flag on the homeostasis artifact is ignored by H1/H3
    # (re-derived from real controllers) but still defeated by H4: the aggregator
    # rejects a report-only substrate, so the re-derived verdict is FORBIDDEN.
    _patch(honest_root, _HOMEO, report_only=True)
    report = nua.build_apex(honest_root)
    assert report["gate"] == "FORBIDDEN"
    assert next(g for g in report["grounds"] if g["id"] == "H4")["holds"] is False


def test_forged_aggregate_is_defeated_by_rederivation(honest_root: Path) -> None:
    # The adversary forges the final verdict to PASS but a substrate is FAIL.
    _patch(honest_root, _FINAL, verdict="PASS")
    _patch(honest_root, _CONCURRENCY, verdict="FAIL")
    report = nua.build_apex(honest_root)
    # H4 is re-derived from the substrate, so the hidden FAIL surfaces.
    assert report["gate"] == "FORBIDDEN"
    assert next(g for g in report["grounds"] if g["id"] == "H4")["holds"] is False


def test_missing_substrate_is_defeated_by_rederivation(honest_root: Path) -> None:
    (honest_root / _CONCURRENCY).unlink()
    report = nua.build_apex(honest_root)
    assert report["gate"] == "FORBIDDEN"
    assert next(g for g in report["grounds"] if g["id"] == "H4")["holds"] is False


def test_wrong_schema_id_substrate_is_defeated(honest_root: Path) -> None:
    # A renamed/unrelated file cannot masquerade as a substrate sub-verdict.
    _patch(honest_root, _CONCURRENCY, schema="geosync.some_other_thing.v1")
    report = nua.build_apex(honest_root)
    assert report["gate"] == "FORBIDDEN"


def test_within_bound_homeostasis_forgery_is_ignored(honest_root: Path) -> None:
    # G2: a plausible-but-false in-bound number (worst_load 0.1) must NOT decide the
    # apex — H1 is re-derived from the real controllers, so the forgery is inert.
    _patch(honest_root, _HOMEO, worst_allostatic_load=0.1, coherence_locked=1.0)
    report = nua.build_apex(honest_root)
    # The gate is whatever the REAL controllers say (ADMISSIBLE), not what the file claims.
    assert report["gate"] == "ADMISSIBLE"
    real = nua._rederive_homeostasis(honest_root)
    assert real["worst_allostatic_load"] != 0.1  # the real number, not the forged one


def test_final_verdict_requires_reproducible_provenance(honest_root: Path) -> None:
    # G3: a non-reproducible / FAIL provenance strand must sink the aggregate, so
    # the apex H4 (re-derived) is FORBIDDEN.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "afiv_g3", ROOT / "tools" / "audit_final_inference_verdict.py"
    )
    assert spec and spec.loader
    afiv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(afiv)
    assert any(s["name"] == "inference_provenance" for s in afiv.INPUTS)  # wired
    _patch(honest_root, "artifacts/provenance/inference_provenance.json", verdict="FAIL")
    assert afiv.build_verdict(honest_root, release=False)["verdict"] == "FAIL"
    assert nua.build_apex(honest_root)["gate"] == "FORBIDDEN"
