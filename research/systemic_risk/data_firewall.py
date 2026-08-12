# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data-reality firewall — eight-gate ingress contract.

Operationalises § 3 of the Canonical-Seven charter. The firewall is the
single, fail-closed entry point through which every empirical panel
must pass before *any* downstream metric is produced. It composes
eight orthogonal gate-checks; if **any** gate rejects, the panel is
considered untrusted and the upstream pipeline must STOP (Tier-action
``STOP`` per :mod:`death_conditions`).

Eight canonical gates:

* **G1 SCHEMA_TYPE** — keys are :class:`datetime.date`; values are
  ``np.ndarray`` with dtype ``np.float64``.
* **G2 SHAPE** — every matrix is square ``(N, N)`` with the same
  ``N`` as ``len(node_labels)``.
* **G3 FINITE** — no NaN / no Inf in any entry.
* **G4 SIGN** — every entry ≥ 0 (no negative interbank exposures).
* **G5 DIAGONAL** — diagonal entries are zero (no self-loops).
* **G6 SPARSITY** — at least one non-zero entry per snapshot
  (no all-zero matrix may smuggle a "no exposures" claim).
* **G7 MONOTONIC_TIME** — dates are strictly increasing across
  the iteration order; no duplicates.
* **G8 PROVENANCE** — every panel snapshot carries a
  ``Provenance`` record with ``source_id``, ``schema_version``,
  ``capture_timestamp_utc`` (ISO-8601 with offset), and a
  non-empty ``payload_sha256`` hex string.

Pure-function API. No I/O. Every gate returns a
:class:`GateOutcome`; the orchestrator returns a
:class:`DataFirewallReport`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "GateName",
    "GateOutcome",
    "DataFirewallReport",
    "Provenance",
    "FIREWALL_GATES",
    "PROVENANCE_SCHEMA_VERSION",
    "gate_schema_type",
    "gate_shape",
    "gate_finite",
    "gate_sign",
    "gate_diagonal",
    "gate_sparsity",
    "gate_monotonic_time",
    "gate_provenance",
    "run_data_firewall",
]


GateName = Literal[
    "G1_schema_type",
    "G2_shape",
    "G3_finite",
    "G4_sign",
    "G5_diagonal",
    "G6_sparsity",
    "G7_monotonic_time",
    "G8_provenance",
]


FIREWALL_GATES: Final[tuple[GateName, ...]] = (
    "G1_schema_type",
    "G2_shape",
    "G3_finite",
    "G4_sign",
    "G5_diagonal",
    "G6_sparsity",
    "G7_monotonic_time",
    "G8_provenance",
)


PROVENANCE_SCHEMA_VERSION: Final[str] = "interbank.panel.v1"


# 64-character lowercase hex, exactly — sha256 hex digest.
_SHA256_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Result of a single gate evaluation.

    Attributes
    ----------
    name
        Gate identifier (matches one of :data:`FIREWALL_GATES`).
    passed
        Whether the gate accepted the input.
    reason
        Human-readable explanation; populated for both pass and
        fail to keep the audit log self-describing.
    """

    name: GateName
    passed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class DataFirewallReport:
    """Aggregate firewall outcome.

    Attributes
    ----------
    passed_all
        ``True`` iff every gate accepted the input. Mirrors the
        :class:`DataFirewallResultLike` protocol consumed by
        :func:`research.systemic_risk.death_conditions
        .trigger_data_proxy_invalid`.
    gate_outcomes
        Full per-gate evaluation log (passed and rejected).
    """

    passed_all: bool
    gate_outcomes: tuple[GateOutcome, ...]


@dataclass(frozen=True, slots=True)
class Provenance:
    """Mandatory provenance record attached to every panel snapshot.

    Attributes
    ----------
    source_id
        Human-readable identifier of the upstream ingest pipeline,
        e.g. ``"e-MID-daily-snapshot"``.
    schema_version
        Schema version string; must equal
        :data:`PROVENANCE_SCHEMA_VERSION` to be accepted.
    capture_timestamp_utc
        ISO-8601 timestamp with explicit offset (e.g.
        ``"2026-05-08T12:00:00+00:00"``) marking when the snapshot
        was captured, **not** when it was ingested.
    payload_sha256
        64-character lowercase hex sha256 of the canonical
        payload representation.
    """

    source_id: str
    schema_version: str
    capture_timestamp_utc: str
    payload_sha256: str


# ---------------------------------------------------------------------------
# Individual gates — each accepts the panel + auxiliary state and returns
# a single GateOutcome. Functions are pure; they do not mutate inputs.
# ---------------------------------------------------------------------------


def gate_schema_type(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G1 — every key is a :class:`date` and every value is ``ndarray[float64]``."""
    if not isinstance(panels, Mapping):
        return GateOutcome(
            name="G1_schema_type",
            passed=False,
            reason="panels is not a Mapping",
        )
    if len(panels) == 0:
        return GateOutcome(
            name="G1_schema_type",
            passed=False,
            reason="panels is empty",
        )
    bad_keys: list[str] = []
    bad_values: list[str] = []
    for k, v in panels.items():
        if not isinstance(k, date) or isinstance(k, datetime):
            # datetime is a subclass of date but the firewall demands
            # a date-only key (no time-of-day).
            bad_keys.append(repr(k))
            continue
        if not isinstance(v, np.ndarray):
            bad_values.append(f"{k.isoformat()}: not ndarray")
            continue
        if v.dtype != np.float64:
            bad_values.append(f"{k.isoformat()}: dtype={v.dtype}")
    if bad_keys or bad_values:
        return GateOutcome(
            name="G1_schema_type",
            passed=False,
            reason=(f"non-date keys: {bad_keys[:3]}; non-ndarray-float64 values: {bad_values[:3]}"),
        )
    return GateOutcome(
        name="G1_schema_type",
        passed=True,
        reason=f"all {len(panels)} entries are (date, ndarray[float64])",
    )


def gate_shape(
    panels: Mapping[date, NDArray[np.float64]],
    n_nodes: int,
) -> GateOutcome:
    """G2 — every matrix is ``(n_nodes, n_nodes)``."""
    if n_nodes <= 0:
        return GateOutcome(
            name="G2_shape",
            passed=False,
            reason=f"n_nodes must be > 0, got {n_nodes}",
        )
    bad: list[str] = []
    for k, v in panels.items():
        if not isinstance(v, np.ndarray):
            bad.append(f"{k.isoformat()}: not ndarray")
            continue
        if v.ndim != 2 or v.shape[0] != n_nodes or v.shape[1] != n_nodes:
            bad.append(f"{k.isoformat()}: shape={v.shape}")
    if bad:
        return GateOutcome(
            name="G2_shape",
            passed=False,
            reason=f"expected ({n_nodes},{n_nodes}); offending: {bad[:3]}",
        )
    return GateOutcome(
        name="G2_shape",
        passed=True,
        reason=f"all snapshots conform to ({n_nodes}, {n_nodes})",
    )


def gate_finite(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G3 — no NaN, no Inf anywhere."""
    bad: list[str] = []
    for k, v in panels.items():
        if not isinstance(v, np.ndarray):
            continue
        if not np.all(np.isfinite(v)):
            n_nan = int(np.isnan(v).sum())
            n_inf = int(np.isinf(v).sum())
            bad.append(f"{k.isoformat()}: nan={n_nan}, inf={n_inf}")
    if bad:
        return GateOutcome(
            name="G3_finite",
            passed=False,
            reason=f"non-finite entries: {bad[:3]}",
        )
    return GateOutcome(
        name="G3_finite",
        passed=True,
        reason=f"all {len(panels)} matrices are finite",
    )


def gate_sign(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G4 — every entry ≥ 0 (negative interbank exposures are unphysical)."""
    bad: list[str] = []
    for k, v in panels.items():
        if not isinstance(v, np.ndarray):
            continue
        n_neg = int((v < 0.0).sum())
        if n_neg > 0:
            bad.append(f"{k.isoformat()}: {n_neg} negative entries")
    if bad:
        return GateOutcome(
            name="G4_sign",
            passed=False,
            reason=f"negative exposures detected: {bad[:3]}",
        )
    return GateOutcome(
        name="G4_sign",
        passed=True,
        reason="all entries non-negative",
    )


def gate_diagonal(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G5 — diagonal entries are zero (a bank does not lend to itself).

    Strict equality to 0.0 — there is no physical interpretation for
    a self-loop in the bilateral exposure graph.
    """
    bad: list[str] = []
    for k, v in panels.items():
        if not isinstance(v, np.ndarray) or v.ndim != 2:
            continue
        diag = np.diagonal(v)
        if np.any(diag != 0.0):
            n_nonzero = int((diag != 0.0).sum())
            bad.append(f"{k.isoformat()}: {n_nonzero} non-zero diag entries")
    if bad:
        return GateOutcome(
            name="G5_diagonal",
            passed=False,
            reason=f"self-loops present: {bad[:3]}",
        )
    return GateOutcome(
        name="G5_diagonal",
        passed=True,
        reason="all diagonals are zero",
    )


def gate_sparsity(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G6 — at least one non-zero entry per snapshot.

    A panel of all-zero matrices would silently pass G3/G4/G5 but
    represent a *missing* observation — the firewall blocks it.
    """
    bad: list[str] = []
    for k, v in panels.items():
        if not isinstance(v, np.ndarray):
            continue
        if v.size == 0 or not np.any(v != 0.0):
            bad.append(k.isoformat())
    if bad:
        return GateOutcome(
            name="G6_sparsity",
            passed=False,
            reason=f"all-zero or empty snapshots: {bad[:3]}",
        )
    return GateOutcome(
        name="G6_sparsity",
        passed=True,
        reason="every snapshot has at least one non-zero exposure",
    )


def gate_monotonic_time(
    panels: Mapping[date, NDArray[np.float64]],
) -> GateOutcome:
    """G7 — dates are strictly increasing across iteration order.

    The firewall accepts the iteration order as authoritative
    (caller is responsible for using a stable mapping such as
    ``dict`` insertion order or :class:`collections.OrderedDict`).
    Duplicate dates are rejected; non-monotonic order is rejected.
    """
    keys = list(panels.keys())
    if len(keys) <= 1:
        return GateOutcome(
            name="G7_monotonic_time",
            passed=True,
            reason="≤ 1 snapshot — vacuously monotonic",
        )
    for prev, curr in zip(keys, keys[1:]):
        if not (isinstance(prev, date) and isinstance(curr, date)):
            return GateOutcome(
                name="G7_monotonic_time",
                passed=False,
                reason=f"non-date key encountered between {prev!r} and {curr!r}",
            )
        if curr <= prev:
            return GateOutcome(
                name="G7_monotonic_time",
                passed=False,
                reason=(f"dates not strictly increasing: {prev.isoformat()} -> {curr.isoformat()}"),
            )
    return GateOutcome(
        name="G7_monotonic_time",
        passed=True,
        reason=f"{len(keys)} dates strictly increasing",
    )


def gate_provenance(
    provenances: Mapping[date, Provenance],
    panel_keys: tuple[date, ...],
) -> GateOutcome:
    """G8 — every snapshot has a complete provenance record.

    Required fields:
      * ``source_id`` — non-empty, non-whitespace.
      * ``schema_version`` == :data:`PROVENANCE_SCHEMA_VERSION`.
      * ``capture_timestamp_utc`` — ISO-8601 with explicit offset.
      * ``payload_sha256`` — exactly 64 lowercase hex characters.

    A panel snapshot without a matching provenance entry fails
    immediately.
    """
    missing = [k.isoformat() for k in panel_keys if k not in provenances]
    if missing:
        return GateOutcome(
            name="G8_provenance",
            passed=False,
            reason=f"missing provenance for: {missing[:3]}",
        )
    bad_fields: list[str] = []
    for k in panel_keys:
        p = provenances[k]
        if not isinstance(p, Provenance):
            bad_fields.append(f"{k.isoformat()}: not Provenance")
            continue
        if not p.source_id or not p.source_id.strip():
            bad_fields.append(f"{k.isoformat()}: empty source_id")
        if p.schema_version != PROVENANCE_SCHEMA_VERSION:
            bad_fields.append(f"{k.isoformat()}: schema_version={p.schema_version!r}")
        try:
            ts = datetime.fromisoformat(p.capture_timestamp_utc)
        except ValueError:
            bad_fields.append(
                f"{k.isoformat()}: unparseable capture_timestamp_utc={p.capture_timestamp_utc!r}"
            )
        else:
            if ts.tzinfo is None:
                bad_fields.append(f"{k.isoformat()}: capture_timestamp_utc lacks tz offset")
        if not _SHA256_HEX_RE.match(p.payload_sha256):
            bad_fields.append(f"{k.isoformat()}: payload_sha256 not 64-hex")
    if bad_fields:
        return GateOutcome(
            name="G8_provenance",
            passed=False,
            reason=f"provenance defects: {bad_fields[:3]}",
        )
    return GateOutcome(
        name="G8_provenance",
        passed=True,
        reason=f"complete provenance for {len(panel_keys)} snapshots",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_data_firewall(
    panels: Mapping[date, NDArray[np.float64]],
    node_labels: tuple[str, ...],
    provenances: Mapping[date, Provenance],
) -> DataFirewallReport:
    """Run all eight gates on the panel.

    Gates are evaluated in canonical order; *every* gate runs
    regardless of earlier failures so the report contains a complete
    audit trail. ``passed_all`` is the conjunction of every gate's
    ``passed`` flag.

    Parameters
    ----------
    panels
        Mapping from snapshot date to ``(N, N)`` exposure matrix.
    node_labels
        Canonical roster of node identifiers; ``len(node_labels)`` is
        the expected ``N``.
    provenances
        One :class:`Provenance` per panel snapshot key.

    Returns
    -------
    DataFirewallReport
        Aggregate outcome plus per-gate evaluation log.
    """
    n_nodes = len(node_labels)
    panel_keys = tuple(panels.keys())
    outcomes: tuple[GateOutcome, ...] = (
        gate_schema_type(panels),
        gate_shape(panels, n_nodes=n_nodes),
        gate_finite(panels),
        gate_sign(panels),
        gate_diagonal(panels),
        gate_sparsity(panels),
        gate_monotonic_time(panels),
        gate_provenance(provenances, panel_keys=panel_keys),
    )
    passed_all = all(o.passed for o in outcomes)
    return DataFirewallReport(passed_all=passed_all, gate_outcomes=outcomes)
