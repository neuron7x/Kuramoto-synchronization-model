#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""EBSVAP WP3 — proof-carrying action gateway.

A consequential action executes ONLY when its certificate validates against the
EXACT arguments, an unexpired approval bound to (action, destination), a live
authority, and a fresh (non-replayed) nonce. The proposer holds no effector
credential; the effector runs only after the gateway returns AUTHORIZED. DENY
produces no side effect. This makes prompt text non-load-bearing for authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field


def _canonicalize(obj: object) -> object:
    """Type-tagged canonical form of a JSON-native value.

    ``json.dumps(..., default=repr)`` (the previous implementation) let a crafted
    ``__repr__`` collide an opaque object with the string it imitates
    (``args_hash({'x': obj_whose_repr_is_'1'}) == args_hash({'x': '1'})``), and
    ``sort_keys`` coerced an int key ``1`` and a str key ``'1'`` to the same JSON
    text. Tagging every scalar with its type closes both: an object is REJECTED
    (raises) rather than silently coerced, and ``["int", 1]`` never equals
    ``["str", "1"]``. Native JSON values stay stable, so existing hashes hold.
    """
    if isinstance(obj, bool):  # bool before int (bool is a subclass of int)
        return ["bool", obj]
    if obj is None:
        return ["null", None]
    if isinstance(obj, int):
        return ["int", obj]
    if isinstance(obj, float):
        return ["float", repr(obj)]  # repr is round-trip stable and exact
    if isinstance(obj, str):
        return ["str", obj]
    if isinstance(obj, (list, tuple)):
        return ["list", [_canonicalize(x) for x in obj]]
    if isinstance(obj, dict):
        items = [[_canonicalize(k), _canonicalize(v)] for k, v in obj.items()]
        # order by the canonical key so hashing is order-independent, while the
        # key's TYPE (int vs str) remains part of the sorted material
        items.sort(key=lambda kv: json.dumps(kv[0], sort_keys=True))
        return ["dict", items]
    raise TypeError(
        f"args_hash: non-JSON-native value of type {type(obj).__name__!r} is "
        "not admissible (repr-coercion would allow a hash collision)"
    )


def args_hash(args: dict) -> str:
    # Canonical, type-tagged serialization — no repr coercion. Non-JSON-native
    # values raise (the authorize hot path catches this and fails CLOSED to a
    # DENY, never a silent admit).
    return hashlib.sha256(json.dumps(_canonicalize(args), sort_keys=True).encode()).hexdigest()


@dataclass
class ActionCertificate:
    action_id: str
    action: str
    destination: str
    arguments_hash: str
    authority: str  # granted authority token for this action
    approval_class: str  # bound to action+destination
    nonce: str
    expiry: int  # logical clock
    signature: str = ""  # HMAC over the fields above, keyed to the issuer


def _cert_payload(cert: ActionCertificate) -> bytes:
    """Canonical bytes of the certificate's authenticated fields (not the
    signature itself). Any mutation of a bound field changes these bytes and so
    invalidates the HMAC."""
    return json.dumps(
        {
            "action_id": cert.action_id,
            "action": cert.action,
            "destination": cert.destination,
            "arguments_hash": cert.arguments_hash,
            "authority": cert.authority,
            "approval_class": cert.approval_class,
            "nonce": cert.nonce,
            "expiry": cert.expiry,
        },
        sort_keys=True,
    ).encode()


def sign_certificate(secret: str, cert: ActionCertificate) -> str:
    """Return the HMAC-SHA256 signature binding ``cert``'s fields to ``secret``
    (the issuer's key). A caller who does not hold the secret cannot forge it."""
    return hmac.new(secret.encode(), _cert_payload(cert), hashlib.sha256).hexdigest()


def issue_certificate(secret: str, cert: ActionCertificate) -> ActionCertificate:
    """Stamp ``cert`` with a valid issuer signature and return it (in place)."""
    cert.signature = sign_certificate(secret, cert)
    return cert


@dataclass
class Gateway:
    """Proof-carrying action gateway.

    Certificate authenticity (DS-19, fail-closed by default): membership of
    ``cert.authority`` in ``live_authorities`` is a *revocation* check, not proof
    of issuance — anyone who knows a live authority string could otherwise mint a
    fresh certificate (own nonce, own arguments_hash) for any amount. By default
    every certificate MUST carry a valid HMAC ``signature`` from the registered
    issuer (``issuer_keys``: an ``authority -> secret`` registry); a certificate
    whose issuance cannot be cryptographically verified — including the case of an
    EMPTY registry — is DENIED (cannot-verify ⇒ deny, never skip). A caller that
    genuinely needs the legacy membership-only behavior must opt in EXPLICITLY via
    ``Gateway(allow_unsigned=True)`` (documented, audited) — the default no longer
    silently authorizes unsigned certs.

    Replay protection (DS-20) is scoped to the nonce ledger, which by default
    lives on THIS instance. Across processes / restarts / a distributed fleet,
    inject a shared, durable ledger via ``Gateway(nonce_ledger=shared_set)``
    (equivalently ``_used_nonces=shared_set``) — otherwise the same certificate
    can replay once per instance. ``expiry`` is inclusive: a certificate is valid
    through ``clock == expiry`` and denied once the clock advances past it.
    """

    live_authorities: set = field(default_factory=set)  # currently granted authorities
    approvals: set = field(default_factory=set)  # {(action,destination,approval_class)}
    clock: int = 0
    _used_nonces: set = field(default_factory=set)
    # authority -> issuer secret; used to verify each cert's HMAC signature
    issuer_keys: dict = field(default_factory=dict)
    # explicit, audited opt-out of signature enforcement (legacy membership-only).
    # Default False => unsigned/forged/unverifiable certs are DENIED fail-closed.
    allow_unsigned: bool = False
    # explicit injection point for a shared/durable nonce ledger; when provided
    # it becomes the backing store so replay is blocked across Gateway instances
    nonce_ledger: set | None = None

    def __post_init__(self) -> None:
        # Wire an injected shared ledger as the backing store for replay state.
        if self.nonce_ledger is not None:
            self._used_nonces = self.nonce_ledger

    def authorize(
        self, cert: ActionCertificate, action: str, args: dict, destination: str
    ) -> tuple[bool, str]:
        # Fail CLOSED if the incoming args cannot be canonically hashed
        # (non-JSON-native) — never crash the hot path into an availability hole.
        try:
            computed = args_hash(args)
        except TypeError:
            return False, "DENY: arguments not canonically hashable"
        if cert.arguments_hash != computed:
            return False, "DENY: argument mutation (hash mismatch)"
        if cert.action != action or cert.destination != destination:
            return False, "DENY: certificate not bound to this action/destination"
        if cert.authority not in self.live_authorities:
            return False, "DENY: authority not live / revoked"
        # DS-19 (fail-closed): require a valid HMAC signature binding the cert's
        # fields to its issuer. An unverifiable cert — no registered key for the
        # authority (incl. an empty registry) or a bad/missing signature — is
        # DENIED. Only an explicit, audited allow_unsigned=True skips this.
        if not self.allow_unsigned:
            secret = self.issuer_keys.get(cert.authority)
            if secret is None:
                return False, "DENY: no registered issuer key for authority"
            expected = sign_certificate(secret, cert)
            if not hmac.compare_digest(expected, cert.signature or ""):
                return False, "DENY: certificate signature invalid or missing"
        if (cert.action, cert.destination, cert.approval_class) not in self.approvals:
            return False, "DENY: no matching approval for action+destination"
        if cert.expiry < self.clock:
            return False, "DENY: certificate expired"
        if cert.nonce in self._used_nonces:
            return False, "DENY: nonce replay"
        self._used_nonces.add(cert.nonce)
        return True, "AUTHORIZED"


def execute(
    gateway: Gateway,
    cert: ActionCertificate,
    action: str,
    args: dict,
    destination: str,
    world: dict,
) -> dict:
    """Effector: mutates `world` ONLY on AUTHORIZED. Returns a receipt."""
    ok, msg = gateway.authorize(cert, action, args, destination)
    if not ok:
        return {"authorized": False, "reason": msg, "side_effect": False}
    world[destination] = args  # the protected side effect
    return {"authorized": True, "reason": msg, "side_effect": True, "receipt": args_hash(args)}
