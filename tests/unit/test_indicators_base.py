# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for feature base classes and composition patterns.

This module tests the core feature transformation API, including:
- BaseFeature interface implementation
- FeatureBlock composition and execution
- FunctionalFeature callable wrapping

Related tests:
- test_indicator_base.py: Focuses on metrics integration
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.indicators.base import (
    BaseFeature,
    BlockFeature,
    FeatureBlock,
    FeatureResult,
    FunctionalFeature,
)


class DoubleFeature(BaseFeature):
    def transform(self, data, **kwargs):
        return FeatureResult(name=self.name, value=float(data) * 2, metadata={})


@dataclass
class IncrementFeature(BaseFeature):
    increment: float = 1.0

    def __init__(self, increment: float = 1.0) -> None:
        super().__init__(name="increment")
        self.increment = increment

    def transform(self, data, **kwargs):
        return FeatureResult(name=self.name, value=float(data) + self.increment, metadata={})


def test_base_feature_callable_contract() -> None:
    """Test that BaseFeature instances are callable and return FeatureResult.

    Validates:
    - Feature can be called directly (callable interface)
    - Result contains correct transformed value
    - Feature name is preserved in result
    """
    feature = DoubleFeature(name="double")
    result = feature(3)
    assert result.value == 6.0, "Value should be doubled"
    assert result.name == "double", "Feature name should be preserved"


def test_feature_block_executes_all_features() -> None:
    """Test that FeatureBlock executes all registered features.

    Validates:
    - All features in block are executed
    - Results are collected in dictionary
    - Feature registration works correctly
    """
    block = FeatureBlock([DoubleFeature(name="double")])
    block.register(IncrementFeature(increment=2.0))
    outputs = block.run(5)
    assert outputs["double"] == 10.0, "Double feature should transform correctly"
    assert outputs["increment"] == 7.0, "Increment feature should add 2.0"


def test_functional_feature_wraps_callable() -> None:
    """Test that FunctionalFeature correctly wraps arbitrary callables.

    This is the primary test for FunctionalFeature callable wrapping.
    See test_indicator_base.py for metadata-specific tests.

    Validates:
    - Arbitrary functions can be wrapped as features
    - Wrapped function is executed during transform
    - Metadata is preserved through wrapping
    """
    func_feature = FunctionalFeature(lambda x: np.sum(x), name="sum", metadata={"kind": "agg"})
    result = func_feature.transform(np.array([1, 2, 3]))
    assert result.value == 6, "Sum should be computed correctly"
    assert result.metadata["kind"] == "agg", "Metadata should be preserved"


def test_feature_block_extend() -> None:
    """Test that FeatureBlock can be extended with multiple features at once.

    Validates:
    - Multiple features can be added via extend()
    - Block remains callable after extension
    - All extended features are executed
    """
    block = FeatureBlock()
    block.extend([DoubleFeature(name="double"), IncrementFeature(increment=0.5)])
    outputs = block(4)
    assert outputs == {
        "double": 8.0,
        "increment": 4.5,
    }, "All extended features should execute"


def test_feature_block_supports_positional_name_and_alias_methods() -> None:
    """Test that FeatureBlock supports both naming and method aliases.

    Validates:
    - Block can be named during construction
    - add_feature() alias works correctly
    - run() method executes all features
    """
    block = FeatureBlock("regime")
    block.add_feature(DoubleFeature(name="double"))
    assert block.name == "regime", "Block name should be set correctly"
    outputs = block.run(3)
    assert outputs == {"double": 6.0}, "Feature should execute via run()"


def test_feature_block_transform_all_returns_feature_results() -> None:
    """Test that transform_all() returns full FeatureResult objects.

    Validates:
    - transform_all() returns dict of FeatureResult objects
    - Unlike run(), full result metadata is preserved
    - Result objects contain all expected fields
    """
    block = FeatureBlock([DoubleFeature(name="double")])
    results = block.transform_all(2)
    assert set(results.keys()) == {"double"}, "All features should be present"
    result = results["double"]
    assert isinstance(
        result, FeatureResult
    ), "Results should be FeatureResult objects, not raw values"
    assert result.value == 4.0


def test_block_feature_wraps_block_and_preserves_metadata() -> None:
    inner = FeatureBlock([DoubleFeature(name="double")], name="inner")
    nested = BlockFeature(inner, name="outer", metadata={"level": "inner"})
    result = nested.transform(5)
    assert result.name == "outer"
    assert result.value == {"double": 10.0}
    assert result.metadata["block"] == "inner"
    assert result.metadata["feature_count"] == 1
    assert result.metadata["level"] == "inner"
