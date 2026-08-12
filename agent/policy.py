"""Action policy §10 of SYSTEM_ARTIFACT_v9.0.

Given the current system context, deterministically choose the
single next ``ActionIntent``. Rules are evaluated in priority order
(RULE_01 first — highest priority). First match wins; if none match,
the agent goes DORMANT.

Honesty contract: the policy never upgrades the state when an
invariant fails. ``inv.check_all(...)`` is consulted BEFORE any rule
fires; any ``passed=False`` invariant whose failure is
action-relevant forces ``DORMANT``.
"""

from __future__ import annotations

from typing import Any

from agent import invariants
from agent.models import (
    ActionIntent,
    ActionKind,
    AgentState,
    AssetSchemaReport,
    Priority,
    SourceDescriptor,
    SubstrateHealth,
    SubstrateStatus,
    ValidationStatus,
    ValidationVerdict,
)


def _any_configured_source(sources: list[SourceDescriptor]) -> bool:
    return any(s.auth_ok for s in sources)


def _any_reachable_source(sources: list[SourceDescriptor]) -> bool:
    return any(s.reachable for s in sources)


def _precursor_critical_fields_missing(schemas: list[AssetSchemaReport]) -> bool:
    """True when no asset carries any precursor-critical field."""
    if not schemas:
        return True
    return not any(s.precursor_capable for s in schemas)


def _derivable_fields_missing(schemas: list[AssetSchemaReport]) -> bool:
    """True when raw bid/ask exist but spread/mid/OFI are not derived yet."""
    return any(
        s.can_derive_spread and not s.has_spread or s.can_derive_ofi and not s.has_ofi
        for s in schemas
    )


#: Invariants whose failure must hard-stop the agent BEFORE any rule
#: fires, regardless of verdict state. These are the truly fail-closed
#: invariants from §6 — "abort current pipeline" / "INVALID" classes.
#: Other invariants (INV_001/002/003/005/011) are already covered by
#: rule-level transitions; INV_006..009 only apply once a verdict
#: exists and are evaluated in the verdict-handling branch.
HARD_STOP_INVARIANTS: frozenset[str] = frozenset(
    {
        "INV_004_nan_policy",
        "INV_010_audit_artifact_present",
    }
)


def select_action(
    *,
    sources: list[SourceDescriptor],
    health: SubstrateHealth | None,
    schemas: list[AssetSchemaReport],
    verdict: ValidationVerdict | None = None,
    missing_artifacts: list[str] | None = None,
) -> ActionIntent:
    """Deterministic single-step policy — returns exactly one ActionIntent."""
    inv_results = invariants.check_all(
        health=health,
        schemas=schemas,
        verdict=verdict,
        missing_artifacts=missing_artifacts,
    )
    failing = [r for r in inv_results if not r.passed]
    inv_summary: dict[str, Any] = {
        r.name: {"passed": r.passed, "reason": r.reason} for r in inv_results
    }

    # ---- Hard-stop pre-check: any HARD_STOP_INVARIANTS failure forces ----
    # ---- DORMANT BEFORE any rule fires, regardless of verdict state.   ----
    # The honesty contract: invariants in this set are non-negotiable
    # and cannot be bypassed by emitting BUILD_FEATURES / VALIDATE on
    # invalid substrate. The CodeRabbit P1 fix.
    hard_failures = [r for r in failing if r.name in HARD_STOP_INVARIANTS]
    if hard_failures:
        return ActionIntent(
            state=AgentState.DORMANT,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.DORMANT,
            priority=Priority.P0,
            target="system",
            why=tuple(f"hard invariant violated: {r.name}" for r in hard_failures),
            blocking_conditions=tuple(r.reason for r in hard_failures),
            next_required_artifact="agent/reports/invariant_violation.json",
            admissible=False,
            diagnostics={
                "invariants": inv_summary,
                "hard_stop_set": sorted(HARD_STOP_INVARIANTS),
                "fired": [r.name for r in hard_failures],
            },
        )

    # -------- RULE_01: no source configured → DISCOVER_SOURCES -------- #
    if not sources or not _any_configured_source(sources):
        return ActionIntent(
            state=AgentState.DISCOVER_SOURCES,
            substrate_status=SubstrateStatus.DEAD,
            action=ActionKind.DISCOVER_SOURCES,
            priority=Priority.P0,
            target="provider_registry",
            why=(
                "no microstructure provider configured",
                "see agent/providers.py for candidates",
            ),
            blocking_conditions=(
                "populate at least one of: DUKASCOPY_DOWNLOAD_DIR, "
                "OANDA_API_TOKEN, DATABENTO_API_KEY, POLYGON_API_KEY, "
                "IBKR_GATEWAY_HOST, BINANCE_WS_ENDPOINT, ASKAR_L2_ENDPOINT",
            ),
            next_required_artifact="agent/reports/provider_manifest.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "n_sources": len(sources)},
        )

    # -------- RULE_02: source configured but auth broken → CHECK_CONN -- #
    if not _any_reachable_source(sources):
        return ActionIntent(
            state=AgentState.CHECK_CONNECTIVITY,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.CHECK_CONNECTIVITY,
            priority=Priority.P0,
            target="configured_sources",
            why=("sources configured but none reachable",),
            blocking_conditions=("verify credentials and network paths",),
            next_required_artifact="agent/reports/connectivity_probe.json",
            admissible=True,
            diagnostics={"invariants": inv_summary},
        )

    # -------- From here on, a health snapshot is required -------- #
    if health is None:
        return ActionIntent(
            state=AgentState.CHECK_LIVENESS,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.REPORT,
            priority=Priority.P0,
            target="feed_sentinel",
            why=("no SubstrateHealth snapshot produced yet",),
            blocking_conditions=("call feed_sentinel.compute_health first",),
            next_required_artifact="agent/reports/substrate_health.json",
            admissible=True,
            diagnostics={"invariants": inv_summary},
        )

    # -------- RULE_03/04: feed_live False or stale → BACKFILL -------- #
    if not health.feed_live:
        return ActionIntent(
            state=AgentState.BACKFILL,
            substrate_status=SubstrateStatus.DEAD,
            action=ActionKind.BACKFILL,
            priority=Priority.P0,
            target="dead_feeds",
            why=("feed not live — DEAD state",),
            blocking_conditions=("provider must respond with live payload",),
            next_required_artifact="agent/reports/backfill_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )
    if health.freshness_minutes > invariants.FRESHNESS_LIMIT_MINUTES:
        return ActionIntent(
            state=AgentState.BACKFILL,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.BACKFILL,
            priority=Priority.P0,
            target="stale_assets",
            why=(
                f"freshness {health.freshness_minutes:.1f}min > "
                f"{invariants.FRESHNESS_LIMIT_MINUTES}min",
            ),
            blocking_conditions=("acquire recent bars from provider",),
            next_required_artifact="agent/reports/backfill_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )

    # -------- RULE_11: schema drift → QUARANTINE -------- #
    if not health.schema_complete:
        return ActionIntent(
            state=AgentState.DEGRADED,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.QUARANTINE,
            priority=Priority.P0,
            target="panel",
            why=("schema incomplete — at least one asset lacks precursor fields",),
            blocking_conditions=("fix schema at source OR drop non-conforming assets",),
            next_required_artifact="agent/reports/quarantine_manifest.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )

    # -------- RULE_05: precursor-critical fields missing → DISCOVER --- #
    if _precursor_critical_fields_missing(schemas):
        return ActionIntent(
            state=AgentState.DISCOVER_SOURCES,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.DISCOVER_SOURCES,
            priority=Priority.P0,
            target="precursor_feeds",
            why=(
                "bid/ask/depth/trades absent from every asset in the panel",
                "substrate is OHLC_CLOSE_ONLY → INV_001 blocks precursor claims",
            ),
            blocking_conditions=(
                "route stakeholder escalation: request raw tick/L2 feed",
                "agent cannot synthesise microstructure from close bars",
            ),
            next_required_artifact="agent/reports/schema_gap_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )

    # -------- RULE_06: raw fields present, derived fields absent → ENRICH ----- #
    if _derivable_fields_missing(schemas):
        return ActionIntent(
            state=AgentState.ENRICH,
            substrate_status=SubstrateStatus.LIVE,
            action=ActionKind.ENRICH,
            priority=Priority.P1,
            target="canonical_panel",
            why=("raw precursor fields present, derived fields missing",),
            blocking_conditions=(),
            next_required_artifact="agent/reports/enrichment_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )

    # -------- RULE_08/09: live substrate + no verdict → BUILD+VALIDATE - #
    if verdict is None:
        return ActionIntent(
            state=AgentState.BUILD_FEATURES,
            substrate_status=SubstrateStatus.LIVE,
            action=ActionKind.BUILD_FEATURES,
            priority=Priority.P2,
            target="microstructure_panel",
            why=("substrate live and precursor-capable — no validation run yet",),
            blocking_conditions=(),
            next_required_artifact="agent/reports/validation_verdict.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "health": health.to_dict()},
        )

    # -------- RULE_10..13: process verdict -------- #
    if verdict.status == ValidationStatus.INSUFFICIENT_SUBSTRATE:
        return ActionIntent(
            state=AgentState.REPORT,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.REPORT,
            priority=Priority.P3,
            target="stakeholder",
            why=(verdict.reason or "insufficient substrate for validation",),
            blocking_conditions=("await richer substrate upgrade",),
            next_required_artifact="agent/reports/honest_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "verdict": verdict.to_dict()},
        )

    if verdict.status == ValidationStatus.REJECT:
        return ActionIntent(
            state=AgentState.REPORT,
            substrate_status=SubstrateStatus.LIVE,
            action=ActionKind.REPORT,
            priority=Priority.P3,
            target="stakeholder",
            why=("validation failed — gate-level REJECT",),
            blocking_conditions=(verdict.reason,),
            next_required_artifact="agent/reports/rejection_report.json",
            admissible=True,
            diagnostics={"invariants": inv_summary, "verdict": verdict.to_dict()},
        )

    # verdict.status == PASS — honesty gates above must ALL pass too
    blocking = [r.reason for r in failing] if failing else []
    if blocking:
        return ActionIntent(
            state=AgentState.DORMANT,
            substrate_status=SubstrateStatus.DEGRADED,
            action=ActionKind.DORMANT,
            priority=Priority.P0,
            target="system",
            why=("validation PASS but invariant failures present",),
            blocking_conditions=tuple(blocking),
            next_required_artifact="agent/reports/invariant_violation.json",
            admissible=False,
            diagnostics={"invariants": inv_summary, "verdict": verdict.to_dict()},
        )

    return ActionIntent(
        state=AgentState.REPORT,
        substrate_status=SubstrateStatus.LIVE,
        action=ActionKind.REPORT,
        priority=Priority.P3,
        target="stakeholder",
        why=("validation PASS, invariants satisfied — REVIEW_READY",),
        blocking_conditions=(),
        next_required_artifact="agent/reports/review_ready.json",
        admissible=True,
        diagnostics={
            "invariants": inv_summary,
            "verdict": verdict.to_dict(),
            "status_note": "REVIEW_READY",
        },
    )


__all__ = ["select_action"]
