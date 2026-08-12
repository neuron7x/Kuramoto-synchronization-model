"""Central numeric configuration helpers for neuro modules."""

from __future__ import annotations

from .neuro_optimizer import NumericConfig

DEFAULT_NUMERIC_CONFIG = NumericConfig()
STABILITY_EPSILON = DEFAULT_NUMERIC_CONFIG.stability_epsilon
