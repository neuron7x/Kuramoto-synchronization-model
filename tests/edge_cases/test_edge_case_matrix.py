# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""IERD-Q7 edge-case coverage gate (Phase-4 EXIT — fail-closed ECC).

Asserts the ``(endpoint × state × test_id)`` matrix is well-formed and
honest, scores ECC, and fail-closes every §532 requirement: the two
*hard* sub-requirements (network_failure + timeout per applicable
endpoint; simulation_diverged ↔ INV-DRO5) **and** the ECC ≥ 0.90
threshold itself.

Phase-4 EXIT: the previously-UNCOVERED client-only cells (loading,
cancelled, per-probe server_error) are now genuinely exercised by the
Playwright route-interception specs in
``apps/web/tests/edge-case-probe.spec.ts`` against the ``/edge-probe``
harness — every state is driven by ``page.route`` (delayed fulfil,
abort, fulfil 500) or a real user cancel, never faked. ECC = 1.00, so
``test_ecc_meets_threshold`` runs unguarded and fail-closed in every
lane; the claim ``edge-case-coverage-matrix`` re-classifies ANCHORED.

Tracks claim ``edge-case-coverage-matrix`` and GitHub issue
IERD-Q7 (#532).
"""

from __future__ import annotations

from tests.edge_cases.coverage_matrix import (
    ECC_THRESHOLD,
    MANDATORY_PER_ENDPOINT_STATES,
    SIMULATION_DIVERGED_STATE,
    cited_targets,
    classify,
    compute_ecc,
    covering_test,
    gated_operations,
    target_exists,
)


def test_every_cited_test_target_resolves() -> None:
    """Each test cited by the matrix still exists (rename/delete = fail).

    This is what gives the matrix teeth: a covered cell is only honest
    while its cited test is real. If any cited target vanishes the gate
    fails even though no ECC number changed.
    """
    missing = sorted(t for t in cited_targets() if not target_exists(t))
    assert not missing, (
        "IERD-Q7 matrix cites test target(s) that no longer resolve "
        f"(deleted/renamed): {missing}. A covered cell whose test has "
        f"vanished is not coverage — restore the test or move the cell "
        f"to UNCOVERED with a reason."
    )


def test_matrix_is_well_formed_and_total() -> None:
    """Every gated op is classified and every applicable cell is scored."""
    covered, applicable, ecc, rows = compute_ecc()
    assert applicable > 0, "empty applicable matrix — spec or classifier broke"
    # Every op classifies without raising.
    for _method, path in gated_operations():
        assert classify(path) in {"collection", "command", "probe"}
    # Each row is either covered (with a cited target) or explicitly
    # UNCOVERED — never an implicit gap.
    for cell, state, status, target in rows:
        assert status in {"covered", "UNCOVERED"}, (cell, state, status)
        if status == "covered":
            assert target != "-", (cell, state)
    assert covered <= applicable


def test_network_failure_and_timeout_covered_for_every_endpoint() -> None:
    """§532 hard requirement — fail-closed.

    Network failure and timeout must be tested for *every* endpoint for
    which they are applicable. This is genuinely satisfied today
    (RequestTimeoutMiddleware behavioural test + fail-closed connector
    suite), so it is asserted strictly regardless of phase.
    """
    gaps: list[str] = []
    for method, path in gated_operations():
        for state in MANDATORY_PER_ENDPOINT_STATES:
            if covering_test(path, state) is None:
                # Only a gap if the state is applicable to this class.
                from tests.edge_cases.coverage_matrix import applicable_states

                if state in applicable_states(path):
                    gaps.append(f"{method} {path} :: {state}")
    assert not gaps, (
        "IERD-Q7 §532 hard requirement violated: network_failure and "
        f"timeout must be tested for every applicable endpoint. Gaps: "
        f"{sorted(gaps)}"
    )


def test_simulation_diverged_correlates_with_inv_dro5() -> None:
    """§532: simulation divergence has a fail-closed path (INV-DRO5).

    Asserted strictly: the collection-class simulation_diverged cell
    must cite the INV-DRO5 fail-closed suite.
    """
    target = covering_test("/features", SIMULATION_DIVERGED_STATE)
    assert target is not None and "inv_dro5_fail_closed" in target, (
        "IERD-Q7 §532: simulation_diverged must correlate with the "
        f"INV-DRO5 fail-closed test; got {target!r}. INV-DRO5 is the "
        f"contract that NaN/Inf/constant/degenerate forecast input is "
        f"rejected rather than silently diverging."
    )
    assert target_exists(target), f"cited INV-DRO5 test missing: {target}"


# Phase-4 EXIT: ECC ≥ 0.90 is now genuinely met (ECC = 1.00) because the
# previously client-only states (loading / cancelled / per-probe
# server_error) are exercised by the Playwright route-interception specs
# in apps/web/tests/edge-case-probe.spec.ts against the /edge-probe
# harness. The sub-test therefore runs unguarded and fail-closed in
# every lane — no env flag, no continue-on-error.
def test_ecc_meets_threshold() -> None:
    """ECC ≥ 0.90 — fail-closed (Phase-4 EXIT, claim ANCHORED)."""
    covered, applicable, ecc, rows = compute_ecc()
    for cell, state, status, target in rows:
        print(f"\n[ecc] {cell:24s} {state:20s} {status:9s} {target}")
    print(
        f"\n[ecc] AGGREGATE covered={covered}/{applicable} "
        f"ECC={ecc:.4f} threshold={ECC_THRESHOLD:.2f}"
    )
    assert ecc >= ECC_THRESHOLD, (
        f"IERD-Q7 §5 ECC below threshold: observed ECC={ecc:.4f} < "
        f"{ECC_THRESHOLD:.2f} (covered {covered} of {applicable} genuine "
        f"applicable cells). The Playwright route-interception specs in "
        f"apps/web/tests/edge-case-probe.spec.ts back the client-only "
        f"cells; do NOT relax the matrix or cite non-exercising tests to "
        f"inflate ECC."
    )
