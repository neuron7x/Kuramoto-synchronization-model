# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate G - final CI lock terminal authorisation artifact tests.

Gate G is term 7 (TERMINAL) of the 7-gate canonical-run authorisation
conjunction A AND B AND C AND D AND E AND F AND G. PASS of Gate G
emits the TERMINAL state CANONICAL_RUN_AUTHORIZED with
``canonical_run_authorized_final = True``. Gate G is the
AUTHORISATION terminal - it does NOT itself execute the D-002H
canonical sweep. The sweep itself is a SEPARATE downstream PR that
produces the scientific R1/R2/R3/R2-B/NULL_AUDIT verdict.

Scope (verification only):
  * 6 prior gate anchors A..F have ``ci_verdict='ALL_REQUIRED_PASS'``
    in the lock artifact (Phase 0 GitHub Actions check-runs query was
    performed at PR creation; this test verifies the recorded verdicts
    do not drift).
  * Each anchor is verified an ancestor of ``origin/main`` via
    ``git merge-base --is-ancestor`` (subprocess).
  * D-002C claim ledger byte-exact at the locked pin.
  * D-002H prereg byte-exact at the locked pin.
  * No ``artifacts/d002h/canonical/results/`` directory exists - Gate G
    does NOT run the sweep.

Two inline sha-anchors are kept as Lesson-4 sanity guards: the D-002C
claim ledger and the D-002H prereg. They mirror the prior Gate F
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
ARTIFACT_RELPATH = "artifacts/d002h/authorization/d002h_canonical_run_final_lock.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELPATH

SCHEMA_VERSION = "D002H-GATE-G-v1"
EXPECTED_STATUS = "CANONICAL_RUN_AUTHORIZED"
EXPECTED_SCOPE = "ricci_flow substrate only (per D-002H prereg substrate_scope)"
EXPECTED_CONJUNCTION_REQUIRED = "A AND B AND C AND D AND E AND F AND G"
EXPECTED_CONJUNCTION_SATISFIED = "A AND B AND C AND D AND E AND F AND G"
EXPECTED_EXECUTION_STATUS = "NOT_STARTED"

# Expected (gate, pr, anchor_sha) tuples for the 6 prior gates A..F.
EXPECTED_PRIOR_GATES: list[dict[str, Any]] = [
    {
        "gate": "A",
        "pr": 683,
        "anchor_sha": "1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5",
    },
    {
        "gate": "B",
        "pr": 684,
        "anchor_sha": "b97daae8b554ab9960510564e19263adcc1fe71b",
    },
    {
        "gate": "C",
        "pr": 685,
        "anchor_sha": "a9d852d34258861809325df81bd7cba6d0e557ec",
    },
    {
        "gate": "D",
        "pr": 686,
        "anchor_sha": "077073ee801c434840d64f911e7b1f39ce2ac0fa",
    },
    {
        "gate": "E",
        "pr": 687,
        "anchor_sha": "e1d3ae304274e8b8f509edeb83b0a9adfeb43a77",
    },
    {
        "gate": "F",
        "pr": 688,
        "anchor_sha": "0e598fff84308356fd93e953d4fdde0b7811ac53",
    },
]

# Content-addressed governance anchors mirroring the Gate F acceptor.
# ``fmt: off`` keeps the literals on a single line; the inline pragma
# silences detect-secrets HexHighEntropy - these are not credentials,
# they are governance anchors enforcing the byte-exact contract.
# fmt: off
# Live (post-append) disk anchor — see Gate E test for full explanation.
D002C_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# Frozen pre-append anchor recorded in the Gate G artifact JSON.
D002C_LEDGER_SHA256_PRE_APPEND: str = "f96ba9b5a2057d2e0bff84afc28578ab316cff73f6dc6673fb0d6d543b8bd6dd"  # noqa: E501  # pragma: allowlist secret  # frozen at Gate F anchor; pre-D-002H-REFUSED-append
D002H_PREREG_SHA256_PIN: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
# fmt: on

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002H_PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
CANONICAL_RESULTS_RELPATH = "artifacts/d002h/canonical/results"


def _load_payload() -> dict[str, Any]:
    """Load + JSON-parse the Gate G final-lock artifact."""
    msg_missing = f"Gate G artifact missing at {ARTIFACT_RELPATH}"
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
    which makes historical commits (e.g. Gate A..F anchor merges) unknown
    locally. We detect this via ``git rev-parse --is-shallow-repository``
    and, if shallow, ask the origin to fetch the missing commit. The
    fetch is bounded and idempotent; failure is silent here and surfaces
    as the explicit shallow-clone diagnostic in :func:`_is_ancestor_of_main`.
    """
    if _git(["cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0:
        return
    if _git(["rev-parse", "--is-shallow-repository"]).stdout.strip() != "true":
        return
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
# 12 contract tests (names exact per the Gate G brief).
# ---------------------------------------------------------------------------


def test_gate_g_artifact_exists() -> None:
    """The Gate G final-lock JSON is on disk and parses as JSON.

    Two-assertion test (Lesson 4 C3): file presence AND payload is a
    non-empty dict.
    """
    assert ARTIFACT_PATH.is_file(), f"Gate G artifact missing at {ARTIFACT_RELPATH}"
    payload = _load_payload()
    msg_nonempty = "Gate G artifact parsed to empty/None payload; expected non-empty dict"
    assert isinstance(payload, dict) and len(payload) > 0, msg_nonempty


def test_gate_g_schema_version() -> None:
    """schema_version is exactly ``D002H-GATE-G-v1``.

    Two-assertion test (Lesson 4 C3): literal match AND non-empty string.
    """
    payload = _load_payload()
    schema = payload["schema_version"]
    msg_schema = f"schema_version drift: got {schema!r}, expected {SCHEMA_VERSION!r}"
    assert schema == SCHEMA_VERSION, msg_schema
    msg_nonempty = f"schema_version must be a non-empty string, got {schema!r}"
    is_nonempty_str = isinstance(schema, str) and len(schema) > 0
    assert is_nonempty_str, msg_nonempty


def test_gate_g_status_canonical_run_authorized() -> None:
    """status == 'CANONICAL_RUN_AUTHORIZED' and study_id == 'D-002H' and gate == 'G'.

    Three-assertion test (Lesson 4 C3): status literal AND study_id
    AND gate label.
    """
    payload = _load_payload()
    msg_status = f"status drift: got {payload['status']!r}, expected {EXPECTED_STATUS!r}"
    assert payload["status"] == EXPECTED_STATUS, msg_status
    msg_study = f"study_id drift: got {payload['study_id']!r}, expected 'D-002H'"
    assert payload["study_id"] == "D-002H", msg_study
    msg_gate = f"gate label drift: got {payload['gate']!r}, expected 'G'"
    assert payload["gate"] == "G", msg_gate


def test_gate_g_canonical_run_authorized_final_is_true() -> None:
    """canonical_run_authorized_final is True (Gate G is TERMINAL).

    Two-assertion test (Lesson 4 C3): the terminal-authorisation
    boolean is explicitly True AND the value is exactly the Python
    singleton True (not a truthy proxy).
    """
    payload = _load_payload()
    final = payload["canonical_run_authorized_final"]
    msg_final = (
        f"canonical_run_authorized_final drift: got {final!r}, "
        "expected True (Gate G is TERMINAL authorisation)"
    )
    assert final is True, msg_final
    msg_type = f"canonical_run_authorized_final must be Python bool True, got {type(final)!r}"
    assert isinstance(final, bool), msg_type


def test_gate_g_conjunction_satisfied_string() -> None:
    """conjunction_satisfied == 'A AND B AND C AND D AND E AND F AND G'.

    Two-assertion test (Lesson 4 C3): satisfied-string literal match
    AND required-string also matches (both pin the full conjunction).
    """
    payload = _load_payload()
    satisfied = payload["conjunction_satisfied"]
    msg_sat = (
        f"conjunction_satisfied drift: got {satisfied!r}, "
        f"expected {EXPECTED_CONJUNCTION_SATISFIED!r}"
    )
    assert satisfied == EXPECTED_CONJUNCTION_SATISFIED, msg_sat
    required = payload["conjunction_required"]
    msg_req = (
        f"conjunction_required drift: got {required!r}, expected {EXPECTED_CONJUNCTION_REQUIRED!r}"
    )
    assert required == EXPECTED_CONJUNCTION_REQUIRED, msg_req


def test_gate_g_chain_has_6_prior_gates() -> None:
    """gate_chain has exactly 6 entries (Gates A, B, C, D, E, F).

    Two-assertion test (Lesson 4 C3): list length AND ordered gate
    labels match expected sequence A..F.
    """
    payload = _load_payload()
    chain = payload["gate_chain"]
    msg_len = f"gate_chain length drift: got {len(chain)}, expected 6"
    assert len(chain) == 6, msg_len
    actual_gates = [entry["gate"] for entry in chain]
    expected_gates = ["A", "B", "C", "D", "E", "F"]
    msg_order = f"gate_chain gate-order drift: got {actual_gates!r}, expected {expected_gates!r}"
    assert actual_gates == expected_gates, msg_order


def test_gate_g_all_6_prior_gates_have_ci_pass_verdict() -> None:
    """Every prior-gate entry carries ``ci_verdict == 'ALL_REQUIRED_PASS'``.

    Multi-assertion test (Lesson 4 C3): per-gate ci_verdict probe
    accumulating drifts AND a final set-equality on the verdict set.
    """
    payload = _load_payload()
    chain = payload["gate_chain"]
    drifts: list[tuple[str, str]] = []
    for entry in chain:
        verdict = entry.get("ci_verdict")
        if verdict != "ALL_REQUIRED_PASS":
            drifts.append((entry["gate"], str(verdict)))
    msg_drift = (
        f"Gate G ci_verdict contract violated for {len(drifts)} prior gates: "
        f"{drifts!r}; expected every gate to record 'ALL_REQUIRED_PASS'."
    )
    assert drifts == [], msg_drift
    verdict_set = {entry["ci_verdict"] for entry in chain}
    msg_set = (
        f"gate_chain ci_verdict set drift: got {verdict_set!r}, expected {{'ALL_REQUIRED_PASS'}}"
    )
    assert verdict_set == {"ALL_REQUIRED_PASS"}, msg_set


def test_gate_g_authorisation_scope_ricci_flow_only() -> None:
    """authorisation_scope pins the sweep to ricci_flow substrate only.

    Two-assertion test (Lesson 4 C3): exact scope-literal match AND
    the scope string contains the substring 'ricci_flow'.
    """
    payload = _load_payload()
    scope = payload["authorisation_scope"]
    msg_scope = f"authorisation_scope drift: got {scope!r}, expected {EXPECTED_SCOPE!r}"
    assert scope == EXPECTED_SCOPE, msg_scope
    msg_sub = (
        f"authorisation_scope must mention 'ricci_flow', got {scope!r}; "
        "cross-substrate generalisation is out of scope per D-002H prereg"
    )
    assert "ricci_flow" in scope, msg_sub


def test_gate_g_canonical_run_execution_not_started() -> None:
    """canonical_run_execution_status == 'NOT_STARTED' - sweep is a downstream PR.

    Three-assertion test (Lesson 4 C3): execution-status literal match
    AND execution-artifact field declares the downstream PR is separate
    AND no ``results`` or ``sweep`` results live inside this artifact.
    """
    payload = _load_payload()
    exec_status = payload["canonical_run_execution_status"]
    msg_exec = (
        f"canonical_run_execution_status drift: got {exec_status!r}, "
        f"expected {EXPECTED_EXECUTION_STATUS!r}"
    )
    assert exec_status == EXPECTED_EXECUTION_STATUS, msg_exec
    exec_artifact = payload["canonical_run_execution_artifact"]
    msg_artifact = (
        f"canonical_run_execution_artifact must declare downstream PR, got {exec_artifact!r}; "
        "Gate G does NOT execute the sweep"
    )
    assert "SEPARATE" in exec_artifact and "downstream" in exec_artifact, msg_artifact
    msg_no_sweep_field = (
        f"Gate G artifact must not embed sweep results, got keys: {sorted(payload.keys())!r}"
    )
    assert "results" not in payload and "sweep" not in payload, msg_no_sweep_field


def test_gate_g_preserves_d002c_ledger() -> None:
    """D-002C claim ledger split-anchor check after PR #692 REFUSED append.

    Three-assertion test (Lesson 4 C3): Gate G artifact records the
    pre-append historical anchor (frozen at Gate F close), disk bytes
    match the post-append live anchor, and the two differ — the
    legitimate D-002H REFUSED append rotates the live sha while the
    historical artifact stays unchanged.
    """
    payload = _load_payload()
    pinned_in_artifact = payload["d002c_ledger_byte_exact"]
    msg_artifact = (
        f"D-002C ledger pin in Gate G artifact drift: got "
        f"{pinned_in_artifact!r}, expected pre-append anchor "
        f"{D002C_LEDGER_SHA256_PRE_APPEND!r} (frozen historical record)"
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
        f"sha {actual_disk!r} (post-append) by construction of PR #692."
    )
    assert pinned_in_artifact != actual_disk, msg_split


def test_gate_g_preserves_d002h_prereg() -> None:
    """D-002H prereg remains byte-exact at the locked pin.

    Three-assertion test (Lesson 4 C3): pinned-sha field in artifact
    equals inline anchor, disk bytes match inline anchor, transitive
    consistency.
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
        f"got {actual_disk!r}; Gate G is forbidden from editing the locked prereg"
    )
    assert actual_disk == D002H_PREREG_SHA256_PIN, msg_disk
    msg_transitive = (
        f"D-002H prereg transitive consistency violated: artifact pin "
        f"{pinned!r} != disk sha {actual_disk!r}"
    )
    assert pinned == actual_disk, msg_transitive


def test_gate_g_does_not_run_sweep() -> None:
    """Gate G's OWN artifact records NOT_STARTED execution.

    Scope-bound to Gate G's contribution. Downstream PRs (e.g. the
    canonical sweep PR) MAY legitimately create
    ``artifacts/d002h/canonical/results/`` — Gate G's invariant is
    that GATE G itself did not execute the sweep, encoded in its own
    ``canonical_run_execution_status`` field, NOT a global filesystem
    check.

    Two-assertion test (Lesson 4 C3): Gate G artifact's
    canonical_run_execution_status == NOT_STARTED AND the artifact
    documents the canonical sweep as a SEPARATE downstream PR.
    """
    payload = _load_payload()
    msg_status = (
        f"canonical_run_execution_status must be NOT_STARTED, got "
        f"{payload['canonical_run_execution_status']!r}"
    )
    assert payload["canonical_run_execution_status"] == EXPECTED_EXECUTION_STATUS, msg_status
    # Drift sentinel: confirm Gate G artifact pins the "separate
    # downstream PR" semantic in its own contract, not via filesystem
    # absence (which is brittle and bleeds across PR boundaries).
    execution_artifact = payload.get("canonical_run_execution_artifact", "")
    msg_artifact_doc = (
        "Gate G artifact must document the canonical-sweep PR as a SEPARATE "
        f"downstream artifact; got {execution_artifact!r}"
    )
    assert "separate" in execution_artifact.lower(), msg_artifact_doc


# ---------------------------------------------------------------------------
# Parametrised ancestor + per-gate verdict drift checks (Lesson 4 C3: >= 2 cases).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expected",
    EXPECTED_PRIOR_GATES,
    ids=lambda entry: f"gate_{entry['gate']}",
)
def test_gate_g_each_anchor_is_ancestor_of_main(expected: dict[str, Any]) -> None:
    """Parametrised over all 6 prior gates: each anchor is an ancestor of main.

    Two-assertion test (Lesson 4 C3): the SHA looks like a 40-hex git
    object id AND the ``git merge-base --is-ancestor`` probe returns 0.
    Six parametrised cases (>= 2 cases).
    """
    sha = expected["anchor_sha"]
    msg_format = f"anchor_sha for gate {expected['gate']} is not a 40-hex git sha: {sha!r}"
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha), msg_format
    msg_ancestor = (
        f"gate {expected['gate']} anchor {sha!r} is NOT an ancestor of "
        "origin/main; Gate G TERMINAL authorisation invalid"
    )
    assert _is_ancestor_of_main(sha), msg_ancestor


@pytest.mark.parametrize(
    "expected",
    EXPECTED_PRIOR_GATES,
    ids=lambda entry: f"gate_{entry['gate']}",
)
def test_gate_g_each_anchor_pin_matches_artifact(expected: dict[str, Any]) -> None:
    """Parametrised over all 6 prior gates: artifact pins match the brief shas.

    Two-assertion test (Lesson 4 C3): per-gate ``anchor_sha`` matches
    brief AND per-gate PR number matches brief. Six parametrised
    cases (>= 2 cases).
    """
    payload = _load_payload()
    chain = payload["gate_chain"]
    by_gate = {entry["gate"]: entry for entry in chain}
    actual = by_gate[expected["gate"]]
    msg_sha = (
        f"gate {expected['gate']} anchor_sha drift: artifact has "
        f"{actual['anchor_sha']!r}, brief expects {expected['anchor_sha']!r}"
    )
    assert actual["anchor_sha"] == expected["anchor_sha"], msg_sha
    msg_pr = (
        f"gate {expected['gate']} PR number drift: artifact has "
        f"{actual['pr']!r}, brief expects {expected['pr']!r}"
    )
    assert actual["pr"] == expected["pr"], msg_pr
