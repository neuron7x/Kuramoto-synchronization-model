# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""EBSVAP governance instruments — executable invariants.

Encodes the WP1/WP3/WP4 falsification metrics as pytest so the governance
surface is gated in CI (not only via the standalone WP runners). Verdict of the
instruments remains LIMITED_SCOPE; scientific/intervention authority DENIED —
these tests assert the *instruments* behave, not that any target claim is true.
"""

from __future__ import annotations

import pytest

from src.ebsvap.authority_gateway import (
    ActionCertificate,
    Gateway,
    args_hash,
    execute,
    issue_certificate,
)
from src.ebsvap.claim_compiler import Claim, compile_claim
from src.ebsvap.process_oracle import classify


# --------------------------------------------------------------------------- #
# WP1 — claim compiler: critical-unsupported recall == 1.0, false rejection 0  #
# --------------------------------------------------------------------------- #

OVERCLAIMS = [
    Claim("O1", "the edge is empirically validated", "EMPIRICAL", {}),
    Claim("O2", "the reviewer is calibrated", "PROBABILISTIC", {}),
    Claim("O3", "X causes Y", "CAUSAL", {"data": "correlation"}),
    Claim("O4", "the method generalizes", "GENERALIZATION", {"data": "iid_only"}),
    Claim("O5", "independently verified", "EMPIRICAL",
          {"data": 1, "source": "impl", "independent_source": "impl"}),
    Claim("O6", "the system is safe", "SAFETY", {"unit_tests_only": True}),
    Claim("O7", "the stopping rule is optimal", "PERFORMANCE", {"data": 1}),
]

VALID = [
    Claim("V1", "coverage established under i.i.d.", "EMPIRICAL", {"data": 1, "raw_log": 1}),
    Claim("V2", "the marginal is not coverable under dependence (counterexample)",
          "EMPIRICAL", {"data": 1}),
    Claim("V3", "kill-switch fails closed on corrupt state", "SAFETY",
          {"data": 1, "unit_tests_only": False}),
]


@pytest.mark.parametrize("claim", OVERCLAIMS, ids=lambda c: c.claim_id)
def test_wp1_overclaims_rejected_with_reason(claim: Claim) -> None:
    r = compile_claim(claim)
    assert r["status"] == "REJECT"
    assert r["reason"], "every rejection must name the failed condition"


@pytest.mark.parametrize("claim", VALID, ids=lambda c: c.claim_id)
def test_wp1_valid_claims_admitted(claim: Claim) -> None:
    assert compile_claim(claim)["status"] == "ADMIT"


def test_wp1_metrics_match_final_act() -> None:
    over = [compile_claim(c) for c in OVERCLAIMS]
    valid = [compile_claim(c) for c in VALID]
    recall = sum(1 for r in over if r["status"] == "REJECT") / len(over)
    false_rej = sum(1 for r in valid if r["status"] == "REJECT") / len(valid)
    assert recall == 1.0
    assert false_rej == 0.0


def test_wp1_unknown_type_fails_closed() -> None:
    r = compile_claim(Claim("U1", "some assertion", "TELEOLOGICAL", {"data": 1}))
    assert r["status"] == "REJECT"
    assert "fail-closed" in r["reason"]


def test_wp1_compound_rejected_if_any_conjunct_unsupported() -> None:
    good = Claim("A", "coverage under i.i.d.", "EMPIRICAL", {"data": 1})
    bad = Claim("B", "the reviewer is calibrated", "PROBABILISTIC", {})
    compound = Claim("C", "joint claim", "EMPIRICAL", {"data": 1, "conjuncts": [good, bad]})
    r = compile_claim(compound)
    assert r["status"] == "REJECT"
    assert "conjunct B" in r["reason"]


def test_wp1_forbidden_word_rejected_when_contract_unmet() -> None:
    # 'proven' without a proof
    assert compile_claim(Claim("P", "the bound is proven", "MATHEMATICAL",
                               {"proof": None}))["status"] == "REJECT"
    # 'proven' WITH a proof is admissible
    assert compile_claim(Claim("P2", "the bound is proven", "MATHEMATICAL",
                               {"proof": "theorem"}))["status"] == "ADMIT"


# every claim-type contract, both the reject and the admit path
_CONTRACT_CASES = [
    # (id, type, evidence, expected_status)
    ("math_reject", "MATHEMATICAL", {}, "REJECT"),
    ("math_admit", "MATHEMATICAL", {"proof": "thm"}, "ADMIT"),
    ("emp_reject", "EMPIRICAL", {}, "REJECT"),
    ("emp_admit", "EMPIRICAL", {"data": 1}, "ADMIT"),
    ("prob_reject", "PROBABILISTIC", {}, "REJECT"),
    ("prob_admit", "PROBABILISTIC", {"calibration": 1}, "ADMIT"),
    ("causal_reject", "CAUSAL", {}, "REJECT"),
    ("causal_admit", "CAUSAL", {"intervention": 1}, "ADMIT"),
    ("gen_no_test", "GENERALIZATION", {"data": 1}, "REJECT"),
    ("gen_iid_only", "GENERALIZATION", {"structural_test": 1, "data": "iid_only"}, "REJECT"),
    ("gen_admit", "GENERALIZATION", {"structural_test": 1, "data": 1}, "ADMIT"),
    ("safety_reject", "SAFETY", {"unit_tests_only": True}, "REJECT"),
    ("safety_admit", "SAFETY", {"data": 1}, "ADMIT"),
    ("opauth_reject", "OPERATIONAL_AUTHORITY", {}, "REJECT"),
    ("opauth_admit", "OPERATIONAL_AUTHORITY", {"holdout": 1}, "ADMIT"),
    ("perf_reject", "PERFORMANCE", {}, "REJECT"),
    ("repro_admit", "REPRODUCIBILITY", {"raw_log": 1}, "ADMIT"),
    ("sec_admit", "SECURITY", {"data": 1}, "ADMIT"),
]


@pytest.mark.parametrize("cid,ctype,ev,expected", _CONTRACT_CASES, ids=[c[0] for c in _CONTRACT_CASES])
def test_wp1_contract_matrix(cid: str, ctype: str, ev: dict, expected: str) -> None:
    # neutral wording so only the type contract (not a forbidden word) decides
    assert compile_claim(Claim(cid, "the descriptor holds", ctype, ev))["status"] == expected


# every forbidden strength word, rejected when its contract is unsatisfied
_WORD_CASES = [
    ("calibrated", "the estimate is calibrated", "EMPIRICAL", {"data": 1}),
    ("safe", "the pipeline is safe", "EMPIRICAL", {"data": 1, "unit_tests_only": True}),
    ("independent", "independent confirmation", "EMPIRICAL",
     {"data": 1, "source": "impl", "independent_source": "impl"}),
    ("optimal", "the policy is optimal", "EMPIRICAL", {"data": 1}),
    ("generalizable", "the result is generalizable", "EMPIRICAL", {"data": "iid_only"}),
    ("validated", "the model is validated", "EMPIRICAL", {"data": 1}),
]


@pytest.mark.parametrize("word,text,ctype,ev", _WORD_CASES, ids=[c[0] for c in _WORD_CASES])
def test_wp1_forbidden_words_matrix(word: str, text: str, ctype: str, ev: dict) -> None:
    # 'validated' with a data path is admissible; the rest must reject
    r = compile_claim(Claim(word, text, ctype, ev))
    if word == "validated":
        assert r["status"] == "ADMIT"
    else:
        assert r["status"] == "REJECT"


def test_wp1_word_check_reject_paths_independent_of_type_contract() -> None:
    # 'validated' passes the SAFETY contract but the word contract has no evidence path
    assert compile_claim(Claim("w1", "the result is validated", "SAFETY", {}))["status"] == "REJECT"
    # 'proven' inside a non-mathematical claim whose type contract passes
    assert compile_claim(Claim("w2", "the bound is proven", "EMPIRICAL",
                               {"data": 1}))["status"] == "REJECT"


def test_wp1_forbidden_word_present_but_satisfied_admits() -> None:
    # 'independent' with a genuinely distinct source -> word contract satisfied
    assert compile_claim(Claim("w3", "independent confirmation", "EMPIRICAL",
                               {"data": 1, "source": "impl", "independent_source": "audit"}))["status"] == "ADMIT"
    # 'optimal' with an optimality proof -> satisfied
    assert compile_claim(Claim("w4", "the policy is optimal", "EMPIRICAL",
                               {"data": 1, "proof": "bellman"}))["status"] == "ADMIT"


def test_wp1_compound_all_conjuncts_supported_admits() -> None:
    a = Claim("A", "coverage under i.i.d.", "EMPIRICAL", {"data": 1})
    b = Claim("B", "kill-switch fails closed", "SAFETY", {"data": 1})
    compound = Claim("C", "the descriptor holds", "EMPIRICAL", {"data": 1, "conjuncts": [a, b]})
    assert compile_claim(compound)["status"] == "ADMIT"


# --------------------------------------------------------------------------- #
# WP3 — proof-carrying action gateway: bypass 0.0, deny-side-effect 0.0        #
# --------------------------------------------------------------------------- #

def _fresh() -> tuple[Gateway, ActionCertificate, dict, str, dict]:
    args = {"amount": 10, "to": "acct-A"}
    # Signature enforcement is fail-closed by default: provision the issuer key
    # and sign the certificate so the valid path authorizes for the right reason.
    secret = "issuer-secret-auth-1"
    gw = Gateway(
        live_authorities={"auth-1"},
        approvals={("transfer", "ledger", "cls-1")},
        clock=5,
        issuer_keys={"auth-1": secret},
    )
    cert = ActionCertificate(
        action_id="act-1", action="transfer", destination="ledger",
        arguments_hash=args_hash(args), authority="auth-1",
        approval_class="cls-1", nonce="n-1", expiry=10,
    )
    issue_certificate(secret, cert)
    return gw, cert, args, "ledger", {}


def test_wp3_valid_action_authorized_and_executes() -> None:
    gw, cert, args, dest, world = _fresh()
    r = execute(gw, cert, "transfer", args, dest, world)
    assert r["authorized"] is True and r["side_effect"] is True
    assert world[dest] == args


@pytest.mark.parametrize("mutate", [
    "replay", "arg_mutation", "wrong_destination", "expired", "revoked", "no_approval",
])
def test_wp3_negative_controls_deny_with_no_side_effect(mutate: str) -> None:
    gw, cert, args, dest, world = _fresh()

    if mutate == "replay":
        execute(gw, cert, "transfer", args, dest, world)   # burn the nonce
        world = {}
        call_args = args
    elif mutate == "arg_mutation":
        call_args = {"amount": 999, "to": "acct-A"}          # hash will mismatch
    elif mutate == "wrong_destination":
        dest = "attacker"
        call_args = args
    elif mutate == "expired":
        gw.clock = 99
        call_args = args
    elif mutate == "revoked":
        gw.live_authorities.clear()
        call_args = args
    elif mutate == "no_approval":
        gw.approvals.clear()
        call_args = args

    r = execute(gw, cert, "transfer", call_args, dest, world)
    assert r["authorized"] is False, f"{mutate} must DENY"
    assert r["side_effect"] is False, f"{mutate} DENY must have no side effect"
    assert dest not in world, f"{mutate} must not mutate the world"


def test_wp3_bypass_and_deny_side_effect_rates_are_zero() -> None:
    # aggregate the WP3 metrics exactly as the FINAL_ACT reports them
    bypass = 0
    deny_side_effect = 0
    for mutate in ("replay", "arg_mutation", "wrong_destination", "expired", "revoked", "no_approval"):
        gw, cert, args, dest, world = _fresh()
        if mutate == "replay":
            execute(gw, cert, "transfer", args, dest, world)
            world = {}
            r = execute(gw, cert, "transfer", args, dest, world)
        elif mutate == "arg_mutation":
            r = execute(gw, cert, "transfer", {"amount": 1}, dest, world)
        elif mutate == "wrong_destination":
            r = execute(gw, cert, "transfer", args, "attacker", world)
        elif mutate == "expired":
            gw.clock = 99
            r = execute(gw, cert, "transfer", args, dest, world)
        elif mutate == "revoked":
            gw.live_authorities.clear()
            r = execute(gw, cert, "transfer", args, dest, world)
        elif mutate == "no_approval":
            gw.approvals.clear()
            r = execute(gw, cert, "transfer", args, dest, world)
        if r["authorized"]:
            bypass += 1
        if r["side_effect"]:
            deny_side_effect += 1
    assert bypass == 0
    assert deny_side_effect == 0


# --------------------------------------------------------------------------- #
# WP4 — process oracle: outcome-correct != process-valid                       #
# --------------------------------------------------------------------------- #

def _all_ran() -> dict:
    return {c: "ran" for c in
            ("schema_validation", "authorization", "safety_gate",
             "fresh_evidence", "rollback_defined")}


def test_wp4_valid_success_requires_all_checkpoints() -> None:
    r = classify({"outcome_correct": True, "checkpoints": _all_ran()})
    assert r["label"] == "VALID_SUCCESS"
    assert r["earliest_violation"] is None


def test_wp4_correct_outcome_after_skipped_checkpoint_is_near_miss() -> None:
    checks = _all_ran()
    checks["authorization"] = "skipped"
    r = classify({"outcome_correct": True, "checkpoints": checks})
    assert r["label"] == "NEAR_MISS"
    assert r["earliest_violation"] == "authorization"


def test_wp4_stale_evidence_counts_as_violation() -> None:
    checks = _all_ran()
    checks["fresh_evidence"] = "stale"
    assert classify({"outcome_correct": True, "checkpoints": checks})["label"] == "NEAR_MISS"


def test_wp4_incorrect_outcome_labels() -> None:
    assert classify({"outcome_correct": False, "checkpoints": _all_ran()})["label"] \
        == "SPEC_OR_MODEL_FAILURE"
    assert classify({"outcome_correct": False, "checkpoints": {}})["label"] \
        == "EXECUTION_FAILURE"


# --------------------------------------------------------------------------- #
# Regression: fail-closed holes closed after the adversarial audit             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", ["ok", "passed", "RAN", True, "skipped_but_ok", "done"])
def test_wp4_non_ran_status_is_a_violation_not_a_pass(status: object) -> None:
    # a checkpoint counts only when it is exactly "ran"; any other value is a
    # violation, so a correct outcome over unrecognised statuses is a NEAR_MISS
    checks = {c: status for c in
              ("schema_validation", "authorization", "safety_gate",
               "fresh_evidence", "rollback_defined")}
    assert classify({"outcome_correct": True, "checkpoints": checks})["label"] == "NEAR_MISS"


def test_wp1_safety_claim_without_evidence_is_rejected() -> None:
    # empty-evidence SAFETY must not ADMIT (contract requires an evidence path)
    assert compile_claim(Claim("s0", "the descriptor holds", "SAFETY", {}))["status"] == "REJECT"
    assert compile_claim(Claim("s1", "the system is safe", "SAFETY", {}))["status"] == "REJECT"
    # with an evidence path (and no unit_tests_only overclaim) it admits
    assert compile_claim(Claim("s2", "the descriptor holds", "SAFETY", {"data": 1}))["status"] == "ADMIT"


def test_wp1_generalizable_requires_structural_test_regardless_of_type() -> None:
    # 'generalizable' routed through the EMPIRICAL contract with plain data must
    # still be rejected — the word demands a structural/non-IID test
    assert compile_claim(Claim("g0", "the result is generalizable", "EMPIRICAL",
                               {"data": 1}))["status"] == "REJECT"
    assert compile_claim(Claim("g1", "the result is generalizable", "EMPIRICAL",
                               {"data": 1, "structural_test": 1}))["status"] == "ADMIT"


@pytest.mark.parametrize("text", [
    "this proves the bound",
    "the estimator is provably correct",
    "the method generalises well",
    "the schedule is provably optimal",
])
def test_wp1_morphological_variants_do_not_evade_word_guard(text: str) -> None:
    # inflected / British forms of strength words must still trip the guard
    # (data present so only the word layer can reject)
    assert compile_claim(Claim("m", text, "EMPIRICAL", {"data": 1}))["status"] == "REJECT"


def test_wp1_safe_word_guard_fires_across_claim_types() -> None:
    # 'safe' in a claim whose type contract passes but which offers no evidence
    # path (here MATHEMATICAL with a proof but no data) must still be rejected
    assert compile_claim(Claim("sx", "the pipeline is safe", "MATHEMATICAL",
                               {"proof": "thm"}))["status"] == "REJECT"
    # 'validated' likewise: MATHEMATICAL contract met by a proof, but no
    # holdout/data evidence path for the validation wording
    assert compile_claim(Claim("vx", "the result is validated", "MATHEMATICAL",
                               {"proof": "thm"}))["status"] == "REJECT"


@pytest.mark.parametrize("neutral", [
    "the pipeline improves throughput",   # 'improves' must NOT match 'prov...'
    "provenance of the artifact is logged",  # 'provenance' must NOT match 'proven'
    "the run is unsafe to repeat",        # 'unsafe' must NOT match 'safe'
])
def test_wp1_word_guard_no_false_positive_on_lookalikes(neutral: str) -> None:
    assert compile_claim(Claim("n", neutral, "EMPIRICAL", {"data": 1}))["status"] == "ADMIT"


def test_wp3_expiry_boundary_is_inclusive() -> None:
    gw, cert, args, dest, world = _fresh()  # expiry=10
    gw.clock = 10  # equal to expiry -> still valid
    assert execute(gw, cert, "transfer", args, dest, world)["authorized"] is True
    gw2, cert2, args2, dest2, world2 = _fresh()
    gw2.clock = 11  # past expiry -> denied
    r = execute(gw2, cert2, "transfer", args2, dest2, world2)
    assert r["authorized"] is False and r["side_effect"] is False


def test_wp3_nonce_replay_across_instances_is_documented_scope() -> None:
    # replay protection is per-ledger; a SHARED ledger blocks cross-instance replay
    shared: set = set()
    a1, c1, ar, d1, w1 = _fresh()
    a1._used_nonces = shared
    a2, c2, _, d2, w2 = _fresh()
    a2._used_nonces = shared
    assert execute(a1, c1, "transfer", ar, d1, w1)["authorized"] is True
    # same nonce on the second instance sharing the ledger -> replay denied
    r = execute(a2, c2, "transfer", ar, d2, w2)
    assert r["authorized"] is False and r["side_effect"] is False
