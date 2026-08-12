# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared, byte-preserving substrate for the CALIB-GRID lineages.

Every CALIB-GRID lineage (CALIB-GRID-001, R1, the identifiability
front-gate, CALIB-GRID-002) previously hand-rolled its own copy of four
identical primitives:

* the ``json.dumps(ledger, sort_keys=True)`` → ``sha256`` ledger
  content-hash (4 verbatim copies);
* a ``_branch_sha`` git-HEAD reader (2 copies differing only in the
  ``parents[N]`` depth);
* the frozen parent pre-registration / parent-ledger git-sha string
  literals (3 copies of the same two constants);
* the thresholded edge-support F1 (2 byte-identical copies).

This module is the single source of truth for all four. It is **purely
structural**: every helper reproduces the exact bytes / numerics the
per-lineage copies produced, so every already-merged sha-pinned
``RESULTS.json`` and every existing drift / no-peek / bit-stability test
stays valid without modification. No threshold, gate, seed, σ, θ₀ or
decision rule lives here — those remain frozen in the per-lineage
pre-registration documents and gate modules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from numpy.typing import NDArray

__all__ = [
    "AMENDMENT_001_PATH",
    "FROZEN_PREREG_SHA",
    "INFEASIBLE_BY_CONSTRUCTION",
    "PARENT_LEDGER_SHA256",
    "PREREG_BRANCH_BASE_SHA",
    "Gate",
    "GateRow",
    "amended_gate_names",
    "branch_sha",
    "ledger_sha256",
    "overall_verdict_amended",
    "topology_f1",
]

# --- Frozen provenance constants (audited content hashes, not secrets) ----
# These pin the CALIB-GRID-001 parent lineage. They are *read* by every
# child lineage and never redefined; centralising the literal removes the
# three divergent copies (run.py / validate.py / cg002.py) without
# changing any emitted byte.
# audited: frozen parent pre-registration git sha, not a credential
FROZEN_PREREG_SHA = "d170d48afa5066c13edeb40b2c1904b3fd708516"  # pragma: allowlist secret
# audited: parent calibration ledger content hash, not a credential
PARENT_LEDGER_SHA256 = (
    "ed8d409b7b222eb053572d6bf9ab6e98c5f4918be1cae384864733a2b4d72aaf"  # pragma: allowlist secret
)
# audited: branch base sha the CALIB-GRID-002 pre-registration was committed off
PREREG_BRANCH_BASE_SHA = "a5e0d533b2201c999b31c792773e858f8da713bf"  # pragma: allowlist secret


def ledger_sha256(ledger: dict[str, Any]) -> str:
    """Content hash of ``ledger`` over its canonical ``sort_keys`` JSON.

    Byte-for-byte identical to the per-lineage copies it replaces::

        payload = json.dumps(ledger, sort_keys=True).encode("utf-8")
        hashlib.sha256(payload).hexdigest()

    ``sort_keys=True`` makes the hash invariant to key *insertion* order,
    so consolidating the four builders cannot perturb any sha-pinned
    artifact even though the unified call site differs.
    """
    payload = json.dumps(ledger, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def branch_sha(repo_root: Path) -> str:
    """Best-effort current commit sha for a ledger provenance field.

    ``repo_root`` is the repository root (the directory containing
    ``.git``). Resolves a symbolic ``ref:`` HEAD to its packed/loose
    object id; returns ``"unknown"`` on any filesystem error (the field
    is provenance only and is excluded from every drift comparison).
    """
    head = repo_root / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref:"):
            ref_path = head.parent / ref.split(" ", 1)[1]
            return ref_path.read_text(encoding="utf-8").strip()
        return ref
    except OSError:
        return "unknown"


def topology_f1(
    k_true: NDArray[np.float64],
    k_hat: NDArray[np.float64],
    rel_threshold: float,
) -> tuple[float, int, int]:
    """Edge-support F1 of the thresholded recovered adjacency.

    The recovered edge is "present" if ``|K_hat_ij|`` exceeds
    ``rel_threshold · max|K_hat|``; the truth edge is present if
    ``|K_true_ij| > 0``. Diagonal excluded. Returns
    ``(f1, n_true_edges, n_recovered_edges)``. Numerically identical to
    the two ``_topology_f1`` copies (calibration.py / cg002.py) it
    replaces.
    """
    n = k_true.shape[0]
    off = ~np.eye(n, dtype=bool)
    true_mask = (np.abs(k_true) > 0.0) & off
    scale = float(np.max(np.abs(k_hat)))
    if scale <= 0.0:
        return 0.0, int(true_mask.sum()), 0
    hat_mask = (np.abs(k_hat) > rel_threshold * scale) & off
    tp = int((true_mask & hat_mask).sum())
    fp = int((~true_mask & hat_mask).sum())
    fn = int((true_mask & ~hat_mask).sum())
    denom = 2 * tp + fp + fn
    f1 = (2.0 * tp / denom) if denom > 0 else 1.0
    return f1, int(true_mask.sum()), int(hat_mask.sum())


@dataclass(frozen=True)
class Gate:
    """A single pre-registered numeric gate (fail-closed comparator).

    Unifies the three copy-evolved gate dataclasses (``GateVerdict`` in
    ``gates.py`` and ``CG002Gate`` in ``cg002.py``) into one shape. The
    thresholds themselves stay frozen in the per-lineage pre-registration
    documents — this only removes the duplicated *carrier* type and its
    twice-copied operator-dispatch logic.
    """

    name: str
    metric_key: str
    operator: str  # "<=" or ">="
    threshold: float
    localises_to: str

    def check(self, observed: float) -> bool:
        """Fail-closed comparison; an unknown operator raises."""
        if self.operator == "<=":
            return observed <= self.threshold
        if self.operator == ">=":
            return observed >= self.threshold
        raise ValueError(f"unknown operator {self.operator!r}")


@dataclass(frozen=True)
class GateRow:
    """Outcome of evaluating one :class:`Gate` against a metric value.

    ``to_dict`` reproduces the exact key set / order the legacy
    ``GateResult.to_dict`` and the cg002 ``_emit`` row dict emitted, so
    every ``gates`` array in every sha-pinned ledger stays byte-identical
    under ``json.dumps(sort_keys=True)``.
    """

    name: str
    metric_key: str
    observed: float
    operator: str
    threshold: float
    passed: bool
    localises_to: str

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable view (sorted keys downstream)."""
        return {
            "name": self.name,
            "metric_key": self.metric_key,
            "observed": self.observed,
            "operator": self.operator,
            "threshold": self.threshold,
            "passed": self.passed,
            "localises_to": self.localises_to,
        }


# --- Pre-Registration Amendment 001 — forward-only verdict layer ---------
#
# This block is the ONLY behavioural change of the F2 amendment and it
# is FORWARD-ONLY. It does NOT touch any threshold value, the frozen
# ``PREREGISTRATION.md`` / ``gates.py``, or any sha-pinned RESULTS
# ledger. The legacy ``gates.overall_verdict`` is left byte-identical,
# so every historical ``build_*_ledger`` reproduces the exact frozen
# bytes when run WITHOUT the amendment. A fresh lineage #6+ run that
# explicitly opts into the amendment uses :func:`overall_verdict_amended`
# instead, which reclassifies the amended ``noisy.*`` gates as
# ``INFEASIBLE_BY_CONSTRUCTION`` (a distinct 0-bit state, not PASS, not
# FAIL) and computes the overall verdict over the remaining genuine
# pass/fail gates only.

# A distinct, zero-bit verdict state for a gate the CG002 sha-pinned
# NEGATIVE proved is information-theoretically unreachable (regressor
# SNR < 0.6 ∀ edge at the frozen σ): P(FAIL)=1 ∀ estimator ⇒ H=0 bits.
INFEASIBLE_BY_CONSTRUCTION = "INFEASIBLE_BY_CONSTRUCTION"

# The append-only amendment document. The single source of truth for
# *which* gates are reclassified is this YAML; a no-peek drift test
# binds these names to the document fail-closed.
AMENDMENT_001_PATH = Path(__file__).resolve().parent / "PREREGISTRATION_AMENDMENT_001.yaml"


def amended_gate_names(amendment_path: Path | None = None) -> frozenset[str]:
    """Gate names PRE-REGISTRATION-AMENDMENT-001 reclassifies (read-only).

    Reads ``PREREGISTRATION_AMENDMENT_001.yaml`` and returns the set of
    gate names reclassified to ``INFEASIBLE_BY_CONSTRUCTION``. This is a
    pure read of the append-only amendment document — no threshold value
    is read or redefined here. ``amendment_path`` defaults to the merged
    amendment; an explicit path is accepted for the drift test.
    """
    path = amendment_path if amendment_path is not None else AMENDMENT_001_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"amendment {path} is not a YAML mapping")
    if data.get("identifier") != "PREREGISTRATION-AMENDMENT-001":
        raise ValueError(f"amendment {path} has an unexpected identifier")
    names = data["reclassification"]["amended_gate_names"]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError(f"amendment {path} amended_gate_names is malformed")
    return frozenset(names)


def overall_verdict_amended(
    rows: list[GateRow],
    *,
    amendment_path: Path | None = None,
) -> tuple[str, dict[str, str]]:
    """Forward-only amended overall verdict (lineage #6+ runs only).

    Returns ``(verdict, per_gate_state)`` where every gate named by
    PRE-REGISTRATION-AMENDMENT-001 is assigned the distinct zero-bit
    state ``INFEASIBLE_BY_CONSTRUCTION`` (neither PASS nor FAIL) and the
    overall ``verdict`` is computed over the **remaining genuine
    pass/fail gates only**: ``"PASS"`` iff every non-amended gate passed,
    else ``"NEGATIVE"`` (fail-closed). If every gate is amended away the
    verdict is ``INFEASIBLE_BY_CONSTRUCTION`` (no genuine gate remains to
    decide). This never mutates ``rows`` and never touches a threshold;
    it only re-partitions the verdict, forward.
    """
    amended = amended_gate_names(amendment_path)
    per_gate: dict[str, str] = {}
    genuine: list[GateRow] = []
    for row in rows:
        if row.name in amended:
            per_gate[row.name] = INFEASIBLE_BY_CONSTRUCTION
        else:
            per_gate[row.name] = "PASS" if row.passed else "FAIL"
            genuine.append(row)
    if not genuine:
        return INFEASIBLE_BY_CONSTRUCTION, per_gate
    verdict = "PASS" if all(r.passed for r in genuine) else "NEGATIVE"
    return verdict, per_gate
