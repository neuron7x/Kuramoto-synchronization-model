# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Replication capsule — pillar 6 of the Canonical Seven.

Operationalises § 6 of the canonical-7 charter. A claim is replicable
iff a sealed manifest can be re-executed and the verdict-bearing
metric reproduces to within a stated tolerance. Divergence drives
:func:`research.systemic_risk.death_conditions.trigger_replication_mismatch`
to KILL the claim — there is no "close enough" branch.

This module ships the **comparator**: a pure-function check that
takes two :class:`RunManifest` records (primary vs rerun) plus the
verdict-bearing metric from each, and returns a frozen
:class:`ReplicationOutcome` whose ``matched`` field is the contract
surface consumed by the death-engine's T4 trigger.

Tolerance taxonomy:

* **bit_identical** — ``np.float64`` byte-for-byte equality. Use for
  pure-deterministic kernels (seeded numpy, no FP reduction order
  mismatch). Tolerance = 0.0.
* **deterministic_with_drift** — bit-identical inputs but the
  pipeline contains operations whose result depends on
  thread-scheduling (e.g. parallel reductions). Tolerance ≤ 1e-12.
* **stochastic_seeded** — the run consumes RNG in a way that may not
  reproduce bit-identically across builds; tolerance is set by the
  caller's pre-registration (e.g. AUC tolerance 5e-3 for n=10000
  bootstrap).

The module is *agnostic* to which kernel produced the metric. Its
job is to compare two scalars under a stated tolerance and report
the outcome, with **provenance of both manifests** so an audit can
reconstruct the rerun. No I/O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, Literal

from .replication import RunManifest

__all__ = [
    "DEFAULT_BIT_IDENTICAL_TOLERANCE",
    "DEFAULT_DETERMINISTIC_TOLERANCE",
    "MismatchReason",
    "ReplicationOutcome",
    "ReplicationToleranceClass",
    "compare_run_outputs",
    "manifest_replication_sha",
]


DEFAULT_BIT_IDENTICAL_TOLERANCE: Final[float] = 0.0
DEFAULT_DETERMINISTIC_TOLERANCE: Final[float] = 1e-12


ReplicationToleranceClass = Literal[
    "bit_identical",
    "deterministic_with_drift",
    "stochastic_seeded",
]


MismatchReason = Literal[
    "matched",
    "metric_deviation_exceeds_tolerance",
    "non_finite_primary_metric",
    "non_finite_secondary_metric",
    "config_hash_diverged",
    "seed_diverged",
    "tolerance_negative",
]


@dataclass(frozen=True, slots=True)
class ReplicationOutcome:
    """Aggregate replication-comparator outcome.

    Attributes
    ----------
    matched
        ``True`` iff every check passed (config + seed + metric within
        tolerance + finite). Mirrors the
        :class:`ReplicationResultLike` protocol consumed by
        :func:`death_conditions.trigger_replication_mismatch`.
    tolerance_class
        Pre-registered tolerance regime (see module docstring).
    tolerance
        Actual tolerance applied (must be ≥ 0).
    primary_metric
        The verdict-bearing metric from the primary run.
    secondary_metric
        The same metric from the rerun.
    deviation
        ``abs(primary_metric - secondary_metric)``. ``inf`` when one
        side is non-finite.
    primary_manifest_sha
        SHA-256 of the primary :class:`RunManifest` (canonical JSON).
    secondary_manifest_sha
        SHA-256 of the secondary :class:`RunManifest`.
    reason
        One of :data:`MismatchReason`. ``"matched"`` only when every
        check passed.
    """

    matched: bool
    tolerance_class: ReplicationToleranceClass
    tolerance: float
    primary_metric: float
    secondary_metric: float
    deviation: float
    primary_manifest_sha: str
    secondary_manifest_sha: str
    reason: MismatchReason


def manifest_replication_sha(manifest: RunManifest) -> str:
    """Return the canonical SHA-256 of a :class:`RunManifest`.

    Uses the manifest's own deterministic JSON form
    (``manifest.to_json()``), so two manifests with the same content
    in any field order produce the same hash. Always 64-char hex.
    """
    payload = manifest.to_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve_tolerance(
    tolerance_class: ReplicationToleranceClass,
    tolerance_override: float | None,
) -> float:
    if tolerance_override is not None:
        return float(tolerance_override)
    if tolerance_class == "bit_identical":
        return DEFAULT_BIT_IDENTICAL_TOLERANCE
    if tolerance_class == "deterministic_with_drift":
        return DEFAULT_DETERMINISTIC_TOLERANCE
    # stochastic_seeded — caller MUST supply tolerance_override.
    raise ValueError(
        "stochastic_seeded tolerance class requires explicit "
        "tolerance_override; refusing to invent a default."
    )


def compare_run_outputs(
    *,
    primary_manifest: RunManifest,
    secondary_manifest: RunManifest,
    primary_metric: float,
    secondary_metric: float,
    tolerance_class: ReplicationToleranceClass,
    tolerance_override: float | None = None,
) -> ReplicationOutcome:
    """Compare two runs and return a frozen :class:`ReplicationOutcome`.

    Order of checks (fail-closed; first failure wins for ``reason``):

    1. ``tolerance >= 0`` — negative tolerance is a contract bug.
    2. ``primary_metric`` finite.
    3. ``secondary_metric`` finite.
    4. ``primary.config_hash == secondary.config_hash`` — different
       configs cannot count as a rerun.
    5. ``primary.seed == secondary.seed`` — different seeds cannot
       count as a *bit-identical* or *deterministic-with-drift* rerun.
       For ``stochastic_seeded`` the seed equality is still required —
       the tolerance regime affects the metric comparison, not the
       contract that *the same root seed* drives both runs.
    6. ``abs(primary_metric - secondary_metric) <= tolerance``.

    Parameters
    ----------
    primary_manifest, secondary_manifest
        Sealed run manifests. ``commit_sha`` need not match (a rerun
        on a fresh build is the canonical use case), but
        ``config_hash`` and ``seed`` must.
    primary_metric, secondary_metric
        The single verdict-bearing scalar from each run (e.g. AUC,
        delta-AUC, posterior log-odds at a stated checkpoint).
    tolerance_class
        Pre-registered tolerance regime. Determines the default
        tolerance unless overridden.
    tolerance_override
        Explicit numeric tolerance. Required for
        ``stochastic_seeded``; optional for the other two classes.

    Returns
    -------
    ReplicationOutcome
        Frozen outcome. ``matched`` is ``True`` iff every check passed.
    """
    tolerance = _resolve_tolerance(tolerance_class, tolerance_override)
    primary_sha = manifest_replication_sha(primary_manifest)
    secondary_sha = manifest_replication_sha(secondary_manifest)

    if tolerance < 0:
        return ReplicationOutcome(
            matched=False,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=float("inf"),
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="tolerance_negative",
        )

    primary_finite = _is_finite(primary_metric)
    secondary_finite = _is_finite(secondary_metric)
    if not primary_finite:
        return ReplicationOutcome(
            matched=False,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=float("inf"),
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="non_finite_primary_metric",
        )
    if not secondary_finite:
        return ReplicationOutcome(
            matched=False,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=float("inf"),
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="non_finite_secondary_metric",
        )

    if primary_manifest.config_hash != secondary_manifest.config_hash:
        return ReplicationOutcome(
            matched=False,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=abs(primary_metric - secondary_metric),
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="config_hash_diverged",
        )
    if primary_manifest.seed != secondary_manifest.seed:
        return ReplicationOutcome(
            matched=False,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=abs(primary_metric - secondary_metric),
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="seed_diverged",
        )

    deviation = abs(primary_metric - secondary_metric)
    if deviation <= tolerance:
        return ReplicationOutcome(
            matched=True,
            tolerance_class=tolerance_class,
            tolerance=tolerance,
            primary_metric=primary_metric,
            secondary_metric=secondary_metric,
            deviation=deviation,
            primary_manifest_sha=primary_sha,
            secondary_manifest_sha=secondary_sha,
            reason="matched",
        )
    return ReplicationOutcome(
        matched=False,
        tolerance_class=tolerance_class,
        tolerance=tolerance,
        primary_metric=primary_metric,
        secondary_metric=secondary_metric,
        deviation=deviation,
        primary_manifest_sha=primary_sha,
        secondary_manifest_sha=secondary_sha,
        reason="metric_deviation_exceeds_tolerance",
    )


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))
