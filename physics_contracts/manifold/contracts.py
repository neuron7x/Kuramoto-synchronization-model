# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed, deterministic contracts for the Physics v2 synchronization manifold.

Every object here is a *frozen* dataclass with a fail-closed ``__post_init__``
validator. Numeric helpers are pure stdlib (``hashlib`` + ``json``) so the
contract layer carries no numpy/jax import cost and produces byte-identical
digests under replay (architecture doc §2 P6: "rerun with same inputs gives
byte-identical manifest").

Design rules (architecture doc §0, §5, §8):

* A contract violation is a ``ValueError`` (or a dedicated subclass), never a
  silent clamp or a best-effort repair.
* No object asserts a market claim. ``ComparisonReport`` can only *downgrade*
  a claim when a negative control is not beaten; it can never promote one.
* A missing licensed-L2 dataset is an explicit ``DATA_UNAVAILABLE`` status —
  ``require_licensed_l2`` raises rather than substituting synthetic data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

# A fingerprint of all-zero hex is the documented placeholder for "no real data"
# (docs/research/l2_ricci_evidence_protocol.md: data_sha256 == zero ⇒ placeholder).
_ZERO_FINGERPRINTS: Final[frozenset[str]] = frozenset(
    {"", "0", "0" * 16, "0" * 32, "0" * 40, "0" * 64}
)

# Synthetic fixtures tag their fingerprint with this prefix so a real-data code
# path can never mistake a deterministic fixture for a licensed dataset.
SYNTHETIC_FINGERPRINT_PREFIX: Final[str] = "synthetic:"

# Claim-maturity tiers that are forbidden when the underlying data is unavailable.
# These mirror the upper rungs of analytics.signals.claim_maturity.LADDER; we keep
# a local frozenset rather than importing it so this contract layer stays
# dependency-light and the coupling is documented, not hidden.
_REAL_DATA_MATURITY_TIERS: Final[frozenset[str]] = frozenset(
    {
        "REAL_DATA_SINGLE_SESSION",
        "REAL_DATA_MULTI_SESSION",
        "ALTERNATIVES_ELIMINATED",
        "NEGATIVE_EVIDENCE_PRESERVED",
        "BOUNDED_CLAIM_ALLOWED",
    }
)

_KNOWN_MATURITY_TIERS: Final[frozenset[str]] = frozenset(
    {
        "UNOBSERVED",
        "OBSERVABLE",
        "MEASURED_SYNTHETIC",
        "ALTERNATIVES_ENUMERATED",
        "DISCRIMINATING_TEST_DEFINED",
        "FALSIFIER_EXECUTED",
        "CALIBRATED",
        "INTEGRATED",
        "REPLAYABLE",
    }
    | _REAL_DATA_MATURITY_TIERS
)

_REGIME_LABELS: Final[frozenset[str]] = frozenset(
    {"subcritical", "supercritical", "critical", "chimera", "unknown"}
)

_CLAIM_STATUSES: Final[frozenset[str]] = frozenset(
    {"HYPOTHESIS", "ARTIFACT_SUSPECTED", "SURVIVED_NULLS"}
)


def canonical_digest(payload: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 over a JSON-canonicalised mapping.

    Keys are sorted and separators are fixed so the digest is stable across
    runs and insertion orders — the foundation of the replay-identity law
    (``manifold.provenance_replay_identity``).
    """

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CausalCutoffStatus(str, Enum):
    """Whether a frame respects its declared causal cutoff."""

    VALID = "valid"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class LicensedDataStatus(str, Enum):
    """Availability of a licensed L2 dataset for a real-data run."""

    AVAILABLE = "available"
    DATA_UNAVAILABLE = "data_unavailable"


class LicensedDataUnavailable(RuntimeError):
    """Raised when a real-data path is requested but no licensed L2 data exists.

    This is the fail-closed signal mandated by architecture doc §2 P6 and §3:
    "No command may silently fall back to synthetic data when real data was
    requested."
    """


@dataclass(frozen=True, slots=True)
class MarketCausalGraphSnapshot:
    """A single time-bounded causal market-graph snapshot (architecture doc §2 P2).

    The snapshot is *structural only*: nodes, directed-or-undirected edges, and
    non-negative edge weights, plus the provenance needed to replay it. It makes
    no claim about price prediction.
    """

    timestamp_start: float
    timestamp_end: float
    nodes: tuple[str, ...]
    edges: tuple[tuple[int, int], ...]
    edge_weights: tuple[float, ...]
    latency_floor_seconds: float
    causal_cutoff_seconds: float
    dataset_fingerprint: str
    construction_config_hash: str
    builder_method: str

    def __post_init__(self) -> None:
        if not _is_finite(self.timestamp_start) or not _is_finite(self.timestamp_end):
            raise ValueError(
                "manifold.metric_snapshot_schema VIOLATED: timestamps must be finite; "
                f"got start={self.timestamp_start!r} end={self.timestamp_end!r}"
            )
        if self.timestamp_end < self.timestamp_start:
            raise ValueError(
                "manifold.metric_snapshot_schema VIOLATED: timestamp_end < timestamp_start "
                f"({self.timestamp_end} < {self.timestamp_start}); snapshot interval must be monotonic"
            )
        if self.latency_floor_seconds < 0.0:
            raise ValueError(
                "manifold.causal_cutoff VIOLATED: latency_floor_seconds is negative "
                f"({self.latency_floor_seconds}); no information can arrive before the data substrate emits it"
            )
        if self.causal_cutoff_seconds < self.latency_floor_seconds:
            raise ValueError(
                "manifold.causal_cutoff VIOLATED: causal_cutoff_seconds < latency_floor_seconds "
                f"({self.causal_cutoff_seconds} < {self.latency_floor_seconds}); "
                "the cutoff cannot be tighter than the substrate latency floor"
            )
        if len(self.edges) != len(self.edge_weights):
            raise ValueError(
                "manifold.metric_snapshot_schema VIOLATED: edges/edge_weights length mismatch "
                f"({len(self.edges)} != {len(self.edge_weights)})"
            )
        n_nodes = len(self.nodes)
        if n_nodes == 0:
            raise ValueError("manifold.metric_snapshot_schema VIOLATED: snapshot has no nodes")
        if len(set(self.nodes)) != n_nodes:
            raise ValueError("manifold.metric_snapshot_schema VIOLATED: node ids are not unique")
        for idx, (u, v) in enumerate(self.edges):
            if not (0 <= u < n_nodes) or not (0 <= v < n_nodes):
                raise ValueError(
                    "manifold.metric_snapshot_schema VIOLATED: edge "
                    f"{(u, v)} references a node index outside [0, {n_nodes})"
                )
            if u == v:
                raise ValueError(f"manifold.metric_snapshot_schema VIOLATED: self-loop at node {u}")
            w = self.edge_weights[idx]
            if not _is_finite(w) or w < 0.0:
                raise ValueError(
                    "manifold.curvature_transport_balance VIOLATED: edge weight "
                    f"{w!r} at edge {(u, v)} must be finite and non-negative"
                )
        if not self.dataset_fingerprint:
            raise ValueError(
                "manifold.provenance_replay_identity VIOLATED: dataset_fingerprint is empty"
            )
        if not self.construction_config_hash:
            raise ValueError(
                "manifold.provenance_replay_identity VIOLATED: construction_config_hash is empty"
            )
        if not self.builder_method:
            raise ValueError("manifold.metric_snapshot_schema VIOLATED: builder_method is empty")

    @property
    def snapshot_id(self) -> str:
        """Deterministic content-address of this snapshot (replay identity)."""

        return canonical_digest(
            {
                "timestamp_start": self.timestamp_start,
                "timestamp_end": self.timestamp_end,
                "nodes": list(self.nodes),
                "edges": [list(e) for e in self.edges],
                "edge_weights": list(self.edge_weights),
                "latency_floor_seconds": self.latency_floor_seconds,
                "causal_cutoff_seconds": self.causal_cutoff_seconds,
                "dataset_fingerprint": self.dataset_fingerprint,
                "construction_config_hash": self.construction_config_hash,
                "builder_method": self.builder_method,
            }
        )

    def assert_no_lookahead(self, source_event_times: tuple[float, ...]) -> None:
        """Fail closed if any source event used to build this snapshot is in its future.

        Architecture doc §2 P2 acceptance: "no look-ahead data access". A builder
        passes the timestamps of every event it consumed; any event strictly after
        ``timestamp_end`` would mean the snapshot peeked into the future.
        """

        for t in source_event_times:
            if not _is_finite(t):
                raise ValueError(
                    "manifold.metric_snapshot_schema VIOLATED: non-finite source event time"
                )
            if t > self.timestamp_end:
                raise ValueError(
                    "manifold.causal_cutoff VIOLATED: look-ahead detected — source event at "
                    f"t={t} is after snapshot timestamp_end={self.timestamp_end}"
                )


@dataclass(frozen=True, slots=True)
class CurvatureSyncFrame:
    """Schema for one curvature/synchronization frame over a snapshot.

    This is a *schema only* — it carries the descriptors a later solver PR will
    populate (order parameter, phase dispersion, mean curvature, regime). It runs
    no dynamics; it just bounds-checks the values it is handed, fail-closed.
    """

    snapshot_id: str
    order_parameter: float
    phase_dispersion: float
    mean_curvature: float
    causal_cutoff_status: CausalCutoffStatus
    finite_size_floor: float
    regime_label: str
    validity_domain: str

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError(
                "manifold.provenance_replay_identity VIOLATED: frame has empty snapshot_id"
            )
        if not (0.0 <= self.order_parameter <= 1.0):
            raise ValueError(
                "kuramoto.order_parameter_bounds VIOLATED: order_parameter "
                f"{self.order_parameter} outside [0, 1]"
            )
        if not _is_finite(self.phase_dispersion) or self.phase_dispersion < 0.0:
            raise ValueError(
                "manifold.finite_size_scaling_with_causal_cutoff VIOLATED: phase_dispersion "
                f"{self.phase_dispersion!r} must be finite and non-negative"
            )
        if not _is_finite(self.mean_curvature):
            raise ValueError(
                "ricci.flow_energy_nonincrease_declared_domain VIOLATED: mean_curvature is non-finite"
            )
        if not _is_finite(self.finite_size_floor) or self.finite_size_floor < 0.0:
            raise ValueError(
                "kuramoto.finite_size_scaling_with_causal_cutoff VIOLATED: finite_size_floor "
                f"{self.finite_size_floor!r} must be finite and non-negative"
            )
        if self.regime_label not in _REGIME_LABELS:
            raise ValueError(
                f"manifold.metric_snapshot_schema VIOLATED: regime_label {self.regime_label!r} "
                f"not in {sorted(_REGIME_LABELS)}"
            )
        if not self.validity_domain:
            raise ValueError("manifold.metric_snapshot_schema VIOLATED: validity_domain is empty")


@dataclass(frozen=True, slots=True)
class NullControl:
    """One negative-control statistic for the falsification battery (doc §2 P5)."""

    name: str
    statistic: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("NullControl VIOLATED: name is empty")
        if not _is_finite(self.statistic):
            raise ValueError(f"NullControl VIOLATED: statistic {self.statistic!r} is non-finite")


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Candidate effect versus its negative controls (architecture doc §2 P5).

    The report is allowed to *downgrade* a claim to ``ARTIFACT_SUSPECTED`` when
    the candidate statistic does not strictly exceed every null control. It is
    structurally incapable of promoting a claim above ``SURVIVED_NULLS`` — and
    even that status is only "the effect outlived its controls", never "alpha".
    """

    candidate_statistic: float
    null_controls: tuple[NullControl, ...]
    claim_status: str
    validity_domain: str

    def __post_init__(self) -> None:
        if not _is_finite(self.candidate_statistic):
            raise ValueError("ComparisonReport VIOLATED: candidate_statistic is non-finite")
        if len(self.null_controls) == 0:
            raise ValueError(
                "ComparisonReport VIOLATED: a positive claim must face at least one negative control "
                "(architecture doc §2 P5 requires four)"
            )
        if self.claim_status not in _CLAIM_STATUSES:
            raise ValueError(
                f"ComparisonReport VIOLATED: claim_status {self.claim_status!r} "
                f"not in {sorted(_CLAIM_STATUSES)}"
            )
        if not self.validity_domain:
            raise ValueError("ComparisonReport VIOLATED: validity_domain is empty")
        # Fail-closed P5 rule: SURVIVED_NULLS is only legal if the candidate strictly
        # beats every control. Claiming survival while a null matches it is the exact
        # over-claim the battery exists to stop.
        if self.claim_status == "SURVIVED_NULLS" and not self.survives_all_controls:
            raise ValueError(
                "ComparisonReport VIOLATED: claim_status=SURVIVED_NULLS but a negative control "
                "is >= the candidate statistic; downgrade to ARTIFACT_SUSPECTED"
            )

    @property
    def survives_all_controls(self) -> bool:
        return all(self.candidate_statistic > nc.statistic for nc in self.null_controls)

    @property
    def report_digest(self) -> str:
        return canonical_digest(
            {
                "candidate_statistic": self.candidate_statistic,
                "null_controls": [[nc.name, nc.statistic] for nc in self.null_controls],
                "claim_status": self.claim_status,
                "validity_domain": self.validity_domain,
            }
        )


def deterministic_run_id(config_hash: str, dataset_fingerprint: str, code_commit: str) -> str:
    """Run id derived from config + dataset + commit (architecture doc §2 P6).

    "run_id deterministic from config + dataset fingerprint + code commit."
    """

    if not config_hash or not dataset_fingerprint or not code_commit:
        raise ValueError(
            "manifold.provenance_replay_identity VIOLATED: run_id requires non-empty "
            "config_hash, dataset_fingerprint, and code_commit"
        )
    return canonical_digest(
        {
            "config_hash": config_hash,
            "dataset_fingerprint": dataset_fingerprint,
            "code_commit": code_commit,
        }
    )


@dataclass(frozen=True, slots=True)
class EvidenceCapsuleShape:
    """The Physics v2 evidence-capsule shape (architecture doc §2 P6).

    This is a *thin* contract that names the fields a Physics v2 run must persist.
    It deliberately mirrors the already-shipped ``instrument_validation.capsule``
    fields (``code_sha``, ``payload_sha256``, ``verdict``) and the
    ``analytics.signals.claim_maturity`` ladder so later PRs reuse those engines
    rather than forking a parallel capsule. See ``artifacts/physics_v2/inventory.md``.
    """

    run_id: str
    dataset_fingerprint: str
    config_hash: str
    code_commit: str
    laws_exercised: tuple[str, ...]
    falsifiers_passed: tuple[str, ...]
    falsifiers_failed: tuple[str, ...]
    comparison_report_digest: str
    claim_maturity: str
    data_status: LicensedDataStatus

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id),
            ("dataset_fingerprint", self.dataset_fingerprint),
            ("config_hash", self.config_hash),
            ("code_commit", self.code_commit),
            ("comparison_report_digest", self.comparison_report_digest),
        ):
            if not value:
                raise ValueError(
                    f"manifold.provenance_replay_identity VIOLATED: capsule field {name!r} is empty"
                )
        if self.claim_maturity not in _KNOWN_MATURITY_TIERS:
            raise ValueError(
                f"EvidenceCapsuleShape VIOLATED: claim_maturity {self.claim_maturity!r} "
                f"not a known maturity tier"
            )
        # Fail-closed: a run without licensed data may not assert any real-data
        # maturity tier (architecture doc §5: no real-L2 claim without artifacts).
        if (
            self.data_status is LicensedDataStatus.DATA_UNAVAILABLE
            and self.claim_maturity in _REAL_DATA_MATURITY_TIERS
        ):
            raise ValueError(
                "EvidenceCapsuleShape VIOLATED: data_status=DATA_UNAVAILABLE but claim_maturity "
                f"{self.claim_maturity!r} asserts real-data evidence; demote to a synthetic-or-lower tier"
            )

    @property
    def capsule_digest(self) -> str:
        return canonical_digest(
            {
                "run_id": self.run_id,
                "dataset_fingerprint": self.dataset_fingerprint,
                "config_hash": self.config_hash,
                "code_commit": self.code_commit,
                "laws_exercised": sorted(self.laws_exercised),
                "falsifiers_passed": sorted(self.falsifiers_passed),
                "falsifiers_failed": sorted(self.falsifiers_failed),
                "comparison_report_digest": self.comparison_report_digest,
                "claim_maturity": self.claim_maturity,
                "data_status": self.data_status.value,
            }
        )


def resolve_data_status(dataset_fingerprint: str | None) -> LicensedDataStatus:
    """Classify a dataset fingerprint as AVAILABLE or DATA_UNAVAILABLE.

    A ``None``, empty, all-zero, or synthetic-tagged fingerprint is treated as
    *no licensed data present*.
    """

    if dataset_fingerprint is None:
        return LicensedDataStatus.DATA_UNAVAILABLE
    fingerprint = dataset_fingerprint.strip().lower()
    if fingerprint in _ZERO_FINGERPRINTS:
        return LicensedDataStatus.DATA_UNAVAILABLE
    if fingerprint.startswith(SYNTHETIC_FINGERPRINT_PREFIX):
        return LicensedDataStatus.DATA_UNAVAILABLE
    return LicensedDataStatus.AVAILABLE


def require_licensed_l2(dataset_fingerprint: str | None) -> str:
    """Return the fingerprint of a present licensed L2 dataset, or fail closed.

    This is the single chokepoint enforcing architecture doc §3: a real-data run
    must never silently fall back to synthetic data. When no licensed dataset is
    available the function raises ``LicensedDataUnavailable`` — it does **not**
    return a synthetic fingerprint and does **not** fabricate one.
    """

    status = resolve_data_status(dataset_fingerprint)
    if status is LicensedDataStatus.DATA_UNAVAILABLE:
        raise LicensedDataUnavailable(
            "DATA_UNAVAILABLE: real-data L2 run requested but no licensed dataset is present "
            f"(fingerprint={dataset_fingerprint!r}). Refusing to substitute synthetic data. "
            "Use the synthetic fixtures path explicitly if a synthetic run is intended."
        )
    assert dataset_fingerprint is not None  # narrowed by resolve_data_status
    return dataset_fingerprint


def _is_finite(x: float) -> bool:
    """True iff x is a finite real number (rejects NaN and +-inf)."""

    return x == x and x not in (float("inf"), float("-inf"))
