# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""Wave-13 destruction-hardening regressions for EBSVAP.

Each test replays a CONFIRMED destroyer repro and asserts the CORRECTED
(fail-closed) behavior, paired with the benign/ASCII twin that must still behave
as before — so the test is non-vacuous: it would have FAILED against the code as
it stood before this remediation.

  DS-01  claim_compiler homoglyph/zero-width/NUL forbidden-word bypass
  DS-14  compile_claim unbounded conjunct recursion -> RecursionError crash
  DS-15  compile_claim AttributeError on malformed claim shapes
  DS-19  authority_gateway certificate forgery (no MAC over cert fields)
  DS-20  authority_gateway cross-instance nonce replay
  DS-21  args_hash repr-coercion collision
"""

from __future__ import annotations

import pytest

from src.ebsvap.authority_gateway import (
    ActionCertificate,
    Gateway,
    args_hash,
    execute,
    issue_certificate,
    sign_certificate,
)
from src.ebsvap.claim_compiler import MAX_CONJUNCT_DEPTH, Claim, compile_claim


# --------------------------------------------------------------------------- #
# DS-01 — forbidden-word guard must not be bypassed by non-ASCII/hidden chars  #
# --------------------------------------------------------------------------- #

# (id, evasive text, correct-reject substring, ASCII twin text)
_DS01_EVASIONS = [
    # Cyrillic о U+043E inside "proven"
    ("homoglyph_proven", "the method is prоven", "proven", "the method is proven"),
    # Cyrillic а U+0430 inside "optimal"
    ("homoglyph_optimal", "the policy is optimаl", "optimal", "the policy is optimal"),
    # Cyrillic і U+0456 inside "independent"
    ("homoglyph_independent", "іndependent verification", "independent",
     "independent verification"),
    # ZWSP U+200B splitting "proven"
    ("zwsp_proven", "pro​ven bound", "proven", "proven bound"),
    # NUL splitting "proven"
    ("nul_proven", "pro\x00ven bound", "proven", "proven bound"),
]


@pytest.mark.parametrize("cid,evasive,needle,ascii_twin", _DS01_EVASIONS, ids=[c[0] for c in _DS01_EVASIONS])
def test_ds01_evasion_now_rejects_like_ascii_twin(
    cid: str, evasive: str, needle: str, ascii_twin: str
) -> None:
    # EMPIRICAL contract is satisfied by data, so ONLY the word layer can reject.
    ev = {"data": [1]}
    evasive_r = compile_claim(Claim(cid, evasive, "EMPIRICAL", dict(ev)))
    ascii_r = compile_claim(Claim(cid + "_ascii", ascii_twin, "EMPIRICAL", dict(ev)))
    # before the fix the evasive form ADMITted while the ASCII twin REJECTed;
    # now BOTH reject, and the evasive form must name the same strength word
    assert ascii_r["status"] == "REJECT", "ASCII twin must reject (guard baseline)"
    assert evasive_r["status"] == "REJECT", f"{cid}: evasion must no longer ADMIT"
    assert needle in evasive_r["reason"], f"{cid}: must name the hidden strength word"


def test_ds01_clean_claim_still_admits() -> None:
    # normalization must not over-reject: a genuinely clean claim (no forbidden
    # word, no homoglyph) with a satisfied contract still ADMITs
    r = compile_claim(Claim("clean", "the pipeline improves throughput", "EMPIRICAL",
                            {"data": 1}))
    assert r["status"] == "ADMIT"


def test_ds01_benign_lookalike_word_not_over_matched() -> None:
    # 'provenance' / 'improves' must NOT trip the 'prov...' guard even after
    # normalization (word-boundary preserved)
    assert compile_claim(Claim("prov", "provenance of the artifact is logged",
                               "EMPIRICAL", {"data": 1}))["status"] == "ADMIT"


# --------------------------------------------------------------------------- #
# DS-14 — unbounded conjunct recursion must fail-closed, not RecursionError    #
# --------------------------------------------------------------------------- #

def _nest(depth: int) -> Claim:
    node = Claim("leaf", "the descriptor holds", "EMPIRICAL", {"data": 1})
    for i in range(depth):
        node = Claim(f"n{i}", "the descriptor holds", "EMPIRICAL",
                     {"data": 1, "conjuncts": [node]})
    return node


def test_ds14_deep_nesting_rejects_not_raises() -> None:
    # repro: ~1000-deep nest previously raised uncaught RecursionError
    deep = _nest(1000)
    r = compile_claim(deep)  # must return, not raise
    assert r["status"] == "REJECT"
    assert "exceeds max depth" in r["reason"]


def test_ds14_legit_shallow_nesting_still_compiles() -> None:
    # a legitimately 3-deep nest (well under the bound) still ADMITs
    assert MAX_CONJUNCT_DEPTH >= 3
    r = compile_claim(_nest(3))
    assert r["status"] == "ADMIT"


# --------------------------------------------------------------------------- #
# DS-15 — malformed claim shapes must REJECT with a reason, not AttributeError #
# --------------------------------------------------------------------------- #

_DS15_MALFORMED = [
    ("evidence_list", Claim("m", "the descriptor holds", "EMPIRICAL", evidence=[])),
    ("evidence_none", Claim("m", "the descriptor holds", "EMPIRICAL", evidence=None)),  # type: ignore[arg-type]
    ("conjuncts_str", Claim("m", "the descriptor holds", "EMPIRICAL",
                            {"data": 1, "conjuncts": "oops"})),
    ("conjuncts_list_of_str", Claim("m", "the descriptor holds", "EMPIRICAL",
                                    {"data": 1, "conjuncts": ["a", "b"]})),
    ("text_int", Claim("m", 123, "EMPIRICAL", {"data": 1})),  # type: ignore[arg-type]
]


@pytest.mark.parametrize("cid,claim", _DS15_MALFORMED, ids=[c[0] for c in _DS15_MALFORMED])
def test_ds15_malformed_shapes_reject_fail_closed(cid: str, claim: Claim) -> None:
    # previously each of these raised AttributeError/TypeError (a crash = no
    # verdict = fail-open); now each REJECTs with a fail-closed reason
    r = compile_claim(claim)
    assert r["status"] == "REJECT", f"{cid} must REJECT"
    assert r["reason"], f"{cid} must name the failure"
    assert "fail-closed" in r["reason"]


def test_ds15_well_formed_twin_still_admits() -> None:
    # the benign twin of the malformed shapes (proper dict evidence, str text)
    # still ADMITs — the guards do not reject valid inputs
    assert compile_claim(Claim("ok", "the descriptor holds", "EMPIRICAL",
                               {"data": 1}))["status"] == "ADMIT"


# --------------------------------------------------------------------------- #
# DS-19 — certificate forgery: a valid authority string is not proof of issue  #
# --------------------------------------------------------------------------- #

_ISSUER = "issuer-secret-key-42"


def _secure_gateway(nonce_ledger: set | None = None) -> Gateway:
    return Gateway(
        live_authorities={"auth-1"},
        approvals={("transfer", "ledger", "cls-1")},
        clock=5,
        issuer_keys={"auth-1": _ISSUER},
        nonce_ledger=nonce_ledger,
    )


def _cert(args: dict, nonce: str = "n-1") -> ActionCertificate:
    return ActionCertificate(
        action_id="act-1", action="transfer", destination="ledger",
        arguments_hash=args_hash(args), authority="auth-1",
        approval_class="cls-1", nonce=nonce, expiry=10,
    )


def test_ds19_forged_unsigned_cert_denied() -> None:
    gw = _secure_gateway()
    # attacker knows the live authority string and mints a cert for 1e9, unsigned
    evil_args = {"amount": 10**9, "to": "attacker"}
    forged = _cert(evil_args)  # signature == "" (no issuer secret held)
    world: dict = {}
    r = execute(gw, forged, "transfer", evil_args, "ledger", world)
    assert r["authorized"] is False
    assert "signature" in r["reason"]
    assert world == {}, "forged cert must produce no side effect"


def test_ds19_forged_wrong_signature_denied() -> None:
    gw = _secure_gateway()
    evil_args = {"amount": 10**9, "to": "attacker"}
    forged = _cert(evil_args)
    forged.signature = sign_certificate("guessed-wrong-key", forged)
    r = execute(gw, forged, "transfer", evil_args, "ledger", {})
    assert r["authorized"] is False
    assert "signature" in r["reason"]


def test_ds19_properly_signed_cert_authorizes() -> None:
    # the legitimate path must be preserved: a cert signed by the registered
    # issuer AUTHORIZES and executes
    gw = _secure_gateway()
    args = {"amount": 10, "to": "acct-A"}
    cert = issue_certificate(_ISSUER, _cert(args))
    world: dict = {}
    r = execute(gw, cert, "transfer", args, "ledger", world)
    assert r["authorized"] is True and r["side_effect"] is True
    assert world["ledger"] == args


def test_ds19_signature_binds_arguments_hash() -> None:
    # a signed cert whose arguments_hash is swapped for a bigger-amount hash is
    # rejected: the swap breaks BOTH the hash-match and the signature
    gw = _secure_gateway()
    small = {"amount": 10, "to": "acct-A"}
    big = {"amount": 10**9, "to": "acct-A"}
    cert = issue_certificate(_ISSUER, _cert(small))
    cert.arguments_hash = args_hash(big)  # tamper after signing
    r = execute(gw, cert, "transfer", big, "ledger", {})
    assert r["authorized"] is False


def test_ds19r2_default_gateway_denies_unsigned_shipped_config() -> None:
    # ROUND-2 closure: signature enforcement is fail-closed BY DEFAULT. A default
    # Gateway with an EMPTY issuer registry and no allow_unsigned opt-out must
    # DENY any presented cert (cannot verify issuance), even one that satisfies
    # every membership/approval check — this is the shipped-config forgery that
    # the opt-in design left open.
    args = {"amount": 10**9, "to": "attacker"}
    gw = Gateway(
        live_authorities={"auth-1"},
        approvals={("transfer", "ledger", "cls-1")},
        clock=5,
    )  # no issuer_keys, no allow_unsigned
    r = execute(gw, _cert(args), "transfer", args, "ledger", {})
    assert r["authorized"] is False
    assert "issuer key" in r["reason"]


def test_ds19r2_allow_unsigned_is_explicit_opt_in() -> None:
    # the legacy membership-only mode is still reachable, but ONLY via the
    # explicit, audited flag — never as a silent default.
    args = {"amount": 10, "to": "acct-A"}
    gw = Gateway(
        live_authorities={"auth-1"},
        approvals={("transfer", "ledger", "cls-1")},
        clock=5,
        allow_unsigned=True,
    )
    r = execute(gw, _cert(args), "transfer", args, "ledger", {})
    assert r["authorized"] is True


# --------------------------------------------------------------------------- #
# DS-20 — cross-instance nonce replay is blocked by a shared ledger            #
# --------------------------------------------------------------------------- #

def test_ds20_shared_ledger_blocks_cross_instance_replay() -> None:
    shared: set = set()
    gw1 = _secure_gateway(nonce_ledger=shared)
    gw2 = _secure_gateway(nonce_ledger=shared)  # separate instance, shared ledger
    args = {"amount": 10, "to": "acct-A"}
    cert = issue_certificate(_ISSUER, _cert(args))
    r1 = execute(gw1, cert, "transfer", args, "ledger", {})
    assert r1["authorized"] is True
    r2 = execute(gw2, cert, "transfer", args, "ledger", {})  # replay on 2nd instance
    assert r2["authorized"] is False
    assert "replay" in r2["reason"]


def test_ds20_default_per_instance_ledger_documents_limitation() -> None:
    # benign twin: WITHOUT a shared ledger the same nonce replays once per
    # instance (the documented single-instance scope) — proves the shared-ledger
    # test above is the load-bearing behavior, not an accident
    gw1 = _secure_gateway()
    gw2 = _secure_gateway()
    args = {"amount": 10, "to": "acct-A"}
    cert = issue_certificate(_ISSUER, _cert(args))
    assert execute(gw1, cert, "transfer", args, "ledger", {})["authorized"] is True
    assert execute(gw2, cert, "transfer", args, "ledger", {})["authorized"] is True


# --------------------------------------------------------------------------- #
# DS-21 — args_hash must not collide an object with a crafted repr             #
# --------------------------------------------------------------------------- #

class _EvilRepr:
    def __repr__(self) -> str:  # imitates the string '1'
        return "1"


def test_ds21_repr_coercion_collision_no_longer_holds() -> None:
    # previously args_hash({'x': _EvilRepr()}) == args_hash({'x': '1'}) because
    # default=repr coerced the object to the string "1". Now the object is
    # REJECTED (fail-closed) so no collision is possible.
    assert args_hash({"x": "1"})  # native value hashes fine
    with pytest.raises(TypeError):
        args_hash({"x": _EvilRepr()})


def test_ds21_int_key_and_str_key_are_distinct() -> None:
    assert args_hash({1: "a"}) != args_hash({"1": "a"})


def test_ds21_int_value_and_str_value_are_distinct() -> None:
    assert args_hash({"x": 1}) != args_hash({"x": "1"})


def test_ds21_native_args_hash_is_stable_and_order_independent() -> None:
    # existing behavior preserved for JSON-native args
    assert args_hash({"amount": 10, "to": "x"}) == args_hash({"to": "x", "amount": 10})
    assert args_hash({"amount": 10, "to": "x"}) != args_hash({"amount": 11, "to": "x"})


# --------------------------------------------------------------------------- #
# DS-01/DS-02 round-2 — combining diacritics + fold-table parity              #
# --------------------------------------------------------------------------- #

import importlib.util as _ilu  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_ROOT = _Path(__file__).resolve().parents[2]


def _load(rel: str, name: str):
    spec = _ilu.spec_from_file_location(name, _ROOT / rel)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_EB_NORM = _load("src/ebsvap/_text_normalize.py", "eb_text_normalize")
_CI_NORM = _load("scripts/ci/_text_normalize.py", "ci_text_normalize")


def test_ds02r2_fold_tables_are_byte_identical() -> None:
    # the two independent copies must never diverge (a weaker CI subset let a
    # Greek-tau homoglyph slip past the CI firewall the ebsvap copy caught)
    assert _EB_NORM._CONFUSABLES == _CI_NORM._CONFUSABLES


@pytest.mark.parametrize("norm", [_EB_NORM.normalize_for_matching, _CI_NORM.normalize_for_matching])
def test_ds01r2_combining_diacritic_folds_to_base(norm) -> None:
    # p r o U+0301 v e n  (combining acute over o) must reduce to "proven"
    combining = "próven"
    assert norm(combining) == "proven"


@pytest.mark.parametrize("norm", [_EB_NORM.normalize_for_matching, _CI_NORM.normalize_for_matching])
def test_ds02r2_greek_tau_folds_to_t(norm) -> None:
    assert norm("validaτed") == "validated"


@pytest.mark.parametrize("norm", [_EB_NORM.normalize_for_matching, _CI_NORM.normalize_for_matching])
def test_ds01r2_clean_ascii_unchanged(norm) -> None:
    for w in ("proven", "validated", "improve", "provenance"):
        assert norm(w) == w


def test_ds01r2_combining_proven_claim_rejected() -> None:
    r = compile_claim(Claim("t", "the method is próven", "EMPIRICAL", {"data": [1]}))
    assert r["status"] == "REJECT"
