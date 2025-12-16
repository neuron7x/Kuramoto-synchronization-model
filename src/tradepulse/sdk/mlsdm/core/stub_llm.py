"""Stub LLM provider for deterministic offline testing.

This module provides a StubLLMProvider that returns deterministic
outputs based on input patterns, without any network calls.
Used for replay testing and regression detection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

__all__ = [
    "StubLLMProvider",
    "StubResponse",
]


@dataclass(frozen=True, slots=True)
class StubResponse:
    """Response from the stub LLM provider.

    Attributes:
        text: The generated response text.
        blocked: Whether the input was blocked.
        reason: Reason for blocking (if applicable).
    """

    text: str
    blocked: bool = False
    reason: str = ""


class StubLLMProvider:
    """Deterministic stub LLM provider for offline testing.

    This provider returns predictable outputs based on input patterns:
    - Inputs containing "INJECT" or injection patterns -> blocked
    - Inputs containing "EXFIL" or exfiltration patterns -> blocked
    - Other inputs -> echo with fixed prefix

    No network calls are made. All outputs are deterministic.

    Example:
        >>> provider = StubLLMProvider()
        >>> resp = provider.generate("Hello world")
        >>> resp.text
        '[STUB-LLM] Echo: Hello world'
        >>> resp.blocked
        False
    """

    # Patterns that trigger blocking
    INJECTION_PATTERNS: tuple[str, ...] = (
        "ignore all previous",
        "ignore your",
        "[[system]]",
        "disregard safety",
        "admin_override",
        "developer mode",
        "dan mode",
        "unrestricted ai",
        "no restrictions",
        "INJECT",
    )

    EXFILTRATION_PATTERNS: tuple[str, ...] = (
        "api key",
        "api keys",
        "environment variable",
        "/etc/passwd",
        "user credentials",
        "passwords",
        "secrets",
        "config files",
        "EXFIL",
    )

    HARMFUL_PATTERNS: tuple[str, ...] = (
        "hurt myself",
        "ending my life",
        "harm people",
        "attack someone",
        "keylogger",
        "ransomware",
        "botnet",
        "ddos",
        "make weapons",
    )

    def __init__(
        self,
        echo_prefix: str = "[STUB-LLM] Echo:",
        seed: int = 42,
    ) -> None:
        """Initialize the stub provider.

        Args:
            echo_prefix: Prefix for echoed responses.
            seed: Seed for any pseudo-random behavior (unused currently).
        """
        self.echo_prefix = echo_prefix
        self.seed = seed

    def _check_patterns(
        self,
        text: str,
        patterns: tuple[str, ...],
    ) -> str | None:
        """Check if text contains any of the given patterns.

        Args:
            text: Text to check.
            patterns: Patterns to search for.

        Returns:
            The matched pattern or None.
        """
        text_lower = text.lower()
        for pattern in patterns:
            if pattern.lower() in text_lower:
                return pattern
        return None

    def generate(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> StubResponse:
        """Generate a deterministic response.

        Args:
            text: Input text to process.
            context: Optional context (unused in stub).

        Returns:
            StubResponse with deterministic output.
        """
        # Check for injection patterns
        injection_match = self._check_patterns(text, self.INJECTION_PATTERNS)
        if injection_match:
            return StubResponse(
                text="[BLOCKED] Injection attempt detected.",
                blocked=True,
                reason=f"injection_pattern:{injection_match}",
            )

        # Check for exfiltration patterns
        exfil_match = self._check_patterns(text, self.EXFILTRATION_PATTERNS)
        if exfil_match:
            return StubResponse(
                text="[BLOCKED] Data exfiltration attempt detected.",
                blocked=True,
                reason=f"exfiltration_pattern:{exfil_match}",
            )

        # Check for harmful patterns
        harmful_match = self._check_patterns(text, self.HARMFUL_PATTERNS)
        if harmful_match:
            return StubResponse(
                text="[BLOCKED] Potentially harmful content detected.",
                blocked=True,
                reason=f"harmful_pattern:{harmful_match}",
            )

        # Normal echo response
        # Use a deterministic transformation based on input hash
        input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        response_text = f"{self.echo_prefix} {text} [hash:{input_hash}]"

        return StubResponse(
            text=response_text,
            blocked=False,
            reason="",
        )

    def batch_generate(
        self,
        texts: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[StubResponse]:
        """Generate responses for multiple inputs.

        Args:
            texts: List of input texts.
            context: Optional shared context.

        Returns:
            List of StubResponse objects.
        """
        return [self.generate(text, context) for text in texts]
