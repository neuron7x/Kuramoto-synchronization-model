#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""EBSVAP WP3 falsification set — no protected side effect without a valid cert."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
s = importlib.util.spec_from_file_location("gw", REPO / "src/ebsvap/authority_gateway.py")
gw = importlib.util.module_from_spec(s)
sys.modules["gw"] = gw
s.loader.exec_module(gw)


# Issuer secret held by the trusted proposer; NOT the public authority string.
# Forging a cert now requires this secret, not merely knowledge of "AUTH_PUBLISH".
ISSUER_SECRET = "wp3-issuer-secret-AUTH_PUBLISH"


def fresh():
    # Signature enforcement is fail-closed by default: provision the issuer key
    # and SIGN the legitimate certificate so the valid path authorizes.
    g = gw.Gateway(issuer_keys={"AUTH_PUBLISH": ISSUER_SECRET})
    g.live_authorities.add("AUTH_PUBLISH")
    g.approvals.add(("publish", "remote", "human_ok"))
    g.clock = 5
    args = {"payload": "x"}
    cert = gw.ActionCertificate(
        "a1",
        "publish",
        "remote",
        gw.args_hash(args),
        "AUTH_PUBLISH",
        "human_ok",
        nonce="n1",
        expiry=10,
    )
    gw.issue_certificate(ISSUER_SECRET, cert)  # stamp a valid issuer signature
    return g, cert, args


cases = []
# valid path
g, c, a = fresh()
w = {}
r = gw.execute(g, c, "publish", a, "remote", w)
cases.append(("valid_authorized", r["authorized"] and w == {"remote": a}))
# replay
g, c, a = fresh()
w = {}
gw.execute(g, c, "publish", a, "remote", w)
r2 = gw.execute(g, c, "publish", a, "remote", w)  # reuse nonce
cases.append(("replay_denied", (not r2["authorized"]) and "replay" in r2["reason"]))
# argument mutation after approval
g, c, a = fresh()
w = {}
r = gw.execute(g, c, "publish", {"payload": "TAMPERED"}, "remote", w)
cases.append(("arg_mutation_denied", (not r["authorized"]) and not r["side_effect"] and w == {}))
# approval copied to another destination
g, c, a = fresh()
w = {}
r = gw.execute(g, c, "publish", a, "OTHER_DEST", w)
cases.append(("wrong_destination_denied", (not r["authorized"]) and w == {}))
# expired
g, c, a = fresh()
g.clock = 99
w = {}
r = gw.execute(g, c, "publish", a, "remote", w)
cases.append(("expired_denied", (not r["authorized"]) and w == {}))
# revoked authority
g, c, a = fresh()
g.live_authorities.clear()
w = {}
r = gw.execute(g, c, "publish", a, "remote", w)
cases.append(("revoked_authority_denied", (not r["authorized"]) and w == {}))
# DS-19 shipped-config forgery: attacker knows the live authority string and
# mints their OWN cert for the exact args, but cannot produce a valid issuer
# signature -> DENIED, no side effect.
g, c, a = fresh()
forged = gw.ActionCertificate(
    "a1",
    "publish",
    "remote",
    gw.args_hash(a),
    "AUTH_PUBLISH",
    "human_ok",
    nonce="forged-nonce",
    expiry=10,
)  # no / attacker-chosen signature
w = {}
r = gw.execute(g, forged, "publish", a, "remote", w)
cases.append(
    (
        "forged_unsigned_cert_denied",
        (not r["authorized"]) and w == {} and "signature" in r["reason"],
    )
)
# deny path has NO side effect (checked in each above: w == {})
deny_no_side = all(ok for name, ok in cases if name.endswith("_denied"))

allpass = all(ok for _, ok in cases)
out = {
    "task": "WP3 proof-carrying action gateway",
    "cases": {n: ok for n, ok in cases},
    "certificate_bypass_rate": 0.0 if allpass else 1.0,
    "deny_side_effect_rate": 0.0 if deny_no_side else 1.0,
    "verdict": "ACTION_CERTIFICATE_PASS" if allpass else "ACTION_CERTIFICATE_FAIL",
}
(REPO / "artifacts/ebsvap/WP3_RESULTS.json").write_text(json.dumps(out, indent=2) + "\n")
for n, ok in cases:
    print(f"  {n}: {'OK' if ok else 'FAIL'}")
print("VERDICT:", out["verdict"])
sys.exit(0 if allpass else 1)
