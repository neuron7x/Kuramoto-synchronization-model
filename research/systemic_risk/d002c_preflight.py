# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4-D — Pre-flight enforcement layer (truth-binding integration).

Mission
=======
The D-002C C2.4 sibling sessions A/B/C emit four pre-flight capsules:

  * ``pos_control``  — :mod:`d002c_pos_control` aggregate capsule
    (``kind: d002c_pos_control_capsule_v1``) carrying
    ``excluded_combos: list[(substrate_id, metric_id)]``.
  * ``neg_control``  — :mod:`d002c_neg_control` aggregate capsule
    (``kind: d002c_neg_control_capsule_v1``) carrying
    ``excluded_cells: list[(substrate_id, metric_id, N)]``.
  * ``null_audit``   — aggregate over per-cell
    :class:`d002c_null_audit.NullAuditResult` payloads
    (``kind: d002c_null_audit_capsule_v1``) carrying a list of
    ``verdict: PASS|FAIL`` per audited cell.
  * ``smoke_test``   — :mod:`d002c_smoke_test` aggregate capsule
    (structural kind: emitted shape carries ``verdict``,
    ``grid_N``, ``grid_lambda``, ``cells``) — no ``kind`` field
    is emitted upstream, so the preflight identifies it
    structurally.

Until this module merges, ``run_sweep`` only validates the
sweep_config against the pre-registration. It does NOT consult
the gate capsules. C2.4-D closes that gap by loading, validating,
hashing, and interpreting all four capsules before any sweep cell
is computed.

Strict scope
============
Truth-binding integration ONLY. NO sweep launch. NO claim layer.
NO threshold tuning. NO post-hoc relaxation. The preflight emits
no claim of its own — it only refuses launch or reduces the
execution grid based on the gate verdicts.

Determinism contract
====================
* Capsule SHA recomputation uses canonical JSON: ``sort_keys=True``,
  separators=(",", ":"), non-finite floats replaced by stable
  string sentinels.
* :class:`PreflightDecision`'s sha256 is content-addressed over its
  load-bearing fields (excluded_combos, excluded_cells, refusal
  reasons, capsule shas, launch_allowed flag).
* Same inputs → bit-exact identical decision sha across calls,
  processes, machines.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .d002c_metrics import ALL_METRICS
from .d002c_neg_control import DEFAULT_NEG_N_GRID
from .d002c_substrates import ALL_SUBSTRATES

# ---------------------------------------------------------------------------
# Capsule kind / schema markers
# ---------------------------------------------------------------------------

#: Emitted by :func:`d002c_pos_control.run_pos_control_all`.
POS_CONTROL_KIND: Final[str] = "d002c_pos_control_capsule_v1"

#: Emitted by :func:`d002c_neg_control.run_neg_control_all`.
NEG_CONTROL_KIND: Final[str] = "d002c_neg_control_capsule_v1"

#: C2.4-D-defined wrapper schema for null-audit results. The null-audit
#: module emits per-cell :class:`NullAuditResult` payloads but does not
#: write an aggregate capsule itself. Orchestrators that drive the
#: null-audit step must wrap the per-cell results in a capsule of this
#: kind for the preflight to consume.
NULL_AUDIT_KIND: Final[str] = "d002c_null_audit_capsule_v1"

#: Structural identity for the smoke-test capsule. The smoke-test
#: module emits a capsule WITHOUT a ``kind`` field; we identify it by
#: required structural fields.
SMOKE_TEST_STRUCTURAL_KIND: Final[str] = "d002c_smoke_test_capsule_v1"

_SMOKE_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "verdict",
        "grid_N",
        "grid_lambda",
        "n_cells_total",
        "n_cells_ok",
        "n_cells_failed",
        "cells",
        "sha256",
        "generated_at",
    }
)

#: Float sentinels used by :func:`canonical_preflight_json`.
_NAN_SENTINEL: Final[str] = "NaN"
_POS_INF_SENTINEL: Final[str] = "Infinity"
_NEG_INF_SENTINEL: Final[str] = "-Infinity"

#: Refusal-reason text catalogue (stable strings for tests and audit).
_R_MISSING_FILE: Final[str] = "capsule_missing_file"
_R_BAD_JSON: Final[str] = "capsule_bad_json"
_R_NOT_OBJECT: Final[str] = "capsule_not_json_object"
_R_BAD_KIND: Final[str] = "capsule_kind_mismatch"
_R_MISSING_SHA: Final[str] = "capsule_missing_sha256"
_R_SHA_MISMATCH: Final[str] = "capsule_sha256_mismatch"
_R_MISSING_TIMESTAMP: Final[str] = "capsule_missing_generated_at"
_R_NON_FINITE_FIELD: Final[str] = "capsule_non_finite_load_bearing_field"
_R_UNKNOWN_SUBSTRATE: Final[str] = "capsule_unknown_substrate_id"
_R_UNKNOWN_METRIC: Final[str] = "capsule_unknown_metric_id"
_R_UNKNOWN_N: Final[str] = "capsule_unknown_N"
_R_SMOKE_NOT_PASS: Final[str] = "smoke_verdict_not_pass"
_R_NULL_NOT_PASS: Final[str] = "null_audit_verdict_not_pass"
_R_NULL_EMPTY: Final[str] = "null_audit_empty_results"
_R_MISSING_VERDICT: Final[str] = "capsule_missing_verdict"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PreflightCapsuleError(RuntimeError):
    """Generic capsule-loading error. Always accumulated, never thrown
    mid-validation — except for :meth:`verify_capsule_sha256` which is
    callable directly by tests and must raise on mismatch."""


class CapsuleShaMismatch(PreflightCapsuleError):
    """Recomputed sha256 disagrees with the on-disk sha256 field."""


class PreflightLaunchRefused(RuntimeError):
    """Raised by :func:`assert_preflight_launch_allowed` when the
    decision's ``launch_allowed`` is False. Carries the full list of
    refusal reasons in its message so a single re-run can fix all of
    them."""


# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreflightCapsulePaths:
    """The four on-disk capsule paths the preflight consumes."""

    pos_control: Path
    neg_control: Path
    null_audit: Path
    smoke_test: Path


@dataclass(frozen=True)
class SkippedCell:
    """One sweep cell skipped because a preflight gate excluded it."""

    cell_key: str
    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    reason: str  # POS_EXCLUDED_COMBO | NEG_EXCLUDED_CELL
    source_capsule: str  # "pos_control" | "neg_control"
    source_capsule_sha256: str


@dataclass(frozen=True)
class RunnableCell:
    """One sweep cell that survives the preflight reduction."""

    cell_key: str
    substrate_id: str
    metric_id: str
    N: int
    lambda_: float


@dataclass(frozen=True)
class PreflightDecision:
    """Frozen verdict over the four preflight capsules.

    Fields
    ------
    launch_allowed
        True iff every capsule loaded cleanly AND every load-bearing
        invariant held (smoke PASS, null-audit all PASS, capsule
        SHAs match, identities are known). POS/NEG exclusions DO NOT
        flip this flag — they only reduce the grid.
    excluded_combos
        ``((substrate_id, metric_id), ...)`` from the POS-control
        capsule. Sweep cells matching these are skipped.
    excluded_cells
        ``((substrate_id, metric_id, N), ...)`` from the NEG-control
        capsule. Sweep cells matching these are skipped (exact triple).
    refusal_reasons
        Full ordered list of reasons launch is refused. Empty iff
        ``launch_allowed`` is True. Tests rely on the stable text
        catalogue (``_R_*`` constants) for assertion stability.
    capsule_shas
        ``{"pos_control": ..., "neg_control": ..., "null_audit": ...,
        "smoke_test": ...}`` — each value is the recomputed canonical
        sha256 if the capsule loaded; the sentinel "UNVERIFIED" if not.
    sha256
        Content-addressed sha256 of the decision payload. Same inputs
        → same decision sha. Used to bind the sweep aggregate sha so
        capsule tampering between runs changes the sweep sha.
    """

    launch_allowed: bool
    excluded_combos: tuple[tuple[str, str], ...]
    excluded_cells: tuple[tuple[str, str, int], ...]
    refusal_reasons: tuple[str, ...]
    capsule_shas: dict[str, str]
    sha256: str


# ---------------------------------------------------------------------------
# Canonical JSON + hashing
# ---------------------------------------------------------------------------


def _sanitize(obj: Any) -> Any:
    """Recursively replace non-finite floats with stable string sentinels.

    Tuples are normalised to lists (JSON arrays are ordered). dict keys
    are stringified by ``sort_keys`` in :func:`canonical_preflight_json`.
    """
    if isinstance(obj, float):
        if math.isnan(obj):
            return _NAN_SENTINEL
        if math.isinf(obj):
            return _POS_INF_SENTINEL if obj > 0 else _NEG_INF_SENTINEL
        return obj
    if isinstance(obj, (list, tuple)):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    return obj


def canonical_preflight_json(payload: dict[str, Any]) -> str:
    """Canonical JSON for preflight artifacts.

    Rules
    -----
    * ``sort_keys=True``
    * Tight separators ``(",", ":")``
    * Non-finite floats replaced by stable string sentinels
      (``"NaN"`` / ``"Infinity"`` / ``"-Infinity"``)
    * Tuples normalised to lists

    Same logical content → bit-exact identical encoding.
    """
    sanitized = _sanitize(payload)
    return json.dumps(sanitized, sort_keys=True, separators=(",", ":"))


def _sha_over(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_preflight_json(payload).encode("utf-8")).hexdigest()


def verify_capsule_sha256(capsule: dict[str, Any]) -> str:
    """Recompute the canonical sha256 over the capsule payload sans sha256.

    Raises
    ------
    CapsuleShaMismatch
        If the on-disk ``sha256`` does not match the recomputed value
        or is missing/non-string.
    """
    if "sha256" not in capsule or not isinstance(capsule["sha256"], str):
        raise CapsuleShaMismatch("capsule missing sha256 string field")
    on_disk = capsule["sha256"]
    body = {k: v for k, v in capsule.items() if k != "sha256"}
    recomputed = _sha_over(body)
    if recomputed != on_disk:
        raise CapsuleShaMismatch(
            f"capsule sha256 mismatch: on-disk={on_disk!r} recomputed={recomputed!r}"
        )
    return recomputed


# ---------------------------------------------------------------------------
# Known-identity registries
# ---------------------------------------------------------------------------

_ALL_SUBSTRATE_IDS: Final[frozenset[str]] = frozenset(s.id for s in ALL_SUBSTRATES)
_ALL_METRIC_IDS: Final[frozenset[str]] = frozenset(m.id for m in ALL_METRICS)
#: N values the pre-registration accepts. NEG_N_GRID is the
#: pre-registration-locked N grid (the same grid the negative control
#: sweeps); the preflight refuses unknown N values referenced from
#: capsules.
_ALL_KNOWN_N: Final[frozenset[int]] = frozenset(DEFAULT_NEG_N_GRID)


# ---------------------------------------------------------------------------
# Internal capsule readers
# ---------------------------------------------------------------------------


def _read_capsule(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Load a capsule JSON; return (data | None, reasons) without raising."""
    reasons: list[str] = []
    if not path.exists():
        reasons.append(f"{_R_MISSING_FILE}: {path}")
        return None, reasons
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        reasons.append(f"{_R_MISSING_FILE}: {path}: {exc}")
        return None, reasons
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        reasons.append(f"{_R_BAD_JSON}: {path}: {exc}")
        return None, reasons
    if not isinstance(data, dict):
        reasons.append(f"{_R_NOT_OBJECT}: {path}: root is {type(data).__name__}")
        return None, reasons
    return data, reasons


def _verify_sha_collecting(data: dict[str, Any], path: Path, reasons: list[str]) -> str | None:
    """Run :func:`verify_capsule_sha256` and collect failures.

    Returns the recomputed sha on success; ``None`` on failure (with a
    refusal reason appended to ``reasons``).
    """
    if "sha256" not in data:
        reasons.append(f"{_R_MISSING_SHA}: {path}")
        return None
    if not isinstance(data["sha256"], str):
        reasons.append(f"{_R_MISSING_SHA}: {path}: sha256 not a string")
        return None
    try:
        return verify_capsule_sha256(data)
    except CapsuleShaMismatch as exc:
        reasons.append(f"{_R_SHA_MISMATCH}: {path}: {exc}")
        return None


def _check_generated_at(data: dict[str, Any], path: Path, reasons: list[str]) -> None:
    ts = data.get("generated_at")
    if not isinstance(ts, str) or not ts:
        reasons.append(f"{_R_MISSING_TIMESTAMP}: {path}")


def _check_kind(
    data: dict[str, Any],
    expected: str,
    path: Path,
    reasons: list[str],
) -> bool:
    got = data.get("kind")
    if got != expected:
        reasons.append(f"{_R_BAD_KIND}: {path}: expected {expected!r}, got {got!r}")
        return False
    return True


def _is_finite_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


# ---------------------------------------------------------------------------
# Per-capsule processing
# ---------------------------------------------------------------------------


def _process_pos_control(
    data: dict[str, Any],
    path: Path,
    reasons: list[str],
) -> tuple[tuple[tuple[str, str], ...], str | None]:
    """Returns (excluded_combos, capsule_sha or None).

    Refuses launch on: bad kind, missing/mismatched sha, missing
    generated_at, unknown substrate/metric id in excluded_combos
    or results list.
    """
    if not _check_kind(data, POS_CONTROL_KIND, path, reasons):
        return (), None
    sha = _verify_sha_collecting(data, path, reasons)
    _check_generated_at(data, path, reasons)

    excluded_raw = data.get("excluded_combos", [])
    if not isinstance(excluded_raw, list):
        reasons.append(f"{_R_BAD_KIND}: {path}: excluded_combos not a list")
        excluded_raw = []
    excluded: list[tuple[str, str]] = []
    for combo in excluded_raw:
        if not (isinstance(combo, list) and len(combo) == 2):
            reasons.append(f"{_R_BAD_KIND}: {path}: malformed combo {combo!r}")
            continue
        sid = str(combo[0])
        mid = str(combo[1])
        if sid not in _ALL_SUBSTRATE_IDS:
            reasons.append(f"{_R_UNKNOWN_SUBSTRATE}: {path}: pos_excluded combo {sid!r}")
        if mid not in _ALL_METRIC_IDS:
            reasons.append(f"{_R_UNKNOWN_METRIC}: {path}: pos_excluded combo {mid!r}")
        excluded.append((sid, mid))

    # Validate every per-cell result identity (load-bearing — an
    # unknown id in the results list means the gate ran on a
    # universe inconsistent with the sweep).
    results_raw = data.get("results", [])
    if isinstance(results_raw, list):
        for r in results_raw:
            if not isinstance(r, dict):
                continue
            sid = str(r.get("substrate_id", ""))
            mid = str(r.get("metric_id", ""))
            if sid not in _ALL_SUBSTRATE_IDS:
                reasons.append(f"{_R_UNKNOWN_SUBSTRATE}: {path}: pos_result {sid!r}")
            if mid not in _ALL_METRIC_IDS:
                reasons.append(f"{_R_UNKNOWN_METRIC}: {path}: pos_result {mid!r}")
            for fld in ("signal_ci_ratio", "threshold", "censoring_fraction"):
                v = r.get(fld)
                if v is not None and not _is_finite_number(v):
                    reasons.append(f"{_R_NON_FINITE_FIELD}: {path}: pos_result.{fld}={v!r}")

    return tuple(excluded), sha


def _process_neg_control(
    data: dict[str, Any],
    path: Path,
    reasons: list[str],
) -> tuple[tuple[tuple[str, str, int], ...], str | None]:
    """Returns (excluded_cells, capsule_sha or None)."""
    if not _check_kind(data, NEG_CONTROL_KIND, path, reasons):
        return (), None
    sha = _verify_sha_collecting(data, path, reasons)
    _check_generated_at(data, path, reasons)

    excluded_raw = data.get("excluded_cells", [])
    if not isinstance(excluded_raw, list):
        reasons.append(f"{_R_BAD_KIND}: {path}: excluded_cells not a list")
        excluded_raw = []
    excluded: list[tuple[str, str, int]] = []
    for cell in excluded_raw:
        if not (isinstance(cell, list) and len(cell) == 3):
            reasons.append(f"{_R_BAD_KIND}: {path}: malformed cell {cell!r}")
            continue
        sid = str(cell[0])
        mid = str(cell[1])
        try:
            n_val = int(cell[2])
        except (TypeError, ValueError):
            reasons.append(f"{_R_BAD_KIND}: {path}: neg_excluded N not int: {cell[2]!r}")
            continue
        if sid not in _ALL_SUBSTRATE_IDS:
            reasons.append(f"{_R_UNKNOWN_SUBSTRATE}: {path}: neg_excluded {sid!r}")
        if mid not in _ALL_METRIC_IDS:
            reasons.append(f"{_R_UNKNOWN_METRIC}: {path}: neg_excluded {mid!r}")
        if n_val not in _ALL_KNOWN_N:
            reasons.append(f"{_R_UNKNOWN_N}: {path}: neg_excluded N={n_val}")
        excluded.append((sid, mid, n_val))

    # Validate per-cell results identities + finite fields
    results_raw = data.get("results", [])
    if isinstance(results_raw, list):
        for r in results_raw:
            if not isinstance(r, dict):
                continue
            sid = str(r.get("substrate_id", ""))
            mid = str(r.get("metric_id", ""))
            n_raw = r.get("N")
            if sid not in _ALL_SUBSTRATE_IDS:
                reasons.append(f"{_R_UNKNOWN_SUBSTRATE}: {path}: neg_result {sid!r}")
            if mid not in _ALL_METRIC_IDS:
                reasons.append(f"{_R_UNKNOWN_METRIC}: {path}: neg_result {mid!r}")
            if isinstance(n_raw, int) and n_raw not in _ALL_KNOWN_N:
                reasons.append(f"{_R_UNKNOWN_N}: {path}: neg_result N={n_raw}")
            for fld in ("fpr", "alpha_bonferroni", "threshold_tolerance"):
                v = r.get(fld)
                if v is not None and not _is_finite_number(v):
                    reasons.append(f"{_R_NON_FINITE_FIELD}: {path}: neg_result.{fld}={v!r}")

    return tuple(excluded), sha


def _process_null_audit(
    data: dict[str, Any],
    path: Path,
    reasons: list[str],
) -> str | None:
    """Returns capsule_sha or None. Appends refusal reasons on FAIL or empty."""
    if not _check_kind(data, NULL_AUDIT_KIND, path, reasons):
        return None
    sha = _verify_sha_collecting(data, path, reasons)
    _check_generated_at(data, path, reasons)

    results_raw = data.get("results", [])
    if not isinstance(results_raw, list):
        reasons.append(f"{_R_BAD_KIND}: {path}: results not a list")
        return sha

    aggregate_only = bool(data.get("aggregate_only", False))
    if not results_raw and not aggregate_only:
        reasons.append(f"{_R_NULL_EMPTY}: {path}")
        return sha

    for idx, r in enumerate(results_raw):
        if not isinstance(r, dict):
            reasons.append(f"{_R_MISSING_VERDICT}: {path}: results[{idx}] not a dict")
            continue
        verdict = r.get("verdict")
        if not isinstance(verdict, str):
            reasons.append(f"{_R_MISSING_VERDICT}: {path}: results[{idx}]")
            continue
        if verdict != "PASS":
            reasons.append(f"{_R_NULL_NOT_PASS}: {path}: results[{idx}].verdict={verdict!r}")
        # Finite check on p_value if present
        p = r.get("p_value_empirical")
        if p is not None and not _is_finite_number(p):
            reasons.append(f"{_R_NON_FINITE_FIELD}: {path}: results[{idx}].p_value_empirical={p!r}")

    return sha


def _process_smoke(
    data: dict[str, Any],
    path: Path,
    reasons: list[str],
) -> str | None:
    """Returns capsule_sha or None. The smoke capsule has no ``kind`` field
    (the writer module does not emit one) — we identify it structurally
    by requiring the canonical field set the smoke writer emits."""
    missing = _SMOKE_REQUIRED_FIELDS - set(data.keys())
    if missing:
        reasons.append(
            f"{_R_BAD_KIND}: {path}: smoke capsule missing required fields: {sorted(missing)}"
        )
        return None
    sha = _verify_sha_collecting(data, path, reasons)
    _check_generated_at(data, path, reasons)

    verdict = data.get("verdict")
    if not isinstance(verdict, str):
        reasons.append(f"{_R_MISSING_VERDICT}: {path}: smoke verdict missing")
    elif verdict != "PASS":
        reasons.append(f"{_R_SMOKE_NOT_PASS}: {path}: verdict={verdict!r}")

    # n_cells_failed must be 0 for a meaningful PASS
    failed = data.get("n_cells_failed")
    if isinstance(failed, int) and failed > 0:
        reasons.append(f"{_R_SMOKE_NOT_PASS}: {path}: n_cells_failed={failed}")

    return sha


# ---------------------------------------------------------------------------
# Public API — load + apply
# ---------------------------------------------------------------------------


def load_and_validate_preflight_capsules(
    paths: PreflightCapsulePaths,
) -> PreflightDecision:
    """Load + validate all four capsules; return a frozen :class:`PreflightDecision`.

    Never raises mid-validation — every error is accumulated into
    ``refusal_reasons`` so a single re-run fixes them all. The decision
    is content-addressed: same inputs → bit-exact identical
    ``decision.sha256``.

    POS/NEG exclusions DO NOT flip ``launch_allowed`` (the gates are
    "reduce the grid, do not abort" by contract); ANY other refusal
    flips it.
    """
    refusal_reasons: list[str] = []
    capsule_shas: dict[str, str] = {
        "pos_control": "UNVERIFIED",
        "neg_control": "UNVERIFIED",
        "null_audit": "UNVERIFIED",
        "smoke_test": "UNVERIFIED",
    }

    # POS
    excluded_combos: tuple[tuple[str, str], ...] = ()
    pos_data, pos_reasons = _read_capsule(paths.pos_control)
    refusal_reasons.extend(pos_reasons)
    if pos_data is not None:
        combos, pos_sha = _process_pos_control(pos_data, paths.pos_control, refusal_reasons)
        excluded_combos = combos
        if pos_sha is not None:
            capsule_shas["pos_control"] = pos_sha

    # NEG
    excluded_cells: tuple[tuple[str, str, int], ...] = ()
    neg_data, neg_reasons = _read_capsule(paths.neg_control)
    refusal_reasons.extend(neg_reasons)
    if neg_data is not None:
        cells, neg_sha = _process_neg_control(neg_data, paths.neg_control, refusal_reasons)
        excluded_cells = cells
        if neg_sha is not None:
            capsule_shas["neg_control"] = neg_sha

    # NULL
    null_data, null_reasons = _read_capsule(paths.null_audit)
    refusal_reasons.extend(null_reasons)
    if null_data is not None:
        null_sha = _process_null_audit(null_data, paths.null_audit, refusal_reasons)
        if null_sha is not None:
            capsule_shas["null_audit"] = null_sha

    # SMOKE
    smoke_data, smoke_reasons = _read_capsule(paths.smoke_test)
    refusal_reasons.extend(smoke_reasons)
    if smoke_data is not None:
        smoke_sha = _process_smoke(smoke_data, paths.smoke_test, refusal_reasons)
        if smoke_sha is not None:
            capsule_shas["smoke_test"] = smoke_sha

    # ``launch_allowed`` is True ONLY if every load-bearing check passed.
    # POS/NEG exclusions DO NOT flip the flag — those are grid reducers,
    # not launch blockers. The refusal_reasons list is what flips it.
    launch_allowed = len(refusal_reasons) == 0

    # Stable, sorted output for deterministic decision sha
    sorted_combos = tuple(sorted(set(excluded_combos)))
    sorted_cells = tuple(sorted(set(excluded_cells)))
    sorted_reasons = tuple(refusal_reasons)  # preserve discovery order

    decision_payload: dict[str, Any] = {
        "launch_allowed": bool(launch_allowed),
        "excluded_combos": [list(c) for c in sorted_combos],
        "excluded_cells": [list(c) for c in sorted_cells],
        "refusal_reasons": list(sorted_reasons),
        "capsule_shas": dict(capsule_shas),
    }
    sha = _sha_over(decision_payload)

    return PreflightDecision(
        launch_allowed=launch_allowed,
        excluded_combos=sorted_combos,
        excluded_cells=sorted_cells,
        refusal_reasons=sorted_reasons,
        capsule_shas=dict(capsule_shas),
        sha256=sha,
    )


def apply_preflight_to_grid(
    full_grid: Iterable[tuple[int, float, str, str]],
    decision: PreflightDecision,
) -> tuple[tuple[RunnableCell, ...], tuple[SkippedCell, ...]]:
    """Apply POS/NEG exclusions to the cartesian sweep grid.

    Parameters
    ----------
    full_grid
        Iterable of ``(N, lambda_, substrate_id, metric_id)`` tuples in
        canonical traversal order.
    decision
        Frozen :class:`PreflightDecision` carrying ``excluded_combos``
        (POS) and ``excluded_cells`` (NEG).

    Returns
    -------
    (runnable, skipped)
        ``runnable`` carries the cells that survive the preflight
        reduction (preserved in input traversal order). ``skipped``
        carries the cells removed by POS or NEG, each tagged with the
        source capsule + its sha256 — so the audit trail is preserved
        in the checkpoint.
    """
    from .sweep_checkpoint import cell_key

    pos_excluded: set[tuple[str, str]] = set(decision.excluded_combos)
    neg_excluded: set[tuple[str, str, int]] = set(decision.excluded_cells)
    pos_sha = decision.capsule_shas.get("pos_control", "UNVERIFIED")
    neg_sha = decision.capsule_shas.get("neg_control", "UNVERIFIED")

    runnable: list[RunnableCell] = []
    skipped: list[SkippedCell] = []
    for N, lam, sid, mid in full_grid:
        ck = cell_key((int(N), float(lam), str(sid), str(mid)))
        if (sid, mid) in pos_excluded:
            skipped.append(
                SkippedCell(
                    cell_key=ck,
                    substrate_id=sid,
                    metric_id=mid,
                    N=int(N),
                    lambda_=float(lam),
                    reason="POS_EXCLUDED_COMBO",
                    source_capsule="pos_control",
                    source_capsule_sha256=pos_sha,
                )
            )
            continue
        if (sid, mid, int(N)) in neg_excluded:
            skipped.append(
                SkippedCell(
                    cell_key=ck,
                    substrate_id=sid,
                    metric_id=mid,
                    N=int(N),
                    lambda_=float(lam),
                    reason="NEG_EXCLUDED_CELL",
                    source_capsule="neg_control",
                    source_capsule_sha256=neg_sha,
                )
            )
            continue
        runnable.append(
            RunnableCell(
                cell_key=ck,
                substrate_id=sid,
                metric_id=mid,
                N=int(N),
                lambda_=float(lam),
            )
        )
    return tuple(runnable), tuple(skipped)


def assert_preflight_launch_allowed(decision: PreflightDecision) -> None:
    """Raise :class:`PreflightLaunchRefused` if ``decision.launch_allowed`` is False.

    The exception message carries the full refusal-reasons list so a
    single re-run can fix all of them.
    """
    if decision.launch_allowed:
        return
    joined = "\n".join(f"  - {r}" for r in decision.refusal_reasons)
    raise PreflightLaunchRefused(
        f"preflight launch refused; sha={decision.sha256[:16]}…:\n{joined}"
    )


__all__ = [
    "POS_CONTROL_KIND",
    "NEG_CONTROL_KIND",
    "NULL_AUDIT_KIND",
    "SMOKE_TEST_STRUCTURAL_KIND",
    "PreflightCapsuleError",
    "CapsuleShaMismatch",
    "PreflightLaunchRefused",
    "PreflightCapsulePaths",
    "PreflightDecision",
    "SkippedCell",
    "RunnableCell",
    "canonical_preflight_json",
    "verify_capsule_sha256",
    "load_and_validate_preflight_capsules",
    "apply_preflight_to_grid",
    "assert_preflight_launch_allowed",
]
