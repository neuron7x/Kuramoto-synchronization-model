# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable resolution audit for descriptor research lines.

This module answers one question, deterministically and fail-closed:
*does a descriptor run carry enough resolution to say anything at all?*

It is a **measurement-discipline gate**, not a descriptor and not a
predictor. "We ran the code" is not "we observed the phenomenon": a run
over four samples from a single session with 40% invalid points and no
replay command has executed, but it has not *resolved* anything. This
auditor reads the run's own metadata — sample depth, session count,
temporal cadence, finite / invalid ratios, graph density, replayability,
provenance completeness — and returns a verdict of ``"sufficient"``,
``"insufficient"``, or ``"unknown"`` together with the concrete list of
resolution dimensions that are blocking a claim.

The verdict carries no predictive, significance, or financial meaning;
every output declares ``claim_boundary="descriptor_only_not_predictor"``.
A ``"sufficient"`` verdict says *the measurement is dense enough to be
described*, never *the descriptor predicts anything*.

Determinism
-----------
:func:`audit_resolution` is a pure function of its input mapping. There is
no clock, no randomness, and no process-global state, so the same metadata
always yields the same verdict and the same (sorted) ``blocked_claims``.

Fail-closed
-----------
Missing or inconsistent input metadata is rejected with :class:`ValueError`
rather than silently defaulted: a missing required key, a non-integer or
negative count, counts that do not reconcile
(``finite_count + invalid_count != input_count``), an empty temporal
token, a non-boolean flag, or a graph density outside ``[0, 1]`` all fail
closed. The auditor never invents resolution it cannot see.

Worked example
--------------
>>> verdict = audit_resolution(
...     {
...         "input_count": 4,
...         "finite_count": 4,
...         "invalid_count": 0,
...         "session_count": 1,
...         "temporal_resolution": "1min",
...         "replayable": False,
...         "artifact_complete": True,
...     }
... )
>>> verdict.resolution_status
'insufficient'
>>> verdict.blocked_claims
('input_depth', 'replayability')
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping

__all__ = [
    "CLAIM_BOUNDARY",
    "MIN_INPUT_COUNT",
    "MIN_SESSION_COUNT",
    "MIN_FINITE_RATIO",
    "MAX_INVALID_RATIO",
    "MIN_GRAPH_DENSITY",
    "ResolutionStatus",
    "ResolutionAudit",
    "audit_resolution",
]

#: The single declared boundary string shared by every verdict's metadata.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"

# ── governed resolution floors ───────────────────────────────────────────
# These are the discipline thresholds. They are descriptor-only resolution
# gates, not tuned predictive parameters; a run below any floor is described
# as under-resolved rather than promoted. Their exact values are governed
# (a calibration concern) — they are pinned here as module constants so the
# verdict stays a pure, byte-deterministic function of (metadata, floors).
MIN_INPUT_COUNT: int = 32
MIN_SESSION_COUNT: int = 1
MIN_FINITE_RATIO: float = 0.95
MAX_INVALID_RATIO: float = 0.05
MIN_GRAPH_DENSITY: float = 1e-3

ResolutionStatus = Literal["sufficient", "insufficient", "unknown"]

#: Sentinel temporal token meaning "cadence not known" — drives "unknown".
_UNKNOWN_TEMPORAL: str = "unknown"

_REQUIRED_KEYS: tuple[str, ...] = (
    "input_count",
    "finite_count",
    "invalid_count",
    "session_count",
    "temporal_resolution",
    "replayable",
    "artifact_complete",
)


@dataclass(frozen=True, slots=True)
class ResolutionAudit:
    """Immutable verdict of a single resolution audit.

    ``resolution_status`` is ``"unknown"`` when the metadata is too thin to
    even assess resolution (no samples, or an explicitly unknown temporal
    cadence), ``"insufficient"`` when one or more dimensions fall below
    their floor, and ``"sufficient"`` only when every applicable dimension
    clears its floor. ``blocked_claims`` is the sorted tuple of failing
    resolution-dimension tokens and is preserved as negative evidence in
    every non-``"sufficient"`` verdict.
    """

    temporal_resolution: str
    session_count: int
    input_count: int
    finite_count: int
    invalid_count: int
    graph_density: float | None
    finite_ratio: float | None
    invalid_ratio: float | None
    replayable: bool
    artifact_complete: bool
    resolution_status: ResolutionStatus
    blocked_claims: tuple[str, ...]
    claim_boundary: str = CLAIM_BOUNDARY

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping with deterministic key ordering."""
        return {
            "temporal_resolution": self.temporal_resolution,
            "session_count": self.session_count,
            "input_count": self.input_count,
            "finite_count": self.finite_count,
            "invalid_count": self.invalid_count,
            "graph_density": self.graph_density,
            "finite_ratio": self.finite_ratio,
            "invalid_ratio": self.invalid_ratio,
            "replayable": self.replayable,
            "artifact_complete": self.artifact_complete,
            "resolution_status": self.resolution_status,
            "blocked_claims": list(self.blocked_claims),
            "claim_boundary": self.claim_boundary,
        }


def _require(metadata: Mapping[str, Any], key: str) -> Any:
    if key not in metadata:
        raise ValueError(f"resolution-auditor: missing required metadata key {key!r}")
    return metadata[key]


def _as_count(value: Any, name: str) -> int:
    """Return ``value`` as a non-negative ``int`` or fail closed.

    ``bool`` is rejected explicitly: ``True``/``False`` are ``int`` subtypes
    that would otherwise pass as counts 1/0 and mask a malformed field.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"resolution-auditor: {name} must be a non-negative int, got {value!r}")
    if value < 0:
        raise ValueError(f"resolution-auditor: {name} must be >= 0, got {value}")
    return value


def _as_flag(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"resolution-auditor: {name} must be a bool, got {value!r}")
    return value


def _as_temporal(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "resolution-auditor: temporal_resolution must be a non-empty string "
            f"(use {_UNKNOWN_TEMPORAL!r} to declare an unknown cadence), got {value!r}"
        )
    return value


def _as_graph_density(value: Any) -> float | None:
    """Return an optional graph density in ``[0, 1]`` or fail closed.

    ``None`` means the descriptor is not graph-based; that dimension is then
    *not applicable* rather than failing. A present density outside the unit
    interval is malformed and fails closed.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"resolution-auditor: graph_density must be a float in [0, 1] or None, got {value!r}"
        )
    density = float(value)
    if not math.isfinite(density):  # rejects NaN and ±inf
        raise ValueError(f"resolution-auditor: graph_density must be finite, got {value!r}")
    if not 0.0 <= density <= 1.0:
        raise ValueError(f"resolution-auditor: graph_density must lie in [0, 1], got {density}")
    return density


def audit_resolution(metadata: Mapping[str, Any]) -> ResolutionAudit:
    """Audit whether ``metadata`` describes a sufficiently resolved run.

    Required keys: ``input_count``, ``finite_count``, ``invalid_count``,
    ``session_count`` (non-negative ints), ``temporal_resolution``
    (non-empty str; ``"unknown"`` to declare an unknown cadence),
    ``replayable`` and ``artifact_complete`` (bools). Optional:
    ``graph_density`` (float in ``[0, 1]`` or ``None`` when the descriptor
    is not graph-based).

    The counts must reconcile: ``finite_count + invalid_count`` must equal
    ``input_count``; any other relation is a malformed record and fails
    closed.
    """
    if not isinstance(metadata, Mapping):
        raise ValueError(
            f"resolution-auditor: metadata must be a mapping, got {type(metadata).__name__}"
        )
    for key in _REQUIRED_KEYS:
        _require(metadata, key)

    input_count = _as_count(metadata["input_count"], "input_count")
    finite_count = _as_count(metadata["finite_count"], "finite_count")
    invalid_count = _as_count(metadata["invalid_count"], "invalid_count")
    session_count = _as_count(metadata["session_count"], "session_count")
    temporal_resolution = _as_temporal(metadata["temporal_resolution"])
    replayable = _as_flag(metadata["replayable"], "replayable")
    artifact_complete = _as_flag(metadata["artifact_complete"], "artifact_complete")
    graph_density = _as_graph_density(metadata.get("graph_density"))

    if finite_count + invalid_count != input_count:
        raise ValueError(
            "resolution-auditor: inconsistent counts — "
            f"finite_count ({finite_count}) + invalid_count ({invalid_count}) "
            f"!= input_count ({input_count})"
        )

    # Ratios are undefined with no samples; surface that as None rather than
    # dividing by zero or inventing a value.
    finite_ratio = finite_count / input_count if input_count > 0 else None
    invalid_ratio = invalid_count / input_count if input_count > 0 else None

    # ── per-dimension failure tokens (sorted, deterministic) ──────────────
    blocked: list[str] = []
    if input_count < MIN_INPUT_COUNT:
        blocked.append("input_depth")
    if session_count < MIN_SESSION_COUNT:
        blocked.append("session_count")
    if finite_ratio is not None and finite_ratio < MIN_FINITE_RATIO:
        blocked.append("finite_ratio")
    if invalid_ratio is not None and invalid_ratio > MAX_INVALID_RATIO:
        blocked.append("invalid_ratio")
    if graph_density is not None and graph_density < MIN_GRAPH_DENSITY:
        blocked.append("graph_density")
    if not replayable:
        blocked.append("replayability")
    if not artifact_complete:
        blocked.append("artifact_completeness")
    blocked_claims = tuple(sorted(blocked))

    # "unknown" dominates: with no samples or an undeclared cadence the run
    # cannot be assessed, even though some dimensions may already fail (those
    # failures are still preserved in blocked_claims as negative evidence).
    status: ResolutionStatus
    if input_count == 0 or temporal_resolution == _UNKNOWN_TEMPORAL:
        status = "unknown"
    elif blocked_claims:
        status = "insufficient"
    else:
        status = "sufficient"

    return ResolutionAudit(
        temporal_resolution=temporal_resolution,
        session_count=session_count,
        input_count=input_count,
        finite_count=finite_count,
        invalid_count=invalid_count,
        graph_density=graph_density,
        finite_ratio=finite_ratio,
        invalid_ratio=invalid_ratio,
        replayable=replayable,
        artifact_complete=artifact_complete,
        resolution_status=status,
        blocked_claims=blocked_claims,
    )
