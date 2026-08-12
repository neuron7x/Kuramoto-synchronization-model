# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified policy engine for MLSdM governance.

This module provides the PolicyEngine class that coordinates
multiple policy modules and produces unified decisions with traces.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .decision_trace import DecisionTrace, Redaction, TraceScrubber, create_trace
from .decision_types import DecisionType, resolve_decisions

__all__ = [
    "PolicyEngine",
    "PolicyModule",
    "PolicyResult",
    "PolicyEngineConfig",
]

logger = logging.getLogger(__name__)


class PolicyModule(Protocol):
    """Protocol for policy modules that can evaluate content."""

    @property
    def name(self) -> str:
        """Module name for tracing."""
        ...

    @property
    def version(self) -> str:
        """Module version for tracing."""
        ...

    def evaluate(
        self,
        content: str,
        context: dict[str, object] | None = None,
    ) -> "PolicyResult":
        """Evaluate content and return a policy result.

        Args:
            content: The content to evaluate.
            context: Optional context for evaluation.

        Returns:
            PolicyResult with decision and metadata.
        """
        ...


@dataclass(slots=True)
class PolicyResult:
    """Result from a policy module evaluation.

    Attributes:
        decision: The policy decision.
        reasons: List of reason tags for the decision.
        confidence: Optional confidence score 0.0-1.0.
        signals: Dict of numeric signals used in decision.
        rule_hits: List of rules that matched.
        redactions: List of applied redactions (for REDACT).
        rewritten_text: Modified text (for REWRITE).
    """

    decision: DecisionType
    reasons: list[str] = field(default_factory=list)
    confidence: float | None = None
    signals: dict[str, float] = field(default_factory=dict)
    rule_hits: list[str] = field(default_factory=list)
    redactions: list[Redaction] = field(default_factory=list)
    rewritten_text: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyEngineConfig:
    """Configuration for the PolicyEngine.

    Attributes:
        strict_mode: If True, ESCALATE becomes BLOCK and exceptions cause BLOCK.
        require_reasons_for_allow: If True, ALLOW without reasons becomes BLOCK.
        log_traces: If True, log all decision traces.
        version: Engine version for tracing.
    """

    strict_mode: bool = False
    require_reasons_for_allow: bool = True
    log_traces: bool = True
    version: str = "1.0.0"


class PolicyEngine:
    """Unified policy engine coordinating multiple policy modules.

    This engine:
    - Runs all registered policy modules
    - Resolves conflicting decisions using priority rules
    - Produces comprehensive decision traces
    - Applies strict_mode fail-closed behavior
    - Scrubs sensitive data from traces
    """

    def __init__(
        self,
        config: PolicyEngineConfig | None = None,
        modules: list[PolicyModule] | None = None,
    ) -> None:
        """Initialize the policy engine.

        Args:
            config: Engine configuration. Uses defaults if None.
            modules: List of policy modules to register.
        """
        self._config = config or PolicyEngineConfig()
        self._modules: list[PolicyModule] = list(modules) if modules else []
        self._scrubber = TraceScrubber()

    @property
    def strict_mode(self) -> bool:
        """Whether strict mode is enabled."""
        return self._config.strict_mode

    def register_module(self, module: PolicyModule) -> None:
        """Register a policy module.

        Args:
            module: The policy module to register.
        """
        self._modules.append(module)

    def evaluate(
        self,
        content: str,
        context: dict[str, object] | None = None,
        stage: str = "policy",
    ) -> tuple[PolicyResult, DecisionTrace]:
        """Evaluate content against all registered policy modules.

        Args:
            content: The content to evaluate.
            context: Optional context for evaluation.
            stage: Pipeline stage for tracing.

        Returns:
            Tuple of (final PolicyResult, DecisionTrace).

        Raises:
            RuntimeError: In strict_mode if any module raises an exception.
        """
        if not self._modules:
            # No modules registered: default to ALLOW with reason
            result = PolicyResult(
                decision=DecisionType.ALLOW,
                reasons=["no_policy_modules_registered"],
            )
            trace = create_trace(
                stage=stage,
                input_text=content,
                module_name="policy_engine",
                module_version=self._config.version,
                final_decision=result.decision,
                reasons=result.reasons,
                strict_mode=self._config.strict_mode,
            )
            return result, trace

        module_results: list[tuple[PolicyModule, PolicyResult]] = []
        all_decisions: list[DecisionType] = []
        all_reasons: list[str] = []
        all_rule_hits: list[str] = []
        all_signals: dict[str, float] = {}
        all_redactions: list[Redaction] = []
        final_rewritten: str | None = None

        for module in self._modules:
            try:
                module_result = module.evaluate(content, context)
                module_results.append((module, module_result))
                all_decisions.append(module_result.decision)
                all_reasons.extend(module_result.reasons)
                all_rule_hits.extend(module_result.rule_hits)
                all_signals.update(
                    {f"{module.name}.{k}": v for k, v in module_result.signals.items()}
                )
                all_redactions.extend(module_result.redactions)
                if module_result.rewritten_text is not None:
                    final_rewritten = module_result.rewritten_text
            except Exception as exc:
                logger.exception(
                    "Policy module %s raised exception: %s",
                    module.name,
                    exc,
                )
                if self._config.strict_mode:
                    # Fail closed: treat exception as BLOCK
                    all_decisions.append(DecisionType.BLOCK)
                    all_reasons.append(f"module_exception:{module.name}")
                else:
                    # Log but continue with other modules
                    all_reasons.append(f"module_error:{module.name}")

        # Resolve final decision
        if not all_decisions:
            # All modules failed, apply strict_mode logic
            if self._config.strict_mode:
                final_decision = DecisionType.BLOCK
                all_reasons.append("all_modules_failed_strict_mode")
            else:
                final_decision = DecisionType.ALLOW
                all_reasons.append("all_modules_failed_permissive")
        else:
            final_decision = resolve_decisions(
                all_decisions,
                strict_mode=self._config.strict_mode,
            )

        # Check for ALLOW without reasons
        if (
            final_decision == DecisionType.ALLOW
            and self._config.require_reasons_for_allow
            and not all_reasons
        ):
            if self._config.strict_mode:
                final_decision = DecisionType.BLOCK
                all_reasons.append("allow_without_reasons_blocked")
            else:
                all_reasons.append("allow_without_explicit_reasons")

        # Compute average confidence
        confidences = [r.confidence for _, r in module_results if r.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        # Build final result
        final_result = PolicyResult(
            decision=final_decision,
            reasons=list(set(all_reasons)),  # Deduplicate
            confidence=avg_confidence,
            signals=all_signals,
            rule_hits=list(set(all_rule_hits)),
            redactions=all_redactions,
            rewritten_text=final_rewritten,
        )

        # Create trace
        trace = create_trace(
            stage=stage,
            input_text=content,
            module_name="policy_engine",
            module_version=self._config.version,
            final_decision=final_decision,
            reasons=final_result.reasons,
            strict_mode=self._config.strict_mode,
            signals=final_result.signals,
            rule_hits=final_result.rule_hits,
            confidence=final_result.confidence,
            redactions=final_result.redactions,
            rewritten_text=final_result.rewritten_text,
            applied_rules=[m.name for m, _ in module_results],
        )

        if self._config.log_traces:
            logger.info(
                "Policy decision: %s (trace_id=%s)",
                final_decision,
                trace.trace_id,
            )

        return final_result, trace


class SimplePolicyModule:
    """Simple policy module for testing and basic use cases.

    This module evaluates content against a list of patterns
    and returns decisions based on matches.
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        patterns: dict[str, DecisionType] | None = None,
        evaluator: Callable[[str, dict[str, object] | None], PolicyResult] | None = None,
    ) -> None:
        """Initialize the simple policy module.

        Args:
            name: Module name.
            version: Module version.
            patterns: Dict mapping patterns to decisions.
            evaluator: Optional custom evaluator function.
        """
        self._name = name
        self._version = version
        self._patterns = patterns or {}
        self._evaluator = evaluator

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def evaluate(
        self,
        content: str,
        context: dict[str, object] | None = None,
    ) -> PolicyResult:
        """Evaluate content against patterns or custom evaluator."""
        if self._evaluator is not None:
            return self._evaluator(content, context)

        content_lower = content.lower()
        matched_decisions: list[DecisionType] = []
        matched_rules: list[str] = []

        for pattern, decision in self._patterns.items():
            if pattern.lower() in content_lower:
                matched_decisions.append(decision)
                matched_rules.append(f"pattern:{pattern}")

        if not matched_decisions:
            return PolicyResult(
                decision=DecisionType.ALLOW,
                reasons=["no_pattern_match"],
            )

        # Return highest priority decision
        final_decision = min(matched_decisions)
        return PolicyResult(
            decision=final_decision,
            reasons=[f"pattern_matched:{r}" for r in matched_rules],
            rule_hits=matched_rules,
        )
