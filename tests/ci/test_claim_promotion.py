# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the tier-promotion gate (RES-020), scripts/ci/check_claim_promotion.py.

The gate binds each docs/CLAIMS.yaml `tier` to the EXECUTED audit verdict it must
have earned. These tests prove it FAILS CLOSED on over-promotion and passes only
correctly-earned tiers.

Structure:
  * PURE teeth       -- evaluate() over FABRICATED report rows (deterministic, no
                        subprocess): every downgrade for ANCHORED / EXTRAPOLATED
                        is RED; correctly-earned tiers GREEN; allowlist pardons an
                        honestly-parked node but never a fired/broken falsifier;
                        stale/dead pardons are RED; evidence-path teeth.
  * INTEGRATION teeth -- drive the REAL geosync.proof.audit.build_report through
                        its dependency-injection seam (resolve_fn/execute_fn/
                        heavy_fn) to FABRICATE the executed verdict over the real
                        27-claim corpus WITHOUT running any pytest node, then run
                        the gate: forcing REFUTED => RED; forcing SUPPORTED =>
                        GREEN. This is the seeded-downgrade demonstration.
  * POLICY-AS-DATA   -- the shipped policy loads, validates, cannot be weakened
                        below the code-pinned contract minimums, and its allowlist
                        references only real claims.

Loaded by path (stdlib + pyyaml only), independent of the repo conftest.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "scripts" / "ci" / "check_claim_promotion.py"
POLICY_PATH = ROOT / "claims" / "promotion_policy.yaml"

_spec = importlib.util.spec_from_file_location("check_claim_promotion", GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

from geosync.proof import audit  # noqa: E402

# A policy fixture mirroring the shipped contract WITHOUT an allowlist, so the
# generic tier teeth are not perturbed by a dead-allowlist check.
POLICY = {
    "require_evidence_paths_exist": True,
    "tier_floor": {
        "ANCHORED": "SUPPORTED",
        "EXTRAPOLATED": "NOT_TESTED",
        "SPECULATIVE": None,
        "UNKNOWN": None,
    },
}
CID = "api-contract-openapi-coverage"
POLICY_AL = {
    "require_evidence_paths_exist": True,
    "tier_floor": dict(POLICY["tier_floor"]),
    "allowlist": {
        CID: {"relaxed_floor": "NOT_TESTED", "reason": "schemathesis optional dependency"}
    },
}


def _always(_rel: str) -> bool:
    return True


def _report(rows, mode="default"):
    return {"mode": mode, "claims": rows}


def _row(tier, verdict, cid="c"):
    return {"id": cid, "tier": tier, "verdict": verdict}


def _claims(*specs):
    # specs: (id, tier, [evidence_paths])
    return [{"id": cid, "tier": tier, "evidence_paths": ep} for cid, tier, ep in specs]


# --------------------------------------------------------------------------
# ANCHORED floor: must have EARNED SUPPORTED. Everything weaker is RED.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", ["DANGLING", "REFUTED", "NOT_TESTED", "FORBIDDEN_LANGUAGE"])
def test_anchored_below_supported_is_red(verdict):
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", verdict)]), _claims(("c", "ANCHORED", [])), _always
    )
    assert res["ok"] is False
    assert any("OVER-PROMOTION" in v and "'c'" in v for v in res["violations"])


def test_anchored_supported_is_green():
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", "SUPPORTED")]), _claims(("c", "ANCHORED", [])), _always
    )
    assert res["ok"] is True and res["violations"] == []


def test_anchored_not_tested_cannot_launder_into_pass():
    # The precise gap RES-020 closes: NOT_TESTED (3) must NOT back ANCHORED (4).
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", "NOT_TESTED")]), _claims(("c", "ANCHORED", [])), _always
    )
    assert res["ok"] is False
    assert any("earned NOT_TESTED" in v for v in res["violations"])


def test_refuted_anchored_says_demote_or_retire():
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", "REFUTED")]), _claims(("c", "ANCHORED", [])), _always
    )
    assert any("FIRED" in v and "demote or RETIRE" in v for v in res["violations"])


# --------------------------------------------------------------------------
# EXTRAPOLATED floor: NOT_TESTED admissible; REFUTED / DANGLING are RED.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", ["NOT_TESTED", "SUPPORTED"])
def test_extrapolated_at_or_above_floor_is_green(verdict):
    res = gate.evaluate(
        POLICY, _report([_row("EXTRAPOLATED", verdict)]), _claims(("c", "EXTRAPOLATED", [])), _always
    )
    assert res["ok"] is True


@pytest.mark.parametrize("verdict", ["REFUTED", "DANGLING", "FORBIDDEN_LANGUAGE"])
def test_extrapolated_below_floor_is_red(verdict):
    res = gate.evaluate(
        POLICY, _report([_row("EXTRAPOLATED", verdict)]), _claims(("c", "EXTRAPOLATED", [])), _always
    )
    assert res["ok"] is False


def test_speculative_and_unknown_have_no_floor():
    for tier in ("SPECULATIVE", "UNKNOWN"):
        res = gate.evaluate(
            POLICY, _report([_row(tier, "REFUTED")]), _claims(("c", tier, [])), _always
        )
        assert res["ok"] is True


# --------------------------------------------------------------------------
# Allowlist: pardons an honestly-parked node, never a fired/broken falsifier.
# --------------------------------------------------------------------------
def test_allowlisted_parked_node_is_green_and_reported():
    res = gate.evaluate(
        POLICY_AL, _report([_row("ANCHORED", "NOT_TESTED", CID)]), _claims((CID, "ANCHORED", [])), _always
    )
    assert res["ok"] is True
    assert len(res["applied"]) == 1 and CID in res["applied"][0]


@pytest.mark.parametrize("verdict", ["REFUTED", "DANGLING", "FORBIDDEN_LANGUAGE"])
def test_allowlist_never_pardons_fired_or_broken_falsifier(verdict):
    res = gate.evaluate(
        POLICY_AL, _report([_row("ANCHORED", verdict, CID)]), _claims((CID, "ANCHORED", [])), _always
    )
    assert res["ok"] is False


def test_stale_allowlist_when_node_now_earns_floor_is_red():
    # schemathesis got installed, node earns SUPPORTED -> the pardon is stale.
    res = gate.evaluate(
        POLICY_AL, _report([_row("ANCHORED", "SUPPORTED", CID)]), _claims((CID, "ANCHORED", [])), _always
    )
    assert res["ok"] is False
    assert any("STALE-ALLOWLIST" in v for v in res["violations"])


def test_dead_allowlist_entry_is_red():
    res = gate.evaluate(
        POLICY_AL, _report([_row("ANCHORED", "SUPPORTED", "other")]), _claims(("other", "ANCHORED", [])), _always
    )
    assert res["ok"] is False
    assert any("DEAD-ALLOWLIST" in v for v in res["violations"])


# --------------------------------------------------------------------------
# Evidence-path existence (independent of the verdict floor).
# --------------------------------------------------------------------------
def test_missing_evidence_path_is_over_promotion():
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", "SUPPORTED")]), _claims(("c", "ANCHORED", ["ghost.py"])), lambda _: False
    )
    assert res["ok"] is False
    assert any("MISSING-EVIDENCE" in v for v in res["violations"])


def test_evidence_paths_not_required_for_unfloored_tier():
    # A SPECULATIVE claim has no floor -> its evidence_paths are not policed here.
    res = gate.evaluate(
        POLICY, _report([_row("SPECULATIVE", "REFUTED")]), _claims(("c", "SPECULATIVE", ["ghost.py"])), lambda _: False
    )
    assert res["ok"] is True


# --------------------------------------------------------------------------
# Mode, staleness-in-report, and unknown-enum fail-closed guards.
# --------------------------------------------------------------------------
def test_resolve_only_report_cannot_satisfy_supported_floor():
    res = gate.evaluate(
        POLICY, _report([_row("ANCHORED", "NOT_TESTED")], mode="resolve"), _claims(("c", "ANCHORED", [])), _always
    )
    assert res["ok"] is False
    assert any(v.startswith("MODE") for v in res["violations"])


def test_claim_absent_from_report_is_red():
    res = gate.evaluate(POLICY, _report([]), _claims(("c", "ANCHORED", [])), _always)
    assert res["ok"] is False
    assert any("MISSING" in v for v in res["violations"])


def test_unknown_verdict_is_red():
    res = gate.evaluate(POLICY, _report([_row("ANCHORED", "WAT")]), _claims(("c", "ANCHORED", [])), _always)
    assert res["ok"] is False and any("UNKNOWN-VERDICT" in v for v in res["violations"])


def test_unknown_tier_is_red():
    res = gate.evaluate(POLICY, _report([_row("MYSTERY", "SUPPORTED")]), _claims(("c", "MYSTERY", [])), _always)
    assert res["ok"] is False and any("UNKNOWN-TIER" in v for v in res["violations"])


def test_evaluate_is_deterministic():
    rep = _report([_row("ANCHORED", "REFUTED"), _row("EXTRAPOLATED", "NOT_TESTED", "d")])
    cl = _claims(("c", "ANCHORED", []), ("d", "EXTRAPOLATED", []))
    assert gate.evaluate(POLICY, rep, cl, _always) == gate.evaluate(POLICY, rep, cl, _always)


# --------------------------------------------------------------------------
# INTEGRATION teeth: drive the REAL build_report via its DI seam. No real pytest
# node executes -- resolve_fn/execute_fn fabricate the executed outcome -- so the
# test is deterministic and fast while exercising the genuine engine+gate path.
# Evaluated against a no-allowlist policy so a forced-SUPPORTED corpus is not
# perturbed by the (then-stale) schemathesis pardon.
# --------------------------------------------------------------------------
_NO_AL_POLICY = {
    "require_evidence_paths_exist": False,  # forcing verdicts; decouple from disk here
    "tier_floor": {"ANCHORED": "SUPPORTED", "EXTRAPOLATED": "NOT_TESTED", "SPECULATIVE": None, "UNKNOWN": None},
}


def _forced_report(rc, junit):
    return audit.build_report(
        mode=audit.MODE_DEFAULT,
        resolve_fn=lambda tid: (True, "collected"),
        execute_fn=lambda tid, timeout: (rc, junit),
        heavy_fn=lambda tid: False,
    )


def test_seeded_downgrade_forced_refuted_makes_gate_red():
    # Every falsifier "FIRES" -> REFUTED on the real ANCHORED corpus.
    report = _forced_report(rc=1, junit="failure")
    res = gate.evaluate(_NO_AL_POLICY, report, audit.load_claims(), _always)
    assert res["ok"] is False, "REFUTED ANCHORED claims must make the promotion gate RED"


def test_forced_supported_earns_anchored_green():
    # Every falsifier HELDS -> SUPPORTED; the 22 ANCHORED claims all name a
    # falsifier, so the gate is GREEN (falsifier-less EXTRAPOLATED stay NOT_TESTED,
    # which meets their floor).
    report = _forced_report(rc=0, junit="passed")
    res = gate.evaluate(_NO_AL_POLICY, report, audit.load_claims(), _always)
    assert res["ok"] is True, f"correctly-earned SUPPORTED corpus must pass: {res['violations']}"


# --------------------------------------------------------------------------
# Policy-as-data validation: the data file may not weaken the contract minimums.
# --------------------------------------------------------------------------
def test_policy_cannot_weaken_anchored_floor():
    weak = {"tier_floor": {"ANCHORED": "NOT_TESTED", "EXTRAPOLATED": "NOT_TESTED"}}
    assert gate.validate_policy(weak) != []


def test_policy_rejects_allowlist_relaxed_to_refuted():
    bad = {
        "tier_floor": {"ANCHORED": "SUPPORTED", "EXTRAPOLATED": "NOT_TESTED"},
        "allowlist": {"x": {"relaxed_floor": "REFUTED", "reason": "r"}},
    }
    assert gate.validate_policy(bad) != []


def test_policy_rejects_allowlist_without_reason():
    bad = {
        "tier_floor": {"ANCHORED": "SUPPORTED", "EXTRAPOLATED": "NOT_TESTED"},
        "allowlist": {"x": {"relaxed_floor": "NOT_TESTED", "reason": "   "}},
    }
    assert gate.validate_policy(bad) != []


def test_policy_rejects_unknown_verdict_name():
    bad = {"tier_floor": {"ANCHORED": "SUPPORTED", "EXTRAPOLATED": "MADEUP"}}
    assert gate.validate_policy(bad) != []


# --------------------------------------------------------------------------
# The SHIPPED policy file is well-formed and its allowlist references real claims.
# --------------------------------------------------------------------------
def test_installed_policy_is_valid():
    policy = gate.load_policy(POLICY_PATH)
    assert gate.validate_policy(policy) == []
    assert policy["tier_floor"]["ANCHORED"] == "SUPPORTED"
    assert policy["tier_floor"]["EXTRAPOLATED"] == "NOT_TESTED"
    claim_ids = {str(c.get("id")) for c in audit.load_claims()}
    for aid in (policy.get("allowlist") or {}):
        assert aid in claim_ids, f"allowlist pardons unknown claim {aid!r}"
