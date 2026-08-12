# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MFN command and artifact contracts.

The MFN surface intentionally uses only the Python standard library so the
packaging, help, and smoke-artifact path remain available before heavyweight
scientific dependencies are installed.
"""

from __future__ import annotations

from dataclasses import dataclass

MFN_COMMANDS: tuple[str, ...] = (
    "simulate",
    "extract",
    "detect",
    "forecast",
    "compare",
    "report",
    "run",
    "validate",
)


@dataclass(frozen=True, slots=True)
class MFNContract:
    """Stable fields emitted by every MFN stage artifact."""

    schema_version: str = "mfn.integration.v1"
    seed: int = 1337
    input_window_sec: int = 30
    claim_tier: str = "INSTRUMENTED"

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("schema_version must be a non-empty string")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(self.input_window_sec, int) or isinstance(self.input_window_sec, bool):
            raise ValueError("input_window_sec must be an integer")
        if self.input_window_sec <= 0:
            raise ValueError("input_window_sec must be positive")
        if not isinstance(self.claim_tier, str) or not self.claim_tier.strip():
            raise ValueError("claim_tier must be a non-empty string")
