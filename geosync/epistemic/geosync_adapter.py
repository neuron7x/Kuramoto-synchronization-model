"""Boundary adapter from legacy GeoSync maturity states to ECP-AS states."""
from __future__ import annotations
from .models import ClaimState

LEGACY_TO_ECP = {
    "UNOBSERVED": ClaimState.UNOBSERVED,
    "OBSERVABLE": ClaimState.TESTABLE,
    "MEASURED_SYNTHETIC": ClaimState.OBSERVED,
    "ALTERNATIVES_ENUMERATED": ClaimState.TESTABLE,
    "DISCRIMINATING_TEST_DEFINED": ClaimState.TESTABLE,
    "FALSIFIER_EXECUTED": ClaimState.INSTRUMENTED,
    "CALIBRATED": ClaimState.INSTRUMENTED,
    "INTEGRATED": ClaimState.INSTRUMENTED,
    "REPLAYABLE": ClaimState.OBSERVED,
    "REAL_DATA_SINGLE_SESSION": ClaimState.OBSERVED,
    "REAL_DATA_MULTI_SESSION": ClaimState.REPLICATED,
    "ALTERNATIVES_ELIMINATED": ClaimState.BOUNDED,
    "NEGATIVE_EVIDENCE_PRESERVED": ClaimState.BOUNDED,
    "BOUNDED_CLAIM_ALLOWED": ClaimState.BOUNDED,
}

def map_legacy_state(state: str) -> ClaimState:
    try: return LEGACY_TO_ECP[state]
    except KeyError as exc: raise ValueError(f"unmapped legacy claim state: {state}") from exc
