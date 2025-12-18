"""Unit tests for policy decision contract.

These tests verify the correctness of:
- DecisionType priority ordering
- Decision resolution logic
- Strict mode behavior
- Trace generation and scrubbing
- Policy engine coordination
"""

from __future__ import annotations

import uuid

import pytest

from tradepulse.policy.decision_trace import (
    Redaction,
    TraceScrubber,
    compute_input_hash,
    create_trace,
)
from tradepulse.policy.decision_types import (
    DecisionType,
    resolve_decisions,
    to_legacy_decision,
)
from tradepulse.policy.policy_engine import (
    PolicyEngine,
    PolicyEngineConfig,
    PolicyResult,
    SimplePolicyModule,
)


class TestDecisionPriority:
    """Tests for decision priority ordering."""

    def test_decision_priority_block_wins(self):
        """BLOCK should win over all other decisions."""
        decisions = [
            DecisionType.ALLOW,
            DecisionType.REWRITE,
            DecisionType.REDACT,
            DecisionType.ESCALATE,
            DecisionType.BLOCK,
        ]
        result = resolve_decisions(decisions)
        assert result == DecisionType.BLOCK

    def test_decision_priority_redact_over_rewrite(self):
        """REDACT should win over REWRITE and ALLOW."""
        decisions = [DecisionType.ALLOW, DecisionType.REWRITE, DecisionType.REDACT]
        result = resolve_decisions(decisions)
        assert result == DecisionType.REDACT

    def test_decision_priority_rewrite_over_allow(self):
        """REWRITE should win over ALLOW."""
        decisions = [DecisionType.ALLOW, DecisionType.REWRITE]
        result = resolve_decisions(decisions)
        assert result == DecisionType.REWRITE

    def test_decision_priority_escalate_over_allow(self):
        """ESCALATE should win over ALLOW."""
        decisions = [DecisionType.ALLOW, DecisionType.ESCALATE]
        result = resolve_decisions(decisions)
        assert result == DecisionType.ESCALATE

    def test_decision_priority_ordering(self):
        """Verify full priority ordering: BLOCK < REDACT < REWRITE < ESCALATE < ALLOW."""
        assert DecisionType.BLOCK.value < DecisionType.REDACT.value
        assert DecisionType.REDACT.value < DecisionType.REWRITE.value
        assert DecisionType.REWRITE.value < DecisionType.ESCALATE.value
        assert DecisionType.ESCALATE.value < DecisionType.ALLOW.value

    def test_empty_decisions_raises(self):
        """Empty decisions list should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot resolve empty"):
            resolve_decisions([])


class TestStrictMode:
    """Tests for strict mode behavior."""

    def test_strict_mode_escalate_becomes_block(self):
        """In strict mode, ESCALATE should be treated as BLOCK."""
        decisions = [DecisionType.ALLOW, DecisionType.ESCALATE]
        result = resolve_decisions(decisions, strict_mode=True)
        assert result == DecisionType.BLOCK

    def test_strict_mode_fail_closed_on_exception(self):
        """In strict mode, policy engine should BLOCK on module exception."""

        def failing_evaluator(content, context):
            raise RuntimeError("Module failure")

        failing_module = SimplePolicyModule(
            name="failing_module",
            version="1.0.0",
            evaluator=failing_evaluator,
        )

        config = PolicyEngineConfig(strict_mode=True)
        engine = PolicyEngine(config=config, modules=[failing_module])

        result, trace = engine.evaluate("test content")

        assert result.decision == DecisionType.BLOCK
        assert "module_exception:failing_module" in result.reasons

    def test_permissive_mode_continues_on_exception(self):
        """In permissive mode, policy engine should continue on module exception."""

        def failing_evaluator(content, context):
            raise RuntimeError("Module failure")

        failing_module = SimplePolicyModule(
            name="failing_module",
            version="1.0.0",
            evaluator=failing_evaluator,
        )
        working_module = SimplePolicyModule(
            name="working_module",
            version="1.0.0",
            patterns={},  # Will return ALLOW
        )

        config = PolicyEngineConfig(strict_mode=False)
        engine = PolicyEngine(config=config, modules=[failing_module, working_module])

        result, trace = engine.evaluate("test content")

        # Should get ALLOW from working module
        assert result.decision == DecisionType.ALLOW
        assert "module_error:failing_module" in result.reasons


class TestDecisionTrace:
    """Tests for decision trace generation."""

    def test_trace_contains_rule_hits_and_stage(self):
        """Trace should contain rule hits and stage information."""
        trace = create_trace(
            stage="prefilter",
            input_text="test input",
            module_name="test_module",
            module_version="1.0.0",
            final_decision=DecisionType.BLOCK,
            reasons=["test_reason"],
            rule_hits=["rule_001", "rule_002"],
        )

        assert trace.stage == "prefilter"
        assert "rule_001" in trace.rule_hits
        assert "rule_002" in trace.rule_hits
        assert trace.final_decision == DecisionType.BLOCK

    def test_trace_has_valid_trace_id(self):
        """Trace should have a valid UUID trace_id."""
        trace = create_trace(
            stage="policy",
            input_text="test",
            module_name="test",
            module_version="1.0.0",
            final_decision=DecisionType.ALLOW,
            reasons=["test"],
        )

        # Should be a valid UUID
        parsed = uuid.UUID(trace.trace_id)
        assert str(parsed) == trace.trace_id

    def test_trace_has_input_hash(self):
        """Trace should have a stable input hash."""
        trace1 = create_trace(
            stage="policy",
            input_text="test input",
            module_name="test",
            module_version="1.0.0",
            final_decision=DecisionType.ALLOW,
            reasons=["test"],
        )
        trace2 = create_trace(
            stage="policy",
            input_text="TEST INPUT",  # Different case
            module_name="test",
            module_version="1.0.0",
            final_decision=DecisionType.ALLOW,
            reasons=["test"],
        )

        # Hashes should be stable (normalized to lowercase)
        assert trace1.input_hash == trace2.input_hash
        assert trace1.input_hash.startswith("sha256:")


class TestTraceScrubber:
    """Tests for trace scrubbing of sensitive data."""

    def test_trace_scrubs_email(self):
        """Scrubber should mask email addresses."""
        scrubber = TraceScrubber()
        text = "Contact user@example.com for help"
        result = scrubber.scrub(text)
        assert "[EMAIL_REDACTED]" in result
        assert "user@example.com" not in result

    def test_trace_scrubs_phone(self):
        """Scrubber should mask phone numbers."""
        scrubber = TraceScrubber()
        text = "Call +1-555-123-4567 now"
        result = scrubber.scrub(text)
        assert "[PHONE_REDACTED]" in result
        assert "555-123-4567" not in result

    def test_trace_scrubs_ssn(self):
        """Scrubber should mask SSN patterns."""
        scrubber = TraceScrubber()
        text = "SSN: 123-45-6789"
        result = scrubber.scrub(text)
        assert "[SSN_REDACTED]" in result
        assert "123-45-6789" not in result

    def test_trace_scrubs_credit_card(self):
        """Scrubber should mask credit card numbers."""
        scrubber = TraceScrubber()
        text = "Card: 4111-1111-1111-1111"
        result = scrubber.scrub(text)
        assert "[CARD_REDACTED]" in result
        assert "4111" not in result

    def test_trace_scrubs_sensitive_patterns(self):
        """Scrubber should mask API tokens."""
        scrubber = TraceScrubber()
        text = "API key: sk_live_abcdef123456789"
        result = scrubber.scrub(text)
        assert "[TOKEN_REDACTED]" in result
        assert "sk_live" not in result

    def test_scrub_dict_recursive(self):
        """Scrubber should handle nested dictionaries."""
        scrubber = TraceScrubber()
        data = {
            "user": {"email": "test@example.com", "name": "John"},
            "metadata": {"phone": "+1-555-123-4567"},
        }
        result = scrubber.scrub_dict(data)
        assert "[EMAIL_REDACTED]" in result["user"]["email"]
        assert "[PHONE_REDACTED]" in result["metadata"]["phone"]
        assert result["user"]["name"] == "John"  # Non-sensitive preserved


class TestRedactMarking:
    """Tests for redaction marking."""

    def test_redact_marks_redactions(self):
        """REDACT decision should include redaction metadata."""
        redaction = Redaction(
            start=10,
            end=25,
            original_length=15,
            replacement="[REDACTED]",
            reason="pii_detected",
        )

        result = PolicyResult(
            decision=DecisionType.REDACT,
            reasons=["pii_detected"],
            redactions=[redaction],
        )

        assert len(result.redactions) == 1
        assert result.redactions[0].reason == "pii_detected"
        assert result.redactions[0].replacement == "[REDACTED]"


class TestRewriteMarking:
    """Tests for rewrite marking."""

    def test_rewrite_marks_rewritten_text(self):
        """REWRITE decision should include rewritten text."""
        result = PolicyResult(
            decision=DecisionType.REWRITE,
            reasons=["content_sanitized"],
            rewritten_text="This is the sanitized version of the content.",
        )

        assert result.rewritten_text is not None
        assert "sanitized" in result.rewritten_text


class TestPolicyEngineReasons:
    """Tests for policy engine reason handling."""

    def test_policy_engine_does_not_allow_on_empty_reasons_strict(self):
        """In strict mode, ALLOW without reasons should become BLOCK."""

        def empty_allow_evaluator(content, context):
            return PolicyResult(
                decision=DecisionType.ALLOW,
                reasons=[],  # Empty reasons
            )

        module = SimplePolicyModule(
            name="empty_reasons",
            version="1.0.0",
            evaluator=empty_allow_evaluator,
        )

        config = PolicyEngineConfig(strict_mode=True, require_reasons_for_allow=True)
        engine = PolicyEngine(config=config, modules=[module])

        result, trace = engine.evaluate("test content")

        assert result.decision == DecisionType.BLOCK
        assert "allow_without_reasons_blocked" in result.reasons


class TestPipelineTraceId:
    """Tests for pipeline trace ID propagation."""

    def test_pipeline_returns_decision_trace_id(self):
        """Pipeline should return a valid trace ID."""
        module = SimplePolicyModule(
            name="test_module",
            version="1.0.0",
            patterns={},
        )

        config = PolicyEngineConfig()
        engine = PolicyEngine(config=config, modules=[module])

        result, trace = engine.evaluate("test content")

        assert trace.trace_id is not None
        assert len(trace.trace_id) > 0
        # Verify it's a valid UUID
        uuid.UUID(trace.trace_id)


class TestLegacyCompatibility:
    """Tests for backward compatibility with GO/HOLD/NO_GO."""

    def test_allow_maps_to_go(self):
        """ALLOW should map to GO for legacy consumers."""
        assert to_legacy_decision(DecisionType.ALLOW) == "GO"

    def test_block_maps_to_no_go(self):
        """BLOCK should map to NO_GO for legacy consumers."""
        assert to_legacy_decision(DecisionType.BLOCK) == "NO_GO"

    def test_redact_maps_to_hold(self):
        """REDACT should map to HOLD for legacy consumers."""
        assert to_legacy_decision(DecisionType.REDACT) == "HOLD"

    def test_rewrite_maps_to_hold(self):
        """REWRITE should map to HOLD for legacy consumers."""
        assert to_legacy_decision(DecisionType.REWRITE) == "HOLD"

    def test_escalate_maps_to_hold(self):
        """ESCALATE should map to HOLD for legacy consumers."""
        assert to_legacy_decision(DecisionType.ESCALATE) == "HOLD"


class TestInputHashStability:
    """Tests for input hash stability."""

    def test_hash_ignores_whitespace(self):
        """Hash should normalize whitespace."""
        hash1 = compute_input_hash("hello   world")
        hash2 = compute_input_hash("hello world")
        assert hash1 == hash2

    def test_hash_case_insensitive(self):
        """Hash should be case-insensitive."""
        hash1 = compute_input_hash("Hello World")
        hash2 = compute_input_hash("hello world")
        assert hash1 == hash2

    def test_hash_deterministic(self):
        """Hash should be deterministic."""
        text = "This is a test input"
        hash1 = compute_input_hash(text)
        hash2 = compute_input_hash(text)
        assert hash1 == hash2
