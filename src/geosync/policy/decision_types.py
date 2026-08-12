# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Policy decision types for MLSdM governance.

This module defines the formal decision types and their priority ordering
for policy evaluation in the MLSdM system.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final

__all__ = [
    "DecisionType",
    "DECISION_PRIORITY",
    "resolve_decisions",
]


class DecisionType(IntEnum):
    """Policy decision types in priority order (lower = higher priority).

    The priority ordering determines which decision wins when multiple
    policy modules produce conflicting results:
    - BLOCK wins over all others
    - REDACT wins over REWRITE/ESCALATE/ALLOW
    - REWRITE wins over ESCALATE/ALLOW
    - ESCALATE wins over ALLOW
    - ALLOW has lowest priority
    """

    BLOCK = 1
    REDACT = 2
    REWRITE = 3
    ESCALATE = 4
    ALLOW = 5

    def __str__(self) -> str:
        return self.name


# Priority mapping for explicit ordering checks
DECISION_PRIORITY: Final[dict[DecisionType, int]] = {
    DecisionType.BLOCK: 1,
    DecisionType.REDACT: 2,
    DecisionType.REWRITE: 3,
    DecisionType.ESCALATE: 4,
    DecisionType.ALLOW: 5,
}


def resolve_decisions(
    decisions: list[DecisionType],
    strict_mode: bool = False,
) -> DecisionType:
    """Resolve multiple decisions according to priority rules.

    Args:
        decisions: List of decisions from different policy modules.
        strict_mode: If True, ESCALATE is treated as BLOCK.

    Returns:
        The highest priority (winning) decision.

    Raises:
        ValueError: If decisions list is empty.
    """
    if not decisions:
        raise ValueError("Cannot resolve empty decisions list")

    # Apply strict_mode transformation
    effective_decisions = []
    for d in decisions:
        if strict_mode and d == DecisionType.ESCALATE:
            effective_decisions.append(DecisionType.BLOCK)
        else:
            effective_decisions.append(d)

    # Lower IntEnum value = higher priority (BLOCK=1 wins over ALLOW=5).
    # min() returns the decision with the highest priority.
    return min(effective_decisions)


# Backward compatibility mapping to legacy GO/HOLD/NO_GO
LEGACY_DECISION_MAP: Final[dict[DecisionType, str]] = {
    DecisionType.ALLOW: "GO",
    DecisionType.BLOCK: "NO_GO",
    DecisionType.REDACT: "HOLD",
    DecisionType.REWRITE: "HOLD",
    DecisionType.ESCALATE: "HOLD",
}


def to_legacy_decision(decision: DecisionType) -> str:
    """Convert DecisionType to legacy GO/HOLD/NO_GO format.

    Args:
        decision: The policy decision.

    Returns:
        Legacy decision string: "GO", "HOLD", or "NO_GO".
    """
    return LEGACY_DECISION_MAP[decision]
