"""Decision trace for policy audit trail.

This module provides structured decision tracing with scrubbing
for sensitive data (PII, secrets, tokens).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

from .decision_types import DecisionType

__all__ = [
    "DecisionTrace",
    "Redaction",
    "TraceScrubber",
    "create_trace",
]


@dataclass(frozen=True, slots=True)
class Redaction:
    """Record of a redaction applied to content.

    Attributes:
        start: Start position in original text.
        end: End position in original text.
        original_length: Length of original content.
        replacement: The replacement text used.
        reason: Why this redaction was applied.
    """

    start: int
    end: int
    original_length: int
    replacement: str
    reason: str


@dataclass(slots=True)
class DecisionTrace:
    """Structured trace of a policy decision for audit.

    All traces are scrubbed to ensure no raw PII or secrets
    appear in logs or audit trails.
    """

    trace_id: str
    stage: str
    input_hash: str
    module_name: str
    module_version: str
    final_decision: DecisionType
    reasons: list[str]
    strict_mode: bool
    created_at: str

    # Optional fields with defaults
    signals: dict[str, float] = field(default_factory=dict)
    rule_hits: list[str] = field(default_factory=list)
    confidence: float | None = None
    redactions: list[Redaction] = field(default_factory=list)
    rewritten_text: str | None = None
    applied_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "stage": self.stage,
            "input_hash": self.input_hash,
            "module_name": self.module_name,
            "module_version": self.module_version,
            "final_decision": str(self.final_decision),
            "reasons": self.reasons,
            "strict_mode": self.strict_mode,
            "created_at": self.created_at,
            "signals": self.signals,
            "rule_hits": self.rule_hits,
            "confidence": self.confidence,
            "redactions": [
                {
                    "start": r.start,
                    "end": r.end,
                    "original_length": r.original_length,
                    "replacement": r.replacement,
                    "reason": r.reason,
                }
                for r in self.redactions
            ],
            "rewritten_text": self.rewritten_text,
            "applied_rules": self.applied_rules,
        }


class TraceScrubber:
    """Scrubber for removing PII and secrets from trace data.

    This scrubber masks sensitive patterns to prevent
    accidental exposure in logs and audit trails.
    """

    # Pre-compiled patterns for performance
    EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )
    PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    )
    SSN_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    CARD_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    )
    TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"\b(?:sk_live_|sk_test_|pk_live_|pk_test_|Bearer\s+|"
        r"api[_-]?key[=:]\s*|token[=:]\s*)[A-Za-z0-9_-]{10,}\b",
        re.IGNORECASE,
    )
    API_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"\b[A-Za-z0-9]{32,64}\b"
    )

    REPLACEMENTS: Final[dict[str, str]] = {
        "email": "[EMAIL_REDACTED]",
        "phone": "[PHONE_REDACTED]",
        "ssn": "[SSN_REDACTED]",
        "card": "[CARD_REDACTED]",
        "token": "[TOKEN_REDACTED]",
    }

    def scrub(self, text: str) -> str:
        """Remove sensitive patterns from text.

        Args:
            text: Input text that may contain PII/secrets.

        Returns:
            Text with sensitive patterns replaced.
        """
        result = text

        # Order matters: more specific patterns first
        result = self.SSN_PATTERN.sub(self.REPLACEMENTS["ssn"], result)
        result = self.CARD_PATTERN.sub(self.REPLACEMENTS["card"], result)
        result = self.TOKEN_PATTERN.sub(self.REPLACEMENTS["token"], result)
        result = self.EMAIL_PATTERN.sub(self.REPLACEMENTS["email"], result)
        result = self.PHONE_PATTERN.sub(self.REPLACEMENTS["phone"], result)

        return result

    def scrub_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively scrub all string values in a dictionary.

        Args:
            data: Dictionary that may contain sensitive values.

        Returns:
            Dictionary with all string values scrubbed.
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.scrub(value)
            elif isinstance(value, dict):
                result[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.scrub(v) if isinstance(v, str) else v for v in value
                ]
            else:
                result[key] = value
        return result


def compute_input_hash(text: str) -> str:
    """Compute stable hash of normalized input.

    Args:
        text: Input text to hash.

    Returns:
        SHA256 hash prefixed with 'sha256:'.
    """
    # Normalize: lowercase, strip whitespace, normalize unicode
    normalized = text.lower().strip()
    normalized = " ".join(normalized.split())  # Normalize whitespace
    hash_bytes = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    # Truncate to 16 hex chars (64 bits) for brevity in traces.
    # This is sufficient for deduplication/correlation; full hash used rarely.
    return f"sha256:{hash_bytes[:16]}"


def create_trace(
    *,
    stage: str,
    input_text: str,
    module_name: str,
    module_version: str,
    final_decision: DecisionType,
    reasons: list[str],
    strict_mode: bool = False,
    signals: dict[str, float] | None = None,
    rule_hits: list[str] | None = None,
    confidence: float | None = None,
    redactions: list[Redaction] | None = None,
    rewritten_text: str | None = None,
    applied_rules: list[str] | None = None,
) -> DecisionTrace:
    """Create a new decision trace with auto-generated fields.

    Args:
        stage: Pipeline stage (prefilter/policy/postfilter).
        input_text: Original input for hash computation.
        module_name: Name of the module making the decision.
        module_version: Version of the module.
        final_decision: The policy decision.
        reasons: Machine-readable reason tags.
        strict_mode: Whether strict mode was active.
        signals: Optional dict of numeric signals.
        rule_hits: Optional list of matched rule IDs.
        confidence: Optional confidence score 0.0-1.0.
        redactions: Optional list of applied redactions.
        rewritten_text: Optional modified text if REWRITE.
        applied_rules: Optional list of applied rule names.

    Returns:
        A new DecisionTrace instance with scrubbed values.
    """
    scrubber = TraceScrubber()

    # Scrub rewritten_text if present
    scrubbed_rewritten = None
    if rewritten_text is not None:
        scrubbed_rewritten = scrubber.scrub(rewritten_text)

    # Scrub reasons
    scrubbed_reasons = [scrubber.scrub(r) for r in reasons]

    return DecisionTrace(
        trace_id=str(uuid.uuid4()),
        stage=stage,
        input_hash=compute_input_hash(input_text),
        module_name=module_name,
        module_version=module_version,
        final_decision=final_decision,
        reasons=scrubbed_reasons,
        strict_mode=strict_mode,
        created_at=datetime.now(timezone.utc).isoformat(),
        signals=signals or {},
        rule_hits=rule_hits or [],
        confidence=confidence,
        redactions=redactions or [],
        rewritten_text=scrubbed_rewritten,
        applied_rules=applied_rules or [],
    )
