# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pipeline result data structures for MLSDM.

This module provides the PipelineResult dataclass for capturing
pipeline execution outcomes with decision traces and cache keys.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "Decision",
    "PipelineResult",
    "create_trace_id",
]


class Decision(str, Enum):
    """Pipeline decision types.

    Attributes:
        ALLOW: Request is allowed to proceed.
        BLOCK: Request is blocked.
        REDACT: Sensitive content is redacted from output.
        REWRITE: Output is rewritten/modified.
    """

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDACT = "REDACT"
    REWRITE = "REWRITE"


def create_trace_id(*, seed: int | None = None) -> str:
    """Create a trace ID for pipeline execution.

    Args:
        seed: Optional seed for deterministic ID generation (for replay).
              If None, generates a random UUID.

    Returns:
        Trace ID string.
    """
    if seed is not None:
        # Deterministic trace ID for replay
        import hashlib

        seed_bytes = str(seed).encode("utf-8")
        hash_hex = hashlib.sha256(seed_bytes).hexdigest()[:32]
        return f"trace-{hash_hex}"
    else:
        # Random trace ID for production
        return f"trace-{uuid.uuid4().hex}"


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of a pipeline execution.

    This dataclass captures the complete outcome of processing a request
    through the MLSDM pipeline, including the decision, output, and
    traceability information.

    Attributes:
        output_text: The processed output text (may be redacted/rewritten).
        decision: The pipeline decision (ALLOW, BLOCK, REDACT, REWRITE).
        reasons: List of reasons explaining the decision.
        cache_key: The canonical cache key for this request.
        trace_id: Unique identifier for this pipeline execution.
        rule_hits: List of policy rules that were triggered.
        metadata: Additional metadata about the execution.
    """

    output_text: str
    decision: Decision
    reasons: tuple[str, ...] = field(default_factory=tuple)
    cache_key: str = ""
    trace_id: str = ""
    rule_hits: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all fields serialized.
        """
        return {
            "output_text": self.output_text,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "cache_key": self.cache_key,
            "trace_id": self.trace_id,
            "rule_hits": list(self.rule_hits),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineResult:
        """Create PipelineResult from dictionary.

        Args:
            data: Dictionary with result data.

        Returns:
            PipelineResult instance.
        """
        return cls(
            output_text=data.get("output_text", ""),
            decision=Decision(data.get("decision", "ALLOW")),
            reasons=tuple(data.get("reasons", [])),
            cache_key=data.get("cache_key", ""),
            trace_id=data.get("trace_id", ""),
            rule_hits=tuple(data.get("rule_hits", [])),
            metadata=dict(data.get("metadata", {})),
        )

    def output_hash(self) -> str:
        """Compute hash of the output for regression testing.

        Returns:
            SHA-256 hash of the output text.
        """
        import hashlib

        return hashlib.sha256(self.output_text.encode("utf-8")).hexdigest()
