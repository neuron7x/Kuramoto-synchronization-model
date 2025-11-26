# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Build domain Signal via HNCM-style consensus."""

from __future__ import annotations

from typing import Mapping, Optional

from analytics.regime.src.consensus.hncm_adapter import (
    AgentVote,
    HNCMConsensusAdapter,
    ews_to_vote,
)
from domain.signals import Signal, SignalAction


def build_signal_with_consensus(
    *,
    symbol: str,
    ews_result: object,
    agent_scores: Mapping[str, float],
    adapter: Optional[HNCMConsensusAdapter] = None,
) -> Signal:
    """Зібрати доменний :class:`Signal` з EWS та інших агентів.

    agent_scores: словник {ім'я_агента: score∈[-1,1]}
    """
    adapter = adapter or HNCMConsensusAdapter()
    votes: list[AgentVote] = [ews_to_vote("ews", ews_result)]
    for agent, s in agent_scores.items():
        votes.append(AgentVote(agent=str(agent), score=float(s), confidence=1.0))
    decision = adapter.decide(tuple(votes))

    action_map = {
        "BUY": SignalAction.BUY,
        "SELL": SignalAction.SELL,
        "HOLD": SignalAction.HOLD,
    }
    rationale = f"HNCM consensus: score={decision.score:.4f}, action={decision.action}"
    metadata = {
        "weights": dict(decision.weights),
        "votes": [
            {
                "agent": v.agent,
                "score": v.score,
                "confidence": v.confidence,
                "rationale": v.rationale,
            }
            for v in decision.votes
        ],
    }

    return Signal(
        symbol=symbol,
        action=action_map[decision.action],
        confidence=decision.confidence,
        rationale=rationale,
        metadata=metadata,
    )
