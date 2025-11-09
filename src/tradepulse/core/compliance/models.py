"""Common data structures used across compliance modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ComplianceIssue:
    """Represents a single compliance violation or warning."""

    severity: str
    message: str


@dataclass(frozen=True)
class ComplianceReport:
    """Summarises the compliance posture of a subsystem."""

    compliant: bool
    issues: tuple[ComplianceIssue, ...]
    metadata: Mapping[str, str]


__all__ = ["ComplianceIssue", "ComplianceReport"]
