# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G — R2-B supplementary gate (M6 placebo coupling).

This module implements the R2-B aggregation logic locked in
``docs/governance/D002G_ACCEPTANCE_RULES.md`` §2 R2-B and
``docs/governance/D002G_PREREGISTRATION.yaml`` §4 supplementary_null.

Procedure (per cell)
====================
For every ``(substrate, metric, N, λ>0)`` cell:

  1. Run the M6 placebo cohort of ``n_seeds`` seeds (locked at 20 in
     the canonical cell-grid).
  2. Compute ``signal_over_ci`` for the M6 cohort vs the M1 cohort
     under the SAME BCa-bootstrap CI machinery the canonical sweep
     uses for R1.
  3. The cell is counted as a placebo-positive iff
     ``signal_over_ci > 1``.

Aggregate
=========
``FPR_R2B = #{cells with signal_over_ci > 1} / #{cells}``

Verdict: PASS iff ``FPR_R2B ≤ 0.05`` (Bonferroni-corrected per-cell
α = 0.05 / 216 is the locked numerical reference; we check the
aggregate FPR against the 0.05 envelope per the acceptance rule).

Strict scope
============
Aggregation logic ONLY. Does NOT call the sweep runner. Does NOT
realise M6 cohorts (that is :mod:`d002g_null_mechanisms` +
downstream integrator). This module is the pure post-cell
aggregator + verdict + capsule.

The function :func:`evaluate_r2b` consumes a sequence of
:class:`d002c_sweep_runner.NullAuditCellPayload` rows (already
emitted with ``null_strategy='M6_PLACEBO_COUPLING'`` per the
Phase 7 sweep-runner extension) plus per-cell BCa endpoints, and
returns an :class:`R2BVerdict`.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

from .d002c_preflight import canonical_preflight_json
from .d002c_sweep_runner import NullAuditCellPayload, bca_bootstrap_ci

# ---------------------------------------------------------------------------
# Locked R2-B parameters (frozen in the pre-registration)
# ---------------------------------------------------------------------------

#: ``acceptance.formal_decisions.r2_b_threshold`` in the pre-registration.
R2B_FPR_THRESHOLD: Final[float] = 0.05

#: ``acceptance.formal_decisions.multiple_testing_correction.n_cells`` in
#: the pre-registration. Locked at 216 for the canonical grid.
R2B_BONFERRONI_N_CELLS: Final[int] = 216

#: ``acceptance.formal_decisions.ci_alpha`` in the pre-registration.
R2B_CI_ALPHA: Final[float] = 0.05

#: Capsule version stamped onto every emission.
R2B_CAPSULE_VERSION: Final[str] = "d002g_r2b_capsule_v1"

# Strike-R2: M6 informativeness is CONDITIONAL on metric-topology coupling.
# Per-cell coupling indicator is Cohen's-d-like: |signal_mean| / pooled_sd
# minus the per-cohort noise floor 1/sqrt(n_seeds) (expected scale of
# |mean|/sd under H0 at finite n). Aggregate floor is set at 0.5 — Cohen's
# medium-effect convention. Below the floor the cohort's metric is
# topology-blind and the verdict downgrades to
# ``R2B_INDETERMINATE_VERDICT`` — neither PASS nor FAIL.
R2B_TOPOLOGY_COUPLING_FLOOR: Final[float] = 0.50
R2B_INDETERMINATE_VERDICT: Final[str] = "INDETERMINATE_R2B_TOPOLOGY_BLIND_METRIC"

# P0-2 Codex review fix: provenance preflight contract. R2-B aggregates
# ONLY M6 placebo payloads. A row that is missing ``null_strategy``,
# carries the legacy CRN strategy, or carries an M1 cohort must be
# rejected fail-closed BEFORE any per-cell statistic is computed. The
# verdict literal below is stamped on the returned R2BVerdict and
# downstream consumers can pattern-match it. R2-B provenance is
# INPUT-VALIDATED, not OUTPUT-INVENTED.
R2B_INVALID_NON_M6_PAYLOAD_VERDICT: Final[str] = "INVALID_R2B_NON_M6_PAYLOAD"

#: Required schema fields on every row before R2-B will compute any
#: statistic. ``null_seed`` is allowed to be None for the legacy v1
#: payload schema; we only reject if the field is missing as an
#: attribute (schema-shape violation).
_R2B_REQUIRED_PAYLOAD_FIELDS: Final[tuple[str, ...]] = (
    "null_strategy",
    "lambda_",
    "substrate_id",
    "cell_key",
    "metric_id",
    "N",
    "precursor_values",
    "null_values",
)


class R2BGateInvalid(RuntimeError):
    """Bad input to :func:`evaluate_r2b`.

    Distinct from :exc:`R2BProvenanceInvalid`: ``R2BGateInvalid``
    signals a STRUCTURAL refusal (empty cohort, malformed array, bad
    parameter range). Provenance failures use the verdict-channel
    return path described on :data:`R2B_INVALID_NON_M6_PAYLOAD_VERDICT`
    so consumers can pattern-match without catching exceptions.
    """


class R2BProvenanceInvalid(RuntimeError):
    """One or more rows failed the M6 provenance preflight.

    Raised by :func:`_r2b_provenance_preflight`. The aggregator catches
    this internally and converts to a verdict-channel refusal
    (``R2B_INVALID_NON_M6_PAYLOAD_VERDICT``) so downstream consumers can
    pattern-match without exception-handling discipline. The exception
    itself is kept for unit-test introspection of the precise failure
    reason.
    """


# ---------------------------------------------------------------------------
# Per-cell + aggregate dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class R2BCellResult:
    """One placebo cohort's R2-B evidence."""

    cell_key: str
    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_seeds: int
    signal_mean: float
    bca_ci_lo: float
    bca_ci_hi: float
    signal_over_ci: float
    is_placebo_positive: bool
    null_strategy: str
    # Strike-R2: per-cell metric-topology-coupling indicator. The
    # indicator is the CI half-width of the placebo-vs-baseline mean
    # divided by the pooled cohort std-dev (large = metric responds to
    # topology rearrangement under M6 with a comparable-scale CI;
    # small = metric is insensitive to topology, M6 gives no signal).
    topology_coupling_indicator: float


@dataclass(frozen=True)
class R2BVerdict:
    """Aggregate R2-B verdict over a cell grid.

    The verdict literal is one of
      * ``"PASS"`` — FPR_R2B ≤ threshold AND topology_coupling_indicator
        mean ≥ floor;
      * ``"FAIL"`` — FPR_R2B > threshold AND coupling indicator OK;
      * ``"INDETERMINATE_R2B_TOPOLOGY_BLIND_METRIC"`` — coupling
        indicator mean < floor; M6 cannot certify either way because
        the metric is topology-blind.
    """

    verdict: str
    fpr_r2b: float
    threshold: float
    n_cells: int
    n_placebo_positive: int
    bonferroni_n_cells: int
    bonferroni_alpha_per_cell: float
    ci_alpha: float
    cell_results: tuple[R2BCellResult, ...]
    sha256: str
    # Strike-R2: aggregate metric-topology-coupling indicator.
    topology_coupling_indicator_mean: float
    topology_coupling_floor: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _finite_or_str(x: float) -> Any:
    f = float(x)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Infinity" if f > 0 else "-Infinity"
    return f


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _per_cell_signal_over_ci(
    placebo: NullAuditCellPayload,
    *,
    n_bootstrap: int,
    ci_alpha: float,
    rng_seed: int,
) -> tuple[float, float, float, float]:
    """Compute (signal_mean, ci_lo, ci_hi, signal_over_ci) on a placebo payload.

    The placebo payload carries paired (precursor_values, null_values).
    Under M6 the "precursor" leg is the placebo-injected cohort and the
    "null" leg is the matched M1 baseline cohort; ``signal_mean`` is
    therefore the placebo-vs-baseline difference. We apply the same BCa
    routine used for R1 (``signal_over_ci = |signal_mean| / CI_half_width``).
    """
    p_arr = np.asarray(placebo.precursor_values, dtype=np.float64)
    n_arr = np.asarray(placebo.null_values, dtype=np.float64)
    if p_arr.shape != n_arr.shape:
        raise R2BGateInvalid(
            f"placebo paired arrays mismatch: precursor={p_arr.shape} null={n_arr.shape}"
        )
    if p_arr.size < 2:
        raise R2BGateInvalid(f"placebo paired arrays too short: size={p_arr.size}")
    diffs = p_arr - n_arr
    s_mean = float(diffs.mean())
    ci_lo, ci_hi = bca_bootstrap_ci(diffs, int(n_bootstrap), float(ci_alpha), seed=int(rng_seed))
    half_width = 0.5 * (ci_hi - ci_lo)
    if half_width > 0.0:
        soc = abs(s_mean) / half_width
    elif s_mean == 0.0:
        soc = 0.0
    else:
        soc = math.inf
    return s_mean, float(ci_lo), float(ci_hi), float(soc)


def _sha_over(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_preflight_json(payload).encode("utf-8")).hexdigest()


def _r2b_provenance_preflight(
    per_cell_payloads: Sequence[NullAuditCellPayload],
) -> tuple[int, dict[str, Any]]:
    """P0-2 fix: enforce M6-only provenance before any statistic.

    Returns
    -------
    (rejected_count, audit_dict)
        ``rejected_count`` is the number of rows that failed the
        preflight; the audit_dict carries per-row evidence for the
        capsule. ``rejected_count == 0`` is the precondition for the
        aggregator to compute per-cell statistics.

    Raises
    ------
    R2BProvenanceInvalid
        At least one row failed the preflight. The exception message
        identifies the first failing row + reason; the audit_dict is
        attached on the exception's ``audit`` attribute.

    Why this is the right discipline
    --------------------------------
    The aggregator previously stamped ``null_strategy="M6_PLACEBO_COUPLING"``
    on every output cell row regardless of input provenance. Mixed
    or mis-routed inputs (e.g. legacy v1 payloads with
    ``null_strategy="D002C_PAIRED_CRN_LEGACY"``, or accidentally
    included M1 cohort rows) would silently produce R2-B verdicts
    against the wrong cohort and mislabel provenance.

    Provenance MUST be input-validated, not output-invented. This
    function is the fail-closed gate; the verdict-channel refusal
    converts the exception into a structured verdict for the consumer.
    """
    rejects: list[dict[str, Any]] = []
    for i, row in enumerate(per_cell_payloads):
        # Schema shape: every required attribute must exist. We assert
        # by ``hasattr`` so this catches both dataclass-typed and
        # dict-typed inputs.
        missing_fields = [f for f in _R2B_REQUIRED_PAYLOAD_FIELDS if not hasattr(row, f)]
        if missing_fields:
            rejects.append(
                {
                    "row_index": i,
                    "reason": "MISSING_REQUIRED_FIELDS",
                    "missing_fields": list(missing_fields),
                    "row_cell_key": getattr(row, "cell_key", None),
                }
            )
            continue
        strategy = str(getattr(row, "null_strategy", ""))
        if strategy != "M6_PLACEBO_COUPLING":
            rejects.append(
                {
                    "row_index": i,
                    "reason": "NON_M6_NULL_STRATEGY",
                    "found_null_strategy": strategy,
                    "expected_null_strategy": "M6_PLACEBO_COUPLING",
                    "row_cell_key": str(getattr(row, "cell_key", "")),
                }
            )
    audit: dict[str, Any] = {
        "rejected_count": len(rejects),
        "rejected_rows": rejects,
        "required_fields": list(_R2B_REQUIRED_PAYLOAD_FIELDS),
        "expected_null_strategy": "M6_PLACEBO_COUPLING",
        "n_cells_examined": len(per_cell_payloads),
    }
    if rejects:
        exc = R2BProvenanceInvalid(
            f"R2-B provenance preflight rejected {len(rejects)} row(s); "
            f"first failure: {rejects[0]!r}"
        )
        # Stash audit on the exception so callers can introspect.
        exc.audit = audit  # type: ignore[attr-defined]
        raise exc
    return 0, audit


def _invalid_payload_verdict(
    audit: dict[str, Any],
    *,
    ci_alpha: float,
    fpr_threshold: float,
    bonferroni_n_cells: int,
    metadata_extra: dict[str, Any] | None,
) -> R2BVerdict:
    """Build the fail-closed verdict for the non-M6-payload refusal path.

    No per-cell statistics are computed; the verdict carries the
    provenance audit in ``metadata`` so the consumer can locate the
    failing rows. ``fpr_r2b`` is set to NaN so any consumer that
    accidentally treats this as a normal verdict immediately surfaces
    the anomaly.
    """
    md = dict(metadata_extra or {})
    md["r2b_provenance_audit"] = audit
    body: dict[str, Any] = {
        "capsule_version": R2B_CAPSULE_VERSION,
        "verdict": R2B_INVALID_NON_M6_PAYLOAD_VERDICT,
        "fpr_r2b": "NaN",
        "threshold": _finite_or_str(float(fpr_threshold)),
        "n_cells": 0,
        "n_placebo_positive": 0,
        "bonferroni_n_cells": int(bonferroni_n_cells),
        "bonferroni_alpha_per_cell": _finite_or_str(
            float(fpr_threshold) / float(bonferroni_n_cells)
        ),
        "ci_alpha": _finite_or_str(float(ci_alpha)),
        "topology_coupling_indicator_mean": "NaN",
        "topology_coupling_floor": _finite_or_str(float(R2B_TOPOLOGY_COUPLING_FLOOR)),
        "cell_results": [],
        "metadata": md,
    }
    sha = _sha_over(body)
    return R2BVerdict(
        verdict=R2B_INVALID_NON_M6_PAYLOAD_VERDICT,
        fpr_r2b=float("nan"),
        threshold=float(fpr_threshold),
        n_cells=0,
        n_placebo_positive=0,
        bonferroni_n_cells=int(bonferroni_n_cells),
        bonferroni_alpha_per_cell=float(fpr_threshold) / float(bonferroni_n_cells),
        ci_alpha=float(ci_alpha),
        cell_results=(),
        sha256=sha,
        topology_coupling_indicator_mean=float("nan"),
        topology_coupling_floor=float(R2B_TOPOLOGY_COUPLING_FLOOR),
        metadata=md,
    )


# ---------------------------------------------------------------------------
# Public aggregator
# ---------------------------------------------------------------------------


def evaluate_r2b(
    per_cell_payloads: Sequence[NullAuditCellPayload],
    *,
    n_bootstrap: int,
    ci_alpha: float = R2B_CI_ALPHA,
    bca_seed: int = 42,
    fpr_threshold: float = R2B_FPR_THRESHOLD,
    bonferroni_n_cells: int = R2B_BONFERRONI_N_CELLS,
    metadata_extra: dict[str, Any] | None = None,
) -> R2BVerdict:
    """Aggregate R2-B verdict over a cohort of M6 placebo cell payloads.

    Parameters
    ----------
    per_cell_payloads
        Iterable of :class:`NullAuditCellPayload` rows from the M6
        cohort sweep. Each row MUST carry ``lambda_ > 0`` (the
        pre-registration scopes R2-B to ``λ > 0`` cells). Rows with
        ``lambda_ <= 0`` are refused fail-closed.
    n_bootstrap
        BCa bootstrap resample count. Same as the canonical sweep's
        n_bootstrap (locked at 16 in the pre-registration).
    ci_alpha
        Two-sided coverage gap (locked at 0.05).
    bca_seed
        Base seed for the BCa RNG. Per-cell seeds are derived
        deterministically from ``bca_seed XOR <cell_key sha>`` so two
        runs over the same payloads produce identical R2-B verdicts.
    fpr_threshold
        Aggregate FPR threshold (locked at 0.05).
    bonferroni_n_cells
        Carried into the capsule for downstream consumers; the verdict
        itself uses the aggregate-FPR rule per the acceptance document.

    Returns
    -------
    R2BVerdict
        Frozen dataclass with per-cell evidence and PASS/FAIL.

    Raises
    ------
    R2BGateInvalid
        Empty cohort, lambda_ <= 0 row, mismatched paired arrays.
    """
    if not isinstance(per_cell_payloads, Sequence):
        # Defensive: tests sometimes pass generators. Materialise once.
        per_cell_payloads = list(per_cell_payloads)
    if len(per_cell_payloads) == 0:
        raise R2BGateInvalid("evaluate_r2b: empty per_cell_payloads")
    if int(n_bootstrap) < 2:
        raise R2BGateInvalid(f"n_bootstrap must be >= 2; got {n_bootstrap}")
    if not (0.0 < ci_alpha < 1.0):
        raise R2BGateInvalid(f"ci_alpha must lie in (0, 1); got {ci_alpha}")
    if not (0.0 < fpr_threshold < 1.0):
        raise R2BGateInvalid(f"fpr_threshold must lie in (0, 1); got {fpr_threshold}")

    # P0-2 Codex review fix: provenance preflight. Every row must carry
    # ``null_strategy == "M6_PLACEBO_COUPLING"`` plus the full schema.
    # Mixed / M1 / legacy / missing-strategy rows trigger
    # R2B_INVALID_NON_M6_PAYLOAD_VERDICT — NO statistics are computed.
    # The aggregator MUST NOT stamp M6 provenance on payloads that did
    # not originate from M6 cohorts. Type discipline first.
    for i, row in enumerate(per_cell_payloads):
        if not isinstance(row, NullAuditCellPayload):
            raise R2BGateInvalid(
                f"per_cell_payloads[{i}] must be NullAuditCellPayload; got {type(row).__name__}"
            )
    try:
        _r2b_provenance_preflight(per_cell_payloads)
    except R2BProvenanceInvalid as exc:
        audit = getattr(exc, "audit", {"rejected_rows": [], "rejected_count": -1})
        return _invalid_payload_verdict(
            audit,
            ci_alpha=float(ci_alpha),
            fpr_threshold=float(fpr_threshold),
            bonferroni_n_cells=int(bonferroni_n_cells),
            metadata_extra=metadata_extra,
        )

    cell_results: list[R2BCellResult] = []
    for row in per_cell_payloads:
        if float(row.lambda_) <= 0.0:
            raise R2BGateInvalid(
                f"R2-B is scoped to lambda_ > 0; row {row.cell_key!r} has lambda_={row.lambda_!r}"
            )
        # Per-cell BCa seed: deterministic, dependent on cell_key.
        per_cell_seed = int(bca_seed) ^ (
            int.from_bytes(hashlib.sha256(row.cell_key.encode("utf-8")).digest()[:4], "big")
        )
        s_mean, ci_lo, ci_hi, soc = _per_cell_signal_over_ci(
            row,
            n_bootstrap=int(n_bootstrap),
            ci_alpha=float(ci_alpha),
            rng_seed=per_cell_seed,
        )
        is_pos = bool(math.isfinite(soc) and soc > 1.0) or (
            not math.isfinite(soc) and soc == math.inf
        )
        # Strike-R2: topology-coupling indicator. Definition:
        #   pooled_sd = max(std(precursor), std(null), 1e-12)
        #   noise_floor = 1/sqrt(n_seeds)   (expected scale of |mean|/sd
        #                                    under H0 at finite n)
        #   indicator = max(0, |s_mean| / pooled_sd - noise_floor)
        # A spectrally-driven metric on a placebo cohort separates the
        # arms by many SD-units (≫ noise floor); a topology-blind metric
        # keeps the arms statistically indistinguishable, so |s_mean|/sd
        # sits at the noise floor and the indicator collapses to ≈ 0.
        # Subtracting the noise floor removes the small-n inflation that
        # mistakenly read 0.35 as "coupled" in early R2 tests.
        p_arr = np.asarray(row.precursor_values, dtype=np.float64)
        n_arr = np.asarray(row.null_values, dtype=np.float64)
        pooled_sd = max(float(np.std(p_arr, ddof=1)), float(np.std(n_arr, ddof=1)), 1e-12)
        n_seeds = int(p_arr.size)
        noise_floor_local = 1.0 / math.sqrt(float(n_seeds)) if n_seeds > 0 else 0.0
        raw_cohen = abs(float(s_mean)) / pooled_sd
        coupling_indicator = max(0.0, raw_cohen - noise_floor_local)
        cell_results.append(
            R2BCellResult(
                cell_key=row.cell_key,
                substrate_id=row.substrate_id,
                metric_id=row.metric_id,
                N=int(row.N),
                lambda_=float(row.lambda_),
                n_seeds=int(len(row.precursor_values)),
                signal_mean=float(s_mean),
                bca_ci_lo=float(ci_lo),
                bca_ci_hi=float(ci_hi),
                signal_over_ci=float(soc),
                is_placebo_positive=bool(is_pos),
                null_strategy="M6_PLACEBO_COUPLING",
                topology_coupling_indicator=float(coupling_indicator),
            )
        )

    n_cells = len(cell_results)
    n_pos = sum(1 for r in cell_results if r.is_placebo_positive)
    fpr = float(n_pos) / float(n_cells)
    bonferroni_alpha = float(fpr_threshold) / float(bonferroni_n_cells)

    # Strike-R2: aggregate coupling indicator gates the verdict.
    coupling_mean = float(
        np.mean([r.topology_coupling_indicator for r in cell_results]) if cell_results else 0.0
    )
    if coupling_mean < R2B_TOPOLOGY_COUPLING_FLOOR:
        verdict_str = R2B_INDETERMINATE_VERDICT
    else:
        verdict_str = "PASS" if fpr <= float(fpr_threshold) else "FAIL"

    sha_body: dict[str, Any] = {
        "capsule_version": R2B_CAPSULE_VERSION,
        "verdict": verdict_str,
        "fpr_r2b": _finite_or_str(fpr),
        "threshold": _finite_or_str(float(fpr_threshold)),
        "n_cells": int(n_cells),
        "n_placebo_positive": int(n_pos),
        "bonferroni_n_cells": int(bonferroni_n_cells),
        "bonferroni_alpha_per_cell": _finite_or_str(bonferroni_alpha),
        "ci_alpha": _finite_or_str(float(ci_alpha)),
        "topology_coupling_indicator_mean": _finite_or_str(coupling_mean),
        "topology_coupling_floor": _finite_or_str(float(R2B_TOPOLOGY_COUPLING_FLOOR)),
        "cell_results": [
            {
                "cell_key": r.cell_key,
                "substrate_id": r.substrate_id,
                "metric_id": r.metric_id,
                "N": int(r.N),
                "lambda_": _finite_or_str(r.lambda_),
                "n_seeds": int(r.n_seeds),
                "signal_mean": _finite_or_str(r.signal_mean),
                "bca_ci_lo": _finite_or_str(r.bca_ci_lo),
                "bca_ci_hi": _finite_or_str(r.bca_ci_hi),
                "signal_over_ci": _finite_or_str(r.signal_over_ci),
                "is_placebo_positive": bool(r.is_placebo_positive),
                "null_strategy": r.null_strategy,
                "topology_coupling_indicator": _finite_or_str(r.topology_coupling_indicator),
            }
            for r in cell_results
        ],
        "metadata": dict(metadata_extra or {}),
    }
    sha = _sha_over(sha_body)

    return R2BVerdict(
        verdict=verdict_str,
        fpr_r2b=float(fpr),
        threshold=float(fpr_threshold),
        n_cells=int(n_cells),
        n_placebo_positive=int(n_pos),
        bonferroni_n_cells=int(bonferroni_n_cells),
        bonferroni_alpha_per_cell=bonferroni_alpha,
        ci_alpha=float(ci_alpha),
        cell_results=tuple(cell_results),
        sha256=sha,
        topology_coupling_indicator_mean=float(coupling_mean),
        topology_coupling_floor=float(R2B_TOPOLOGY_COUPLING_FLOOR),
        metadata=dict(metadata_extra or {}),
    )


def _rule_correlation_matrix(
    cell_results: tuple[R2BCellResult, ...],
) -> tuple[list[str], list[list[float]]]:
    """Strike-R7: empirical Pearson correlation across rule statistics.

    Statistics:
      * ``signal_over_ci`` — R1/R2/R2-B common driver
      * ``topology_coupling_indicator`` — Strike-R2 indicator
      * ``signal_mean`` — direction-bearing summary
      * ``bca_ci_half_width`` — CI half-width (denominator of soc)

    Returns ``(labels, matrix)`` where matrix is k×k, diagonal == 1.
    With a single cell the correlation matrix is degenerate (variance 0
    across the singleton); we return an identity matrix in that case
    so the diagonal invariant still holds.
    """
    labels = [
        "signal_over_ci",
        "topology_coupling_indicator",
        "signal_mean",
        "bca_ci_half_width",
    ]
    k = len(labels)
    if not cell_results:
        return labels, [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    n = len(cell_results)
    arrs = {
        "signal_over_ci": np.asarray(
            [(r.signal_over_ci if math.isfinite(r.signal_over_ci) else 0.0) for r in cell_results],
            dtype=np.float64,
        ),
        "topology_coupling_indicator": np.asarray(
            [r.topology_coupling_indicator for r in cell_results],
            dtype=np.float64,
        ),
        "signal_mean": np.asarray(
            [r.signal_mean for r in cell_results],
            dtype=np.float64,
        ),
        "bca_ci_half_width": np.asarray(
            [0.5 * (r.bca_ci_hi - r.bca_ci_lo) for r in cell_results],
            dtype=np.float64,
        ),
    }
    if n < 2:
        return labels, [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    mat: list[list[float]] = [[0.0] * k for _ in range(k)]
    for i, li in enumerate(labels):
        for j, lj in enumerate(labels):
            ai = arrs[li]
            aj = arrs[lj]
            std_i = float(np.std(ai, ddof=1))
            std_j = float(np.std(aj, ddof=1))
            if i == j:
                mat[i][j] = 1.0
            elif std_i <= 0.0 or std_j <= 0.0:
                # Degenerate (constant) statistic — correlation undefined.
                # Emit 0 by convention; the consumer reads it as
                # "uncorrelated by lack of variance".
                mat[i][j] = 0.0
            else:
                cov_ij = float(np.cov(ai, aj, ddof=1)[0, 1])
                rho = cov_ij / (std_i * std_j)
                # Clip to [-1, 1] to absorb tiny float overshoot.
                mat[i][j] = float(max(-1.0, min(1.0, rho)))
    return labels, mat


def r2b_verdict_to_capsule(verdict: R2BVerdict) -> dict[str, Any]:
    """JSON-pure capsule for on-disk emission."""
    labels, mat = _rule_correlation_matrix(verdict.cell_results)
    return {
        "capsule_version": R2B_CAPSULE_VERSION,
        "generated_at": _now_iso(),
        "verdict": verdict.verdict,
        "fpr_r2b": _finite_or_str(verdict.fpr_r2b),
        "threshold": _finite_or_str(verdict.threshold),
        "n_cells": int(verdict.n_cells),
        "n_placebo_positive": int(verdict.n_placebo_positive),
        "bonferroni_n_cells": int(verdict.bonferroni_n_cells),
        "bonferroni_alpha_per_cell": _finite_or_str(verdict.bonferroni_alpha_per_cell),
        "ci_alpha": _finite_or_str(verdict.ci_alpha),
        # Strike-R2: coupling indicator carried through into the on-disk capsule.
        "topology_coupling_indicator_mean": _finite_or_str(
            verdict.topology_coupling_indicator_mean
        ),
        "topology_coupling_floor": _finite_or_str(verdict.topology_coupling_floor),
        # Strike-R7: empirical correlation matrix across rule statistics.
        "rule_correlation_labels": list(labels),
        "rule_correlation_matrix": [[_finite_or_str(v) for v in row] for row in mat],
        "cell_results": [
            {
                "cell_key": r.cell_key,
                "substrate_id": r.substrate_id,
                "metric_id": r.metric_id,
                "N": int(r.N),
                "lambda_": _finite_or_str(r.lambda_),
                "n_seeds": int(r.n_seeds),
                "signal_mean": _finite_or_str(r.signal_mean),
                "bca_ci_lo": _finite_or_str(r.bca_ci_lo),
                "bca_ci_hi": _finite_or_str(r.bca_ci_hi),
                "signal_over_ci": _finite_or_str(r.signal_over_ci),
                "is_placebo_positive": bool(r.is_placebo_positive),
                "null_strategy": r.null_strategy,
                "topology_coupling_indicator": _finite_or_str(r.topology_coupling_indicator),
            }
            for r in verdict.cell_results
        ],
        "metadata": dict(verdict.metadata),
        "sha256": verdict.sha256,
    }


__all__ = [
    "R2B_BONFERRONI_N_CELLS",
    "R2B_CAPSULE_VERSION",
    "R2B_CI_ALPHA",
    "R2B_FPR_THRESHOLD",
    "R2B_INDETERMINATE_VERDICT",
    "R2B_INVALID_NON_M6_PAYLOAD_VERDICT",
    "R2B_TOPOLOGY_COUPLING_FLOOR",
    "R2BCellResult",
    "R2BGateInvalid",
    "R2BProvenanceInvalid",
    "R2BVerdict",
    "evaluate_r2b",
    "r2b_verdict_to_capsule",
]
