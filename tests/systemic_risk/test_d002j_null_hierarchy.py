# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P6 guard tests — null-model hierarchy v1.

Enforces the null-as-falsifier discipline: exactly 10 null families,
each with a non-empty target false explanation (anti-decorative),
declared+numerically-checked preserve/destroy structure, applicability
domain, deterministic seed policy. Phase-coupling P6->P5: every P5
substrate binds >=2 applicable nulls; no null lists a non-existent
substrate. N7/N8 carry the H_I2 forward-declared conditional; N10 has
inverted pass semantics. Nulls run deterministically and the
preserve/destroy invariants are verified numerically.

P6 builds the null-generator hierarchy contract; it does NOT execute
nulls against real substrate data at scale (P7/P8) and authorises no
canonical run.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from research.systemic_risk.nulls.d002j import (
    ALL_NULLS,
    N1LabelPermutationNull,
    N3TemporalBlockBootstrapNull,
    N5DegreePreservingGraphNull,
    N7ConfigurationModelNull,
    N8SparseMaxEntReconstructionNull,
    N10VintageLeakageTrapNull,
)
from research.systemic_risk.nulls.d002j.null_base import autocorr_at_lag

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
NULLS_DIR: Path = REPO_ROOT / "artifacts" / "d002j" / "nulls"
MANIFEST_JSON: Path = NULLS_DIR / "null_hierarchy_manifest_v1.json"
SUMMARY_JSON: Path = NULLS_DIR / "null_hierarchy_summary_v1.json"
CONTRACTS_MD: Path = REPO_ROOT / "docs" / "research" / "D002J_NULL_MODEL_CONTRACTS.md"
P6_CAPSULE_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_p6_verdict_v1.json"
)
DAG_VERDICT_JSON: Path = (
    REPO_ROOT / "artifacts" / "governance" / "verdicts" / "d002j_verdict_dag_v1.json"
)
P5_MANIFEST_JSON: Path = (
    REPO_ROOT / "artifacts" / "d002j" / "substrates" / "substrate_candidate_manifest_v1.json"
)
D002J_PREREG: Path = REPO_ROOT / "docs" / "governance" / "D002J_PREREGISTRATION.yaml"
NULLS_PKG: Path = REPO_ROOT / "research" / "systemic_risk" / "nulls" / "d002j"

_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")

_EXPECTED_NULL_IDS: tuple[str, ...] = (
    "N1_label_permutation",
    "N2_time_window_shift_placebo",
    "N3_temporal_block_bootstrap",
    "N4_iaaft_surrogate",
    "N5_degree_preserving_graph_null",
    "N6_weight_preserving_shuffle",
    "N7_configuration_model",
    "N8_sparse_maximum_entropy_reconstruction",
    "N9_shock_time_placebo",
    "N10_vintage_leakage_trap_null",
)
_H_I2_CONDITIONAL_IDS: frozenset[str] = frozenset(
    {"N7_configuration_model", "N8_sparse_maximum_entropy_reconstruction"}
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    assert isinstance(payload, dict), f"{path} must be a JSON object"
    return payload


def _nulls(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    fams = manifest["null_families"]
    assert isinstance(fams, list)
    return fams


def _ts() -> "np.ndarray[Any, np.dtype[np.float64]]":
    t = np.linspace(0.0, 8.0 * np.pi, 96)
    out: np.ndarray[Any, np.dtype[np.float64]] = np.sin(t) + 0.3 * np.cos(3.0 * t) + 0.05 * t
    return out


def _graph() -> "np.ndarray[Any, np.dtype[np.float64]]":
    rng = np.random.default_rng(11)
    a = (rng.random((14, 14)) < 0.35).astype(float)
    a = np.triu(a, 1)
    out: np.ndarray[Any, np.dtype[np.float64]] = a + a.T
    return out


# ---------------------------------------------------------------------------
# 1
# ---------------------------------------------------------------------------


def test_null_hierarchy_manifest_exists() -> None:
    assert MANIFEST_JSON.is_file(), f"missing {MANIFEST_JSON}"
    m = _load_json(MANIFEST_JSON)
    assert m["schema_version"] == "D002J-NULL-HIERARCHY-MANIFEST-v1", m["schema_version"]
    assert m["phase"] == "P6", m["phase"]


# ---------------------------------------------------------------------------
# 2
# ---------------------------------------------------------------------------


def test_null_hierarchy_summary_exists() -> None:
    assert SUMMARY_JSON.is_file(), f"missing {SUMMARY_JSON}"
    s = _load_json(SUMMARY_JSON)
    assert s["schema_version"] == "D002J-NULL-HIERARCHY-SUMMARY-v1", s["schema_version"]
    assert s["decision"] == "NULL_HIERARCHY_READY", s["decision"]


# ---------------------------------------------------------------------------
# 3
# ---------------------------------------------------------------------------


def test_ten_null_families_present() -> None:
    m = _load_json(MANIFEST_JSON)
    fams = _nulls(m)
    assert len(fams) == 10, f"expected exactly 10 null families, got {len(fams)}"
    ids = tuple(nf["null_id"] for nf in fams)
    assert ids == _EXPECTED_NULL_IDS, f"null id/order mismatch: {ids}"
    assert len(ALL_NULLS) == 10, f"ALL_NULLS must hold 10 classes, got {len(ALL_NULLS)}"


# ---------------------------------------------------------------------------
# 4
# ---------------------------------------------------------------------------


def test_each_null_has_target_false_explanation_nonempty() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        tfe = nf.get("target_false_explanation", "")
        assert isinstance(tfe, str) and tfe.strip(), f"{nf['null_id']} empty target"
        assert len(tfe) >= 25, f"{nf['null_id']} target too short to be a real claim"
    for cls in ALL_NULLS:
        attr = getattr(cls, "target_false_explanation", "")
        assert isinstance(attr, str) and attr.strip(), f"{cls.__name__} class attr empty"


# ---------------------------------------------------------------------------
# 5
# ---------------------------------------------------------------------------


def test_each_null_has_preserves_and_destroys() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        pres = nf.get("preserves", [])
        dest = nf.get("destroys", [])
        assert isinstance(pres, list) and len(pres) >= 1, f"{nf['null_id']} no preserves"
        assert isinstance(dest, list) and len(dest) >= 1, f"{nf['null_id']} no destroys"


# ---------------------------------------------------------------------------
# 6
# ---------------------------------------------------------------------------


def test_each_null_has_admission_test() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        at = nf.get("admission_test", "")
        assert isinstance(at, str) and at.strip(), f"{nf['null_id']} no admission_test"


# ---------------------------------------------------------------------------
# 7
# ---------------------------------------------------------------------------


def test_each_null_has_rejection_test() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        rt = nf.get("rejection_test", "")
        assert isinstance(rt, str) and rt.strip(), f"{nf['null_id']} no rejection_test"
        assert "REJECT" in rt, f"{nf['null_id']} rejection_test must name REJECT"


# ---------------------------------------------------------------------------
# 8
# ---------------------------------------------------------------------------


def test_each_null_has_expected_failure_mode() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        efm = nf.get("expected_failure_mode", "")
        assert isinstance(efm, str) and efm.strip(), f"{nf['null_id']} no failure mode"


# ---------------------------------------------------------------------------
# 9
# ---------------------------------------------------------------------------


def test_each_null_has_seed_policy() -> None:
    m = _load_json(MANIFEST_JSON)
    for nf in _nulls(m):
        sp = nf.get("seed_policy", "")
        assert isinstance(sp, str) and sp.strip(), f"{nf['null_id']} no seed_policy"
        assert "deterministic" in sp.lower(), f"{nf['null_id']} seed_policy not deterministic"


# ---------------------------------------------------------------------------
# 10
# ---------------------------------------------------------------------------


def test_n1_label_permutation_deterministic_and_destroys_label_structure() -> None:
    labels = _ts()
    n = N1LabelPermutationNull()
    i1 = n.apply(labels, 42)
    i2 = n.apply(labels, 42)
    assert np.array_equal(i1.nulled_array, i2.nulled_array), "N1 not deterministic"
    assert np.array_equal(np.sort(labels), np.sort(i1.nulled_array)), "N1 lost multiset"
    assert not np.array_equal(labels, i1.nulled_array), "N1 did not destroy alignment"
    assert i1.admitted, "N1 must be admitted (preserve+destroy checks pass)"


# ---------------------------------------------------------------------------
# 11
# ---------------------------------------------------------------------------


def test_n3_temporal_block_bootstrap_preserves_autocorrelation_band() -> None:
    series = np.cumsum(np.random.default_rng(3).normal(size=128)).astype(float)
    n = N3TemporalBlockBootstrapNull()
    inst = n.apply(series, 7)
    assert inst.preserved_invariants_checked["autocorrelation_band_lag1"] is True
    ac_src = autocorr_at_lag(series, 1)
    ac_null = autocorr_at_lag(inst.nulled_array, 1)
    assert abs(ac_null - ac_src) <= 0.6 * (abs(ac_src) + 0.5), (ac_src, ac_null)
    assert inst.destroyed_structure_checked["global_trajectory_order"] is True


# ---------------------------------------------------------------------------
# 12
# ---------------------------------------------------------------------------


def test_n5_degree_preserving_null_preserves_degree_sequence_exactly() -> None:
    g = _graph()
    n = N5DegreePreservingGraphNull()
    inst = n.apply(g, 99)
    binary = (g != 0.0).astype(int)
    np.fill_diagonal(binary, 0)
    deg_src = binary.sum(axis=1)
    deg_null = (inst.nulled_array != 0.0).astype(int).sum(axis=1)
    assert np.array_equal(deg_src, deg_null), "N5 degree sequence NOT exactly preserved"
    assert inst.preserved_invariants_checked["degree_sequence_exact"] is True
    assert inst.destroyed_structure_checked["edge_placement"] is True


# ---------------------------------------------------------------------------
# 13
# ---------------------------------------------------------------------------


def test_n7_configuration_model_h_i2_conditional_true() -> None:
    g = _graph()
    inst = N7ConfigurationModelNull().apply(g, 5)
    assert inst.metadata["h_i2_conditional"] is True
    assert "H_I2" in inst.metadata["h_i2_note"], inst.metadata["h_i2_note"]
    assert N7ConfigurationModelNull.h_i2_conditional is True


# ---------------------------------------------------------------------------
# 14
# ---------------------------------------------------------------------------


def test_n8_sparse_maxent_h_i2_conditional_true() -> None:
    g = _graph()
    inst = N8SparseMaxEntReconstructionNull().apply(g, 5)
    assert inst.metadata["h_i2_conditional"] is True
    assert "H_I2" in inst.metadata["h_i2_note"], inst.metadata["h_i2_note"]
    assert N8SparseMaxEntReconstructionNull.h_i2_conditional is True


# ---------------------------------------------------------------------------
# 15
# ---------------------------------------------------------------------------


def test_n10_vintage_leakage_trap_inverts_pass_semantics() -> None:
    series = _ts()
    inst = N10VintageLeakageTrapNull().apply(series, 1)
    assert inst.metadata["inverted_pass_semantics"] is True
    assert N10VintageLeakageTrapNull.inverted_pass_semantics is True
    pd = inst.metadata["pass_definition"].lower()
    assert "disappear" in pd, pd
    m = _load_json(MANIFEST_JSON)
    n10 = next(nf for nf in _nulls(m) if nf["null_id"] == "N10_vintage_leakage_trap_null")
    assert n10["inverted_pass_semantics"] is True
    assert "INVERTED" in n10["expected_failure_mode"], n10["expected_failure_mode"]


# ---------------------------------------------------------------------------
# 16 phase-coupling P6 -> P5
# ---------------------------------------------------------------------------


def test_each_p5_substrate_has_min_two_applicable_nulls() -> None:
    m = _load_json(MANIFEST_JSON)
    p5 = _load_json(P5_MANIFEST_JSON)
    p5_ids = {s["substrate_id"] for s in p5["substrates"]}
    counts: dict[str, int] = {sid: 0 for sid in p5_ids}
    for nf in _nulls(m):
        for sid in nf["applicable_substrates"]:
            counts[sid] = counts.get(sid, 0) + 1
    for sid in p5_ids:
        assert counts[sid] >= 2, f"P5 substrate {sid} has <2 applicable nulls: {counts[sid]}"
    assert min(counts.values()) >= 2, counts


# ---------------------------------------------------------------------------
# 17 phase-coupling P6 -> P5
# ---------------------------------------------------------------------------


def test_no_null_applicable_to_nonexistent_substrate() -> None:
    m = _load_json(MANIFEST_JSON)
    p5 = _load_json(P5_MANIFEST_JSON)
    p5_ids = {s["substrate_id"] for s in p5["substrates"]}
    for nf in _nulls(m):
        for sid in nf["applicable_substrates"]:
            assert sid in p5_ids, f"{nf['null_id']} lists non-existent substrate {sid!r}"
        for sid in nf["non_applicable_substrates"]:
            assert sid in p5_ids, f"{nf['null_id']} non_applicable lists unknown {sid!r}"


# ---------------------------------------------------------------------------
# 18 anti-decorative
# ---------------------------------------------------------------------------


def test_no_null_without_target_false_explanation() -> None:
    m = _load_json(MANIFEST_JSON)
    offenders = [
        nf["null_id"] for nf in _nulls(m) if not str(nf.get("target_false_explanation", "")).strip()
    ]
    assert offenders == [], f"decorative nulls (no target false explanation): {offenders}"
    # A null must also name what it can falsify via preserve/destroy.
    for nf in _nulls(m):
        assert nf["preserves"] and nf["destroys"], f"{nf['null_id']} decorative (no P/D)"


# ---------------------------------------------------------------------------
# 19
# ---------------------------------------------------------------------------


def test_h_i2_conditional_nulls_documented() -> None:
    m = _load_json(MANIFEST_JSON)
    flagged = {nf["null_id"] for nf in _nulls(m) if nf.get("h_i2_conditional") is True}
    assert flagged == set(_H_I2_CONDITIONAL_IDS), f"H_I2 flag mismatch: {flagged}"
    text = CONTRACTS_MD.read_text(encoding="utf-8")
    assert "H_I2 conditional" in text, "contracts doc missing H_I2 section"
    assert "fresh admissibility justification before canonical use (P8)" in text
    s = _load_json(SUMMARY_JSON)
    assert s["h_i2_conditional_count"] == 2, s["h_i2_conditional_count"]
    assert set(s["h_i2_conditional_nulls"]) == set(_H_I2_CONDITIONAL_IDS)


# ---------------------------------------------------------------------------
# 20
# ---------------------------------------------------------------------------


def test_each_null_simulate_deterministic() -> None:
    ts = _ts()
    g = _graph()
    rng = np.random.default_rng(2)
    w = g * rng.random(g.shape)
    w = np.triu(w, 1)
    w = w + w.T
    for cls in ALL_NULLS:
        name = cls.__name__
        if name in {
            "N5DegreePreservingGraphNull",
            "N7ConfigurationModelNull",
            "N8SparseMaxEntReconstructionNull",
        }:
            inp: np.ndarray = g
        elif name == "N6WeightPreservingShuffleNull":
            inp = w
        else:
            inp = ts
        inst = cls()
        a = inst.apply(inp, 42)
        b = inst.apply(inp, 42)
        assert np.array_equal(a.nulled_array, b.nulled_array), f"{name} non-deterministic"
        assert a.admitted, f"{name} not admitted (preserve/destroy check failed)"


# ---------------------------------------------------------------------------
# 21
# ---------------------------------------------------------------------------


def test_no_canonical_run_authorized() -> None:
    s = _load_json(SUMMARY_JSON)
    assert s["no_canonical_run"] is True, s
    assert s["no_real_data_null_execution"] is True, s
    dag = _load_json(DAG_VERDICT_JSON)
    assert dag["canonical_run_authorized_anywhere"] is False, dag
    cap = _load_json(P6_CAPSULE_JSON)
    assert cap["decision"] == "NULL_HIERARCHY_READY", cap["decision"]
    assert cap["forbidden_next_nodes"] == ["D002J-P8", "D002J-P9"], cap["forbidden_next_nodes"]


# ---------------------------------------------------------------------------
# 22
# ---------------------------------------------------------------------------


def test_no_d002j_prereg_edit() -> None:
    expected = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"  # pragma: allowlist secret
    actual = hashlib.sha256(D002J_PREREG.read_bytes()).hexdigest()
    assert actual == expected, f"D-002J prereg sha drift: {actual} != {expected}"
    assert D002J_PREREG.is_file(), "D-002J prereg must still exist"


# ---------------------------------------------------------------------------
# 23
# ---------------------------------------------------------------------------


def test_no_research_systemic_risk_unauthorized_edit() -> None:
    # P6 may only add files under research/systemic_risk/nulls/d002j/.
    assert NULLS_PKG.is_dir(), f"missing nulls package {NULLS_PKG}"
    expected_files = {
        "__init__.py",
        "null_base.py",
        "null_families.py",
    }
    actual = {p.name for p in NULLS_PKG.glob("*.py")}
    assert actual == expected_files, f"unexpected files in nulls pkg: {actual}"
    # The package must not import any real-data or canonical-run module.
    for p in NULLS_PKG.glob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "real_data_contract" not in src, f"{p.name} imports real data contract"
        assert "canonical_seven" not in src, f"{p.name} imports canonical run"


# ---------------------------------------------------------------------------
# 24
# ---------------------------------------------------------------------------


def test_no_unresolved_merge_markers() -> None:
    targets = [
        MANIFEST_JSON,
        SUMMARY_JSON,
        CONTRACTS_MD,
        P6_CAPSULE_JSON,
        NULLS_PKG / "__init__.py",
        NULLS_PKG / "null_base.py",
        NULLS_PKG / "null_families.py",
        Path(__file__),
    ]
    hits: list[tuple[str, int]] = []
    for p in targets:
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if _MARKER.match(line):
                hits.append((str(p.relative_to(REPO_ROOT)), i))
    assert hits == [], f"unresolved merge markers: {hits}"
    cap = _load_json(P6_CAPSULE_JSON)
    assert cap["parent_nodes"] == ["D002J-P5"], cap["parent_nodes"]
    assert cap["allowed_next_nodes"] == ["D002J-P7"], cap["allowed_next_nodes"]
