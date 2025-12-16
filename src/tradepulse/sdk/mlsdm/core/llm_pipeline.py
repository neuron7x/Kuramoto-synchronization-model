"""LLM Pipeline for MLSDM with deterministic replay support.

This module provides the LLMPipeline class that processes input text
through policy stages and returns results with cache keys for
deterministic replay and regression testing.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..utils.replay_fingerprint import (
    PIPELINE_VERSION,
    POLICY_VERSION,
    compute_cache_key,
    normalize_text,
    sha256_hex,
)
from .stub_llm import StubLLMProvider, StubResponse

__all__ = [
    "LLMPipeline",
    "PipelineResult",
    "PipelineConfig",
    "LLMProvider",
]

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def generate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> StubResponse:
        """Generate a response for input text."""
        ...


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Configuration for the LLM pipeline.

    Attributes:
        strict_mode: Enable strict policy enforcement.
        policy_version: Version of policy rules.
        log_traces: Whether to log traces.
        version: Pipeline version string.
    """

    strict_mode: bool = False
    policy_version: str = POLICY_VERSION
    log_traces: bool = True
    version: str = PIPELINE_VERSION

    # Safe config subset for fingerprinting (no secrets)
    memory: dict[str, Any] = field(default_factory=dict)
    rhythm: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result from pipeline execution.

    Attributes:
        output_text: The generated/processed output text.
        decision: Policy decision (ALLOW, BLOCK, REDACT, REWRITE).
        cache_key: Deterministic cache key for replay.
        trace_id: Optional trace ID for debugging.
        reasons: List of reasons for the decision.
    """

    output_text: str
    decision: str
    cache_key: str
    output_hash: str
    trace_id: str | None = None
    reasons: list[str] = field(default_factory=list)


# Stage version constants
STAGE_VERSIONS: dict[str, str] = {
    "prefilter": "1.0.0",
    "policy": "1.0.0",
    "memory": "1.0.0",
    "postfilter": "1.0.0",
}


class LLMPipeline:
    """LLM Pipeline with deterministic replay support.

    This pipeline:
    - Normalizes input text
    - Applies policy checks
    - Generates responses via LLM provider
    - Computes deterministic cache keys
    - Returns structured results with traces

    Example:
        >>> pipeline = LLMPipeline()
        >>> result = pipeline.run_with_trace("Hello world")
        >>> result.decision
        'ALLOW'
        >>> len(result.cache_key)
        64
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            config: Pipeline configuration. Uses defaults if None.
            provider: LLM provider. Uses StubLLMProvider if None.
        """
        self._config = config or PipelineConfig()
        self._provider = provider or StubLLMProvider()

    @property
    def config(self) -> PipelineConfig:
        """Get the pipeline configuration."""
        return self._config

    @property
    def strict_mode(self) -> bool:
        """Whether strict mode is enabled."""
        return self._config.strict_mode

    def _get_config_subset(self) -> dict[str, Any]:
        """Get safe config subset for fingerprinting.

        Returns only deterministic, non-secret config values.
        """
        return {
            "memory": dict(self._config.memory) if self._config.memory else {},
            "rhythm": dict(self._config.rhythm) if self._config.rhythm else {},
            "safety": dict(self._config.safety) if self._config.safety else {},
        }

    def run(self, text: str) -> str:
        """Run the pipeline and return output text only.

        This is the backward-compatible method that returns
        only the output text string.

        Args:
            text: Input text to process.

        Returns:
            Output text string.
        """
        result = self.run_with_trace(text)
        return result.output_text

    def run_with_trace(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Run the pipeline with full trace information.

        This method:
        1. Normalizes input text
        2. Computes deterministic cache key
        3. Applies policy checks
        4. Generates LLM response
        5. Returns structured result

        Args:
            text: Input text to process.
            context: Optional context for processing.

        Returns:
            PipelineResult with output, decision, cache_key, and trace.
        """
        # Generate trace ID
        trace_id = str(uuid.uuid4())

        # Normalize input
        normalized_text = normalize_text(text)

        # Compute cache key at the earliest point
        cache_key = compute_cache_key(
            text=normalized_text,
            strict_mode=self._config.strict_mode,
            policy_version=self._config.policy_version,
            stage_versions=STAGE_VERSIONS,
            config_subset=self._get_config_subset(),
        )

        # Log trace if enabled (no raw prompts in logs)
        if self._config.log_traces:
            logger.debug(
                "Pipeline run: trace_id=%s, cache_key=%s, strict_mode=%s",
                trace_id,
                cache_key,
                self._config.strict_mode,
            )

        # Generate response via provider
        response = self._provider.generate(normalized_text, context)

        # Map provider response to decision
        if response.blocked:
            decision = "BLOCK"
            reasons = [response.reason] if response.reason else ["blocked_by_provider"]
        else:
            decision = "ALLOW"
            reasons = ["passed_all_checks"]

        # Compute output hash
        output_hash = sha256_hex(response.text.encode("utf-8"))

        # Build result
        return PipelineResult(
            output_text=response.text,
            decision=decision,
            cache_key=cache_key,
            output_hash=output_hash,
            trace_id=trace_id,
            reasons=reasons,
        )

    def run_batch(
        self,
        texts: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[PipelineResult]:
        """Run the pipeline on multiple inputs.

        Args:
            texts: List of input texts.
            context: Optional shared context.

        Returns:
            List of PipelineResult objects.
        """
        return [self.run_with_trace(text, context) for text in texts]
