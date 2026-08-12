"""Deterministic state machine per §5 of SYSTEM_ARTIFACT_v9.0.

The transitions are hard-wired — the cognitive layer can only pick
the current state's admissible successor, never jump to an unrelated
state. Any invariant violation short-circuits to ``ABORT``.
"""

from __future__ import annotations

from agent.models import AgentState

# Declarative transition table. Each entry maps (current_state) → allowed
# set of next states. Keeping this as a module-level constant lets the
# policy layer assert that its chosen ``next_state`` is legal.
TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.BOOT: frozenset({AgentState.DISCOVER_SOURCES, AgentState.ABORT}),
    AgentState.DISCOVER_SOURCES: frozenset(
        {
            AgentState.CHECK_CONNECTIVITY,
            AgentState.DEGRADED,
            AgentState.ABORT,
        }
    ),
    AgentState.CHECK_CONNECTIVITY: frozenset(
        {
            AgentState.CHECK_LIVENESS,
            AgentState.DEGRADED,
            AgentState.ABORT,
        }
    ),
    AgentState.CHECK_LIVENESS: frozenset(
        {
            AgentState.AUDIT_SCHEMA,
            AgentState.BACKFILL,
            AgentState.DEGRADED,
            AgentState.ABORT,
        }
    ),
    AgentState.AUDIT_SCHEMA: frozenset(
        {
            AgentState.CANONICALIZE,
            AgentState.DEGRADED,
            AgentState.ABORT,
        }
    ),
    AgentState.BACKFILL: frozenset(
        {AgentState.CHECK_LIVENESS, AgentState.DEGRADED, AgentState.ABORT}
    ),
    AgentState.CANONICALIZE: frozenset({AgentState.ENRICH, AgentState.ABORT}),
    AgentState.ENRICH: frozenset(
        {AgentState.BUILD_FEATURES, AgentState.DEGRADED, AgentState.ABORT}
    ),
    AgentState.BUILD_FEATURES: frozenset({AgentState.VALIDATE, AgentState.ABORT}),
    AgentState.VALIDATE: frozenset({AgentState.REVIEW, AgentState.ABORT}),
    AgentState.REVIEW: frozenset({AgentState.REPORT, AgentState.ABORT}),
    AgentState.REPORT: frozenset({AgentState.CHECK_LIVENESS, AgentState.ABORT}),
    AgentState.DEGRADED: frozenset(
        {AgentState.DISCOVER_SOURCES, AgentState.DORMANT, AgentState.ABORT}
    ),
    AgentState.DORMANT: frozenset({AgentState.DISCOVER_SOURCES, AgentState.ABORT}),
    AgentState.ABORT: frozenset({AgentState.DORMANT}),
}


def is_legal_transition(current: AgentState, nxt: AgentState) -> bool:
    return nxt in TRANSITIONS.get(current, frozenset())


def legal_successors(current: AgentState) -> frozenset[AgentState]:
    return TRANSITIONS.get(current, frozenset())


__all__ = ["TRANSITIONS", "is_legal_transition", "legal_successors"]
