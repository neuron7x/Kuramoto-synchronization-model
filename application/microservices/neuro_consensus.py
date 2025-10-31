# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Neuro-consensus microservice builder for TradePulse."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Mapping, Optional

from domain.signals import ModelMetadata, Signal, SignalAction

# Local import path in repository context:
from analytics.regime.src.consensus.hncm_neuro import (
    NeuroConsensusAdapter,
    AgentVote,
)

def ews_to_vote(agent_name: str, ews_result: object) -> AgentVote:
    score = 0.0
    if hasattr(ews_result, "probability") and ews_result.probability is not None:
        score = max(-1.0, min(1.0, 2.0 * float(ews_result.probability) - 1.0))
    elif hasattr(ews_result, "ews_score"):
        score = max(-1.0, min(1.0, float(ews_result.ews_score)))
    return AgentVote(agent=agent_name, score=score, confidence=1.0, rationale="EWS meta-signal")


def build_signal_with_neuro_consensus(
    *,
    symbol: str,
    ews_result: object,
    agent_scores: Mapping[str, float],
    adapter: Optional[NeuroConsensusAdapter] = None,
    model_metadata: ModelMetadata | None = None,
) -> Signal:
    adapter = adapter or NeuroConsensusAdapter()
    votes = [ews_to_vote("ews", ews_result)]
    for agent, s in agent_scores.items():
        votes.append(AgentVote(agent=agent, score=float(s), confidence=1.0))
    decision = adapter.decide(votes)

    action_map = {"BUY": SignalAction.BUY, "SELL": SignalAction.SELL, "HOLD": SignalAction.HOLD}
    rationale = f"Neuro consensus: score={decision.score:.4f}, action={decision.action}"
    metadata = {
        "weights": dict(decision.weights),
        "votes": [{"agent": v.agent, "score": v.score, "confidence": v.confidence} for v in decision.votes],
        "neuro": {"tau": adapter.tau},
    }
    resolved_metadata = model_metadata or NEURO_CONSENSUS_MODEL_METADATA
    return Signal(
        symbol=symbol,
        action=action_map[decision.action],
        confidence=decision.confidence,
        model_metadata=resolved_metadata,
        rationale=rationale,
        metadata=metadata,
    )
NEURO_CONSENSUS_MODEL_METADATA = ModelMetadata(
    model_id="tradepulse.neuro.consensus",
    model_version="2025.1",
    model_hash=hashlib.sha256(b"tradepulse.neuro.consensus:2025.1").hexdigest(),
    training_timestamp=datetime(2025, 2, 1, tzinfo=timezone.utc),
)

