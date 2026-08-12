# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structured exception hierarchy for the canonical entry contract.

The official validation protocol (§ 5 — Entry-Point Gate) requires every
boundary failure to surface as an explicit, typed exception so that
upstream pipelines can pattern-match on the failure class instead of
parsing free-form ``ValueError`` strings.

The hierarchy is single-rooted under :class:`SystemicRiskInputError`
and inherits from :class:`ValueError` — backward-compatible with every
existing ``except ValueError`` site, but pattern-matchable for new
callers.
"""

from __future__ import annotations

__all__ = [
    "SystemicRiskInputError",
    "InvalidExposureMatrixError",
    "InvalidNodeLabelsError",
    "InvalidTemporalPanelError",
]


class SystemicRiskInputError(ValueError):
    """Root of the structured-error hierarchy.

    Existing callers using ``except ValueError`` continue to work
    because every concrete error is also a ``ValueError``.
    """


class InvalidExposureMatrixError(SystemicRiskInputError):
    """Raised when the exposure matrix violates a documented invariant.

    Examples: non-square shape, NaN / Inf entries, negative entries,
    constraint mismatch with ``node_labels`` length.
    """


class InvalidNodeLabelsError(SystemicRiskInputError):
    """Raised when ``node_labels`` violates a documented invariant.

    Examples: duplicate labels, length mismatch with the exposure
    matrix, empty-string labels.
    """


class InvalidTemporalPanelError(SystemicRiskInputError):
    """Raised when a temporal-snapshot pipeline detects a panel-level defect.

    Examples: non-monotonic timestamps, snapshot cardinality
    inconsistent across pipeline stages, empty snapshot tuple where
    at least one is required.
    """
