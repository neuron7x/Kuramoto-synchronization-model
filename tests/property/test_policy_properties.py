# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property-based tests for policy decision contract.

These tests use Hypothesis to verify invariants across
randomly generated inputs.
"""

from __future__ import annotations

import string

import pytest

from geosync.policy.decision_trace import TraceScrubber, compute_input_hash
from geosync.policy.decision_types import DecisionType, resolve_decisions
from geosync.policy.policy_engine import (
    PolicyEngine,
    PolicyEngineConfig,
    SimplePolicyModule,
)

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

    # Define no-op decorators for when hypothesis is not available
    # These preserve basic function metadata by returning the skipped function
    def _skip_decorator(*args, **kwargs):
        def decorator(f):
            return pytest.mark.skip(reason="hypothesis not installed")(f)

        return decorator

    given = _skip_decorator

    def settings(*args, **kwargs):
        return lambda f: f

    st = None


# Injection patterns that should never result in ALLOW
INJECTION_PATTERNS = [
    "ignore all previous",
    "ignore your instructions",
    "[[SYSTEM]]",
    "ADMIN_OVERRIDE",
    "DAN mode",
    "developer mode",
    "unrestricted ai",
    "disregard safety",
    "no ethical guidelines",
]


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestInjectionPatterns:
    """Property tests for injection pattern detection."""

    @given(
        prefix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        suffix=st.text(alphabet=string.ascii_letters + " ", min_size=0, max_size=20),
        pattern_idx=st.integers(min_value=0, max_value=len(INJECTION_PATTERNS) - 1),
    )
    @settings(max_examples=50)
    def test_injection_patterns_not_allow(self, prefix, suffix, pattern_idx):
        """Injection patterns should never result in ALLOW."""
        pattern = INJECTION_PATTERNS[pattern_idx]
        content = f"{prefix} {pattern} {suffix}"

        # Create policy engine with injection detector
        injection_module = SimplePolicyModule(
            name="injection_detector",
            version="1.0.0",
            patterns={p: DecisionType.BLOCK for p in INJECTION_PATTERNS},
        )

        config = PolicyEngineConfig(strict_mode=True)
        engine = PolicyEngine(config=config, modules=[injection_module])

        result, trace = engine.evaluate(content)

        # Should not be ALLOW
        assert (
            result.decision != DecisionType.ALLOW
        ), f"Injection pattern '{pattern}' was incorrectly ALLOWED in: {content}"


# Token-like patterns that should be scrubbed
TOKEN_PATTERNS = [
    ("sk_live_", 20),  # Stripe live key prefix
    ("sk_test_", 20),  # Stripe test key prefix
    ("Bearer ", 30),  # JWT Bearer token
]


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestTraceScrubber:
    """Property tests for trace scrubber."""

    @given(
        token_chars=st.text(
            alphabet=string.ascii_letters + string.digits + "_-",
            min_size=15,
            max_size=40,
        ),
        prefix_idx=st.integers(min_value=0, max_value=len(TOKEN_PATTERNS) - 1),
    )
    @settings(max_examples=50)
    def test_token_patterns_scrubbed(self, token_chars, prefix_idx):
        """Token-like strings should not appear in scrubbed output."""
        prefix, min_len = TOKEN_PATTERNS[prefix_idx]

        # Generate a token-like string
        if len(token_chars) < min_len - len(prefix):
            token_chars = token_chars + "x" * (min_len - len(prefix) - len(token_chars))

        token = f"{prefix}{token_chars}"
        content = f"Use this token: {token} for authentication"

        scrubber = TraceScrubber()
        result = scrubber.scrub(content)

        # The full token should not appear in the result
        assert token not in result, f"Token '{token}' was not scrubbed from output: {result}"
        # But the replacement should be present
        assert "[TOKEN_REDACTED]" in result or prefix not in result

    @given(
        local_part=st.text(
            alphabet=string.ascii_lowercase + string.digits + "._",
            min_size=1,
            max_size=10,
        ).filter(lambda x: x and x[0].isalnum()),
        domain=st.text(
            alphabet=string.ascii_lowercase + string.digits,
            min_size=1,
            max_size=10,
        ).filter(lambda x: x and x[0].isalnum()),
    )
    @settings(max_examples=50)
    def test_email_patterns_scrubbed(self, local_part, domain):
        """Email addresses should be scrubbed."""
        email = f"{local_part}@{domain}.com"
        content = f"Contact us at {email} for support"

        scrubber = TraceScrubber()
        result = scrubber.scrub(content)

        # Email should not appear in clear text
        assert email not in result, f"Email '{email}' was not scrubbed from output: {result}"

    @given(
        area=st.integers(min_value=100, max_value=999),
        exchange=st.integers(min_value=100, max_value=999),
        subscriber=st.integers(min_value=1000, max_value=9999),
    )
    @settings(max_examples=30)
    def test_phone_patterns_scrubbed(self, area, exchange, subscriber):
        """Phone numbers should be scrubbed."""
        phone = f"{area}-{exchange}-{subscriber}"
        content = f"Call us at {phone}"

        scrubber = TraceScrubber()
        result = scrubber.scrub(content)

        # Phone should not appear in result
        assert phone not in result, f"Phone '{phone}' was not scrubbed from output: {result}"


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestDecisionResolution:
    """Property tests for decision resolution."""

    @given(
        decisions=st.lists(
            st.sampled_from(list(DecisionType)),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_resolution_returns_valid_decision(self, decisions):
        """Resolution should always return a valid DecisionType."""
        result = resolve_decisions(decisions)
        assert isinstance(result, DecisionType)

    @given(
        decisions=st.lists(
            st.sampled_from(list(DecisionType)),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_resolution_respects_priority(self, decisions):
        """Resolution should return the highest priority decision."""
        result = resolve_decisions(decisions)
        # Result should be <= all decisions (lower value = higher priority)
        assert all(result.value <= d.value for d in decisions)

    @given(
        other_decisions=st.lists(
            st.sampled_from(
                [
                    DecisionType.ALLOW,
                    DecisionType.REWRITE,
                    DecisionType.REDACT,
                    DecisionType.ESCALATE,
                ]
            ),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_block_always_wins(self, other_decisions):
        """BLOCK should always win over any other decisions."""
        decisions = other_decisions + [DecisionType.BLOCK]
        result = resolve_decisions(decisions)
        assert result == DecisionType.BLOCK


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestInputHashProperties:
    """Property tests for input hash computation."""

    @given(
        text=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=50)
    def test_hash_deterministic(self, text):
        """Same input should always produce same hash."""
        hash1 = compute_input_hash(text)
        hash2 = compute_input_hash(text)
        assert hash1 == hash2

    @given(
        text=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=50)
    def test_hash_format(self, text):
        """Hash should have correct format."""
        result = compute_input_hash(text)
        assert result.startswith("sha256:")
        # Hash portion should be hex
        hash_portion = result.split(":")[1]
        assert all(c in "0123456789abcdef" for c in hash_portion)

    @given(
        text=st.text(
            alphabet=string.ascii_letters + string.digits + string.punctuation + " ",
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=50)
    def test_hash_case_insensitive(self, text):
        """Hash should be case-insensitive for ASCII text."""
        hash_lower = compute_input_hash(text.lower())
        hash_upper = compute_input_hash(text.upper())
        assert hash_lower == hash_upper
