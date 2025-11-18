"""Tests for heuristic gate configuration."""

from __future__ import annotations

from core.heuristic_gate.config import HeuristicGateConfig


def test_default_weights_sum_to_one() -> None:
    """Test that default configuration weights sum to 1.0."""
    cfg = HeuristicGateConfig.default()
    assert abs(sum(cfg.weights.values()) - 1.0) < 1e-6


def test_invalid_blend_ratio_raises() -> None:
    """Test that invalid blend ratio raises ValueError."""
    cfg = HeuristicGateConfig(
        _weights=HeuristicGateConfig.default()._weights,
        _ranges=HeuristicGateConfig.default()._ranges,
        blend_ratio=1.5,
        _thresholds=HeuristicGateConfig.default()._thresholds,
    )
    raised = False
    try:
        cfg.validated()
    except ValueError:
        raised = True
    assert raised
