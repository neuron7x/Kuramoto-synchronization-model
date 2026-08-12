# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""PRE-REGISTRATION-AMENDMENT-001 — forward-only verdict reclassification.

F2 of the supersession/amendment governance correction. CALIB-GRID-002
proved the two frozen ``noisy.*`` gates (σ=0.02 @ frozen θ₀/record
length) sit at an information-theoretically unreachable operating point
— FAIL with P=1 ∀ estimator ⇒ H=0 bits. The append-only amendment
``PREREGISTRATION_AMENDMENT_001.yaml`` reclassifies them, **forward
only**, from pass/fail acceptance gates to ``INFEASIBLE_BY_CONSTRUCTION``
zero-bit diagnostics; the overall verdict is then computed over the
remaining genuine pass/fail gates only.

These tests pin the two hard invariants of F2:

1. **The three historical lineages are NOT recomputed.** The merged
   CALIB-GRID-001 / R1 / CALIB-GRID-002 ledgers reproduce their exact
   historical bytes (verdict + gate pass-flags) — the default builders
   are byte-stable and untouched by the amendment.
2. **A fresh run UNDER the amendment** emits the distinct
   ``INFEASIBLE_BY_CONSTRUCTION`` state for the amended gates and the
   correct reduced-gate overall verdict (no threshold value touched).

Plus a no-peek drift test binding the amendment constants to the
substrate (mirrors the existing amendment-binding pattern).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.calibration.grid_kuramoto import (
    NOISELESS_GATES,
    NOISY_GATES,
    SimConfig,
    evaluate_gates,
    run_calibration,
    wscc_9_bus,
)
from research.calibration.grid_kuramoto._substrate import (
    INFEASIBLE_BY_CONSTRUCTION,
    amended_gate_names,
    overall_verdict_amended,
)
from research.calibration.grid_kuramoto.run import (
    build_amended_ledger,
    build_ledger,
    build_r1_ledger,
)

_LINEAGE_ROOT = Path(__file__).resolve().parents[3] / "research" / "calibration" / "grid_kuramoto"
_AMENDMENT_YAML = _LINEAGE_ROOT / "PREREGISTRATION_AMENDMENT_001.yaml"
_AMENDMENT_MD = _LINEAGE_ROOT / "PREREGISTRATION_AMENDMENT_001.md"


# ---------------------------------------------------------------------------
# No-peek drift: the amendment document binds the substrate constants
# ---------------------------------------------------------------------------


def test_amendment_001_matches_code() -> None:
    """No-peek: PREREGISTRATION_AMENDMENT_001.yaml binds the substrate.

    Mirrors the existing amendment-binding pattern
    (``test_cg002_preregistration_matches_code``). The set of gate names
    the substrate reclassifies must equal the document's
    ``amended_gate_names`` exactly; both amended gates must be real
    frozen ``NOISY_GATES`` names; the amendment must self-declare it is
    not a science claim; and the human ``.md`` must reference the
    machine YAML (single source). Changing either side without the
    other fails closed (post-data-edit detector).
    """
    data = yaml.safe_load(_AMENDMENT_YAML.read_text(encoding="utf-8"))
    assert data["identifier"] == "PREREGISTRATION-AMENDMENT-001"
    assert data["is_science_claim"] is False
    assert data["is_hypothesis"] is False

    doc_names = set(data["reclassification"]["amended_gate_names"])
    code_names = set(amended_gate_names())
    assert (
        doc_names == code_names
    ), f"amendment doc/code drift: doc {sorted(doc_names)} != substrate {sorted(code_names)}"

    # Every amended name must be a real frozen NOISY_GATES name — the
    # amendment reclassifies an existing gate, it does not invent one,
    # and it must not name a NOISELESS gate.
    frozen_noisy = {g.name for g in NOISY_GATES}
    frozen_noiseless = {g.name for g in NOISELESS_GATES}
    assert code_names == frozen_noisy, (
        f"amended gates {sorted(code_names)} must be exactly the frozen "
        f"noisy gates {sorted(frozen_noisy)}"
    )
    assert not (code_names & frozen_noiseless), "amendment must not touch a noiseless gate"

    # Provenance: amends the frozen prereg sha; cites the CG002 ledger.
    assert (
        data["amends"]["frozen_preregistration_sha"]
        == "d170d48afa5066c13edeb40b2c1904b3fd708516"  # pragma: allowlist secret
    )
    assert (  # pragma: allowlist secret
        data["evidence"]["cg002_ledger_sha256"]
        == "d0f89e24341b099598e2e5cc9809772ee2c47627f77bf3354f957fab860819b1"  # pragma: allowlist secret
    )
    assert data["evidence"]["cross_reference"] == "SUPERSESSIONS.yaml::SUPERSEDE-001"

    md = _AMENDMENT_MD.read_text(encoding="utf-8")
    assert (
        "PREREGISTRATION_AMENDMENT_001.yaml" in md
    ), "the amendment .md must reference the machine YAML (single source)"
    # No threshold VALUE may appear in the amendment (classification
    # only — values stay frozen in gates.py / PREREGISTRATION.md).
    for g in NOISY_GATES:
        assert f"threshold: {g.threshold}" not in _AMENDMENT_YAML.read_text(encoding="utf-8"), (
            f"amendment must not restate a threshold value ({g.name}) — "
            f"it reclassifies the gate CLASS only"
        )


# ---------------------------------------------------------------------------
# HARD invariant 1: the three historical lineages are NOT recomputed
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("lineage", ["cg001", "r1"])
def test_historical_artifacts_not_recomputed_by_amendment(lineage: str) -> None:
    """The default builders stay byte-stable: the amendment is opt-in.

    The merged CALIB-GRID-001 / R1 ``RESULTS.json`` carry a historical
    ``NEGATIVE`` verdict with the ``noisy.*`` gates FAILing. The
    amendment is forward-only and opt-in: ``build_ledger`` /
    ``build_r1_ledger`` must STILL emit the historical ``NEGATIVE`` with
    the ``noisy.*`` gates FAILing (``passed == False``) and must NOT
    carry the amended ``per_gate_state`` / ``INFEASIBLE_BY_CONSTRUCTION``
    keys. This is the regression/golden proof that the historical record
    is not recomputed.
    """
    builder = {"cg001": build_ledger, "r1": build_r1_ledger}[lineage]
    art = (
        _LINEAGE_ROOT / "RESULTS.json"
        if lineage == "cg001"
        else _LINEAGE_ROOT / "r1" / "RESULTS.json"
    )
    committed = json.loads(art.read_text(encoding="utf-8"))
    fresh = builder(wscc_9_bus(), SimConfig())

    # Historical verdict preserved (not recomputed under the amendment).
    assert committed["verdict"] == fresh["verdict"] == "NEGATIVE"
    # The amendment keys must be ABSENT from the default builder output.
    assert "per_gate_state" not in fresh
    assert "infeasible_by_construction_gates" not in fresh
    # The noisy gates still FAIL in the historical reproduction.
    fresh_gates = {g["name"]: g["passed"] for g in fresh["gates"]}
    committed_gates = {g["name"]: g["passed"] for g in committed["gates"]}
    for name in (g.name for g in NOISY_GATES):
        assert fresh_gates[name] is False, f"{lineage}: {name} must still FAIL historically"
        assert committed_gates[name] is False, f"{lineage}: committed {name} historical FAIL"


# ---------------------------------------------------------------------------
# HARD invariant 2: a fresh AMENDED run reclassifies correctly
# ---------------------------------------------------------------------------


def test_overall_verdict_amended_partitions_zero_bit_gates() -> None:
    """``overall_verdict_amended`` excludes amended gates from the verdict.

    Pure-logic property (no simulation): construct a gate-row set where
    every genuine (non-amended) gate PASSes and the amended ``noisy.*``
    gates FAIL. The amended verdict must be ``PASS`` (the zero-bit
    gates are excluded), every amended gate carries
    ``INFEASIBLE_BY_CONSTRUCTION``, and every genuine gate carries
    ``PASS``/``FAIL`` — never the infeasible state.
    """
    from research.calibration.grid_kuramoto._substrate import GateRow

    amended = amended_gate_names()
    rows: list[GateRow] = []
    for g in (*NOISELESS_GATES, *NOISY_GATES):
        passed = g.name not in amended  # genuine pass, amended fail
        rows.append(
            GateRow(
                name=g.name,
                metric_key=g.metric_key,
                observed=0.0,
                operator=g.operator,
                threshold=g.threshold,
                passed=passed,
                localises_to=g.localises_to,
            )
        )
    verdict, per_gate = overall_verdict_amended(rows)
    assert verdict == "PASS", "genuine gates all pass ⇒ reduced verdict PASS"
    for name in amended:
        assert per_gate[name] == INFEASIBLE_BY_CONSTRUCTION
    for g in NOISELESS_GATES:
        assert per_gate[g.name] in ("PASS", "FAIL")
        assert per_gate[g.name] != INFEASIBLE_BY_CONSTRUCTION

    # Now flip a genuine gate to FAIL → reduced verdict NEGATIVE,
    # amended gates still INFEASIBLE (never absorb a genuine failure).
    rows2 = [
        GateRow(
            name=r.name,
            metric_key=r.metric_key,
            observed=r.observed,
            operator=r.operator,
            threshold=r.threshold,
            passed=False if r.name == "noiseless.frobenius" else r.passed,
            localises_to=r.localises_to,
        )
        for r in rows
    ]
    verdict2, per_gate2 = overall_verdict_amended(rows2)
    assert verdict2 == "NEGATIVE"
    for name in amended:
        assert per_gate2[name] == INFEASIBLE_BY_CONSTRUCTION


@pytest.mark.slow
def test_fresh_amended_run_emits_infeasible_and_reduced_verdict() -> None:
    """A fresh lineage #6 run under the amendment reclassifies correctly.

    ``build_amended_ledger`` runs the R1 swing path on the frozen
    config, reads the frozen gates, and emits the distinct
    ``INFEASIBLE_BY_CONSTRUCTION`` state for both ``noisy.*`` gates with
    the overall verdict computed over the remaining genuine pass/fail
    gates only. The R1 swing path noiseless Frobenius PASSes but the
    noiseless critical-coupling gate still FAILs (the genuine,
    information-bearing residual), so the reduced verdict is NEGATIVE —
    and crucially it is NEGATIVE on a genuine gate, NOT saturated by the
    zero-bit noisy gates. No threshold value is touched.
    """
    led = build_amended_ledger(wscc_9_bus(), SimConfig())
    assert led["lineage"].startswith("AMENDED-001")
    assert led["is_science_claim"] is False
    assert led["amendment"] == "PREREGISTRATION-AMENDMENT-001"
    assert led["amendment_cross_reference"] == "SUPERSESSIONS.yaml::SUPERSEDE-001"

    per_gate = led["per_gate_state"]
    for name in (g.name for g in NOISY_GATES):
        assert (
            per_gate[name] == INFEASIBLE_BY_CONSTRUCTION
        ), f"{name} must be reclassified to INFEASIBLE_BY_CONSTRUCTION"
    assert sorted(led["infeasible_by_construction_gates"]) == sorted(g.name for g in NOISY_GATES)

    # The reduced verdict is decided ONLY by genuine gates. The R1
    # swing path: noiseless.frobenius PASS, noiseless.topology_f1 PASS,
    # noiseless.critical_coupling FAIL (the genuine residual) ⇒ NEGATIVE.
    assert led["verdict"] == "NEGATIVE"
    genuine_failed = {g["name"] for g in led["failed_gates"]}
    assert (
        "noiseless.critical_coupling" in genuine_failed
    ), "the reduced NEGATIVE must rest on a GENUINE gate, not the zero-bit noisy gates"
    # No noisy gate may appear in failed_gates (they are not FAIL — they
    # are INFEASIBLE_BY_CONSTRUCTION).
    for name in (g.name for g in NOISY_GATES):
        assert name not in genuine_failed

    # Cross-check: the same metrics under the legacy (non-amended) path
    # still produce a noisy FAIL — proving the amendment only re-labels.
    nl = run_calibration(wscc_9_bus(), SimConfig(), noisy=False, estimator_path="swing")
    ny = run_calibration(wscc_9_bus(), SimConfig(), noisy=True, estimator_path="swing")
    legacy = evaluate_gates(nl, NOISELESS_GATES) + evaluate_gates(ny, NOISY_GATES)
    legacy_by_name = {r.name: r.passed for r in legacy}
    for name in (g.name for g in NOISY_GATES):
        assert legacy_by_name[name] is False, (
            f"sanity: {name} genuinely FAILs the raw metric — the "
            f"amendment reclassifies, it does not improve the number"
        )
