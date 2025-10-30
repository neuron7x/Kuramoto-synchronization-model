# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
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
        return FeatureResult(
            name=self.name, value=float(data) + self.increment, metadata={}
        )


def test_base_feature_callable_contract() -> None:
    feature = DoubleFeature(name="double")
    result = feature(3)
    assert result.value == 6.0
    assert result.name == "double"


def test_feature_block_executes_all_features() -> None:
    block = FeatureBlock([DoubleFeature(name="double")])
    block.register(IncrementFeature(increment=2.0))
    outputs = block.run(5)
    assert outputs["double"] == 10.0
    assert outputs["increment"] == 7.0


def test_functional_feature_wraps_callable() -> None:
    func_feature = FunctionalFeature(
        lambda x: np.sum(x), name="sum", metadata={"kind": "agg"}
    )
    result = func_feature.transform(np.array([1, 2, 3]))
    assert result.value == 6
    assert result.metadata["kind"] == "agg"


def test_feature_block_extend() -> None:
    block = FeatureBlock()
    block.extend([DoubleFeature(name="double"), IncrementFeature(increment=0.5)])
    outputs = block(4)
    assert outputs == {"double": 8.0, "increment": 4.5}


def test_feature_block_supports_positional_name_and_alias_methods() -> None:
    block = FeatureBlock("regime")
    block.add_feature(DoubleFeature(name="double"))
    assert block.name == "regime"
    outputs = block.run(3)
    assert outputs == {"double": 6.0}


def test_feature_block_transform_all_returns_feature_results() -> None:
    block = FeatureBlock([DoubleFeature(name="double")])
    results = block.transform_all(2)
    assert set(results.keys()) == {"double"}
    result = results["double"]
    assert isinstance(result, FeatureResult)
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
