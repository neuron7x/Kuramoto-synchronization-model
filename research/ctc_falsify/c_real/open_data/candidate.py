# SPDX-License-Identifier: MIT
"""Pure, offline-deterministic admissibility logic. No network here.

A candidate is ADMISSIBLE_BINDABLE only if EVERY frozen-prereg requirement
is *positively confirmed*. A required field that is unknown (None) can
never satisfy the gate — at best the candidate is
UNKNOWN_NEEDS_MANUAL_REVIEW, which is NOT admissible. The independent
routing label is mandatory and is essentially never inferable from coarse
archive metadata, so metadata-only discovery fails closed by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# Session-disjoint OOS evaluation needs a real minimum (carried from
# C-real config: MIN_SESSIONS). Subjects OR sessions may satisfy it.
MIN_SESSIONS_OR_SUBJECTS: Final[int] = 8
MAX_ENV_BYTES: Final[int] = 8 * 1024**3  # >8 GiB ⇒ too large for this env

CANDIDATE_VERDICTS: Final[tuple[str, ...]] = (
    "ADMISSIBLE_BINDABLE",
    "ADMISSIBLE_METADATA_ONLY",
    "REJECT_NO_LFP",
    "REJECT_NO_SPIKES",
    "REJECT_SINGLE_AREA",
    "REJECT_NO_INDEPENDENT_LABEL",
    "REJECT_NO_TRIAL_STRUCTURE",
    "REJECT_ACCESS_BLOCKED",
    "REJECT_TOO_LARGE_FOR_ENV",
    "UNKNOWN_NEEDS_MANUAL_REVIEW",
)

TERMINAL_VERDICTS: Final[tuple[str, ...]] = (
    "DATASET_BOUND_READY_FOR_C_REAL",
    "INADMISSIBLE_NO_OPEN_DATASET_FOUND",
    "INADMISSIBLE_TOOLING_MISSING",
    "INADMISSIBLE_DATASET_UNSUITABLE",
    "INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL",
    "INADMISSIBLE_TOO_LARGE_FOR_ENVIRONMENT",
    "INADMISSIBLE_LICENSE_OR_ACCESS_BLOCKED",
)


@dataclass(frozen=True)
class OpenDataCandidate:
    dataset_id: str
    source: str
    source_url: str
    license_or_access_status: str
    data_format: str
    estimated_size_bytes: int | None
    access_method: str
    has_spikes: bool | None
    has_lfp: bool | None
    has_two_or_more_areas: bool | None
    has_trials: bool | None
    has_independent_routing_label: bool | None
    candidate_routing_label_name: str | None
    sessions_count_estimate: int | None
    subject_count_estimate: int | None
    access_reproducible: bool | None
    checked_at_utc: str
    evidence_urls: tuple[str, ...] = field(default_factory=tuple)


def _session_disjoint_possible(c: OpenDataCandidate) -> bool | None:
    vals = [v for v in (c.sessions_count_estimate, c.subject_count_estimate) if v is not None]
    if not vals:
        return None
    return max(vals) >= MIN_SESSIONS_OR_SUBJECTS


def _too_large(c: OpenDataCandidate) -> bool | None:
    if c.estimated_size_bytes is None:
        return None
    return c.estimated_size_bytes > MAX_ENV_BYTES


def explain_candidate_blockers(c: OpenDataCandidate) -> tuple[str, ...]:
    b: list[str] = []
    if c.access_reproducible is False or c.license_or_access_status.lower() in {
        "restricted",
        "embargoed",
        "request_required",
        "blocked",
    }:
        b.append("access_or_license_blocked")
    if _too_large(c) is True:
        b.append("too_large_for_environment")
    if c.has_spikes is not True:
        b.append("spikes_not_confirmed")
    if c.has_lfp is not True:
        b.append("lfp_not_confirmed")
    if c.has_two_or_more_areas is not True:
        b.append("two_or_more_areas_not_confirmed")
    if c.has_trials is not True:
        b.append("trial_structure_not_confirmed")
    if c.has_independent_routing_label is not True:
        b.append("independent_routing_label_not_confirmed")
    if _session_disjoint_possible(c) is not True:
        b.append("session_disjoint_capacity_not_confirmed")
    return tuple(b)


def has_minimal_c_real_requirements(c: OpenDataCandidate) -> bool:
    """All required gates positively True (no None, no False)."""
    return (
        c.has_spikes is True
        and c.has_lfp is True
        and c.has_two_or_more_areas is True
        and c.has_trials is True
        and c.has_independent_routing_label is True
        and _session_disjoint_possible(c) is True
        and c.access_reproducible is True
        and _too_large(c) is not True
    )


def classify_candidate(c: OpenDataCandidate) -> str:
    # Hard rejecters first (access/size), then missing-modality rejecters.
    if c.access_reproducible is False or c.license_or_access_status.lower() in {
        "restricted",
        "embargoed",
        "request_required",
        "blocked",
    }:
        return "REJECT_ACCESS_BLOCKED"
    if _too_large(c) is True:
        return "REJECT_TOO_LARGE_FOR_ENV"
    if c.has_spikes is False:
        return "REJECT_NO_SPIKES"
    if c.has_lfp is False:
        return "REJECT_NO_LFP"
    if c.has_two_or_more_areas is False:
        return "REJECT_SINGLE_AREA"
    if c.has_trials is False:
        return "REJECT_NO_TRIAL_STRUCTURE"
    if c.has_independent_routing_label is False:
        return "REJECT_NO_INDEPENDENT_LABEL"
    if has_minimal_c_real_requirements(c):
        return "ADMISSIBLE_BINDABLE"
    # Anything unproven (None on a required field) is never admissible.
    return "UNKNOWN_NEEDS_MANUAL_REVIEW"


def terminal_verdict(verdicts: list[str], *, binding_tooling_present: bool) -> str:
    """Fail-closed roll-up over the candidate manifest."""
    if not verdicts:
        return "INADMISSIBLE_NO_OPEN_DATASET_FOUND"
    if "ADMISSIBLE_BINDABLE" in verdicts:
        if not binding_tooling_present:
            return "INADMISSIBLE_TOOLING_MISSING"
        return "DATASET_BOUND_READY_FOR_C_REAL"
    if all(v == "REJECT_ACCESS_BLOCKED" for v in verdicts):
        return "INADMISSIBLE_LICENSE_OR_ACCESS_BLOCKED"
    if all(v == "REJECT_TOO_LARGE_FOR_ENV" for v in verdicts):
        return "INADMISSIBLE_TOO_LARGE_FOR_ENVIRONMENT"
    if any(v in {"REJECT_NO_SPIKES", "REJECT_NO_LFP", "REJECT_SINGLE_AREA"} for v in verdicts) and (
        "UNKNOWN_NEEDS_MANUAL_REVIEW" not in verdicts
        and "REJECT_NO_INDEPENDENT_LABEL" not in verdicts
    ):
        return "INADMISSIBLE_DATASET_UNSUITABLE"
    # The dominant honest blocker for metadata-only discovery: the
    # mandatory independent routing label is not confirmable from coarse
    # archive metadata, so no candidate clears the gate.
    return "INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL"
