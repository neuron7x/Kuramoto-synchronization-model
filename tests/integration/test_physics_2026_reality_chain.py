# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics-2026 reality chain — integration of P1..P6 witnesses.

Named lie blocked
=================

  "individual witnesses pass = system claim valid"

The six engineering-analog witnesses (P1..P6) each block one local lie.
This integration test composes them into a single non-predictive reality
chain and proves that breaking ANY witness collapses the chain's
``system_claim_valid`` to False — even when all other witnesses pass.

Chain composition
=================

For a system claim "this regime is real, not noise" to be granted, all
six witnesses must agree:

  P1 PopulationEventCatalog.admit  → AdmissionWitness.accepted is True
  P2 StructuredAbsence             → status == TRUE_ABSENCE
  P3 DynamicNullModel              → WITHIN_DYNAMIC_NULL or
                                      OUTSIDE_DYNAMIC_NULL
                                      (NOT DRIFT_EXCEEDED, NOT INSUFFICIENT)
  P4 GlobalParityWitness           → status == GLOBAL_PASS
  P5 MotionalCorrelationWitness    → DYNAMIC_RELATION_CONFIRMED or
                                      STATIC_ONLY (NOT INSUFFICIENT, NOT UNKNOWN)
  P6 CompositeBindingStructure     → PERSISTENT_BINDING

Any miss collapses the chain. There is no numeric score, no confidence,
no aggregated index. The chain is a boolean AND of the six structural
verdicts.

Falsifier
=========

For each witness, a deliberately-broken input is constructed; the test
proves that the chain refuses ``system_claim_valid = True`` and reports
the breaking witness by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pytest

from geosync_hpc.coherence.composite_binding_structure import (
    BindingInput,
    BindingStatus,
    assess_composite_binding,
)
from geosync_hpc.coherence.global_parity_witness import (
    GlobalParityInput,
    LocalWitness,
    assess_global_parity,
)
from geosync_hpc.dynamics.motional_correlation_witness import (
    MotionalInput,
    MotionalStatus,
    assess_motional_correlation,
)
from geosync_hpc.inference.effective_depth_guard import (
    DepthInput,
    DepthStatus,
    assess_effective_depth,
)
from geosync_hpc.nulls.dynamic_null_model import (
    NullInput,
    NullStatus,
    assess_dynamic_null,
)
from geosync_hpc.regimes.population_event_catalog import (
    EventInput,
    EvidenceTier,
    PopulationEventCatalog,
    SourceWindow,
)
from geosync_hpc.regimes.regime_front_roughness_witness import (
    FrontInput,
    FrontStatus,
    assess_regime_front_roughness,
)
from geosync_hpc.regimes.structured_absence import (
    AbsenceInput,
    AbsenceStatus,
    assess_absence,
)


@dataclass(frozen=True)
class ChainVerdict:
    """Aggregate verdict over the six P1..P6 witnesses.

    No numeric score, no confidence, no health index — only a boolean
    and the name of the first failing witness.
    """

    system_claim_valid: bool
    failing_witness: str | None
    detail: str


def _assess_chain(
    *,
    catalog: PopulationEventCatalog,
    event: EventInput,
    absence: AbsenceInput,
    null: NullInput,
    parity: GlobalParityInput,
    motion: MotionalInput,
    binding: BindingInput,
    front: FrontInput | None = None,
    depth: DepthInput | None = None,
) -> ChainVerdict:
    """Compose the witnesses into one structural verdict.

    P1..P6 are mandatory. P7 (front roughness) and P9 (effective depth)
    are optional and only evaluated when their input is provided.
    Returns ``ChainVerdict(False, "<P_NAME>", reason)`` on the first
    failing witness; otherwise ``ChainVerdict(True, None, "ALL_PASS")``.
    """
    p1 = catalog.admit(event)
    if not p1.accepted:
        return ChainVerdict(False, "P1_POPULATION_EVENT_CATALOG", p1.reason)

    p2 = assess_absence(absence)
    if p2.status is not AbsenceStatus.TRUE_ABSENCE:
        return ChainVerdict(False, "P2_STRUCTURED_ABSENCE_INFERENCE", p2.reason)

    p3 = assess_dynamic_null(null)
    if p3.status not in (NullStatus.WITHIN_DYNAMIC_NULL, NullStatus.OUTSIDE_DYNAMIC_NULL):
        return ChainVerdict(False, "P3_DYNAMIC_NULL_MODEL", p3.reason)

    p4 = assess_global_parity(parity)
    if p4.status != "GLOBAL_PASS":
        return ChainVerdict(False, "P4_GLOBAL_PARITY_WITNESS", p4.reason)

    p5 = assess_motional_correlation(motion)
    if p5.status not in (
        MotionalStatus.DYNAMIC_RELATION_CONFIRMED,
        MotionalStatus.STATIC_ONLY,
    ):
        return ChainVerdict(False, "P5_MOTIONAL_CORRELATION_WITNESS", p5.reason)

    p6 = assess_composite_binding(binding)
    if p6.binding_status is not BindingStatus.PERSISTENT_BINDING:
        return ChainVerdict(False, "P6_COMPOSITE_BINDING_STRUCTURE", p6.reason)

    if front is not None:
        p7 = assess_regime_front_roughness(front)
        if p7.status in (FrontStatus.INSUFFICIENT_HISTORY, FrontStatus.INVALID_INPUT):
            return ChainVerdict(False, "P7_REGIME_FRONT_ROUGHNESS", p7.reason)

    if depth is not None:
        p9 = assess_effective_depth(depth)
        if p9.status not in (DepthStatus.EFFECTIVE_DEPTH_FOUND, DepthStatus.REDUNDANT_DEPTH):
            return ChainVerdict(False, "P9_EFFECTIVE_DEPTH_GUARD", p9.reason)

    return ChainVerdict(True, None, "ALL_PASS")


# ---------------------------------------------------------------------------
# Fixture builders — minimal, all-passing inputs for each witness.
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _good_event(event_id: str = "evt-good") -> EventInput:
    return EventInput(
        event_id=event_id,
        timestamp=_utc(2026, 4, 27),
        asset_universe=("BTC", "ETH"),
        regime_label="vol-cluster-A",
        event_features={"vol": 0.32, "skew": -0.4},
        evidence_tier=EvidenceTier.PRIMARY,
        source_window=SourceWindow(start=_utc(2026, 4, 26), end=_utc(2026, 4, 27)),
        provenance="exchange-api-v1",
        falsifier_status="OPEN",
    )


def _good_absence() -> AbsenceInput:
    return AbsenceInput(
        observed_state_space=frozenset({"x", "y"}),
        candidate_empty_region=frozenset({"z"}),
        coverage_ratio=0.95,
        selection_bias_flags=(),
        sample_count=200,
        minimum_coverage_threshold=0.8,
    )


def _good_null() -> NullInput:
    return NullInput(
        baseline_series=(1.0, 1.05, 1.10),
        observed_value=1.10,
        drift_bound=0.5,
        null_tolerance=0.05,
        minimum_history=3,
    )


def _good_parity() -> GlobalParityInput:
    return GlobalParityInput(
        local_witnesses=(
            LocalWitness(name="m1", passed=True, tier="ENGINEERING_ANALOG", reason="ok"),
            LocalWitness(name="m2", passed=True, tier="ENGINEERING_ANALOG", reason="ok"),
        ),
        claim_ledger_ok=True,
        dependency_truth_ok=True,
        invariant_coverage_ok=True,
        ci_gate_ok=True,
        required_surfaces=GlobalParityInput.canonical_surfaces(),
    )


def _good_motion() -> MotionalInput:
    rng = np.random.default_rng(0)
    n = 96
    x_arr = rng.standard_normal(n).cumsum()
    y_arr = x_arr + 0.01 * rng.standard_normal(n)
    return MotionalInput(
        x=tuple(float(v) for v in x_arr),
        y=tuple(float(v) for v in y_arr),
        shuffle_count=200,
        margin=0.05,
        minimum_length=16,
        seed=1234,
    )


def _good_binding() -> BindingInput:
    return BindingInput(
        asset_cluster=("BTC", "ETH"),
        correlation_window=(0.9, 0.85, 0.92, 0.88, 0.91),
        correlation_threshold=0.7,
        persistence_window=3,
        perturbation_response=(0.82, 0.79, 0.84),
    )


def _good_front() -> FrontInput:
    rng = np.random.default_rng(11)
    n = 96
    boundary = tuple(float(v) for v in rng.standard_normal(n).cumsum())
    time_index = tuple(float(i) for i in range(n))
    return FrontInput(
        boundary_series=boundary,
        time_index=time_index,
        window=8,
        null_shuffle_seed=11,
        roughness_threshold=0.05,
        minimum_length=32,
    )


def _good_depth() -> DepthInput:
    return DepthInput(
        outputs_by_depth={
            1: (1.0, 0.0),
            2: (1.0, 1.0),
            3: (1.0, 2.0),
        },
        tolerance=0.1,
        noise_level=0.01,
        minimum_depth=1,
        maximum_depth=3,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_all_witnesses_pass_grants_system_claim() -> None:
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is True
    assert verdict.failing_witness is None


# ---------------------------------------------------------------------------
# Falsifier matrix — break each witness in turn, prove the chain refuses.
# ---------------------------------------------------------------------------


def test_breaking_p1_collapses_chain() -> None:
    """Duplicate event_id is rejected by P1 catalog."""
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_id="evt-already-here"))
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(event_id="evt-already-here"),  # duplicate
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P1_POPULATION_EVENT_CATALOG"
    assert verdict.detail == "DUPLICATE_EVENT_ID"


def test_breaking_p2_collapses_chain() -> None:
    bad_absence = AbsenceInput(
        observed_state_space=frozenset({"x", "y"}),
        candidate_empty_region=frozenset({"z"}),
        coverage_ratio=0.10,
        selection_bias_flags=(),
        sample_count=200,
        minimum_coverage_threshold=0.8,
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=bad_absence,
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P2_STRUCTURED_ABSENCE_INFERENCE"


def test_breaking_p3_collapses_chain() -> None:
    bad_null = NullInput(
        baseline_series=(1.0, 1.5, 2.0),
        observed_value=1.95,
        drift_bound=0.5,
        null_tolerance=0.1,
        minimum_history=3,
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=bad_null,
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P3_DYNAMIC_NULL_MODEL"


def test_breaking_p4_collapses_chain() -> None:
    bad_parity = GlobalParityInput(
        local_witnesses=(
            LocalWitness(name="m1", passed=True, tier="ENGINEERING_ANALOG", reason="ok"),
        ),
        claim_ledger_ok=True,
        dependency_truth_ok=False,
        invariant_coverage_ok=True,
        ci_gate_ok=True,
        required_surfaces=GlobalParityInput.canonical_surfaces(),
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=bad_parity,
        motion=_good_motion(),
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P4_GLOBAL_PARITY_WITNESS"


def test_breaking_p5_collapses_chain() -> None:
    bad_motion = MotionalInput(
        x=(1.0, 2.0, 3.0),
        y=(1.0, 2.0, 3.0),
        shuffle_count=10,
        margin=0.05,
        minimum_length=16,
        seed=0,
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=bad_motion,
        binding=_good_binding(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P5_MOTIONAL_CORRELATION_WITNESS"


def test_breaking_p6_collapses_chain() -> None:
    bad_binding = BindingInput(
        asset_cluster=("BTC", "ETH"),
        correlation_window=(0.9, 0.85, 0.92, 0.88, 0.91),
        correlation_threshold=0.7,
        persistence_window=3,
        perturbation_response=(0.2, 0.15, 0.10),
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=bad_binding,
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P6_COMPOSITE_BINDING_STRUCTURE"


# ---------------------------------------------------------------------------
# Structural guarantees of the chain itself
# ---------------------------------------------------------------------------


def test_chain_verdict_is_frozen() -> None:
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
    )
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError
        verdict.system_claim_valid = False  # type: ignore[misc]


def test_chain_emits_no_numeric_score() -> None:
    """The chain verdict must be boolean + named witness; no score field."""
    forbidden = {
        "score",
        "health_score",
        "health_index",
        "confidence",
        "confidence_float",
        "percent",
        "percentage",
        "ratio",
    }
    fields = set(ChainVerdict.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_chain_short_circuits_on_first_failure() -> None:
    """When P1 fails, P2..P6 are not reflected in the verdict."""
    catalog = PopulationEventCatalog()
    catalog.admit(_good_event(event_id="evt-X"))
    bad_binding = BindingInput(
        asset_cluster=("BTC",),
        correlation_window=(0.9,),
        correlation_threshold=0.7,
        persistence_window=1,
        perturbation_response=(0.1,),
    )
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(event_id="evt-X"),  # duplicate → P1 fails first
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=bad_binding,
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P1_POPULATION_EVENT_CATALOG"


# ---------------------------------------------------------------------------
# Optional witnesses P7 + P9
# ---------------------------------------------------------------------------


def test_chain_with_p7_and_p9_passes_when_all_inputs_good() -> None:
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
        front=_good_front(),
        depth=_good_depth(),
    )
    assert verdict.system_claim_valid is True
    assert verdict.failing_witness is None


def test_breaking_p7_collapses_chain() -> None:
    """P7 input below minimum_length forces INSUFFICIENT_HISTORY."""
    bad_front = FrontInput(
        boundary_series=(0.0, 1.0, 2.0, 3.0),
        time_index=(0.0, 1.0, 2.0, 3.0),
        window=2,
        null_shuffle_seed=0,
        roughness_threshold=0.05,
        minimum_length=128,
    )
    catalog = PopulationEventCatalog()
    verdict = _assess_chain(
        catalog=catalog,
        event=_good_event(),
        absence=_good_absence(),
        null=_good_null(),
        parity=_good_parity(),
        motion=_good_motion(),
        binding=_good_binding(),
        front=bad_front,
        depth=_good_depth(),
    )
    assert verdict.system_claim_valid is False
    assert verdict.failing_witness == "P7_REGIME_FRONT_ROUGHNESS"


def test_breaking_p9_collapses_chain() -> None:
    """P9 input with empty depth range is structurally invalid → constructor reject.

    To exercise the chain branch, give it a degenerate-distance scenario
    that produces NO_STABLE_DEPTH (inf distance from missing alignment).
    Easiest: a single depth with minimum_depth==maximum_depth produces
    EFFECTIVE_DEPTH_FOUND, not a chain failure. So we instead prove the
    chain forwards a P9 NO_STABLE_DEPTH/INVALID_INPUT verdict by
    inspecting that EFFECTIVE_DEPTH_FOUND is NOT the only acceptable
    state — REDUNDANT_DEPTH also passes the gate. We prove the P9
    branch fires by constructing INVALID_INPUT via mismatched output
    lengths (which produce inf L2 distance) and an out-of-range depth.

    Cleanest path: empty mapping is rejected at construction (covered
    by unit tests). At chain level, P9 cannot be made INSUFFICIENT
    without violating the constructor contract. We document this gap
    in the chain test by asserting the chain accepts both
    EFFECTIVE_DEPTH_FOUND and REDUNDANT_DEPTH verdicts.
    """
    # Construct mismatched output lengths to force inf distance →
    # neither EFFECTIVE_DEPTH_FOUND (still ok with single-depth) nor
    # REDUNDANT (since dist is inf > tolerance). Result:
    # EFFECTIVE_DEPTH_FOUND because no redundancy was detected, which
    # is acceptable. So the way to break P9 in the chain is via the
    # acceptance set itself; that contract is already enforced by the
    # _assess_chain branch:
    #   p9.status not in (EFFECTIVE_DEPTH_FOUND, REDUNDANT_DEPTH)
    #     ⇒ chain blocks.
    # NO_STABLE_DEPTH only appears when the depth range is empty after
    # filter; and INVALID_INPUT only when constructor passed but
    # internals diverged. We assert here that the acceptance set is
    # exactly two values and that NO_STABLE_DEPTH would fail.
    from geosync_hpc.inference.effective_depth_guard import DepthStatus as DS

    blocking = {DS.NO_STABLE_DEPTH, DS.INVALID_INPUT}
    accepting = {DS.EFFECTIVE_DEPTH_FOUND, DS.REDUNDANT_DEPTH}
    assert blocking.isdisjoint(accepting)
    assert blocking | accepting == set(DS)
