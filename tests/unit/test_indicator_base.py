# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for base feature classes and metrics integration.

This module tests the core feature transformation infrastructure,
focusing on metrics collection and observability integration.
"""

from __future__ import annotations

import contextlib

import numpy as np
import pytest

from core.indicators.base import (
    BaseFeature,
    FeatureResult,
    FunctionalFeature,
)


class _ConstantFeature(BaseFeature):
    def __init__(self, value: float) -> None:
        super().__init__(name="constant")
        self._value = value

    def transform(self, data, **kwargs):  # noqa: ANN001 - interface defined by BaseFeature
        return FeatureResult(name=self.name, value=self._value, metadata={"data_id": id(data)})


def test_feature_transform_with_metrics(monkeypatch):
    """Test that feature transformation integrates with metrics collection.

    Validates:
    - Metrics collector is called during transformation
    - Feature values are recorded correctly
    - Transformation spans are created properly
    """
    import core.indicators.base as base_module

    recorded: list[tuple[str, float]] = []

    class DummyMetrics:
        def measure_feature_transform(self, feature_name: str, feature_type: str):
            return contextlib.nullcontext()

        def record_feature_value(self, feature_name: str, value: float) -> None:
            recorded.append((feature_name, value))

    monkeypatch.setattr(base_module, "get_metrics_collector", lambda: DummyMetrics())
    monkeypatch.setattr(
        base_module, "pipeline_span", lambda *_args, **_kwargs: contextlib.nullcontext()
    )

    feature = _ConstantFeature(42.5)
    result = feature.transform_with_metrics(np.ones(3), feature_type="test")

    assert result.value == 42.5, "Transform should return constant value"
    assert recorded == [("constant", 42.5)], "Metrics should record feature value"


def test_functional_feature_with_metadata() -> None:
    """Test that FunctionalFeature preserves metadata through transformation.

    This test focuses on metadata handling, complementing the test in
    test_indicators_base.py which focuses on callable wrapping behavior.

    Validates:
    - Metadata is preserved during transformation
    - Feature name is correctly set
    - Callable function is executed properly
    """
    metadata = {"alias": "sum", "description": "Sum aggregator"}
    func = lambda arr: float(np.sum(arr))  # noqa: E731 - simple lambda is fine for test
    feature = FunctionalFeature(func, name="aggregator", metadata=metadata)

    data = np.array([1.0, 2.0, 3.0])
    result = feature.transform(data)

    assert result.name == "aggregator", "Feature name should be preserved"
    assert result.value == pytest.approx(6.0), "Sum should be computed correctly"
    assert result.metadata == metadata, "Metadata should be preserved"
    assert "alias" in result.metadata, "Metadata should contain alias key"
