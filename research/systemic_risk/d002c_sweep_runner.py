# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.4 — Signal Amplification Sweep runner core.

Rationale
=========
The D-002C pre-registration commits 216 cells (3 substrates × 3
metrics × 3 N × 6 λ × ...) to a falsification protocol whose
verdict is computed mechanically from a BCa-bootstrap CI on the
per-seed signal differences. This module is the driver that walks
the cell grid, dispatches a single cell to substrate → integrator
→ metric → BCa-CI → direction, and writes each completed cell
through the D-002D :class:`CheckpointManager` for atomic per-cell
durability.

API
===
* :class:`SweepCellOutput` — frozen per-cell payload (sha256
  content-addressed; same inputs → same sha).
* :class:`SweepResult`     — frozen aggregate over the whole
  cell grid (carries the per-cell tuple + a stable aggregate
  sha256).
* :func:`run_one_cell`     — one (substrate, metric, N, λ) cell:
  paired-CRN over ``n_seeds`` substrate realisations + Kuramoto
  integrations, BCa bootstrap CI on the per-seed diff vector,
  direction by sign-count consistency.
* :func:`run_sweep`        — full sweep over the locked grid with
  resumable per-cell checkpointing. Refuses to launch on any
  pre-registration mismatch (delegates to
  :func:`d002c_preregistration.validate_sweep_config`).

Paired-CRN protocol
===================
Mirrors the C2.3 CRN validator:
* For seed ``i`` in ``[base, base + n_seeds)``:
    substrate.realize(seed=i) → ``(K_baseline, K_precursor)``
    simulate_kuramoto(K_baseline, seed=i)  → R/θ trajectory
    simulate_kuramoto(K_precursor, seed=i) → R/θ trajectory
    metric.evaluate(...) on each → ``(eval_null, eval_precursor)``
* Same seed → same ω draw → same θ(0). Shared noise cancels in
  the metric difference. This is the only stream-CRN protocol
  that survives the proof from C2.3.

BCa bootstrap CI
================
First-principles BCa (DiCiccio & Efron 1996):

1. θ̂ = mean(samples) on the original sample.
2. Resample with replacement ``n_bootstrap`` times → θ̂_b.
3. Bias correction
       z_0 = Φ^{-1}( #{θ̂_b < θ̂} / n_bootstrap )
4. Acceleration via jackknife
       θ̂_{-i} = mean(samples without i)
       θ̂_{··} = mean(θ̂_{-i})
       a = Σ(θ̂_{··} − θ̂_{-i})³ / [6 · (Σ(θ̂_{··} − θ̂_{-i})²)^{3/2}]
5. Adjusted endpoints
       α₁ = Φ(z_0 + (z_0 + z_{α/2})   / (1 − a (z_0 + z_{α/2})))
       α₂ = Φ(z_0 + (z_0 + z_{1−α/2}) / (1 − a (z_0 + z_{1−α/2})))
       CI = (percentile(θ̂_b, α₁), percentile(θ̂_b, α₂))

Edge cases:
* ``n_bootstrap < 2``         → ValueError.
* Empty / single-element sample → ValueError.
* Zero bootstrap variance     → CI collapses to (θ̂, θ̂).
* Zero jackknife denominator  → ``a = 0`` (degenerate but defined).
* ``z_0`` saturated by an empty resample tail → clamped to a
  finite value before substitution.

Strict scope
============
Sweep driver + BCa bootstrap. NO claim layer. NO threshold
tuning. NO post-hoc relaxation. The verdict that consumes
:class:`SweepResult` is the C2.5 acceptance evaluator (pending);
this module emits no claim of its own.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

from .d002c_kuramoto import (
    DEFAULT_OMEGA_GAMMA,
    DEFAULT_STEPS_PER_QUARTER,
    simulate_kuramoto,
)
from .d002c_metrics import (
    METRIC_BY_ID,
    Metric,
    MetricEvaluation,
    signal_mean,
)
from .d002c_preflight import (
    PreflightCapsulePaths,
    PreflightDecision,
    PreflightLaunchRefused,
    SkippedCell,
    apply_preflight_to_grid,
    assert_preflight_launch_allowed,
    canonical_preflight_json,
    load_and_validate_preflight_capsules,
)
from .d002c_preregistration import (
    D002CPreregistration,
    validate_sweep_config,
)
from .d002c_substrates import (
    EVENT_QUARTER,
    PRE_EVENT_START_QUARTER,
    SUBSTRATE_BY_ID,
    Substrate,
)
from .sweep_checkpoint import (
    CellResult,
    CheckpointManager,
    canonical_json,
    cell_key,
)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: The pre-event window in metric-step units depends on the integrator's
#: ``steps_per_quarter``. The metric layer reports values relative to the
#: window start; the right-censoring horizon for the KM aggregator equals
#: the window length in steps.
PRE_EVENT_WINDOW_QUARTERS: Final[int] = EVENT_QUARTER - PRE_EVENT_START_QUARTER

#: Default code sha used by :func:`run_sweep` if the caller does not pass
#: an explicit ``code_sha``. The CheckpointManager stores this as soft
#: metadata; a drift versus the on-disk file is a warning, not a refusal.
DEFAULT_CODE_SHA: Final[str] = "d002c_sweep_runner@unknown"

#: Version tag stamped onto every :class:`NullAuditCellPayload`. Bumped
#: only when the per-seed metric layout changes in a way that invalidates
#: previously persisted payloads. The aggregator does not parse this; it
#: is folded into the payload sha256 so a metric-layer rev is visible as
#: a sha drift to the audit row.
METRIC_VERSION: Final[str] = "d002c_metrics_v1"

#: Version tag stamped onto every :class:`NullAuditCellPayload`. Bumped
#: only when the substrate realisation contract changes (so the paired
#: precursor/null realisations stop being byte-equivalent across runs).
SUBSTRATE_VERSION: Final[str] = "d002c_substrates_v1"

#: Payload schema tag carried inside :class:`NullAuditCellPayload`.
#: ``d002c_null_audit_cell_v1`` is the legacy (D-002C / paired-CRN) layout
#: with no ``null_strategy`` / ``null_seed`` fields. ``d002c_null_audit_cell_v2``
#: is the D-002G extension that adds:
#:
#:   * ``null_strategy`` — one of {"M1_INDEPENDENT_SEED",
#:     "M6_PLACEBO_COUPLING", "D002C_PAIRED_CRN_LEGACY"}.
#:   * ``null_seed`` — explicit seed used to draw the null cohort
#:     (None under legacy paired-CRN).
#:
#: A v1 payload reads back as ``payload_schema=v1`` with
#: ``null_strategy="D002C_PAIRED_CRN_LEGACY"`` and ``null_seed=None`` —
#: the sha-input is the v1 shape so legacy payloads round-trip bit-exactly.
PAYLOAD_SCHEMA_V1: Final[str] = "d002c_null_audit_cell_v1"
PAYLOAD_SCHEMA_V2: Final[str] = "d002c_null_audit_cell_v2"

#: Default null-strategy tag for v1 emissions and pre-A2 callers.
DEFAULT_NULL_STRATEGY: Final[str] = "D002C_PAIRED_CRN_LEGACY"


class SweepRunnerInvalid(RuntimeError):
    """Bad input to :func:`run_one_cell` / :func:`run_sweep`."""


class NullAuditPayloadInvalid(RuntimeError):
    """Bad input to :class:`NullAuditCellPayload` construction / reload.

    Raised by :meth:`NullAuditCellPayload.from_payload_dict` on any
    contract violation (paired-array length mismatch, non-finite element,
    paired_by_seed=False, sha mismatch). Fail-closed: a corrupted on-disk
    payload MUST NOT be silently accepted into the null-audit aggregator.
    """


# ---------------------------------------------------------------------------
# Determinism helpers (forward-declared so the payload dataclass can use
# them; the bulk of the helper section is below the dataclass cluster).
# ---------------------------------------------------------------------------


def _finite_or_str(x: float) -> Any:
    """JSON-safe float: non-finite → string sentinel (NaN/+Inf/-Inf).

    Canonical JSON disallows non-finite floats; the sweep contract
    requires every cell payload to be JSON-serialisable so the
    checkpoint ledger and the sha256 are well-defined. We replace
    non-finite floats with a string sentinel ("NaN", "Infinity",
    "-Infinity") that is deterministic + hashable + reviewable.
    """
    f = float(x)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Infinity" if f > 0 else "-Infinity"
    return f


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_preflight_canonical(payload: dict[str, Any]) -> str:
    """sha256 over the preflight-canonical JSON form.

    The :class:`NullAuditCellPayload` content-addresses itself with the
    SAME canonical JSON discipline the C2.4-D preflight validator uses
    so the post-sweep aggregator can recompute it bit-exactly via
    :func:`d002c_preflight.canonical_preflight_json`. This is the C2.6
    sha-alignment pattern: one canonical formula across writer + reader.
    """
    return hashlib.sha256(canonical_preflight_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Frozen outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NullAuditCellPayload:
    """Per-cell paired-CRN evidence for the post-sweep null audit.

    D-002C C2.4-A2 data contract. Carries the per-seed precursor / null
    metric values BEFORE aggregation so the C2.4-C2 null-audit aggregator
    (``run_null_audit_all``) can run the permutation test on the actual
    paired vector rather than on a reconstructed surrogate.

    Invariants
    ----------
    * ``len(seed_ids) == len(precursor_values) == len(null_values)``
    * ``paired_by_seed is True`` under the paired-CRN protocol locked in
      C2.3; the aggregator MUST refuse a payload with this flag False.
    * Every element of ``precursor_values`` / ``null_values`` is finite.
    * ``sha256`` is content-addressed over
      :func:`d002c_preflight.canonical_preflight_json` of the payload
      (sans the sha256 field itself and sans ``generated_at``, so a
      machine-clock difference does not change the sha). This is the
      same canonical formula the preflight validator uses on the
      ``d002c_null_audit_capsule_v1`` aggregate.

    Fail-closed semantics
    ---------------------
    A cell that the preflight gates skipped (``SKIPPED_BY_PREFLIGHT``)
    does NOT receive a payload — the absence of evidence is recorded as
    ``SKIPPED_BY_PREFLIGHT`` in the checkpoint and the aggregator's
    ``SKIPPED_NO_PER_SEED_DATA`` sentinel is reserved for cells that
    failed to emit a payload through any other path.
    """

    cell_key: str
    N: int
    lambda_: float
    substrate_id: str
    metric_id: str
    seed_ids: tuple[int, ...]
    precursor_values: tuple[float, ...]
    null_values: tuple[float, ...]
    paired_by_seed: bool
    crn_identity_hash: str
    metric_version: str
    substrate_version: str
    generated_at: str
    sha256: str
    # D-002G v1/v2 schema branching (Strike-R7 documentation; v1 default
    # preserves bit-exact legacy sha).
    payload_schema: str = PAYLOAD_SCHEMA_V1
    null_strategy: str = DEFAULT_NULL_STRATEGY
    null_seed: int | None = None

    def to_payload_dict(self) -> dict[str, Any]:
        """JSON-pure dict for on-disk storage and sha recomputation.

        ``generated_at`` and ``sha256`` are excluded from the sha-input
        form returned by :meth:`to_sha_input_dict`; this method keeps
        every field so the on-disk row carries the full audit trail.

        v1/v2 branching: v1 omits ``payload_schema`` / ``null_strategy``
        / ``null_seed`` from the dict to preserve byte-exact legacy
        on-disk representation. v2 emits all three.
        """
        out: dict[str, Any] = {
            "cell_key": self.cell_key,
            "N": int(self.N),
            "lambda_": float(self.lambda_),
            "substrate_id": self.substrate_id,
            "metric_id": self.metric_id,
            "seed_ids": [int(s) for s in self.seed_ids],
            "precursor_values": [_finite_or_str(v) for v in self.precursor_values],
            "null_values": [_finite_or_str(v) for v in self.null_values],
            "paired_by_seed": bool(self.paired_by_seed),
            "crn_identity_hash": self.crn_identity_hash,
            "metric_version": self.metric_version,
            "substrate_version": self.substrate_version,
            "generated_at": self.generated_at,
            "sha256": self.sha256,
        }
        if self.payload_schema == PAYLOAD_SCHEMA_V2:
            out["payload_schema"] = self.payload_schema
            out["null_strategy"] = self.null_strategy
            out["null_seed"] = self.null_seed
        return out

    def to_sha_input_dict(self) -> dict[str, Any]:
        """Load-bearing fields the sha256 is computed over.

        ``sha256`` and ``generated_at`` are excluded so the sha is stable
        across machines / clocks with identical scientific inputs.

        v1/v2 branching: under v1 the sha input is the legacy 12-field
        shape (back-compat); under v2 it adds ``payload_schema``,
        ``null_strategy``, and ``null_seed`` (D-002G P1 contract).
        A v1 payload always round-trips to its legacy sha; a v2 payload
        bit-exactly addresses its (strategy, seed) provenance.
        """
        base: dict[str, Any] = {
            "cell_key": self.cell_key,
            "N": int(self.N),
            "lambda_": float(self.lambda_),
            "substrate_id": self.substrate_id,
            "metric_id": self.metric_id,
            "seed_ids": [int(s) for s in self.seed_ids],
            "precursor_values": [_finite_or_str(v) for v in self.precursor_values],
            "null_values": [_finite_or_str(v) for v in self.null_values],
            "paired_by_seed": bool(self.paired_by_seed),
            "crn_identity_hash": self.crn_identity_hash,
            "metric_version": self.metric_version,
            "substrate_version": self.substrate_version,
        }
        if self.payload_schema == PAYLOAD_SCHEMA_V2:
            base["payload_schema"] = self.payload_schema
            base["null_strategy"] = self.null_strategy
            base["null_seed"] = self.null_seed
        return base

    @classmethod
    def from_payload_dict(cls, d: dict[str, Any]) -> NullAuditCellPayload:
        """Reverse of :meth:`to_payload_dict` with fail-closed verification.

        Raises
        ------
        NullAuditPayloadInvalid
            On paired-array length mismatch, non-finite element,
            ``paired_by_seed=False``, missing field, or recomputed sha
            mismatch versus the on-disk ``sha256``.
        """
        try:
            seed_ids = tuple(int(s) for s in d["seed_ids"])
            precursor_values = tuple(_load_float(v) for v in d["precursor_values"])
            null_values = tuple(_load_float(v) for v in d["null_values"])
        except (KeyError, TypeError, ValueError) as exc:
            raise NullAuditPayloadInvalid(
                f"null_audit_payload missing or malformed array field: {exc}"
            ) from exc
        if not (len(seed_ids) == len(precursor_values) == len(null_values)):
            raise NullAuditPayloadInvalid(
                "null_audit_payload paired-array length mismatch: "
                f"len(seed_ids)={len(seed_ids)} "
                f"len(precursor_values)={len(precursor_values)} "
                f"len(null_values)={len(null_values)}"
            )
        if not bool(d.get("paired_by_seed", False)):
            raise NullAuditPayloadInvalid(
                "null_audit_payload paired_by_seed is False; CRN pairing "
                "identity cannot be reconstructed — aggregator refuses"
            )
        for arr_name, arr in (
            ("precursor_values", precursor_values),
            ("null_values", null_values),
        ):
            for v in arr:
                if not math.isfinite(float(v)):
                    raise NullAuditPayloadInvalid(
                        f"null_audit_payload {arr_name} has non-finite element: {v!r}"
                    )
        # v1/v2 schema detection: presence of ``payload_schema`` field with
        # the v2 tag enables v2 sha input; absence (legacy) defaults to v1.
        raw_schema = str(d.get("payload_schema", PAYLOAD_SCHEMA_V1))
        if raw_schema not in {PAYLOAD_SCHEMA_V1, PAYLOAD_SCHEMA_V2}:
            raise NullAuditPayloadInvalid(
                f"null_audit_payload unknown payload_schema: {raw_schema!r}; "
                f"expected one of {{{PAYLOAD_SCHEMA_V1!r}, {PAYLOAD_SCHEMA_V2!r}}}"
            )
        if raw_schema == PAYLOAD_SCHEMA_V2:
            v2_strategy = str(d.get("null_strategy", DEFAULT_NULL_STRATEGY))
            raw_null_seed = d.get("null_seed")
            v2_null_seed: int | None = None if raw_null_seed is None else int(raw_null_seed)
        else:
            v2_strategy = DEFAULT_NULL_STRATEGY
            v2_null_seed = None
        try:
            payload = cls(
                cell_key=str(d["cell_key"]),
                N=int(d["N"]),
                lambda_=float(d["lambda_"]),
                substrate_id=str(d["substrate_id"]),
                metric_id=str(d["metric_id"]),
                seed_ids=seed_ids,
                precursor_values=precursor_values,
                null_values=null_values,
                paired_by_seed=True,
                crn_identity_hash=str(d["crn_identity_hash"]),
                metric_version=str(d["metric_version"]),
                substrate_version=str(d["substrate_version"]),
                generated_at=str(d.get("generated_at", "")),
                sha256=str(d["sha256"]),
                payload_schema=raw_schema,
                null_strategy=v2_strategy,
                null_seed=v2_null_seed,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NullAuditPayloadInvalid(
                f"null_audit_payload missing or malformed scalar field: {exc}"
            ) from exc
        recomputed = _sha256_preflight_canonical(payload.to_sha_input_dict())
        if recomputed != payload.sha256:
            raise NullAuditPayloadInvalid(
                "null_audit_payload sha256 mismatch: "
                f"on-disk={payload.sha256!r} recomputed={recomputed!r} "
                "— payload was tampered with or written by an incompatible "
                "writer"
            )
        return payload


def _load_float(x: Any) -> float:
    """Reverse of :func:`_finite_or_str`.

    String sentinels round-trip back to their respective IEEE-754
    values; numeric values pass through ``float`` unchanged.
    """
    if isinstance(x, str):
        if x == "NaN":
            return math.nan
        if x == "Infinity":
            return math.inf
        if x == "-Infinity":
            return -math.inf
        raise SweepRunnerInvalid(f"unknown float sentinel: {x!r}")
    return float(x)


def _crn_identity_hash(
    *,
    substrate_id: str,
    metric_id: str,
    N: int,
    lambda_: float,
    rng_seed_base: int,
    n_seeds: int,
    steps_per_quarter: int,
    omega_gamma: float,
) -> str:
    """Stable digest binding the paired-CRN realisation identity.

    The CRN pairing identity is fully determined by the substrate, metric,
    cell coordinates ``(N, λ)`` and the integrator seeds. Two runs with
    identical scientific inputs produce identical hashes; any drift in
    seed_base / steps_per_quarter / omega_gamma produces a different
    hash, surfacing the divergence to the aggregator.
    """
    return _sha256_preflight_canonical(
        {
            "substrate_id": substrate_id,
            "metric_id": metric_id,
            "N": int(N),
            "lambda_": float(lambda_),
            "rng_seed_base": int(rng_seed_base),
            "n_seeds": int(n_seeds),
            "steps_per_quarter": int(steps_per_quarter),
            "omega_gamma": float(omega_gamma),
            "metric_version": METRIC_VERSION,
            "substrate_version": SUBSTRATE_VERSION,
        }
    )


@dataclass(frozen=True)
class SweepCellOutput:
    """One sweep cell's verdict-ready payload.

    Fields
    ------
    cell_key
        Canonical-JSON form of ``[N, lambda_, substrate_id, metric_id]``.
        Matches :func:`sweep_checkpoint.cell_key` so the checkpoint
        ledger and the runner agree on identity.
    sha256
        Hex sha256 over the canonical-JSON payload of the load-bearing
        fields (everything except ``sha256`` itself and the wallclock).
        Same inputs → same sha across calls / processes / machines.
    """

    cell_key: str
    substrate_id: str
    metric_id: str
    N: int
    lambda_: float
    n_seeds: int
    n_bootstrap: int
    signal_mean: float
    bca_ci_lo: float
    bca_ci_hi: float
    signal_over_ci: float
    direction: str  # "up" | "down" | "none"
    censoring_fraction_precursor: float
    censoring_fraction_null: float
    wallclock_seconds: float
    sha256: str
    #: D-002C C2.4-A2 data contract. Optional only for backward
    #: compatibility with pre-A2 callers (e.g. ``test_d002c_verdict``
    #: fixtures that fabricate :class:`SweepCellOutput` directly without
    #: a sweep); :func:`run_one_cell` ALWAYS populates this field on
    #: every cell it computes.
    null_audit_payload: NullAuditCellPayload | None = None

    def to_payload_dict(self) -> dict[str, Any]:
        """Canonical dict used both for sha computation and on-disk storage.

        Wallclock is excluded from the sha so a re-run with identical
        inputs and a different machine clock produces the same sha.
        """
        return {
            "cell_key": self.cell_key,
            "substrate_id": self.substrate_id,
            "metric_id": self.metric_id,
            "N": int(self.N),
            "lambda_": float(self.lambda_),
            "n_seeds": int(self.n_seeds),
            "n_bootstrap": int(self.n_bootstrap),
            "signal_mean": _finite_or_str(self.signal_mean),
            "bca_ci_lo": _finite_or_str(self.bca_ci_lo),
            "bca_ci_hi": _finite_or_str(self.bca_ci_hi),
            "signal_over_ci": _finite_or_str(self.signal_over_ci),
            "direction": self.direction,
            "censoring_fraction_precursor": float(self.censoring_fraction_precursor),
            "censoring_fraction_null": float(self.censoring_fraction_null),
        }


@dataclass(frozen=True)
class SweepResult:
    """Frozen aggregate over a full sweep.

    ``skipped_cells`` (added in C2.4-D) carries the cells removed by
    the preflight POS/NEG gates; ``preflight_decision_sha`` is the
    content-addressed sha of the preflight decision and is folded into
    the aggregate sha256, so capsule tampering between runs changes the
    sweep sha. Both fields default to empty / empty string for
    backward-compatibility with legacy callers that run with
    ``require_preflight=False``.
    """

    preregistration_sha: str
    completed_cells: int
    total_cells: int
    results: tuple[SweepCellOutput, ...]
    sha256: str
    generated_at: str
    wallclock_seconds: float
    skipped_cells: tuple[SkippedCell, ...] = ()
    preflight_decision_sha: str = ""


# ---------------------------------------------------------------------------
# Determinism helpers (cell-payload sha; see also _sha256_preflight_canonical
# above, which is used by NullAuditCellPayload for the C2.4-C2 / C2.6
# canonical-JSON alignment with the preflight validator).
# ---------------------------------------------------------------------------


def _sha256_over_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# BCa bootstrap
# ---------------------------------------------------------------------------


def _percentile_of_value(samples: NDArray[np.float64], value: float) -> float:
    """Empirical fraction of ``samples`` strictly less than ``value``.

    Returns a value in [0, 1]. Used to bias-correct in BCa.
    """
    if samples.size == 0:
        return 0.5
    return float(np.mean(samples < value))


def _empirical_percentile(samples: NDArray[np.float64], fraction: float) -> float:
    """``numpy.quantile`` with the BCa-canonical 'linear' interpolation.

    ``fraction`` is in [0, 1]. We clamp to that range to absorb the
    occasional 1-ULP overshoot from ``norm.cdf`` and to keep
    :func:`numpy.quantile` from raising on a saturated bias-correction
    in degenerate small-B regimes.
    """
    frac = max(0.0, min(1.0, float(fraction)))
    return float(np.quantile(samples, frac, method="linear"))


def bca_bootstrap_ci(
    samples: NDArray[np.float64] | list[float],
    n_bootstrap: int,
    alpha: float,
    *,
    seed: int = 0,
) -> tuple[float, float]:
    """Bias-corrected, accelerated bootstrap CI on the sample mean.

    Parameters
    ----------
    samples
        1-D array-like of observed per-seed signal differences. Must
        contain at least one finite element; ``len(samples) >= 2`` is
        required to define the jackknife acceleration.
    n_bootstrap
        Number of resamples with replacement. ``>= 2``.
    alpha
        Two-sided coverage gap. ``0 < alpha < 1``. CI is
        ``[α/2, 1 − α/2]`` after BCa adjustment.
    seed
        Seed for the resampling RNG. Determinism contract: same
        ``(samples, n_bootstrap, alpha, seed)`` → identical ``(lo, hi)``.

    Returns
    -------
    (lo, hi)
        BCa-adjusted endpoints. If every bootstrap replicate equals the
        observed estimate (no variance among resamples), the CI
        collapses to ``(θ̂, θ̂)``.

    Raises
    ------
    ValueError
        On any contract violation (empty / 1-element sample,
        non-finite element, ``n_bootstrap < 2``, ``alpha`` outside
        ``(0, 1)``).

    Notes
    -----
    The BCa endpoints (DiCiccio & Efron, *Stat Sci* 1996, §2) are

        z_0 = Φ^{-1}(p₀),         p₀ = #{θ̂_b < θ̂} / B
        a   = Σ Δ_i³ / [6 (Σ Δ_i²)^{3/2}],   Δ_i = θ̂_{··} − θ̂_{-i}
        α₁  = Φ(z_0 + (z_0 + z_{α/2})  / (1 − a(z_0 + z_{α/2})))
        α₂  = Φ(z_0 + (z_0 + z_{1−α/2})/ (1 − a(z_0 + z_{1−α/2})))
        CI  = (percentile(θ̂_b, α₁), percentile(θ̂_b, α₂))

    Degeneracies handled:
      * Σ Δ_i² == 0 → a = 0 (every jackknife replicate identical).
      * p₀ == 0 or p₀ == 1 → z_0 finite via clamping to
        [1/(B+1), B/(B+1)] before Φ^{-1}. Saturated tails would
        otherwise drive z_0 to ±∞ and explode the endpoints.
      * 1 − a·(z_0 + z_p) == 0 → α-endpoint pinned to {0, 1}
        depending on the numerator sign. Fail-closed inside the
        percentile clamp; the empirical CI then collapses to the
        empirical extremum, which is the only honest answer when
        the BCa correction is singular.
    """
    arr = np.asarray(samples, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"samples must be 1-D; got shape {arr.shape}")
    if arr.size < 2:
        raise ValueError(f"samples must contain >= 2 elements; got size {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("samples contains non-finite element(s)")
    if n_bootstrap < 2:
        raise ValueError(f"n_bootstrap must be >= 2; got {n_bootstrap}")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must lie in (0, 1); got {alpha}")

    rng = np.random.default_rng(int(seed))
    n = arr.size
    theta_hat = float(arr.mean())

    # 1. Resamples
    idx = rng.integers(0, n, size=(int(n_bootstrap), n))
    theta_boot: NDArray[np.float64] = arr[idx].mean(axis=1)

    # If every bootstrap replicate matches θ̂ exactly (e.g. constant
    # sample), the BCa percentile lookup is moot — the CI is a point.
    if float(np.max(theta_boot) - np.min(theta_boot)) == 0.0:
        return theta_hat, theta_hat

    # 2. Bias correction z_0
    p0 = _percentile_of_value(theta_boot, theta_hat)
    # Clamp p0 away from {0, 1} so Φ^{-1} is finite
    lo_clamp = 1.0 / float(n_bootstrap + 1)
    hi_clamp = float(n_bootstrap) / float(n_bootstrap + 1)
    p0_safe = max(lo_clamp, min(hi_clamp, p0))
    z0 = float(norm.ppf(p0_safe))

    # 3. Acceleration via jackknife
    total = arr.sum()
    jackknife = (total - arr) / float(n - 1)
    jack_mean = float(jackknife.mean())
    diff = jack_mean - jackknife
    num = float((diff**3).sum())
    den = float((diff**2).sum())
    if den <= 0.0:
        accel = 0.0
    else:
        accel = num / (6.0 * (den**1.5))

    # 4. Adjusted endpoints
    z_lo = float(norm.ppf(alpha / 2.0))
    z_hi = float(norm.ppf(1.0 - alpha / 2.0))

    def _adjusted(z_q: float) -> float:
        denom = 1.0 - accel * (z0 + z_q)
        if denom == 0.0:
            # BCa correction singular: drive the endpoint to the
            # appropriate tail of the bootstrap distribution.
            return 0.0 if (z0 + z_q) < 0.0 else 1.0
        return float(norm.cdf(z0 + (z0 + z_q) / denom))

    alpha_1 = _adjusted(z_lo)
    alpha_2 = _adjusted(z_hi)

    lo = _empirical_percentile(theta_boot, alpha_1)
    hi = _empirical_percentile(theta_boot, alpha_2)
    # Tolerate inverted endpoints (rare, only when the BCa correction
    # is extremely strong) by ordering them at the caller boundary.
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi


# ---------------------------------------------------------------------------
# Direction-consistency rule
# ---------------------------------------------------------------------------


def _direction(diffs: NDArray[np.float64], *, min_seeds_same_sign: int) -> str:
    """Classify direction from a vector of per-seed signed signal diffs.

    Returns
    -------
    "up"   — at least ``min_seeds_same_sign`` diffs are strictly positive
    "down" — at least ``min_seeds_same_sign`` diffs are strictly negative
    "none" — otherwise

    A diff of exactly 0.0 contributes to neither tally. If both rails
    fire (impossible when ``min_seeds_same_sign > len(diffs) / 2`` but
    permissible at smaller thresholds), we resolve by the larger count;
    ties → "none" (consistent with the pre-registration intent of
    refusing weak directional signal).
    """
    up = int(np.sum(diffs > 0.0))
    down = int(np.sum(diffs < 0.0))
    up_pass = up >= min_seeds_same_sign
    down_pass = down >= min_seeds_same_sign
    if up_pass and not down_pass:
        return "up"
    if down_pass and not up_pass:
        return "down"
    if up_pass and down_pass:
        if up > down:
            return "up"
        if down > up:
            return "down"
        return "none"
    return "none"


# ---------------------------------------------------------------------------
# One-cell driver
# ---------------------------------------------------------------------------


def _evaluate_paired(
    substrate: Substrate,
    metric: Metric,
    *,
    N: int,
    lambda_: float,
    seed: int,
    steps_per_quarter: int,
    omega_gamma: float,
) -> tuple[MetricEvaluation, MetricEvaluation]:
    """Substrate.realize(seed) + paired-CRN Kuramoto + metric.evaluate.

    Returns (eval_null, eval_precursor). Shared seed → shared ω + θ(0)
    across the two integrator runs; the only difference is the K matrix.
    """
    real = substrate.realize(N=N, lambda_=lambda_, seed=seed)
    traj_null = simulate_kuramoto(
        real.K_baseline,
        seed=seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    traj_pre = simulate_kuramoto(
        real.K_precursor,
        seed=seed,
        steps_per_quarter=steps_per_quarter,
        omega_gamma=omega_gamma,
    )
    return metric.evaluate(traj_null), metric.evaluate(traj_pre)


def run_one_cell(
    *,
    substrate: Substrate,
    metric: Metric,
    N: int,
    lambda_: float,
    n_seeds: int,
    n_bootstrap: int,
    rng_seed_base: int,
    direction_consistency_min_seeds: int,
    ci_alpha: float,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
) -> SweepCellOutput:
    """Run one sweep cell to a verdict-ready :class:`SweepCellOutput`.

    Parameters
    ----------
    substrate, metric
        Cell identity along the substrate × metric axis.
    N, lambda_
        Cell identity along the N × λ axis.
    n_seeds
        Number of paired-CRN seeds. Each seed → one substrate
        realisation + two Kuramoto integrations + two metric
        evaluations → one signal-difference scalar.
    n_bootstrap
        BCa bootstrap resample count. Must be ``>= 2``.
    rng_seed_base
        Lowest seed used; seed range is ``[base, base + n_seeds)``.
    direction_consistency_min_seeds
        Threshold for the direction rule (pre-registration:
        ``D002CPreregistration.direction_consistency_min_seeds``).
    ci_alpha
        Two-sided coverage gap for BCa (pre-registration:
        ``D002CPreregistration.ci_alpha``).
    steps_per_quarter, omega_gamma
        Integrator hyperparameters.

    Returns
    -------
    SweepCellOutput
        Carries the BCa-CI endpoints, ``|signal|/CI_half_width``
        ratio, direction verdict, per-cohort censoring fractions,
        wallclock, and a sha256 that is bit-stable across calls.

    Raises
    ------
    SweepRunnerInvalid
        On any contract violation.
    """
    if n_seeds < 2:
        raise SweepRunnerInvalid(f"n_seeds must be >= 2; got {n_seeds}")
    if n_bootstrap < 2:
        raise SweepRunnerInvalid(f"n_bootstrap must be >= 2; got {n_bootstrap}")
    if direction_consistency_min_seeds < 1:
        raise SweepRunnerInvalid(
            f"direction_consistency_min_seeds must be >= 1; got {direction_consistency_min_seeds}"
        )
    if not (0.0 < ci_alpha < 1.0):
        raise SweepRunnerInvalid(f"ci_alpha must lie in (0, 1); got {ci_alpha}")
    if N < 2:
        raise SweepRunnerInvalid(f"N must be >= 2; got {N}")
    if not math.isfinite(lambda_) or lambda_ < 0.0:
        raise SweepRunnerInvalid(f"lambda_ must be finite and >= 0; got {lambda_}")
    if steps_per_quarter < 1:
        raise SweepRunnerInvalid(f"steps_per_quarter must be >= 1; got {steps_per_quarter}")
    if not math.isfinite(omega_gamma) or omega_gamma <= 0.0:
        raise SweepRunnerInvalid(f"omega_gamma must be finite and > 0; got {omega_gamma}")

    t0 = time.monotonic()

    evals_null: list[MetricEvaluation] = []
    evals_pre: list[MetricEvaluation] = []
    per_seed_diffs = np.empty(n_seeds, dtype=np.float64)
    seed_ids_list: list[int] = []
    precursor_values_list: list[float] = []
    null_values_list: list[float] = []
    for i in range(n_seeds):
        seed_i = rng_seed_base + i
        eval_null, eval_pre = _evaluate_paired(
            substrate,
            metric,
            N=N,
            lambda_=lambda_,
            seed=seed_i,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        evals_null.append(eval_null)
        evals_pre.append(eval_pre)
        per_seed_diffs[i] = float(eval_pre.value) - float(eval_null.value)
        # D-002C C2.4-A2 — retain the per-seed paired metric values for
        # the post-sweep null-audit aggregator. Order is the seed order
        # (i = 0..n_seeds-1, seed_i = rng_seed_base + i); aligning to
        # ``seed_ids`` so any downstream consumer can re-derive the
        # paired (precursor, null) pair from a seed identity.
        seed_ids_list.append(int(seed_i))
        precursor_values_list.append(float(eval_pre.value))
        null_values_list.append(float(eval_null.value))

    # Cohort signal estimate (handles right-censoring via KM RMST).
    horizon_steps = float(PRE_EVENT_WINDOW_QUARTERS * steps_per_quarter)
    signal_estimate = signal_mean(
        metric,
        evals_pre,
        evals_null,
        horizon=horizon_steps,
    )
    s_mean = float(signal_estimate.signal_mean)

    # BCa CI on the per-seed paired-diff vector. The BCa CI is on
    # the per-seed paired diffs (not on the cohort-RMST difference);
    # this is the rule the pre-registration locks: a 20-seed paired
    # CRN distribution of signal samples is the input distribution
    # to BCa, with the cohort mean as θ̂.
    bca_seed = int(rng_seed_base) ^ 0x9E37_79B9
    ci_lo, ci_hi = bca_bootstrap_ci(
        per_seed_diffs, int(n_bootstrap), float(ci_alpha), seed=bca_seed
    )
    half_width = 0.5 * (ci_hi - ci_lo)
    if half_width > 0.0:
        signal_over_ci = abs(s_mean) / half_width
    elif s_mean == 0.0:
        signal_over_ci = 0.0
    else:
        signal_over_ci = math.inf

    direction = _direction(per_seed_diffs, min_seeds_same_sign=direction_consistency_min_seeds)

    ck = cell_key((int(N), float(lambda_), substrate.id, metric.id))
    payload = {
        "cell_key": ck,
        "substrate_id": substrate.id,
        "metric_id": metric.id,
        "N": int(N),
        "lambda_": float(lambda_),
        "n_seeds": int(n_seeds),
        "n_bootstrap": int(n_bootstrap),
        "signal_mean": _finite_or_str(s_mean),
        "bca_ci_lo": _finite_or_str(ci_lo),
        "bca_ci_hi": _finite_or_str(ci_hi),
        "signal_over_ci": _finite_or_str(signal_over_ci),
        "direction": direction,
        "censoring_fraction_precursor": float(signal_estimate.censoring_fraction_precursor),
        "censoring_fraction_null": float(signal_estimate.censoring_fraction_null),
        "rng_seed_base": int(rng_seed_base),
        "ci_alpha": float(ci_alpha),
        "direction_consistency_min_seeds": int(direction_consistency_min_seeds),
        "steps_per_quarter": int(steps_per_quarter),
        "omega_gamma": float(omega_gamma),
    }
    sha = _sha256_over_payload(payload)

    # D-002C C2.4-A2 — assemble the per-seed null-audit payload from the
    # paired metric values retained above. The payload's own sha256 is
    # computed via canonical_preflight_json so the post-sweep aggregator
    # can recompute it bit-exactly through the same canonical formula
    # the preflight validator uses on aggregate capsules.
    seed_ids_t = tuple(seed_ids_list)
    precursor_values_t = tuple(precursor_values_list)
    null_values_t = tuple(null_values_list)
    crn_hash = _crn_identity_hash(
        substrate_id=substrate.id,
        metric_id=metric.id,
        N=int(N),
        lambda_=float(lambda_),
        rng_seed_base=int(rng_seed_base),
        n_seeds=int(n_seeds),
        steps_per_quarter=int(steps_per_quarter),
        omega_gamma=float(omega_gamma),
    )
    null_audit_generated_at = _now_iso()
    null_audit_input = {
        "cell_key": ck,
        "N": int(N),
        "lambda_": float(lambda_),
        "substrate_id": substrate.id,
        "metric_id": metric.id,
        "seed_ids": list(seed_ids_t),
        "precursor_values": [_finite_or_str(v) for v in precursor_values_t],
        "null_values": [_finite_or_str(v) for v in null_values_t],
        "paired_by_seed": True,
        "crn_identity_hash": crn_hash,
        "metric_version": METRIC_VERSION,
        "substrate_version": SUBSTRATE_VERSION,
    }
    null_audit_sha = _sha256_preflight_canonical(null_audit_input)
    null_audit_payload = NullAuditCellPayload(
        cell_key=ck,
        N=int(N),
        lambda_=float(lambda_),
        substrate_id=substrate.id,
        metric_id=metric.id,
        seed_ids=seed_ids_t,
        precursor_values=precursor_values_t,
        null_values=null_values_t,
        paired_by_seed=True,
        crn_identity_hash=crn_hash,
        metric_version=METRIC_VERSION,
        substrate_version=SUBSTRATE_VERSION,
        generated_at=null_audit_generated_at,
        sha256=null_audit_sha,
    )

    wall = time.monotonic() - t0
    return SweepCellOutput(
        cell_key=ck,
        substrate_id=substrate.id,
        metric_id=metric.id,
        N=int(N),
        lambda_=float(lambda_),
        n_seeds=int(n_seeds),
        n_bootstrap=int(n_bootstrap),
        signal_mean=s_mean,
        bca_ci_lo=ci_lo,
        bca_ci_hi=ci_hi,
        signal_over_ci=signal_over_ci,
        direction=direction,
        censoring_fraction_precursor=float(signal_estimate.censoring_fraction_precursor),
        censoring_fraction_null=float(signal_estimate.censoring_fraction_null),
        wallclock_seconds=wall,
        sha256=sha,
        null_audit_payload=null_audit_payload,
    )


# ---------------------------------------------------------------------------
# Full sweep driver with D-002D checkpoint integration
# ---------------------------------------------------------------------------


def _build_full_grid(
    preregistration: D002CPreregistration,
) -> list[tuple[int, float, str, str]]:
    """Cartesian product of N × λ × substrate × metric in canonical order.

    Order is fixed so two callers building from the same prereg produce
    the same grid traversal. The checkpoint manager treats cells as a
    set, so order only matters for the progress callback and for
    streamed wallclock observability.
    """
    full_grid: list[tuple[int, float, str, str]] = []
    for N in preregistration.N_grid:
        for lam in preregistration.lambda_grid:
            for sid in preregistration.substrate_ids:
                for mid in preregistration.metric_ids:
                    full_grid.append((int(N), float(lam), str(sid), str(mid)))
    return full_grid


def _resolve_substrate(substrate_id: str) -> Substrate:
    if substrate_id not in SUBSTRATE_BY_ID:
        raise SweepRunnerInvalid(
            f"substrate_id {substrate_id!r} not in registry; available={sorted(SUBSTRATE_BY_ID)}"
        )
    return SUBSTRATE_BY_ID[substrate_id]


def _resolve_metric(metric_id: str) -> Metric:
    if metric_id not in METRIC_BY_ID:
        raise SweepRunnerInvalid(
            f"metric_id {metric_id!r} not in registry; available={sorted(METRIC_BY_ID)}"
        )
    return METRIC_BY_ID[metric_id]


def _payload_for_storage(cell_out: SweepCellOutput) -> dict[str, Any]:
    """Pure-JSON dict for storage in CellResult.payload.

    D-002C C2.4-A2 — the on-disk row includes the
    ``null_audit_payload`` sub-dict iff the cell carries one (always
    True for :func:`run_one_cell` outputs; the optional field is only
    used by pre-A2 test fixtures that fabricate SweepCellOutput without
    a sweep).
    """
    stored: dict[str, Any] = {
        **cell_out.to_payload_dict(),
        "sha256": cell_out.sha256,
        "wallclock_seconds": float(cell_out.wallclock_seconds),
    }
    if cell_out.null_audit_payload is not None:
        stored["null_audit_payload"] = cell_out.null_audit_payload.to_payload_dict()
    return stored


def _restore_cell_from_payload(payload: dict[str, Any]) -> SweepCellOutput:
    """Reverse of :func:`_payload_for_storage` — used on resume.

    D-002C C2.4-A2 — a row that carries a ``null_audit_payload`` is
    reconstructed with fail-closed verification (paired-array invariants
    + sha recompute) via :meth:`NullAuditCellPayload.from_payload_dict`;
    a row without one (legacy v1 schema or a pre-A2 row) is loaded with
    ``null_audit_payload=None`` and surfaces as "no per-seed data" to
    the aggregator, which records it as SKIPPED_NO_PER_SEED_DATA
    (fail-closed at the aggregator boundary, not silently dropped).
    """
    null_audit_dict = payload.get("null_audit_payload")
    null_audit_payload: NullAuditCellPayload | None = None
    if null_audit_dict is not None:
        if not isinstance(null_audit_dict, dict):
            raise NullAuditPayloadInvalid(
                f"null_audit_payload must be a dict; got {type(null_audit_dict).__name__}"
            )
        null_audit_payload = NullAuditCellPayload.from_payload_dict(null_audit_dict)

    return SweepCellOutput(
        cell_key=str(payload["cell_key"]),
        substrate_id=str(payload["substrate_id"]),
        metric_id=str(payload["metric_id"]),
        N=int(payload["N"]),
        lambda_=float(payload["lambda_"]),
        n_seeds=int(payload["n_seeds"]),
        n_bootstrap=int(payload["n_bootstrap"]),
        signal_mean=_load_float(payload["signal_mean"]),
        bca_ci_lo=_load_float(payload["bca_ci_lo"]),
        bca_ci_hi=_load_float(payload["bca_ci_hi"]),
        signal_over_ci=_load_float(payload["signal_over_ci"]),
        direction=str(payload["direction"]),
        censoring_fraction_precursor=float(payload["censoring_fraction_precursor"]),
        censoring_fraction_null=float(payload["censoring_fraction_null"]),
        wallclock_seconds=float(payload.get("wallclock_seconds", 0.0)),
        sha256=str(payload["sha256"]),
        null_audit_payload=null_audit_payload,
    )


def _skipped_cell_to_payload(s: SkippedCell) -> dict[str, Any]:
    """JSON-pure payload for a SKIPPED_BY_PREFLIGHT checkpoint entry."""
    return {
        "cell_key": s.cell_key,
        "substrate_id": s.substrate_id,
        "metric_id": s.metric_id,
        "N": int(s.N),
        "lambda_": float(s.lambda_),
        "status": "SKIPPED_BY_PREFLIGHT",
        "reason": s.reason,
        "source_capsule": s.source_capsule,
        "source_capsule_sha256": s.source_capsule_sha256,
    }


def _payload_is_skipped(payload: dict[str, Any]) -> bool:
    return payload.get("status") == "SKIPPED_BY_PREFLIGHT"


def _restore_skipped_from_payload(payload: dict[str, Any]) -> SkippedCell:
    return SkippedCell(
        cell_key=str(payload["cell_key"]),
        substrate_id=str(payload["substrate_id"]),
        metric_id=str(payload["metric_id"]),
        N=int(payload["N"]),
        lambda_=float(payload["lambda_"]),
        reason=str(payload["reason"]),
        source_capsule=str(payload["source_capsule"]),
        source_capsule_sha256=str(payload["source_capsule_sha256"]),
    )


def run_sweep(
    *,
    preregistration: D002CPreregistration,
    sweep_config: dict[str, Any],
    checkpoint_path: Path,
    rng_seed_base: int = 42,
    steps_per_quarter: int = DEFAULT_STEPS_PER_QUARTER,
    omega_gamma: float = DEFAULT_OMEGA_GAMMA,
    progress_callback: Callable[[int, int], None] | None = None,
    code_sha: str = DEFAULT_CODE_SHA,
    preflight_capsules: PreflightCapsulePaths | None = None,
    require_preflight: bool = True,
) -> SweepResult:
    """Drive the full pre-registered grid with per-cell checkpointing.

    Parameters
    ----------
    preregistration
        Locked frozen contract built by :func:`load_and_lock`.
    sweep_config
        Driver-side snapshot that MUST agree with the preregistration
        on every key in
        :data:`d002c_preregistration._EXPECTED_KEYS`. Mismatches are
        collected and raised together as a single
        :class:`PreregistrationMismatch`.
    checkpoint_path
        On-disk path for the D-002D :class:`CheckpointManager`.
        Each completed cell is durably saved before the next cell
        starts; a kill mid-sweep loses at most one in-flight cell.
    rng_seed_base
        Lowest paired-CRN seed; cell ``i`` uses ``[base, base + n_seeds)``
        (the same base for every cell — the substrate / metric / N / λ
        identity is what distinguishes their results).
    steps_per_quarter, omega_gamma
        Integrator hyperparameters.
    progress_callback
        Optional ``(done, total)`` callback fired once per completed
        cell. Exceptions in the callback are NOT caught — by design
        the caller's progress UI must not silently swallow errors.
    code_sha
        Soft metadata for the checkpoint ledger. Drift versus the
        on-disk file is a WARNING from :class:`CheckpointManager`,
        not a refusal.
    preflight_capsules
        Optional :class:`PreflightCapsulePaths` for the four C2.4-D
        gate capsules (pos_control, neg_control, null_audit,
        smoke_test). When supplied the runner loads + validates them
        via :func:`load_and_validate_preflight_capsules`, refuses
        launch on a refusal verdict, and reduces the execution grid
        by ``excluded_combos`` (POS) and ``excluded_cells`` (NEG).
    require_preflight
        Default ``True`` — preflight is mandatory and a missing
        ``preflight_capsules`` argument refuses launch. Set ``False``
        ONLY for legacy callers (e.g. unit tests of run_one_cell
        plumbing) that pre-date C2.4-D; in that mode the runner
        behaves identically to the pre-C2.4-D version.

    Returns
    -------
    SweepResult
        Carries every cell output (sorted by cell_key for stability),
        the preflight-skipped cells, the preflight decision sha, and a
        stable aggregate sha256 (which folds in the preflight sha so
        capsule tampering between runs changes the sweep sha).

    Raises
    ------
    PreregistrationMismatch
        From :func:`validate_sweep_config` — refuses to launch on any
        disagreement with the locked contract.
    PreflightLaunchRefused
        From :func:`assert_preflight_launch_allowed` — refuses launch
        on any preflight failure (missing/bad capsule, smoke FAIL,
        null audit FAIL, unknown identity). The exception carries the
        full refusal-reasons list.
    SweepRunnerInvalid
        On unresolvable substrate / metric ids or bad inputs.
    """
    validate_sweep_config(preregistration, sweep_config)

    # ---- preflight gate ----------------------------------------------------
    decision: PreflightDecision | None = None
    if require_preflight:
        if preflight_capsules is None:
            raise PreflightLaunchRefused(
                "preflight is required (require_preflight=True) but "
                "preflight_capsules is None; pass a PreflightCapsulePaths"
            )
        decision = load_and_validate_preflight_capsules(preflight_capsules)
        assert_preflight_launch_allowed(decision)
    elif preflight_capsules is not None:
        # Caller opted in despite require_preflight=False — honour the
        # gate but do not synthesise one if absent.
        decision = load_and_validate_preflight_capsules(preflight_capsules)
        assert_preflight_launch_allowed(decision)

    # ---- grid construction + preflight-driven reduction -------------------
    full_grid = _build_full_grid(preregistration)
    total_cells = len(full_grid)

    if decision is not None:
        runnable, skipped = apply_preflight_to_grid(full_grid, decision)
        runnable_tuples: list[tuple[int, float, str, str]] = [
            (rc.N, rc.lambda_, rc.substrate_id, rc.metric_id) for rc in runnable
        ]
        skipped_cells: tuple[SkippedCell, ...] = skipped
    else:
        runnable_tuples = list(full_grid)
        skipped_cells = ()

    cell_key_to_tuple: dict[str, tuple[int, float, str, str]] = {
        cell_key((N, lam, sid, mid)): (N, lam, sid, mid) for (N, lam, sid, mid) in runnable_tuples
    }
    all_keys: list[str] = list(cell_key_to_tuple.keys())

    mgr = CheckpointManager(
        Path(checkpoint_path), sweep_config=dict(sweep_config), code_sha=code_sha
    )
    checkpoint = mgr.load_or_create()

    # Restore already-completed cells from the on-disk checkpoint so
    # the aggregate sha is stable across resume. Persisted
    # SKIPPED_BY_PREFLIGHT entries are restored into the skipped tuple
    # (idempotent with the in-memory ``skipped_cells``); legacy entries
    # (no ``status`` field) become SweepCellOutput as before.
    restored: dict[str, SweepCellOutput] = {}
    persisted_skipped: dict[str, SkippedCell] = {}
    for k, v in checkpoint.results.items():
        if _payload_is_skipped(v.payload):
            persisted_skipped[k] = _restore_skipped_from_payload(v.payload)
        else:
            restored[k] = _restore_cell_from_payload(v.payload)

    # Codex P1 fix (2026-05-12): when resuming a checkpoint under a NEW
    # preflight decision, every persisted cell must still agree with the
    # current decision. Three drift modes are possible and ALL are
    # fail-closed:
    #
    #   (a) persisted_skipped AND now runnable —
    #       the operator updated POS/NEG capsules so exclusion was
    #       lifted, but ``remaining_cells`` would treat the cell as
    #       already done and silently skip recomputation. The new
    #       sweep would return an incomplete grid under a fresh
    #       aggregate sha, defeating the tamper-evidence contract.
    #
    #   (b) persisted_computed AND now skipped —
    #       the cell already has a real metric value, but the new
    #       decision says it should never have run. Persisting both
    #       a SKIPPED row and the real result is internally
    #       contradictory; the operator must explicitly resolve.
    #
    #   (c) persisted_skipped AND still skipped BUT source_capsule
    #       sha drifted — exclusion happened to be preserved but the
    #       capsule was rotated. The exclusion provenance has
    #       changed under our feet; the operator must acknowledge
    #       this rather than have the runner silently rewrite the
    #       audit row.
    #
    # In every case the runner refuses launch and tells the
    # operator to start a fresh checkpoint path (or run with
    # ``require_preflight=False`` for the legacy ungated path).
    if preflight_capsules is not None:
        current_skipped_keys: dict[str, SkippedCell] = {s.cell_key: s for s in skipped_cells}
        current_runnable_keys: set[str] = set(cell_key_to_tuple.keys())
        drift_reasons: list[str] = []
        for k in sorted(checkpoint.results.keys()):
            is_persisted_skip = k in persisted_skipped
            is_currently_skip = k in current_skipped_keys
            is_currently_runnable = k in current_runnable_keys
            if is_persisted_skip and is_currently_runnable:
                drift_reasons.append(
                    f"persisted_skipped_cell_no_longer_excluded:{k} — "
                    "the previous run skipped this cell under a preflight "
                    "exclusion that the current decision does not assert; "
                    "resume would silently treat the cell as completed."
                )
            elif (not is_persisted_skip) and is_currently_skip:
                drift_reasons.append(
                    f"persisted_computed_cell_now_excluded:{k} — "
                    "this cell already has a real metric value on disk "
                    "but the current preflight decision now excludes it; "
                    "the audit trail cannot be both 'computed' and "
                    "'skipped' for the same cell."
                )
            elif is_persisted_skip and is_currently_skip:
                persisted = persisted_skipped[k]
                current = current_skipped_keys[k]
                if persisted.source_capsule_sha256 != current.source_capsule_sha256:
                    drift_reasons.append(
                        f"persisted_skipped_cell_source_capsule_sha_drifted:"
                        f"{k} — exclusion preserved but capsule provenance "
                        f"changed (was {persisted.source_capsule_sha256[:8]}…, "
                        f"now {current.source_capsule_sha256[:8]}…); "
                        "the audit row cannot be silently rewritten."
                    )
        if drift_reasons:
            raise PreflightLaunchRefused(
                "checkpoint contradicts current preflight decision; the "
                "saved sweep state cannot be safely resumed under the new "
                "contract. Start a fresh checkpoint path or run with "
                "require_preflight=False (legacy mode). Drift:\n"
                + "\n".join(f"  - {r}" for r in drift_reasons)
            )

    # Persist any preflight-skipped cells that aren't yet on disk. This
    # makes the checkpoint a complete audit trail: SKIPPED_BY_PREFLIGHT
    # rows survive a kill and bind the source_capsule_sha256 so resume
    # cannot silently recompute a previously-skipped cell.
    for s in skipped_cells:
        if s.cell_key in persisted_skipped:
            continue
        mgr.save_cell(
            s.cell_key,
            CellResult(
                cell_key=s.cell_key,
                payload=_skipped_cell_to_payload(s),
                duration_seconds=0.0,
            ),
        )
        persisted_skipped[s.cell_key] = s

    t0 = time.monotonic()
    remaining = mgr.remaining_cells(all_keys)
    # Subtract the runnable cells already computed from the work count;
    # SKIPPED rows are accounted for separately.
    done_count = len(all_keys) - len(remaining)

    for ck in remaining:
        N, lam, sid, mid = cell_key_to_tuple[ck]
        substrate = _resolve_substrate(sid)
        metric = _resolve_metric(mid)
        cell_out = run_one_cell(
            substrate=substrate,
            metric=metric,
            N=N,
            lambda_=lam,
            n_seeds=preregistration.n_seeds,
            n_bootstrap=preregistration.n_bootstrap,
            rng_seed_base=rng_seed_base,
            direction_consistency_min_seeds=preregistration.direction_consistency_min_seeds,
            ci_alpha=preregistration.ci_alpha,
            steps_per_quarter=steps_per_quarter,
            omega_gamma=omega_gamma,
        )
        mgr.save_cell(
            ck,
            CellResult(
                cell_key=ck,
                payload=_payload_for_storage(cell_out),
                duration_seconds=float(cell_out.wallclock_seconds),
            ),
        )
        restored[ck] = cell_out
        done_count += 1
        if progress_callback is not None:
            progress_callback(done_count, total_cells)

    wall = time.monotonic() - t0

    # Stable order: sort by cell_key so the aggregate sha is invariant
    # under the traversal order (and stable across resume). Skipped
    # cells appear in their own deterministic tuple, also sorted.
    ordered_keys = sorted(restored.keys())
    results = tuple(restored[k] for k in ordered_keys)
    final_skipped = tuple(persisted_skipped[k] for k in sorted(persisted_skipped.keys()))
    preflight_sha = decision.sha256 if decision is not None else ""

    aggregate = {
        "preregistration_sha": preregistration.preregistration_sha,
        "per_cell_shas": [r.sha256 for r in results],
        "completed_cells": len(results),
        "total_cells": total_cells,
        "rng_seed_base": int(rng_seed_base),
        "steps_per_quarter": int(steps_per_quarter),
        "omega_gamma": float(omega_gamma),
        # Truth-binding: capsule tampering between runs changes the sweep sha.
        "preflight_decision_sha": preflight_sha,
        "skipped_cell_keys": [s.cell_key for s in final_skipped],
        "skipped_cell_source_shas": [s.source_capsule_sha256 for s in final_skipped],
    }
    sha = _sha256_over_payload(aggregate)

    return SweepResult(
        preregistration_sha=preregistration.preregistration_sha,
        completed_cells=len(results),
        total_cells=total_cells,
        results=results,
        sha256=sha,
        generated_at=_now_iso(),
        wallclock_seconds=wall,
        skipped_cells=final_skipped,
        preflight_decision_sha=preflight_sha,
    )


# ---------------------------------------------------------------------------
# Re-export the integrator defaults so callers needn't reach across modules
# for the canonical step / γ values.
# ---------------------------------------------------------------------------


__all__ = [
    "DEFAULT_STEPS_PER_QUARTER",
    "DEFAULT_OMEGA_GAMMA",
    "DEFAULT_CODE_SHA",
    "METRIC_VERSION",
    "PRE_EVENT_WINDOW_QUARTERS",
    "SUBSTRATE_VERSION",
    "NullAuditCellPayload",
    "NullAuditPayloadInvalid",
    "SweepCellOutput",
    "SweepResult",
    "SweepRunnerInvalid",
    "bca_bootstrap_ci",
    "run_one_cell",
    "run_sweep",
]


# Keep json imported for side-effect-free import checks in static analysis.
_ = json
