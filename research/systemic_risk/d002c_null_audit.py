# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Null audit (permutation test) for the Signal Amplification Sweep.

Mission
=======
A precursor cohort produced by the sweep yields a per-seed (precursor, null)
pair (CRN-paired by construction in C2.3). The aggregate signal is

    S = |mean(precursor) − mean(null)| = |signal_mean|

If the precursor truly carries information, swapping the precursor/null
labels at random will DESTROY the signal — most label-permuted shuffles
produce |signal_mean| << S. If swapping doesn't destroy it, the
"signal" is a label artefact, statistical noise, or a metric that
saturates regardless of precursor injection. The audit's job is to
catch that failure BEFORE the sweep's headline number propagates.

Method
======
For ``n_shuffles`` independent permutations, draw a Bernoulli(0.5)
mask of length ``n_seeds`` per shuffle. Inside each pair, swap the
(precursor, null) values where the mask is 1; recompute
|mean_diff|. The empirical p-value is the fraction of shuffles
with |shuffled| ≥ |unshuffled|. PASS iff ``p_value < 0.05``.

This is the standard paired-difference permutation test for the
sign of a paired effect; bit-exact deterministic in ``rng_seed``,
``n_shuffles``, and the input arrays.

Strict scope
============
Permutation-test logic ONLY. NO sweep launch. NO claim layer. NO
metric estimation. NO promotion of a verdict into a tier — the
sweep's headline claim layer reads the verdict and refuses to
publish if FAIL.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Locked defaults
# ---------------------------------------------------------------------------
DEFAULT_N_SHUFFLES: Final[int] = 100
DEFAULT_RNG_SEED: Final[int] = 42
DEFAULT_P_VALUE_THRESHOLD: Final[float] = 0.05
MIN_N_SHUFFLES: Final[int] = 10
MIN_N_SEEDS: Final[int] = 2

logger = logging.getLogger(__name__)


class NullAuditInvalid(RuntimeError):
    """Bad input to the null audit (empty arrays, shape mismatch, ...)."""


@dataclass(frozen=True)
class NullAuditResult:
    """Per-cell null audit verdict.

    ``unshuffled_greater_than_median`` is the load-bearing sanity check:
    the true signal must dominate the median of the label-shuffled null
    distribution. ``p_value_empirical`` is the formal verdict driver.
    """

    n_seeds: int
    n_shuffles: int
    unshuffled_abs_signal: float
    shuffled_abs_signal_median: float
    shuffled_abs_signal_p95: float
    unshuffled_greater_than_median: bool
    p_value_empirical: float
    verdict: str  # "PASS" | "FAIL"
    sha256: str
    rng_seed: int = DEFAULT_RNG_SEED
    p_value_threshold: float = DEFAULT_P_VALUE_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Atomic capsule writer (inlined to match sibling-module discipline)
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace. Cleanup on exception, never mask original."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Core permutation test
# ---------------------------------------------------------------------------


def run_null_audit(
    precursor_values: NDArray[np.float64],
    null_values: NDArray[np.float64],
    *,
    n_shuffles: int = DEFAULT_N_SHUFFLES,
    rng_seed: int = DEFAULT_RNG_SEED,
    p_value_threshold: float = DEFAULT_P_VALUE_THRESHOLD,
) -> NullAuditResult:
    """Paired-difference permutation test for the signal's reality.

    Parameters
    ----------
    precursor_values, null_values
        1-D arrays of shape ``(n_seeds,)``. Paired by index: entry ``i``
        in both arrays is the metric from seed ``i``'s precursor and
        null run (CRN-paired upstream in C2.3).
    n_shuffles
        Number of random label-permutations. Must be >= ``MIN_N_SHUFFLES``
        (10). 100 is the locked default — gives a discretised p-value
        resolution of 0.01.
    rng_seed
        Seeds numpy's PCG64. Determinism: same arrays + same
        (rng_seed, n_shuffles) → bit-exact identical result.
    p_value_threshold
        PASS iff ``p_value_empirical < threshold``. Default 0.05.

    Returns
    -------
    NullAuditResult
        Frozen dataclass with canonical sha256 over the load-bearing
        fields. See the module docstring for the verdict semantics.

    Raises
    ------
    NullAuditInvalid
        Empty arrays, mismatched shapes, non-1-D inputs, non-finite
        values, n_shuffles below the floor, or non-finite threshold.
    """
    precursor_values = np.asarray(precursor_values, dtype=np.float64)
    null_values = np.asarray(null_values, dtype=np.float64)
    if precursor_values.ndim != 1 or null_values.ndim != 1:
        raise NullAuditInvalid(
            f"inputs must be 1-D; got shapes precursor={precursor_values.shape} "
            f"null={null_values.shape}"
        )
    if precursor_values.shape != null_values.shape:
        raise NullAuditInvalid(
            f"precursor and null arrays must have identical shape; got "
            f"precursor={precursor_values.shape} null={null_values.shape}"
        )
    n_seeds = int(precursor_values.shape[0])
    if n_seeds < MIN_N_SEEDS:
        raise NullAuditInvalid(f"need >= {MIN_N_SEEDS} paired seeds; got n_seeds={n_seeds}")
    if not np.all(np.isfinite(precursor_values)) or not np.all(np.isfinite(null_values)):
        raise NullAuditInvalid("inputs must be finite (no NaN / Inf)")
    if n_shuffles < MIN_N_SHUFFLES:
        raise NullAuditInvalid(f"n_shuffles must be >= {MIN_N_SHUFFLES}; got {n_shuffles}")
    if not np.isfinite(p_value_threshold) or not (0.0 < p_value_threshold < 1.0):
        raise NullAuditInvalid(
            f"p_value_threshold must be finite and in (0, 1); got {p_value_threshold}"
        )

    # True (unshuffled) signal
    unshuffled_abs = float(abs(precursor_values.mean() - null_values.mean()))

    # Permutation distribution: per-pair Bernoulli(0.5) label swap
    rng = np.random.default_rng(rng_seed)
    # signs[i, j] in {0, 1}; if 1, swap pair j in shuffle i
    masks = rng.integers(0, 2, size=(n_shuffles, n_seeds), dtype=np.int64).astype(bool)
    # Under swap, new_precursor = mask*null + (1-mask)*precursor
    # new_null      = mask*precursor + (1-mask)*null
    # mean_diff(shuffled) = mean(new_precursor - new_null)
    #                     = mean((1 - 2*mask) * (precursor - null))
    diff = precursor_values - null_values
    sign = 1.0 - 2.0 * masks.astype(np.float64)  # +1 keep, -1 swap
    shuffled_means = (sign * diff[np.newaxis, :]).mean(axis=1)
    shuffled_abs = np.abs(shuffled_means)
    shuffled_median = float(np.median(shuffled_abs))
    shuffled_p95 = float(np.percentile(shuffled_abs, 95.0))

    # Empirical p-value: fraction with |shuffled| >= |unshuffled|
    n_ge = int(np.sum(shuffled_abs >= unshuffled_abs))
    p_value = n_ge / float(n_shuffles)
    verdict = "PASS" if p_value < p_value_threshold else "FAIL"

    payload: dict[str, Any] = {
        "n_seeds": n_seeds,
        "n_shuffles": int(n_shuffles),
        "unshuffled_abs_signal": unshuffled_abs,
        "shuffled_abs_signal_median": shuffled_median,
        "shuffled_abs_signal_p95": shuffled_p95,
        "unshuffled_greater_than_median": unshuffled_abs > shuffled_median,
        "p_value_empirical": p_value,
        "verdict": verdict,
        "rng_seed": int(rng_seed),
        "p_value_threshold": float(p_value_threshold),
    }
    sha = _sha256(payload)
    return NullAuditResult(
        n_seeds=n_seeds,
        n_shuffles=int(n_shuffles),
        unshuffled_abs_signal=unshuffled_abs,
        shuffled_abs_signal_median=shuffled_median,
        shuffled_abs_signal_p95=shuffled_p95,
        unshuffled_greater_than_median=unshuffled_abs > shuffled_median,
        p_value_empirical=p_value,
        verdict=verdict,
        sha256=sha,
        rng_seed=int(rng_seed),
        p_value_threshold=float(p_value_threshold),
    )


# ---------------------------------------------------------------------------
# Capsule replay path: parse a sweep capsule and run an audit per cell
# ---------------------------------------------------------------------------


def _extract_per_seed_arrays(
    cell: dict[str, Any],
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    """Try to extract paired (precursor, null) per-seed arrays from a cell.

    Returns ``None`` if the cell does not carry enough per-seed data to
    audit. The keys we accept are intentionally a small union — a stub
    capsule from C2.3 that only carries aggregate variances will be
    skipped cleanly, with a log line.

    D-002C C2.4-A2 — the sweep runner writes the paired vectors under a
    nested ``null_audit_payload`` sub-dict whose own ``sha256`` field
    is content-addressed via ``canonical_preflight_json``. When that
    sub-dict is present we route through
    :meth:`d002c_sweep_runner.NullAuditCellPayload.from_payload_dict`
    so the sha is verified fail-closed (a one-byte tamper of the
    on-disk payload makes the aggregator record SKIPPED_NO_PER_SEED_DATA,
    NEVER silently accept the row). For pre-A2 capsules and the C2.3
    flat schema we fall back to the legacy key set.
    """
    nested = cell.get("null_audit_payload")
    if isinstance(nested, dict):
        # Lazy import to avoid a module-load cycle with d002c_sweep_runner
        # (which in turn imports from this module via the preflight
        # validator chain). Function-scope mirrors the
        # _canonical_capsule_sha pattern below.
        from .d002c_sweep_runner import (
            NullAuditCellPayload,
            NullAuditPayloadInvalid,
        )

        try:
            payload = NullAuditCellPayload.from_payload_dict(nested)
        except NullAuditPayloadInvalid as exc:
            # Fail-closed: a corrupted on-disk payload is NOT silently
            # downgraded to "no data"; surface the divergence so the
            # aggregator records SKIPPED for the cell instead of an
            # invented PASS.
            logger.info("null_audit: payload rejected (%s) — treating as no per-seed data", exc)
            return None
        p_arr = np.asarray(payload.precursor_values, dtype=np.float64)
        n_arr = np.asarray(payload.null_values, dtype=np.float64)
        if p_arr.shape != n_arr.shape or p_arr.ndim != 1 or p_arr.size < MIN_N_SEEDS:
            return None
        return p_arr, n_arr

    candidates_precursor = (
        "precursor_per_seed",
        "per_seed_precursor",
        "precursor_values",
    )
    candidates_null = ("null_per_seed", "per_seed_null", "null_values")
    p_arr_opt: NDArray[np.float64] | None = None
    n_arr_opt: NDArray[np.float64] | None = None
    for k in candidates_precursor:
        if k in cell and cell[k] is not None:
            p_arr_opt = np.asarray(cell[k], dtype=np.float64)
            break
    for k in candidates_null:
        if k in cell and cell[k] is not None:
            n_arr_opt = np.asarray(cell[k], dtype=np.float64)
            break
    if p_arr_opt is None or n_arr_opt is None:
        return None
    if p_arr_opt.shape != n_arr_opt.shape or p_arr_opt.ndim != 1 or p_arr_opt.size < MIN_N_SEEDS:
        return None
    return p_arr_opt, n_arr_opt


def run_null_audit_from_capsule(
    capsule_path: Path,
    *,
    n_shuffles: int = DEFAULT_N_SHUFFLES,
    rng_seed: int = DEFAULT_RNG_SEED,
    p_value_threshold: float = DEFAULT_P_VALUE_THRESHOLD,
) -> tuple[NullAuditResult, ...]:
    """Run a null audit on each per-cell entry in a sweep capsule.

    Stub-friendly: cells that lack per-seed data are skipped with a
    logger.info line citing the cell's substrate/metric id; cells that
    DO carry per-seed arrays are audited and a result is appended.
    A capsule with NO auditable cells returns an empty tuple — the
    caller decides if that is a failure or simply means C2.3-style
    aggregate-only output.

    Parameters
    ----------
    capsule_path
        Path to a JSON capsule written by the sweep runner (C2.4
        session A) or by C2.3 (CRN validator). The shape we accept
        is the same dict-of-lists schema both use.
    n_shuffles, rng_seed, p_value_threshold
        Forwarded to :func:`run_null_audit` for each auditable cell.

    Raises
    ------
    NullAuditInvalid
        If the capsule path does not exist or does not decode as JSON.
    """
    capsule_path = Path(capsule_path)
    if not capsule_path.exists():
        raise NullAuditInvalid(f"capsule does not exist: {capsule_path}")
    try:
        raw = capsule_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise NullAuditInvalid(f"could not parse capsule {capsule_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise NullAuditInvalid(f"capsule root must be a JSON object; got {type(data).__name__}")
    results_list = data.get("results")
    if not isinstance(results_list, list):
        logger.info(
            "null_audit: capsule %s has no 'results' list — nothing to audit",
            capsule_path,
        )
        return ()
    out: list[NullAuditResult] = []
    for cell in results_list:
        if not isinstance(cell, dict):
            continue
        arrays = _extract_per_seed_arrays(cell)
        cell_id = (
            f"{cell.get('substrate_id', '?')}×{cell.get('metric_id', '?')}"
            f"@N={cell.get('N', '?')},λ={cell.get('lambda_', '?')}"
        )
        if arrays is None:
            logger.info("null_audit: cell %s lacks per-seed data — skipping", cell_id)
            continue
        p_arr, n_arr = arrays
        res = run_null_audit(
            p_arr,
            n_arr,
            n_shuffles=n_shuffles,
            rng_seed=rng_seed,
            p_value_threshold=p_value_threshold,
        )
        out.append(res)
    return tuple(out)


# ---------------------------------------------------------------------------
# C2.4-C2 — Aggregate null audit (D-002C launch-hygiene contract)
#
# The preflight validator at d002c_preflight._process_null_audit expects a
# capsule of kind d002c_null_audit_capsule_v1 with per-cell NullAuditResult
# payloads (each carrying verdict in {"PASS","FAIL"}) and a recomputed
# sha256 that matches the validator's canonical_preflight_json discipline.
#
# Until C2.4-C2 lands, the runtime path emits an aggregate_only=true escape
# capsule with results=[] — the validator accepts that as a launch-hygiene
# compromise (no real null-audit FAIL signal is exercised). This block
# closes that gap: run_null_audit_all aggregates per-cell audits across
# the full sweep grid and emits a real capsule whose sha aligns with the
# validator's recompute, so launch_allowed reflects the actual null-audit
# result.
#
# Strict scope: aggregation + capsule emission ONLY. NO claim layer. NO
# tier promotion. NO modification of the per-pair primitive contract.
# ---------------------------------------------------------------------------

NULL_AUDIT_AGGREGATE_KIND: Final[str] = "d002c_null_audit_capsule_v1"

#: Verdict emitted for cells that the capsule path lacks per-seed data
#: for. Treated as fail-closed by the aggregate verdict (NOT counted
#: as PASS): a missing audit is not evidence of a passing audit.
SKIPPED_NO_PER_SEED_DATA: Final[str] = "SKIPPED_NO_PER_SEED_DATA"


class NullAuditAggregateInvalid(RuntimeError):
    """Bad input to :func:`run_null_audit_all`.

    Raised when caller-side preconditions fail (both/neither input source
    supplied, empty results without ``aggregate_only=true``, etc.). Per-cell
    audit failures DO NOT raise — they are recorded in the capsule and
    flip ``aggregate_verdict`` to ``"FAIL"`` for the caller to handle.
    """


@dataclass(frozen=True)
class NullAuditInputCell:
    """Per-cell input payload for the aggregate audit.

    Carries the paired (precursor, null) per-seed samples for one
    (substrate × metric × N × λ) sweep cell. The ``cell_key`` is the
    canonical identity string (any stable encoding of the cell tuple
    — the aggregator does not parse it, only carries it through to the
    emitted capsule).
    """

    cell_key: str
    precursor_values: NDArray[np.float64]
    null_values: NDArray[np.float64]


@dataclass(frozen=True)
class NullAuditAggregateResult:
    """Frozen aggregate verdict across all audited sweep cells.

    Fields
    ------
    aggregate_verdict
        ``"PASS"`` iff EVERY audited cell has ``verdict == "PASS"`` AND
        zero cells were skipped for missing per-seed data. Any FAIL or
        SKIPPED cell flips it to ``"FAIL"`` (fail-closed).
    n_audited_cells
        Number of cells with a real audit verdict (PASS or FAIL).
        Does NOT include SKIPPED_NO_PER_SEED_DATA cells.
    n_pass, n_fail
        Counts within ``n_audited_cells``.
    results
        Tuple of per-cell :class:`NullAuditResult` (one per
        audited-or-skipped cell, in input traversal order). Skipped
        cells carry verdict=``SKIPPED_NO_PER_SEED_DATA``.
    sha256
        Canonical sha256 of the emitted capsule body (recomputed
        through :func:`d002c_preflight.canonical_preflight_json` so it
        matches the preflight validator's recompute bit-exactly).
    generated_at
        ISO-8601 UTC timestamp written into the capsule.
    """

    aggregate_verdict: str  # "PASS" | "FAIL"
    n_audited_cells: int
    n_pass: int
    n_fail: int
    results: tuple[NullAuditResult, ...]
    sha256: str
    generated_at: str


def _result_to_payload(res: NullAuditResult, cell_key: str) -> dict[str, Any]:
    """Convert a :class:`NullAuditResult` into the dict layout the
    preflight validator iterates over in ``_process_null_audit``.

    Keeps the canonical NullAuditResult sha (a different sha — over the
    per-cell payload — than the aggregate capsule sha) and adds the
    aggregator-only ``cell_key`` field. Skipped cells get a synthetic
    payload with verdict=SKIPPED_NO_PER_SEED_DATA and a deterministic
    sha over the cell_key alone, so the aggregate capsule is content-
    addressed even when some cells are unaudited.
    """
    return {
        "cell_key": cell_key,
        "n_seeds": int(res.n_seeds),
        "n_shuffles": int(res.n_shuffles),
        "unshuffled_abs_signal": float(res.unshuffled_abs_signal),
        "shuffled_abs_signal_median": float(res.shuffled_abs_signal_median),
        "shuffled_abs_signal_p95": float(res.shuffled_abs_signal_p95),
        "p_value_empirical": float(res.p_value_empirical),
        "verdict": str(res.verdict),
        "sha256": str(res.sha256),
    }


def _skipped_result(cell_key: str) -> NullAuditResult:
    """Build a synthetic NullAuditResult for a cell lacking per-seed
    data. The aggregate verdict treats it as FAIL (fail-closed). The
    per-cell sha is deterministic in ``cell_key`` so two runs over the
    same skipped cell produce the same aggregate capsule sha."""
    payload: dict[str, Any] = {
        "cell_key": cell_key,
        "verdict": SKIPPED_NO_PER_SEED_DATA,
    }
    sha = _sha256(payload)
    return NullAuditResult(
        n_seeds=0,
        n_shuffles=0,
        unshuffled_abs_signal=0.0,
        shuffled_abs_signal_median=0.0,
        shuffled_abs_signal_p95=0.0,
        unshuffled_greater_than_median=False,
        p_value_empirical=1.0,
        verdict=SKIPPED_NO_PER_SEED_DATA,
        sha256=sha,
    )


def _iter_cells_from_capsule(
    capsule_path: Path,
) -> tuple[tuple[str, tuple[NDArray[np.float64], NDArray[np.float64]] | None], ...]:
    """Walk a sweep capsule and yield (cell_key, arrays_or_None) pairs.

    Two on-disk shapes are accepted:

    * **C2.3 sweep capsule** — ``data["results"]`` is a list of per-cell
      dicts. The cell identity is derived from
      ``substrate_id/metric_id/N/lambda_`` fields on the dict itself.
    * **D-002D sweep checkpoint** (D-002C C2.4-A2 emitter) —
      ``data["results"]`` is a dict mapping ``cell_key`` strings to
      ``{cell_key, payload, duration_seconds}`` rows; the per-seed
      paired vectors live under ``payload.null_audit_payload``. We walk
      the dict in sorted-key order so two invocations on the same
      checkpoint emit deterministic per-cell sequences.

    Cells lacking per-seed data are yielded with ``None`` so the
    aggregator can record them as SKIPPED — they MUST NOT be silently
    dropped (a dropped cell would falsely raise aggregate=PASS).
    """
    capsule_path = Path(capsule_path)
    if not capsule_path.exists():
        raise NullAuditInvalid(f"capsule does not exist: {capsule_path}")
    try:
        raw = capsule_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise NullAuditInvalid(f"could not parse capsule {capsule_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise NullAuditInvalid(f"capsule root must be a JSON object; got {type(data).__name__}")
    results_field = data.get("results")
    out: list[tuple[str, tuple[NDArray[np.float64], NDArray[np.float64]] | None]] = []

    if isinstance(results_field, list):
        for cell in results_field:
            if not isinstance(cell, dict):
                continue
            cell_id = (
                f"[N={cell.get('N', '?')},"
                f"lambda={cell.get('lambda_', '?')},"
                f"sub={cell.get('substrate_id', '?')},"
                f"metric={cell.get('metric_id', '?')}]"
            )
            arrays = _extract_per_seed_arrays(cell)
            out.append((cell_id, arrays))
        return tuple(out)

    if isinstance(results_field, dict):
        # D-002D checkpoint layout: deterministic walk by sorted
        # cell_key so the aggregator output is stable across runs.
        for key in sorted(results_field.keys()):
            row = results_field[key]
            if not isinstance(row, dict):
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            # Skip preflight-excluded rows; they are SKIPPED_BY_PREFLIGHT
            # in the checkpoint and carry no metric values.
            if payload.get("status") == "SKIPPED_BY_PREFLIGHT":
                continue
            arrays = _extract_per_seed_arrays(payload)
            out.append((str(key), arrays))
        return tuple(out)

    return ()


def run_null_audit_all(
    *,
    output_path: Path,
    sweep_results: tuple[NullAuditInputCell, ...] | None = None,
    sweep_capsule_path: Path | None = None,
    n_shuffles: int = DEFAULT_N_SHUFFLES,
    rng_seed: int = DEFAULT_RNG_SEED,
    p_value_threshold: float = DEFAULT_P_VALUE_THRESHOLD,
    aggregate_only_if_empty: bool = False,
    generated_at: str | None = None,
) -> NullAuditAggregateResult:
    """Aggregate null audit across all sweep cells.

    Runs :func:`run_null_audit` on every (precursor, null) pair the
    caller supplies (or that the capsule path carries), records each
    per-cell verdict, and emits a ``d002c_null_audit_capsule_v1``
    capsule whose sha256 matches the preflight validator's canonical
    recompute (so ``launch_allowed=True`` is reachable for the canonical
    D-002C launch hygiene path).

    Exactly one of ``sweep_results`` or ``sweep_capsule_path`` must be
    provided.

    Parameters
    ----------
    output_path
        Where to write the emitted capsule (atomic tmp + fsync +
        os.replace; on-disk JSON is content-addressed).
    sweep_results
        Tuple of :class:`NullAuditInputCell` carrying per-cell
        paired-seed precursor/null samples.
    sweep_capsule_path
        Path to a sweep result capsule from which per-cell pair samples
        are loaded. Cells lacking per-seed data are recorded with
        ``verdict=SKIPPED_NO_PER_SEED_DATA`` — NEVER silently dropped.
    n_shuffles, rng_seed, p_value_threshold
        Forwarded per-cell to :func:`run_null_audit`.
    aggregate_only_if_empty
        Genuine-empty-grid escape hatch. If True AND the resolved cell
        list is empty, emit ``aggregate_only=true, results=[]`` (which
        the preflight accepts) instead of raising. Required for, e.g.,
        a sweep that has POS/NEG-excluded the entire grid.
    generated_at
        Optional ISO-8601 UTC timestamp. Defaults to ``_now_iso()``.
        Override only when test-pinning determinism of the sha.

    Returns
    -------
    NullAuditAggregateResult
        Frozen aggregate carrying the per-cell results, capsule sha,
        and ``aggregate_verdict`` (PASS iff every audited cell PASSes
        AND no cell was skipped).

    Raises
    ------
    NullAuditAggregateInvalid
        Both inputs missing, both inputs supplied, or empty resolved
        cell list without ``aggregate_only_if_empty=True``.
    """
    if (sweep_results is None) == (sweep_capsule_path is None):
        raise NullAuditAggregateInvalid(
            "exactly one of sweep_results or sweep_capsule_path must be provided"
        )

    # Resolve the (cell_key, arrays_or_None) sequence.
    resolved: list[tuple[str, tuple[NDArray[np.float64], NDArray[np.float64]] | None]] = []
    if sweep_results is not None:
        for cell in sweep_results:
            if not isinstance(cell, NullAuditInputCell):
                raise NullAuditAggregateInvalid(
                    f"sweep_results must contain NullAuditInputCell; got {type(cell).__name__}"
                )
            resolved.append((cell.cell_key, (cell.precursor_values, cell.null_values)))
    else:
        assert sweep_capsule_path is not None  # mypy guard
        resolved.extend(_iter_cells_from_capsule(sweep_capsule_path))

    # Empty path: aggregate_only escape hatch, or fail-closed refuse.
    if not resolved:
        if not aggregate_only_if_empty:
            raise NullAuditAggregateInvalid(
                "resolved cell list is empty and aggregate_only_if_empty=False — refuse "
                "to emit an empty real-results capsule (the preflight escape hatch must "
                "be opt-in)"
            )
        ts = generated_at if generated_at is not None else _now_iso()
        body: dict[str, Any] = {
            "kind": NULL_AUDIT_AGGREGATE_KIND,
            "generated_at": ts,
            "n_audited_cells": 0,
            "n_pass": 0,
            "n_fail": 0,
            "n_shuffles_per_cell": int(n_shuffles),
            "aggregate_verdict": "PASS",
            "aggregate_only": True,
            "results": [],
        }
        sha = _canonical_capsule_sha(body)
        body["sha256"] = sha
        _atomic_write(output_path, body)
        return NullAuditAggregateResult(
            aggregate_verdict="PASS",
            n_audited_cells=0,
            n_pass=0,
            n_fail=0,
            results=(),
            sha256=sha,
            generated_at=ts,
        )

    # Per-cell audits (or SKIPPED records).
    per_cell_results: list[NullAuditResult] = []
    per_cell_payloads: list[dict[str, Any]] = []
    n_audited = 0
    n_pass = 0
    n_fail = 0
    n_skipped = 0
    for cell_key, arrays in resolved:
        if arrays is None:
            res = _skipped_result(cell_key)
            per_cell_results.append(res)
            per_cell_payloads.append(_result_to_payload(res, cell_key))
            n_skipped += 1
            continue
        precursor_arr, null_arr = arrays
        res = run_null_audit(
            precursor_arr,
            null_arr,
            n_shuffles=n_shuffles,
            rng_seed=rng_seed,
            p_value_threshold=p_value_threshold,
        )
        per_cell_results.append(res)
        per_cell_payloads.append(_result_to_payload(res, cell_key))
        n_audited += 1
        if res.verdict == "PASS":
            n_pass += 1
        else:
            n_fail += 1

    # Aggregate verdict: fail-closed on any FAIL or any SKIPPED cell.
    aggregate_verdict = "PASS" if (n_fail == 0 and n_skipped == 0 and n_audited > 0) else "FAIL"
    ts = generated_at if generated_at is not None else _now_iso()

    body = {
        "kind": NULL_AUDIT_AGGREGATE_KIND,
        "generated_at": ts,
        "n_audited_cells": int(n_audited),
        "n_pass": int(n_pass),
        "n_fail": int(n_fail),
        "n_skipped_cells": int(n_skipped),
        "n_shuffles_per_cell": int(n_shuffles),
        "aggregate_verdict": aggregate_verdict,
        "aggregate_only": False,
        "results": per_cell_payloads,
    }
    sha = _canonical_capsule_sha(body)
    body["sha256"] = sha
    _atomic_write(output_path, body)

    return NullAuditAggregateResult(
        aggregate_verdict=aggregate_verdict,
        n_audited_cells=int(n_audited),
        n_pass=int(n_pass),
        n_fail=int(n_fail),
        results=tuple(per_cell_results),
        sha256=sha,
        generated_at=ts,
    )


def _canonical_capsule_sha(body: dict[str, Any]) -> str:
    """Compute the capsule sha using the preflight validator's canonical
    JSON discipline. Lazy import: ``d002c_preflight`` already imports
    several sibling modules (substrates, metrics, neg_control); a top-
    level import here is safe today but would couple this module to the
    preflight's import graph for all callers. We follow the C2.6
    function-scope import pattern (used for ``d002c_neg_control`` from
    ``d002c_preflight``) so any future import-graph change in
    ``d002c_preflight`` does not break ``d002c_null_audit`` at module
    load time."""
    from .d002c_preflight import canonical_preflight_json

    body_for_sha = {k: v for k, v in body.items() if k != "sha256"}
    canon = canonical_preflight_json(body_for_sha)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_N_SHUFFLES",
    "DEFAULT_RNG_SEED",
    "DEFAULT_P_VALUE_THRESHOLD",
    "MIN_N_SHUFFLES",
    "MIN_N_SEEDS",
    "NULL_AUDIT_AGGREGATE_KIND",
    "SKIPPED_NO_PER_SEED_DATA",
    "NullAuditInvalid",
    "NullAuditAggregateInvalid",
    "NullAuditInputCell",
    "NullAuditResult",
    "NullAuditAggregateResult",
    "run_null_audit",
    "run_null_audit_from_capsule",
    "run_null_audit_all",
]
