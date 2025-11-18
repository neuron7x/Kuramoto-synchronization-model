"""Custom exceptions for heuristic gate system."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class InvalidSignalsError(ValueError):
    """Raised when heuristic signals fail validation.

    Attributes:
        issues: List of validation issues detected
        data: Signal data that failed validation
    """

    def __init__(
        self,
        message: str,
        *,
        issues: Sequence[str],
        data: Mapping[str, Any],
    ) -> None:
        """Initialize exception with validation details.

        Args:
            message: Error message
            issues: List of validation issues
            data: Signal data that failed validation
        """
        super().__init__(message)
        self.issues = tuple(issues)
        self.data = dict(data)

    def __str__(self) -> str:
        """String representation including issues."""
        base = super().__str__()
        return f"{base}. issues={self.issues!r}"
