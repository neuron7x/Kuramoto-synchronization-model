# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate E - locked-ledger byte-exact verification tests.

These tests assert that the 16 files pinned in
``artifacts/d002h/locks/d002h_locked_file_pins.json`` carry, on the
current working tree, the same sha256 they had at the Gate D merge
anchor (``077073ee801c434840d64f911e7b1f39ce2ac0fa``). Any byte-level
drift in any of the 16 files fails Gate E.

Gate E is term 5 of the 7-gate canonical-run authorisation conjunction
(A AND B AND C AND D AND E AND F AND G). PASS of Gate E alone does NOT
authorise canonical run; the conjunction is the contract. Gates F and
G remain open.

Scope (read-only verification):
  * 4 D-002C governance anchors (ledger + prereg + canonical-run report
    + null-audit falsification report).
  * 6 D-002G governance anchors (prereg + non-degenerate null design +
    acceptance rules + P3/M3 prereg + structural closure + negative
    space map).
  * 4 D-002H governance anchors (prereg + scope rationale + claim
    boundary + canonical-run authorisation gates doc).
  * 2 source-code modules (D-002C substrates + D-002G null mechanisms).

The shas live in the JSON artifact only (not duplicated inline in the
test file). Two inline sha-anchors are kept as Lesson-4 sanity guards:
the D-002C claim ledger and the D-002H prereg. They mirror the prior
Gate D acceptor's pinned anchors and double-lock the two most-quoted
governance files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_RELPATH = "artifacts/d002h/locks/d002h_locked_file_pins.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELPATH

SCHEMA_VERSION = "D002H-GATE-E-v1"
ANCHOR_MAIN_SHA = "077073ee801c434840d64f911e7b1f39ce2ac0fa"
EXPECTED_N_PINNED = 16
EXPECTED_DOWNSTREAM_GATES = ["F", "G"]

# Content-addressed governance anchors mirroring the Gate D acceptor.
# ``fmt: off`` keeps the literals on a single line; the inline pragma
# silences detect-secrets HexHighEntropy - these are not credentials,
# they are governance anchors enforcing the Gate D byte-exact contract.
# fmt: off
# Live (post-append) disk anchor: this is the sha256 of the on-disk ledger
# after the legitimate D-002H REFUSED entry append in PR #692.
D002C_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# Frozen pre-append historical anchor: this is the sha256 the ledger had
# at the Gate E merge anchor (077073ee). The Gate E artifact JSON is a
# historical record and preserves this sha — it must NOT be mutated.
D002C_LEDGER_SHA256_PRE_APPEND: str = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"  # noqa: E501  # pragma: allowlist secret  # frozen at Gate E anchor; pre-D-002H-REFUSED-append
D002H_PREREG_SHA256_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
# fmt: on

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
D002C_SUBSTRATES_RELPATH = "research/systemic_risk/d002c_substrates.py"
D002G_MECHANISMS_RELPATH = "research/systemic_risk/d002g_null_mechanisms.py"


def _load_payload() -> dict[str, Any]:
    """Load + JSON-parse the Gate E pins artifact."""
    msg_missing = f"Gate E artifact missing at {ARTIFACT_RELPATH}"
    assert ARTIFACT_PATH.is_file(), msg_missing
    payload: dict[str, Any] = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    return payload


def _compute_disk_sha(relpath: str) -> str:
    """sha256 of the file at ``REPO_ROOT/relpath``, hex-digest lower-case."""
    path = REPO_ROOT / relpath
    msg_missing = f"pinned file missing on disk: {relpath}"
    assert path.is_file(), msg_missing
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 10 contract tests (names exact per the Gate E brief).
# ---------------------------------------------------------------------------


def test_gate_e_artifact_exists() -> None:
    """The Gate E pins JSON is on disk and carries schema 'D002H-GATE-E-v1'.

    Two-assertion test (Lesson 4): file presence AND schema literal.
    """
    assert ARTIFACT_PATH.is_file(), f"Gate E artifact missing at {ARTIFACT_RELPATH}"
    payload = _load_payload()
    msg_schema = (
        f"schema_version drift: got {payload['schema_version']!r}, expected {SCHEMA_VERSION!r}"
    )
    assert payload["schema_version"] == SCHEMA_VERSION, msg_schema
    assert payload["study_id"] == "D-002H"
    assert payload["gate"] == "E"


def test_gate_e_pinned_count_is_16() -> None:
    """Exactly 16 files are pinned; n_pinned_files counter matches list len.

    Two-assertion test (Lesson 4 C3): counter consistency AND list len.
    """
    payload = _load_payload()
    pinned = payload["pinned_files"]
    msg_count = f"n_pinned_files counter drift: got {payload['n_pinned_files']!r}, expected {EXPECTED_N_PINNED!r}"
    assert payload["n_pinned_files"] == EXPECTED_N_PINNED, msg_count
    msg_list = f"pinned_files list drift: got len {len(pinned)}, expected {EXPECTED_N_PINNED}"
    assert len(pinned) == EXPECTED_N_PINNED, msg_list
    msg_consistency = (
        f"n_pinned_files counter / list-len mismatch: "
        f"counter={payload['n_pinned_files']!r}, list-len={len(pinned)!r}"
    )
    assert payload["n_pinned_files"] == len(pinned), msg_consistency


def test_gate_e_all_pinned_shas_byte_exact() -> None:
    """Core invariant: every pinned sha256 matches the on-disk sha256.

    This is the Gate E byte-exact preservation contract. Each pinned
    file's sha256 is recomputed from disk bytes and compared to the
    pinned value. Any drift in any file fails Gate E for the full PR.

    Exception: the D-002C claim ledger entry. The Gate E artifact
    records the pre-append historical sha at gate close; the live disk
    sha has rotated post-PR #692 (legitimate D-002H REFUSED append,
    acceptor-authorised). For this single entry we assert (1) the
    artifact pin equals the pre-append anchor (historical record
    correct) and (2) the disk sha equals the post-append anchor (live
    state correct).
    """
    payload = _load_payload()
    pinned = payload["pinned_files"]
    drifts: list[tuple[str, str, str]] = []
    for entry in pinned:
        relpath = entry["path"]
        expected = entry["sha256"]
        actual = _compute_disk_sha(relpath)
        if relpath == D002C_LEDGER_RELPATH:
            # Split-anchor check: artifact pin frozen at pre-append sha,
            # disk sha rotated to post-append sha by PR #692.
            if expected != D002C_LEDGER_SHA256_PRE_APPEND:
                drifts.append((relpath, D002C_LEDGER_SHA256_PRE_APPEND, expected))
            if actual != D002C_LEDGER_SHA256_PIN:
                drifts.append((relpath, D002C_LEDGER_SHA256_PIN, actual))
            continue
        if actual != expected:
            drifts.append((relpath, expected, actual))
    msg = (
        f"Gate E byte-exact contract violated for {len(drifts)} files: "
        f"{drifts!r}; expected all 16 pinned shas to match disk "
        "(D-002C ledger entry: artifact==pre-append anchor, disk==post-append anchor)."
    )
    assert drifts == [], msg
    # Two-assertion sentinel (Lesson 4): pinned set was non-empty AND
    # all matched. An empty pinned list would silently pass without
    # this sentinel.
    assert len(pinned) == EXPECTED_N_PINNED


def test_gate_e_d002c_ledger_pinned() -> None:
    """Specific guard: D-002C claim ledger is pinned in the Gate E artifact
    at the pre-append historical anchor, and on disk at the post-append
    live anchor (rotated by PR #692, the D-002H REFUSED ledger append).

    Three assertions (Lesson 4 C3): presence in pin set, artifact pin
    equals pre-append anchor (frozen Gate E historical record), disk
    bytes equal post-append anchor (live state).
    """
    payload = _load_payload()
    entry = next(
        (item for item in payload["pinned_files"] if item["path"] == D002C_LEDGER_RELPATH),
        None,
    )
    msg_present = f"D-002C ledger missing from pin set: {D002C_LEDGER_RELPATH}"
    assert entry is not None, msg_present
    msg_pin = (
        f"D-002C ledger artifact pin drift: got {entry['sha256']!r}, "
        f"expected pre-append anchor {D002C_LEDGER_SHA256_PRE_APPEND!r} "
        "(Gate E artifact is a frozen historical record)"
    )
    assert entry["sha256"] == D002C_LEDGER_SHA256_PRE_APPEND, msg_pin
    actual = _compute_disk_sha(D002C_LEDGER_RELPATH)
    msg_disk = (
        f"D-002C ledger disk sha drift: expected post-append anchor "
        f"{D002C_LEDGER_SHA256_PIN!r} (live, after PR #692 append), got {actual!r}"
    )
    assert actual == D002C_LEDGER_SHA256_PIN, msg_disk


def test_gate_e_d002h_prereg_pinned() -> None:
    """Specific guard: D-002H prereg is pinned AND byte-exact AND not mutated.

    Three assertions (Lesson 4 C3): presence, pinned sha, disk sha.
    """
    payload = _load_payload()
    entry = next(
        (item for item in payload["pinned_files"] if item["path"] == D002H_PREREG_RELPATH),
        None,
    )
    msg_present = f"D-002H prereg missing from pin set: {D002H_PREREG_RELPATH}"
    assert entry is not None, msg_present
    msg_pin = (
        f"D-002H prereg pinned sha drift: got {entry['sha256']!r}, "
        f"expected {D002H_PREREG_SHA256_PIN!r}"
    )
    assert entry["sha256"] == D002H_PREREG_SHA256_PIN, msg_pin
    actual = _compute_disk_sha(D002H_PREREG_RELPATH)
    msg_disk = (
        f"D-002H prereg MUTATED on disk: expected {D002H_PREREG_SHA256_PIN!r}, got {actual!r}; "
        "Gate E is forbidden from editing the locked prereg"
    )
    assert actual == D002H_PREREG_SHA256_PIN, msg_disk


def test_gate_e_substrate_code_pinned() -> None:
    """D-002C substrates module is pinned AND byte-exact AND categorised as source_code.

    Three assertions (Lesson 4 C3): presence, category label, disk-sha
    byte-exact equality.
    """
    payload = _load_payload()
    entry = next(
        (item for item in payload["pinned_files"] if item["path"] == D002C_SUBSTRATES_RELPATH),
        None,
    )
    msg_present = f"D-002C substrates module missing from pin set: {D002C_SUBSTRATES_RELPATH}"
    assert entry is not None, msg_present
    msg_cat = f"D-002C substrates category drift: got {entry['category']!r}, expected 'source_code'"
    assert entry["category"] == "source_code", msg_cat
    actual = _compute_disk_sha(D002C_SUBSTRATES_RELPATH)
    msg_disk = (
        f"D-002C substrates MUTATED on disk: expected {entry['sha256']!r}, got {actual!r}; "
        "substrate code is locked under the Gate D / Gate E contract"
    )
    assert actual == entry["sha256"], msg_disk


def test_gate_e_mechanism_code_pinned() -> None:
    """D-002G null-mechanisms module is pinned AND byte-exact AND categorised as source_code.

    Three assertions (Lesson 4 C3): presence, category label, disk-sha
    byte-exact equality.
    """
    payload = _load_payload()
    entry = next(
        (item for item in payload["pinned_files"] if item["path"] == D002G_MECHANISMS_RELPATH),
        None,
    )
    msg_present = f"D-002G mechanisms module missing from pin set: {D002G_MECHANISMS_RELPATH}"
    assert entry is not None, msg_present
    msg_cat = f"D-002G mechanisms category drift: got {entry['category']!r}, expected 'source_code'"
    assert entry["category"] == "source_code", msg_cat
    actual = _compute_disk_sha(D002G_MECHANISMS_RELPATH)
    msg_disk = (
        f"D-002G mechanisms MUTATED on disk: expected {entry['sha256']!r}, got {actual!r}; "
        "null-mechanism code is locked under the Gate D / Gate E contract"
    )
    assert actual == entry["sha256"], msg_disk


def _load_pinned_entries() -> list[dict[str, Any]]:
    """Return the pinned_files list once for parametrised drift checks."""
    payload = _load_payload()
    pinned = payload["pinned_files"]
    assert isinstance(pinned, list)
    return pinned


@pytest.mark.parametrize(
    "entry",
    _load_pinned_entries(),
    ids=lambda entry: entry["path"],
)
def test_gate_e_no_drift_in_any_pin(entry: dict[str, Any]) -> None:
    """Parametrised over all 16 pins: each disk-sha matches the pinned-sha exactly.

    Two-assertion test (Lesson 4 C3): file presence on disk AND
    byte-exact sha equality. Parametrisation gives 16 distinct test
    cases (>= 2 cases) by file path.

    Exception: D-002C claim ledger. The Gate E artifact's pin is frozen
    at the pre-append historical anchor; the live disk sha has rotated
    to the post-append anchor (PR #692 legitimate REFUSED append). The
    assertion is split: artifact pin == pre-append, disk sha == post-
    append.
    """
    relpath = entry["path"]
    expected = entry["sha256"]
    path = REPO_ROOT / relpath
    msg_present = f"pinned file missing on disk: {relpath}"
    assert path.is_file(), msg_present
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if relpath == D002C_LEDGER_RELPATH:
        msg_artifact = (
            f"Gate E artifact pin drift for {relpath}: artifact={expected!r}, "
            f"expected pre-append anchor {D002C_LEDGER_SHA256_PRE_APPEND!r}"
        )
        assert expected == D002C_LEDGER_SHA256_PRE_APPEND, msg_artifact
        msg_disk = (
            f"Gate E disk sha drift for {relpath}: disk={actual!r}, "
            f"expected post-append anchor {D002C_LEDGER_SHA256_PIN!r} (PR #692 append)"
        )
        assert actual == D002C_LEDGER_SHA256_PIN, msg_disk
        return
    msg_drift = f"Gate E byte-exact drift for {relpath}: expected {expected!r}, got {actual!r}"
    assert actual == expected, msg_drift


def test_gate_e_prior_gate_anchors_recorded() -> None:
    """prior_gate_anchors block records Gates A, B, C, D and the Gate D sha matches anchor_main_sha.

    Lesson 4 C3 multi-assertion: 4 anchor keys present AND Gate D anchor
    matches the top-level anchor_main_sha (since Gate E branches off
    the Gate D merge).
    """
    payload = _load_payload()
    anchors = payload["prior_gate_anchors"]
    expected_keys = {"gate_a", "gate_b", "gate_c", "gate_d"}
    msg_keys = (
        f"prior_gate_anchors keys drift: got {sorted(anchors.keys())!r}, "
        f"expected {sorted(expected_keys)!r}"
    )
    assert set(anchors.keys()) == expected_keys, msg_keys
    msg_top = (
        f"anchor_main_sha drift: got {payload['anchor_main_sha']!r}, expected {ANCHOR_MAIN_SHA!r}"
    )
    assert payload["anchor_main_sha"] == ANCHOR_MAIN_SHA, msg_top
    msg_d = (
        f"gate_d anchor mismatch: got {anchors['gate_d']!r}, "
        f"expected {ANCHOR_MAIN_SHA!r} (Gate E branches off Gate D merge)"
    )
    assert anchors["gate_d"] == ANCHOR_MAIN_SHA, msg_d


def test_gate_e_gate_e_verdict_is_pass() -> None:
    """Verdict is PASS, canonical_run_authorized is False, downstream gates ['F','G'].

    Three assertions (Lesson 4 C3): verdict literal, authorisation
    boolean, downstream-gate-vector exact match.
    """
    payload = _load_payload()
    msg_verdict = f"gate_e_verdict drift: got {payload['gate_e_verdict']!r}, expected 'PASS'"
    assert payload["gate_e_verdict"] == "PASS", msg_verdict
    msg_auth = (
        f"canonical_run_authorized drift: got {payload['canonical_run_authorized']!r}, "
        "expected False (Gate E PASS does NOT authorise canonical run)"
    )
    assert payload["canonical_run_authorized"] is False, msg_auth
    msg_remaining = (
        f"downstream_gates_remaining drift: got {payload['downstream_gates_remaining']!r}, "
        f"expected {EXPECTED_DOWNSTREAM_GATES!r}"
    )
    assert payload["downstream_gates_remaining"] == EXPECTED_DOWNSTREAM_GATES, msg_remaining
