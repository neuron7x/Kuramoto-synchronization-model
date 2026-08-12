# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate C — canonical parameter grid declaration tests.

Pure declaration: the grid JSON pins, byte-equivalent, the
``canonical_grid`` block from the locked D-002H pre-registration. No
compute, no sweep, no results. Gate C PASS alone does NOT authorise
canonical run; the conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the
authorisation contract.

These tests are fast JSON / sha / file-presence checks; they do NOT
recompute eligibility or any null-mechanism state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

ARTIFACT_RELPATH = "artifacts/d002h/canonical/d002h_canonical_grid.json"
ARTIFACT_PATH = REPO_ROOT / ARTIFACT_RELPATH

PREREG_RELPATH = "docs/governance/D002H_PREREGISTRATION.yaml"
PREREG_PATH = REPO_ROOT / PREREG_RELPATH

D002C_LEDGER_RELPATH = "docs/governance/D002C_CLAIM_LEDGER.yaml"
D002C_LEDGER_PATH = REPO_ROOT / D002C_LEDGER_RELPATH

CANONICAL_RESULTS_DIR = REPO_ROOT / "artifacts" / "d002h" / "canonical" / "results"
D002H_ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "d002h"

# Content-addressed sha256 anchors. Inline pragmas silence detect-secrets
# HexHighEntropy; these are governance hashes, not credentials. ``fmt: off``
# keeps the long literal on one line for byte-equivalent review.
# fmt: off
D002C_LEDGER_SHA256: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
D002H_PREREG_SHA256: str = "44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec"  # noqa: E501  # pragma: allowlist secret
# fmt: on

EXPECTED_SUBSTRATES: list[str] = ["ricci_flow"]
EXPECTED_N: list[int] = [50, 100, 200]
EXPECTED_LAMBDA: list[float] = [0.0, 0.05, 0.10, 0.20, 0.40, 1.0]
EXPECTED_N_SEEDS: int = 20
EXPECTED_N_BOOTSTRAP: int = 16
EXPECTED_TOTAL_CELLS: int = 18
EXPECTED_BASE_SEED: int = 42
EXPECTED_NULL_SEED_M3: int = 12345
EXPECTED_DOWNSTREAM_GATES: list[str] = ["D", "E", "F", "G"]

# Drift sentinels (Lesson 4 — false-confidence C3 single-assert): a
# second negative case prevents an accidental rebind of the locked
# sampling parameters to a common Python default.
N_SEEDS_DRIFT_SENTINELS: set[int] = {1, 5, 10, 50, 100}
N_BOOTSTRAP_DRIFT_SENTINELS: set[int] = {1, 100, 1000}


def _load_artifact() -> dict[str, Any]:
    raw = ARTIFACT_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def _load_prereg_canonical_grid() -> dict[str, Any]:
    prereg = yaml.safe_load(PREREG_PATH.read_text(encoding="utf-8"))
    assert isinstance(prereg, dict)
    cg = prereg["canonical_grid"]
    assert isinstance(cg, dict)
    return cg


# ---------------------------------------------------------------------------
# User-contract test names (10 tests, per the Gate C brief).
# ---------------------------------------------------------------------------


def test_d002h_gate_c_grid_artifact_exists() -> None:
    """JSON loads and carries the locked schema_version 'D002H-CANONICAL-GRID-v1'."""
    assert ARTIFACT_PATH.is_file(), f"Gate C artifact missing at {ARTIFACT_RELPATH}"
    payload = _load_artifact()
    assert payload["schema_version"] == "D002H-CANONICAL-GRID-v1"
    assert payload["study_id"] == "D-002H"
    assert payload["gate"] == "C"


def test_d002h_gate_c_grid_matches_d002h_prereg() -> None:
    """Grid JSON is byte-equivalent to D-002H prereg ``canonical_grid``.

    Compares the six grid-defining fields (substrates / N / lambda_values
    / n_seeds / n_bootstrap / total_cells). Any drift means either the
    JSON has rebound or the prereg has been edited; either is a
    contract violation.
    """
    payload = _load_artifact()
    cg = _load_prereg_canonical_grid()
    msg_sub = f"substrates drift: json={payload['substrates']!r} prereg={cg['substrates']!r}"
    assert payload["substrates"] == cg["substrates"], msg_sub
    msg_n = f"N drift: json={payload['N']!r} prereg={cg['N']!r}"
    assert payload["N"] == cg["N"], msg_n
    msg_lam = (
        f"lambda_values drift: json={payload['lambda_values']!r} prereg={cg['lambda_values']!r}"
    )
    assert payload["lambda_values"] == cg["lambda_values"], msg_lam
    msg_seeds = f"n_seeds drift: json={payload['n_seeds']!r} prereg={cg['n_seeds']!r}"
    assert payload["n_seeds"] == cg["n_seeds"], msg_seeds
    msg_boot = f"n_bootstrap drift: json={payload['n_bootstrap']!r} prereg={cg['n_bootstrap']!r}"
    assert payload["n_bootstrap"] == cg["n_bootstrap"], msg_boot
    msg_cells = f"total_cells drift: json={payload['total_cells']!r} prereg={cg['total_cells']!r}"
    assert payload["total_cells"] == cg["total_cells"], msg_cells


def test_d002h_gate_c_grid_substrate_ricci_flow_only() -> None:
    """Substrate scope is exactly ['ricci_flow']; excluded substrates absent.

    Negative cases (Lesson 4) pin the D-002H prereg exclusions —
    block_structured and temporal_coupling MUST NOT appear in scope.
    """
    payload = _load_artifact()
    substrates: list[str] = payload["substrates"]
    assert substrates == EXPECTED_SUBSTRATES
    assert "block_structured" not in substrates
    assert "temporal_coupling" not in substrates


def test_d002h_gate_c_grid_n_seeds_locked() -> None:
    """n_seeds == 20; not a common Python-default value (drift sentinel)."""
    payload = _load_artifact()
    n_seeds: int = payload["n_seeds"]
    assert n_seeds == EXPECTED_N_SEEDS
    msg_drift = (
        f"n_seeds={n_seeds} collides with common-default drift sentinel "
        f"{N_SEEDS_DRIFT_SENTINELS}; suspect silent rebind"
    )
    assert n_seeds not in N_SEEDS_DRIFT_SENTINELS, msg_drift


def test_d002h_gate_c_grid_n_bootstrap_locked() -> None:
    """n_bootstrap == 16; not a common Python-default value (drift sentinel)."""
    payload = _load_artifact()
    n_bootstrap: int = payload["n_bootstrap"]
    assert n_bootstrap == EXPECTED_N_BOOTSTRAP
    msg_drift = (
        f"n_bootstrap={n_bootstrap} collides with common-default drift sentinel "
        f"{N_BOOTSTRAP_DRIFT_SENTINELS}; suspect silent rebind"
    )
    assert n_bootstrap not in N_BOOTSTRAP_DRIFT_SENTINELS, msg_drift


def test_d002h_gate_c_grid_total_cells_18() -> None:
    """total_cells == 18 == |N| * |λ| (3 × 6); algebraic consistency."""
    payload = _load_artifact()
    total_cells: int = payload["total_cells"]
    assert total_cells == EXPECTED_TOTAL_CELLS
    assert total_cells == len(payload["N"]) * len(payload["lambda_values"])


def test_d002h_gate_c_does_not_run_sweep() -> None:
    """Gate C's OWN artifact is pure declaration, not a sweep result.

    Scope-bound to Gate C's contribution. Downstream PRs (e.g. the
    canonical sweep PR after Gate G) MAY legitimately create
    ``artifacts/d002h/canonical/results/`` as their own scientific
    output — Gate C's invariant is that GATE C did not run the sweep,
    not that no sweep ever runs.

    Enforces two invariants on Gate C's own grid JSON:
      1. The grid JSON has no ``results`` top-level field.
      2. The grid JSON has no ``sweep`` top-level field.
    """
    payload = _load_artifact()
    msg_results_field = "Gate C grid JSON must not embed results — declaration only"
    msg_sweep_field = "Gate C grid JSON must not embed sweep state — declaration only"
    assert "results" not in payload, msg_results_field
    assert "sweep" not in payload, msg_sweep_field


def test_d002h_gate_c_preserves_d002c_ledger() -> None:
    """D-002C claim ledger sha256 byte-exact UNCHANGED at the locked anchor."""
    assert D002C_LEDGER_PATH.is_file(), f"D-002C ledger missing at {D002C_LEDGER_RELPATH}"
    actual = hashlib.sha256(D002C_LEDGER_PATH.read_bytes()).hexdigest()
    msg_ledger = (
        f"D-002C ledger MUTATED: expected {D002C_LEDGER_SHA256}, got {actual}. "
        "Gate C is forbidden from touching the D-002C claim ledger."
    )
    assert actual == D002C_LEDGER_SHA256, msg_ledger


def test_d002h_gate_c_preserves_prereg_lock() -> None:
    """D-002H pre-registration sha256 byte-exact UNCHANGED at the PR #683 anchor."""
    assert PREREG_PATH.is_file(), f"D-002H prereg missing at {PREREG_RELPATH}"
    actual = hashlib.sha256(PREREG_PATH.read_bytes()).hexdigest()
    msg_prereg = (
        f"D-002H prereg MUTATED: expected {D002H_PREREG_SHA256}, got {actual}. "
        "Editing the locked prereg constitutes a fresh D-002J pre-registration; "
        "Gate C is forbidden from this."
    )
    assert actual == D002H_PREREG_SHA256, msg_prereg


def test_d002h_gate_c_no_canonical_run_authorisation() -> None:
    """canonical_run_authorized == False AND downstream gates ['D','E','F','G'] remain open."""
    payload = _load_artifact()
    assert payload["canonical_run_authorized"] is False
    downstream: list[str] = payload["downstream_gates_remaining"]
    assert downstream == EXPECTED_DOWNSTREAM_GATES
    # Negative case: Gate C must NOT list itself as still-open.
    assert "C" not in downstream
