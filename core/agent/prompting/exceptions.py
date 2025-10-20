"""Custom exceptions for the prompt management subsystem."""

from __future__ import annotations

__all__ = [
    "PromptError",
    "PromptTemplateNotFoundError",
    "PromptInjectionDetected",
    "PromptGuardrailViolation",
    "PromptExperimentError",
]


class PromptError(RuntimeError):
    """Base class for prompt related failures."""


class PromptTemplateNotFoundError(PromptError):
    """Raised when a requested prompt template is missing from the library."""


class PromptInjectionDetected(PromptError):
    """Raised when the sanitizer detects a probable prompt-injection attempt."""


class PromptGuardrailViolation(PromptError):
    """Raised when user inputs fail to satisfy configured guardrails."""


class PromptExperimentError(PromptError):
    """Raised for invalid experiment configuration or lifecycle actions."""
