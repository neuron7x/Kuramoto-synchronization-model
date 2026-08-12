"""Hard invariants §6 of SYSTEM_ARTIFACT_v9.0.

Every invariant is a pure function ``(context) → (ok, reason)``. The
policy layer calls each invariant on the current system state; if
any returns ``ok=False`` the state machine must transition to
``DORMANT`` or ``ABORT`` depending on severity.

Protectors always override generators (INV_012).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.models import AssetSchemaReport, SubstrateHealth, ValidationVerdict


@dataclass(frozen=True, slots=True)
class InvariantResult:
    name: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "reason": self.reason}


FRESHNESS_LIMIT_MINUTES = 60.0
MIN_ASSETS_FOR_CROSS_TOPOLOGY = 10
MAX_P_VALUE = 0.10
MIN_IC = 0.08


def inv_001_ohlc_only_blocks_precursor(
    schemas: list[AssetSchemaReport],
) -> InvariantResult:
    """INV_001: if input_origin == OHLC_CLOSE_ONLY → precursor_claim = false."""
    any_precursor = any(s.precursor_capable for s in schemas)
    return InvariantResult(
        name="INV_001_ohlc_only_blocks_precursor",
        passed=any_precursor,
        reason=(
            "at least one precursor-capable asset present"
            if any_precursor
            else "all assets are OHLC-close-only — precursor claims forbidden"
        ),
    )


def inv_002_missing_all_microstructure(
    schemas: list[AssetSchemaReport],
) -> InvariantResult:
    """INV_002: missing_all([bid, ask, trades, bid_depth, ask_depth]) → DEGRADED."""
    if not schemas:
        return InvariantResult("INV_002_missing_all_microstructure", False, "no schemas")
    ok = any(
        s.has_bid or s.has_ask or s.has_trades or s.has_bid_depth or s.has_ask_depth
        for s in schemas
    )
    return InvariantResult(
        name="INV_002_missing_all_microstructure",
        passed=ok,
        reason=(
            "at least one asset carries microstructure field"
            if ok
            else "every asset missing bid/ask/trades/depth — DEGRADED"
        ),
    )


def inv_003_freshness(health: SubstrateHealth) -> InvariantResult:
    """INV_003: stale feed forbids validation."""
    ok = health.freshness_minutes <= FRESHNESS_LIMIT_MINUTES
    return InvariantResult(
        name="INV_003_freshness",
        passed=ok,
        reason=(
            f"freshness={health.freshness_minutes:.1f}min ≤ {FRESHNESS_LIMIT_MINUTES}"
            if ok
            else f"stale: {health.freshness_minutes:.1f}min > {FRESHNESS_LIMIT_MINUTES}"
        ),
    )


def inv_004_nan_policy(health: SubstrateHealth) -> InvariantResult:
    """INV_004: nan_rate > 0 → abort current pipeline."""
    ok = health.nan_rate == 0.0
    return InvariantResult(
        name="INV_004_nan_policy",
        passed=ok,
        reason=(
            "zero NaN in active payload"
            if ok
            else f"nan_rate={health.nan_rate:.6f} > 0 — strict policy violation"
        ),
    )


def inv_005_asset_coverage(health: SubstrateHealth) -> InvariantResult:
    """INV_005: asset_coverage below minimum → no cross-asset topology."""
    ok = health.asset_coverage >= MIN_ASSETS_FOR_CROSS_TOPOLOGY
    return InvariantResult(
        name="INV_005_asset_coverage",
        passed=ok,
        reason=(
            f"coverage={health.asset_coverage} ≥ {MIN_ASSETS_FOR_CROSS_TOPOLOGY}"
            if ok
            else f"coverage={health.asset_coverage} < {MIN_ASSETS_FOR_CROSS_TOPOLOGY}"
        ),
    )


def inv_006_orthogonality_measured(verdict: ValidationVerdict | None) -> InvariantResult:
    """INV_006: orthogonality not measured → no final verdict."""
    if verdict is None:
        return InvariantResult("INV_006_orthogonality_measured", False, "no verdict available")
    any_ortho = (
        verdict.corr_momentum is not None
        or verdict.corr_vol is not None
        or verdict.corr_vix is not None
        or verdict.corr_hyg is not None
    )
    return InvariantResult(
        name="INV_006_orthogonality_measured",
        passed=any_ortho,
        reason=(
            "orthogonality metrics present" if any_ortho else "no orthogonality metric measured"
        ),
    )


def inv_007_lead_capture_measured(verdict: ValidationVerdict | None) -> InvariantResult:
    """INV_007: lead_capture not measured → no precursor claim."""
    if verdict is None:
        return InvariantResult("INV_007_lead_capture_measured", False, "no verdict available")
    ok = verdict.lead_capture is not None
    return InvariantResult(
        name="INV_007_lead_capture_measured",
        passed=ok,
        reason=(
            "lead_capture measured"
            if ok
            else "lead_capture not measured — precursor claim forbidden"
        ),
    )


def inv_008_p_value_gate(verdict: ValidationVerdict | None) -> InvariantResult:
    """INV_008: p_value >= max_allowed_p → REJECT."""
    if verdict is None:
        return InvariantResult("INV_008_p_value_gate", False, "no verdict available")
    ok = verdict.p_value < MAX_P_VALUE
    return InvariantResult(
        name="INV_008_p_value_gate",
        passed=ok,
        reason=(
            f"p={verdict.p_value:.4f} < {MAX_P_VALUE}"
            if ok
            else f"p={verdict.p_value:.4f} ≥ {MAX_P_VALUE} — REJECT"
        ),
    )


def inv_009_ic_gate(verdict: ValidationVerdict | None) -> InvariantResult:
    """INV_009: IC < minimum_ic → REJECT."""
    if verdict is None:
        return InvariantResult("INV_009_ic_gate", False, "no verdict available")
    ok = verdict.IC >= MIN_IC
    return InvariantResult(
        name="INV_009_ic_gate",
        passed=ok,
        reason=(
            f"IC={verdict.IC:.4f} ≥ {MIN_IC}" if ok else f"IC={verdict.IC:.4f} < {MIN_IC} — REJECT"
        ),
    )


def inv_010_audit_artifact_present(required_artifacts: list[str]) -> InvariantResult:
    """INV_010: any audit artifact missing → pipeline = INVALID."""
    ok = len(required_artifacts) == 0
    return InvariantResult(
        name="INV_010_audit_artifact_present",
        passed=ok,
        reason=(
            "all required audit artifacts present"
            if ok
            else f"missing artifacts: {required_artifacts}"
        ),
    )


def inv_011_schema_drift(health: SubstrateHealth) -> InvariantResult:
    """INV_011: schema_drift_detected → quarantine affected assets."""
    ok = health.schema_complete
    return InvariantResult(
        name="INV_011_schema_drift",
        passed=ok,
        reason=("schema complete" if ok else "schema drift detected — quarantine required"),
    )


def inv_012_protectors_override_generators() -> InvariantResult:
    """INV_012: protectors always override generators.

    Always passes by construction — this is a design constraint, not a
    runtime check. It exists in the invariant registry so it can be
    referenced in every audit trail.
    """
    return InvariantResult(
        name="INV_012_protectors_override_generators",
        passed=True,
        reason="maintenance > processing by GeoSync physics doctrine",
    )


def check_all(
    health: SubstrateHealth | None,
    schemas: list[AssetSchemaReport],
    verdict: ValidationVerdict | None,
    missing_artifacts: list[str] | None = None,
) -> list[InvariantResult]:
    """Evaluate every invariant against the current system context."""
    missing = list(missing_artifacts or [])
    results: list[InvariantResult] = [
        inv_001_ohlc_only_blocks_precursor(schemas),
        inv_002_missing_all_microstructure(schemas),
    ]
    if health is not None:
        results.append(inv_003_freshness(health))
        results.append(inv_004_nan_policy(health))
        results.append(inv_005_asset_coverage(health))
        results.append(inv_011_schema_drift(health))
    results.append(inv_006_orthogonality_measured(verdict))
    results.append(inv_007_lead_capture_measured(verdict))
    results.append(inv_008_p_value_gate(verdict))
    results.append(inv_009_ic_gate(verdict))
    results.append(inv_010_audit_artifact_present(missing))
    results.append(inv_012_protectors_override_generators())
    return results


__all__ = [
    "InvariantResult",
    "FRESHNESS_LIMIT_MINUTES",
    "MIN_ASSETS_FOR_CROSS_TOPOLOGY",
    "MAX_P_VALUE",
    "MIN_IC",
    "inv_001_ohlc_only_blocks_precursor",
    "inv_002_missing_all_microstructure",
    "inv_003_freshness",
    "inv_004_nan_policy",
    "inv_005_asset_coverage",
    "inv_006_orthogonality_measured",
    "inv_007_lead_capture_measured",
    "inv_008_p_value_gate",
    "inv_009_ic_gate",
    "inv_010_audit_artifact_present",
    "inv_011_schema_drift",
    "inv_012_protectors_override_generators",
    "check_all",
]
