# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate F - canonical-run authorisation artifact tests.

Gate F is term 6 of the 7-gate canonical-run authorisation conjunction
(A AND B AND C AND D AND E AND F AND G). PASS of Gate F snapshots the
conjunction A AND B AND C AND D AND E AND F and certifies that prior
gates A-E PASS on main; it does NOT itself authorise canonical run.
Gate G (final CI lock) is the remaining open term and is required for
absolute authorisation.

Scope (declaration + ancestor verification only):
  * 5 prior gate anchors verified via ``git merge-base --is-ancestor``
    against ``origin/main`` (subprocess call inside the tests).
  * D-002C claim ledger byte-exact at the locked pin.
  * D-002H prereg byte-exact at the locked pin.
  * Artifact schema, status, and downstream-gate-vector exact match.

Two inline sha-anchors are kept as Lesson-4 sanity guards: the D-002C
claim ledger and the D-002H prereg. They mirror the prior Gate E
acceptor's pinned anchors and double-lock the two most-quoted
governance files.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_RELPATH = "artifacts/d002h/authorization/d002h_canonical_run_authorisation.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELPATH

SCHEMA_VERSION = "D002H-CANONICAL-RUN-AUTHORISATION-v1"
EXPECTED_DOWNSTREAM_GATES: list[str] = ["G"]
EXPECTED_CONJUNCTION_REQUIRED = "A AND B AND C AND D AND E AND F AND G"
EXPECTED_CONJUNCTION_SATISFIED = "A AND B AND C AND D AND E AND F"
EXPECTED_CONJUNCTION_OPEN = "G"

# Expected (gate, name, anchor_sha) tuples for the 5 prior gates.
EXPECTED_PRIOR_GATES: list[dict[str, str]] = [
    {
        "gate": "A",
        "name": "D-002H prereg lock",
        "anchor_sha": "1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5",
    },
    {
        "gate": "B",
        "name": "ricci_flow M1/M3 eligibility reverification",
        "anchor_sha": "b97daae8b554ab9960510564e19263adcc1fe71b",
    },
    {
        "gate": "C",
        "name": "canonical parameter grid declaration",
        "anchor_sha": "a9d852d34258861809325df81bd7cba6d0e557ec",
    },
    {
        "gate": "D",
        "name": "forbidden-claim scanner",
        "anchor_sha": "077073ee801c434840d64f911e7b1f39ce2ac0fa",
    },
    {
        "gate": "E",
        "name": "locked-ledger verification",
        "anchor_sha": "e1d3ae304274e8b8f509edeb83b0a9adfeb43a77",
    },
]

# Content-addressed governance anchors mirroring the Gate E acceptor.
# ``fmt: off`` keeps the literals on a single line; the inline pragma
# silences detect-secrets HexHighEntropy - these are not credentials,
# they are governance anchors enforcing the byte-exact contract.
# fmt: off
# Live (post-append) disk anchor — see Gate E test for full explanation.
D002C_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# Frozen pre-append anchor: the Gate F artifact JSON records the ledger sha
# at Gate E close, which is the OLD pre-append anchor. The artifact stays
# historical; the live disk has rotated post-PR #692.
D002C_LEDGER_SHA256_PRE_APPEND: str = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"  # noqa: E501  # pragma: allowlist secret  # frozen at Gate E anchor; pre-D-002H-REFUSED-append
D002H_PREREG_SHA256_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
# fmt: on

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"


def _load_payload() -> dict[str, Any]:
    """Load + JSON-parse the Gate F authorisation artifact."""
    msg_missing = f"Gate F artifact missing at {ARTIFACT_RELPATH}"
    assert ARTIFACT_PATH.is_file(), msg_missing
    payload: dict[str, Any] = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    return payload


def _compute_disk_sha(relpath: str) -> str:
    """sha256 of the file at ``REPO_ROOT/relpath``, hex-digest lower-case."""
    path = REPO_ROOT / relpath
    msg_missing = f"file missing on disk: {relpath}"
    assert path.is_file(), msg_missing
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git command in ``REPO_ROOT`` without raising on non-zero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def _ensure_commit_fetched(sha: str) -> None:
    """Best-effort fetch of ``sha`` when the working clone is shallow.

    GitHub Actions ``actions/checkout`` defaults to ``fetch-depth: 1``,
    which makes historical commits (e.g. Gate A..E anchor merges) unknown
    locally. We detect this via ``git rev-parse --is-shallow-repository``
    and, if shallow, ask the origin to fetch the missing commit. The
    fetch is bounded and idempotent; failure is silent here and surfaces
    as the explicit shallow-clone diagnostic in :func:`_is_ancestor_of_main`.
    """
    if _git(["cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0:
        return
    if _git(["rev-parse", "--is-shallow-repository"]).stdout.strip() != "true":
        return
    # Try a targeted fetch first (cheap, works on GHA/Pro), then fall back
    # to --unshallow (heavier, but guarantees full history).
    if _git(["fetch", "--depth=1", "origin", sha]).returncode == 0:
        return
    _git(["fetch", "--unshallow", "origin"])


def _is_ancestor_of_main(sha: str) -> bool:
    """Return True iff ``sha`` is an ancestor of ``origin/main``.

    Uses ``git merge-base --is-ancestor`` (exit 0 = ancestor, 1 = not).
    Any other exit code is treated as an environment failure (most commonly
    a shallow clone that doesn't carry the historical anchor commit) and
    raised with an actionable message pointing at the workflow's
    ``actions/checkout`` ``fetch-depth`` setting.
    """
    _ensure_commit_fetched(sha)
    result = _git(["merge-base", "--is-ancestor", sha, "origin/main"])
    if result.returncode in (0, 1):
        return result.returncode == 0
    is_shallow = _git(["rev-parse", "--is-shallow-repository"]).stdout.strip() == "true"
    msg = (
        f"git merge-base --is-ancestor returned unexpected code "
        f"{result.returncode} for {sha!r}: stderr={result.stderr!r}. "
        f"shallow_clone={is_shallow}. If shallow=True, the calling "
        f"workflow's actions/checkout step needs `fetch-depth: 0` "
        f"(historical D-002H gate anchor commits are not present in "
        f"depth=1 clones). See .github/workflows/main-validation.yml "
        f"python-full-validation job for the canonical setting."
    )
    raise AssertionError(msg)


# ---------------------------------------------------------------------------
# 10 contract tests (names exact per the Gate F brief).
# ---------------------------------------------------------------------------


def test_gate_f_artifact_exists() -> None:
    """The Gate F authorisation JSON is on disk and carries the locked schema.

    Two-assertion test (Lesson 4): file presence AND schema literal.
    """
    assert ARTIFACT_PATH.is_file(), f"Gate F artifact missing at {ARTIFACT_RELPATH}"
    payload = _load_payload()
    msg_schema = (
        f"schema_version drift: got {payload['schema_version']!r}, expected {SCHEMA_VERSION!r}"
    )
    assert payload["schema_version"] == SCHEMA_VERSION, msg_schema
    assert payload["study_id"] == "D-002H"
    assert payload["gate"] == "F"


def test_gate_f_schema_version() -> None:
    """schema_version is exactly ``D002H-CANONICAL-RUN-AUTHORISATION-v1``.

    Two-assertion test (Lesson 4): literal match AND non-empty.
    """
    payload = _load_payload()
    schema = payload["schema_version"]
    msg_schema = f"schema_version drift: got {schema!r}, expected {SCHEMA_VERSION!r}"
    assert schema == SCHEMA_VERSION, msg_schema
    msg_nonempty = f"schema_version must be a non-empty string, got {schema!r}"
    is_nonempty_str = isinstance(schema, str) and len(schema) > 0
    assert is_nonempty_str, msg_nonempty


def test_gate_f_status_authorised() -> None:
    """status == 'AUTHORISED' and canonical_run_authorized_at_gate_f is True.

    Two-assertion test (Lesson 4 C3): status literal AND intermediate
    boolean True.
    """
    payload = _load_payload()
    msg_status = f"status drift: got {payload['status']!r}, expected 'AUTHORISED'"
    assert payload["status"] == "AUTHORISED", msg_status
    msg_inter = (
        f"canonical_run_authorized_at_gate_f drift: got "
        f"{payload['canonical_run_authorized_at_gate_f']!r}, expected True"
    )
    assert payload["canonical_run_authorized_at_gate_f"] is True, msg_inter


def test_gate_f_canonical_run_authorized_final_is_false() -> None:
    """canonical_run_authorized_final is False (Gate G still required).

    Two-assertion test (Lesson 4): the final-authorisation boolean is
    explicitly False AND the final_authorisation_pending_gate is 'G'.
    """
    payload = _load_payload()
    final = payload["canonical_run_authorized_final"]
    msg_final = (
        f"canonical_run_authorized_final drift: got {final!r}, "
        "expected False (Gate G still required for absolute authorisation)"
    )
    assert final is False, msg_final
    pending = payload["final_authorisation_pending_gate"]
    msg_pending = f"final_authorisation_pending_gate drift: got {pending!r}, expected 'G'"
    assert pending == "G", msg_pending


def test_gate_f_prior_gate_chain_has_5_entries() -> None:
    """prior_gate_chain has exactly 5 entries (Gates A, B, C, D, E).

    Two-assertion test (Lesson 4 C3): list length AND ordered gate
    labels.
    """
    payload = _load_payload()
    chain = payload["prior_gate_chain"]
    msg_len = f"prior_gate_chain length drift: got {len(chain)}, expected 5"
    assert len(chain) == 5, msg_len
    actual_gates = [entry["gate"] for entry in chain]
    expected_gates = ["A", "B", "C", "D", "E"]
    msg_order = (
        f"prior_gate_chain gate-order drift: got {actual_gates!r}, expected {expected_gates!r}"
    )
    assert actual_gates == expected_gates, msg_order


def test_gate_f_all_5_anchors_pinned_correctly() -> None:
    """All 5 prior-gate anchors carry the expected (gate, name, anchor_sha, verdict='PASS').

    Multi-assertion test (Lesson 4 C3): one comparison per gate against
    EXPECTED_PRIOR_GATES, plus a final verdict-set assertion.
    """
    payload = _load_payload()
    chain = payload["prior_gate_chain"]
    drifts: list[tuple[str, dict[str, Any], dict[str, str]]] = []
    for actual, expected in zip(chain, EXPECTED_PRIOR_GATES, strict=True):
        if (
            actual["gate"] != expected["gate"]
            or actual["name"] != expected["name"]
            or actual["anchor_sha"] != expected["anchor_sha"]
        ):
            drifts.append((expected["gate"], actual, expected))
    msg_drift = (
        f"prior_gate_chain anchor drift for {len(drifts)} entries: {drifts!r}; "
        "expected all 5 gates pinned at the brief-specified shas + names."
    )
    assert drifts == [], msg_drift
    verdicts = {entry["verdict"] for entry in chain}
    msg_verdicts = f"prior_gate_chain verdicts drift: got {verdicts!r}, expected {{'PASS'}}"
    assert verdicts == {"PASS"}, msg_verdicts


def test_gate_f_all_5_anchors_are_ancestors_of_main() -> None:
    """Every prior-gate anchor SHA is an ancestor of ``origin/main``.

    Multi-assertion test (Lesson 4 C3): one ancestry check per gate +
    a final non-empty-checked sentinel.
    """
    payload = _load_payload()
    chain = payload["prior_gate_chain"]
    non_ancestors: list[tuple[str, str]] = []
    for entry in chain:
        sha = entry["anchor_sha"]
        if not _is_ancestor_of_main(sha):
            non_ancestors.append((entry["gate"], sha))
    msg = (
        f"Gate F ancestry contract violated for {len(non_ancestors)} prior-gate "
        f"anchors: {non_ancestors!r}; expected every anchor to be an ancestor "
        "of origin/main."
    )
    assert non_ancestors == [], msg
    assert len(chain) == 5, f"unexpected chain length {len(chain)} (expected 5)"


def test_gate_f_final_authorisation_pending_gate_g() -> None:
    """final_authorisation_pending_gate == 'G' and conjunction_still_open == 'G'.

    Two-assertion test (Lesson 4 C3): both fields point at Gate G as
    the single remaining open term.
    """
    payload = _load_payload()
    pending = payload["final_authorisation_pending_gate"]
    msg_pending = f"final_authorisation_pending_gate drift: got {pending!r}, expected 'G'"
    assert pending == "G", msg_pending
    still_open = payload["conjunction_still_open"]
    msg_open = (
        f"conjunction_still_open drift: got {still_open!r}, expected {EXPECTED_CONJUNCTION_OPEN!r}"
    )
    assert still_open == EXPECTED_CONJUNCTION_OPEN, msg_open


def test_gate_f_downstream_gates_remaining_is_g_only() -> None:
    """downstream_gates_remaining is exactly ['G'] - only Gate G remains.

    Two-assertion test (Lesson 4 C3): list-literal exact match AND
    length == 1.
    """
    payload = _load_payload()
    remaining = payload["downstream_gates_remaining"]
    msg_remaining = (
        f"downstream_gates_remaining drift: got {remaining!r}, "
        f"expected {EXPECTED_DOWNSTREAM_GATES!r}"
    )
    assert remaining == EXPECTED_DOWNSTREAM_GATES, msg_remaining
    msg_len = f"downstream_gates_remaining length drift: got {len(remaining)}, expected 1"
    assert len(remaining) == 1, msg_len


def test_gate_f_preserves_d002c_ledger() -> None:
    """D-002C claim ledger split-anchor check after PR #692 REFUSED append.

    Three assertions (Lesson 4 C3): Gate F artifact carries the
    pre-append Gate E anchor (frozen historical record), disk bytes
    match the post-append live anchor, and the artifact pin is the
    frozen pre-append sha (NOT equal to live disk — the legitimate
    append rotated the live sha while the historical record stays).
    """
    payload = _load_payload()
    pinned_in_artifact = payload["d002c_ledger_byte_exact_at_gate_e"]
    msg_artifact = (
        f"D-002C ledger pin in Gate F artifact drift: got "
        f"{pinned_in_artifact!r}, expected pre-append anchor "
        f"{D002C_LEDGER_SHA256_PRE_APPEND!r} (frozen Gate E historical record)"
    )
    assert pinned_in_artifact == D002C_LEDGER_SHA256_PRE_APPEND, msg_artifact
    actual_disk = _compute_disk_sha(D002C_LEDGER_RELPATH)
    msg_disk = (
        f"D-002C ledger disk sha drift: expected post-append anchor "
        f"{D002C_LEDGER_SHA256_PIN!r} (live, after PR #692 append), "
        f"got {actual_disk!r}"
    )
    assert actual_disk == D002C_LEDGER_SHA256_PIN, msg_disk
    msg_split = (
        f"D-002C ledger split-anchor invariant: artifact pin "
        f"{pinned_in_artifact!r} (pre-append) MUST differ from live disk "
        f"sha {actual_disk!r} (post-append); the legitimate D-002H REFUSED "
        "append rotates the live sha while the historical record stays."
    )
    assert pinned_in_artifact != actual_disk, msg_split


# ---------------------------------------------------------------------------
# Parametrised drift checks (Lesson 4: >= 2 cases).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expected",
    EXPECTED_PRIOR_GATES,
    ids=lambda entry: f"gate_{entry['gate']}",
)
def test_gate_f_each_anchor_is_ancestor_of_main(expected: dict[str, str]) -> None:
    """Parametrised over all 5 prior gates: each anchor is an ancestor of main.

    Two-assertion test (Lesson 4 C3): the SHA looks like a 40-hex git
    object id AND the git merge-base --is-ancestor probe returns 0.
    Five parametrised cases (>=2 cases).
    """
    sha = expected["anchor_sha"]
    msg_format = f"anchor_sha for gate {expected['gate']} is not a 40-hex git sha: {sha!r}"
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha), msg_format
    msg_ancestor = (
        f"gate {expected['gate']} anchor {sha!r} is NOT an ancestor of "
        "origin/main; Gate F authorisation invalid"
    )
    assert _is_ancestor_of_main(sha), msg_ancestor


def test_gate_f_d002h_prereg_pin_present() -> None:
    """The artifact records D-002H prereg sha and it matches the locked pin on disk.

    Three-assertion sentinel (Lesson 4 C3): artifact field present,
    value matches inline anchor, disk bytes match inline anchor.
    """
    payload = _load_payload()
    pinned = payload["d002h_prereg_byte_exact"]
    msg_field = (
        f"d002h_prereg_byte_exact drift: got {pinned!r}, expected {D002H_PREREG_SHA256_PIN!r}"
    )
    assert pinned == D002H_PREREG_SHA256_PIN, msg_field
    actual_disk = _compute_disk_sha(D002H_PREREG_RELPATH)
    msg_disk = (
        f"D-002H prereg MUTATED on disk: expected {D002H_PREREG_SHA256_PIN!r}, "
        f"got {actual_disk!r}; Gate F is forbidden from editing the locked prereg"
    )
    assert actual_disk == D002H_PREREG_SHA256_PIN, msg_disk
    assert pinned == actual_disk, (
        f"D-002H prereg transitive consistency violated: artifact pin "
        f"{pinned!r} != disk sha {actual_disk!r}"
    )


def test_gate_f_conjunction_strings_locked() -> None:
    """The three conjunction strings carry exact literals.

    Three-assertion test (Lesson 4 C3): required, satisfied-at-F, still-open.
    """
    payload = _load_payload()
    req = payload["conjunction_required"]
    msg_req = f"conjunction_required drift: got {req!r}, expected {EXPECTED_CONJUNCTION_REQUIRED!r}"
    assert req == EXPECTED_CONJUNCTION_REQUIRED, msg_req
    sat = payload["conjunction_satisfied_at_gate_f"]
    msg_sat = (
        f"conjunction_satisfied_at_gate_f drift: got {sat!r}, expected "
        f"{EXPECTED_CONJUNCTION_SATISFIED!r}"
    )
    assert sat == EXPECTED_CONJUNCTION_SATISFIED, msg_sat
    still = payload["conjunction_still_open"]
    msg_still = (
        f"conjunction_still_open drift: got {still!r}, expected {EXPECTED_CONJUNCTION_OPEN!r}"
    )
    assert still == EXPECTED_CONJUNCTION_OPEN, msg_still
