# SPDX-License-Identifier: MIT
"""Offline, network-free guards for C-real open-data admissibility.

Fail-closed by construction: UNKNOWN never becomes admissible; any None
on a required field blocks; rejected candidates always carry a blocker.
"""

from __future__ import annotations

from research.ctc_falsify.c_real.open_data.candidate import (
    OpenDataCandidate,
    classify_candidate,
    explain_candidate_blockers,
    has_minimal_c_real_requirements,
    terminal_verdict,
)

_BASE = dict(
    dataset_id="DANDI:T",
    source="DANDI Archive",
    source_url="https://dandiarchive.org/dandiset/T",
    license_or_access_status="public",
    data_format="NWB",
    estimated_size_bytes=1024,
    access_method="dandi-api-metadata",
    candidate_routing_label_name="attention_cue",
    sessions_count_estimate=12,
    subject_count_estimate=12,
    access_reproducible=True,
    checked_at_utc="1970-01-01T00:00:00+00:00",
)


def _c(**kw: object) -> OpenDataCandidate:
    d = dict(_BASE)
    d.update(kw)
    return OpenDataCandidate(**d)  # type: ignore[arg-type]


def test_fully_confirmed_candidate_is_admissible() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
    )
    assert has_minimal_c_real_requirements(c) is True
    assert classify_candidate(c) == "ADMISSIBLE_BINDABLE"
    assert explain_candidate_blockers(c) == ()


def test_no_lfp_rejects() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=False,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
    )
    assert classify_candidate(c) == "REJECT_NO_LFP"


def test_no_spikes_rejects() -> None:
    c = _c(
        has_spikes=False,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
    )
    assert classify_candidate(c) == "REJECT_NO_SPIKES"


def test_single_area_rejects() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=False,
        has_trials=True,
        has_independent_routing_label=True,
    )
    assert classify_candidate(c) == "REJECT_SINGLE_AREA"


def test_no_independent_label_rejects() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=False,
    )
    assert classify_candidate(c) == "REJECT_NO_INDEPENDENT_LABEL"


def test_no_trial_structure_rejects() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=False,
        has_independent_routing_label=True,
    )
    assert classify_candidate(c) == "REJECT_NO_TRIAL_STRUCTURE"


def test_access_blocked_rejects() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
        license_or_access_status="embargoed",
    )
    assert classify_candidate(c) == "REJECT_ACCESS_BLOCKED"


def test_too_large_does_not_become_admissible() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
        estimated_size_bytes=500 * 1024**3,
    )
    assert classify_candidate(c) == "REJECT_TOO_LARGE_FOR_ENV"
    assert has_minimal_c_real_requirements(c) is False


def test_unknown_never_becomes_admissible() -> None:
    # spikes+lfp known, but areas/trials/label unknown ⇒ UNKNOWN, not adm.
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=None,
        has_trials=None,
        has_independent_routing_label=None,
    )
    v = classify_candidate(c)
    assert v == "UNKNOWN_NEEDS_MANUAL_REVIEW"
    assert has_minimal_c_real_requirements(c) is False
    assert "independent_routing_label_not_confirmed" in explain_candidate_blockers(c)


def test_self_derived_label_is_not_independent() -> None:
    # has_independent_routing_label must be the *independent* flag; a
    # named candidate label with the flag still None cannot pass.
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=None,
        candidate_routing_label_name="derived_from_signal",
    )
    assert classify_candidate(c) != "ADMISSIBLE_BINDABLE"


def test_session_disjoint_capacity_required() -> None:
    c = _c(
        has_spikes=True,
        has_lfp=True,
        has_two_or_more_areas=True,
        has_trials=True,
        has_independent_routing_label=True,
        sessions_count_estimate=2,
        subject_count_estimate=2,
    )
    assert has_minimal_c_real_requirements(c) is False
    assert "session_disjoint_capacity_not_confirmed" in explain_candidate_blockers(c)


def test_terminal_no_open_dataset_when_empty() -> None:
    assert terminal_verdict([], binding_tooling_present=True) == (
        "INADMISSIBLE_NO_OPEN_DATASET_FOUND"
    )


def test_terminal_tooling_missing_blocks_even_admissible() -> None:
    assert (
        terminal_verdict(["ADMISSIBLE_BINDABLE"], binding_tooling_present=False)
        == "INADMISSIBLE_TOOLING_MISSING"
    )
    assert (
        terminal_verdict(["ADMISSIBLE_BINDABLE"], binding_tooling_present=True)
        == "DATASET_BOUND_READY_FOR_C_REAL"
    )


def test_terminal_no_independent_label_is_the_metadata_only_outcome() -> None:
    v = terminal_verdict(
        ["UNKNOWN_NEEDS_MANUAL_REVIEW", "REJECT_TOO_LARGE_FOR_ENV"],
        binding_tooling_present=False,
    )
    assert v == "INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL"


def test_rejected_candidate_always_has_a_blocker() -> None:
    for kw in (
        dict(has_spikes=False, has_lfp=True),
        dict(has_spikes=True, has_lfp=False),
    ):
        c = _c(
            has_two_or_more_areas=True,
            has_trials=True,
            has_independent_routing_label=True,
            **kw,
        )
        assert classify_candidate(c).startswith("REJECT_")
        assert explain_candidate_blockers(c) != ()
