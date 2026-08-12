# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.pipeline module."""

from __future__ import annotations

import pandas as pd
import pytest

from core.data.pipeline import (
    AnonymizationRule,
    BalanceConfig,
    PipelineConfigurationError,
    PipelineContext,
    PipelineError,
    PipelineExecutionError,
    PipelineSLAError,
    SLAConfig,
    SourceOfTruthSpec,
    StratifiedSplitConfig,
    SyntheticAugmentationConfig,
    ToxicityFilterConfig,
)


class TestSourceOfTruthSpec:
    def test_defaults(self):
        spec = SourceOfTruthSpec(name="test", loader=lambda ctx: pd.DataFrame())
        assert spec.name == "test"
        assert spec.priority == 100
        assert spec.datasets == frozenset()

    def test_supports_all_when_empty(self):
        spec = SourceOfTruthSpec(name="t", loader=lambda c: pd.DataFrame())
        assert spec.supports("any_dataset")

    def test_supports_specific(self):
        spec = SourceOfTruthSpec(
            name="t", loader=lambda c: pd.DataFrame(), datasets=frozenset({"ds1"})
        )
        assert spec.supports("ds1")
        assert not spec.supports("ds2")

    def test_custom_priority(self):
        spec = SourceOfTruthSpec(name="t", loader=lambda c: pd.DataFrame(), priority=50)
        assert spec.priority == 50


class TestToxicityFilterConfig:
    def test_defaults(self):
        cfg = ToxicityFilterConfig()
        assert cfg.column == "toxicity_score"
        assert cfg.threshold == 3.0

    def test_custom(self):
        cfg = ToxicityFilterConfig(column="toxic", threshold=5.0)
        assert cfg.column == "toxic"
        assert cfg.threshold == 5.0


class TestAnonymizationRule:
    def test_apply_hashes_column(self):
        rule = AnonymizationRule(column="user_id", salt=b"secret")
        df = pd.DataFrame({"user_id": ["alice", "bob"], "other": [1, 2]})
        rule.apply(df)
        assert df["user_id"].iloc[0] != "alice"
        assert len(df["user_id"].iloc[0]) == 64  # hex digest

    def test_apply_missing_column_noop(self):
        rule = AnonymizationRule(column="missing", salt=b"secret")
        df = pd.DataFrame({"other": [1, 2]})
        rule.apply(df)  # should not raise
        assert "missing" not in df.columns

    def test_keep_last_chars(self):
        rule = AnonymizationRule(column="email", salt=b"salt", keep_last_chars=4)
        df = pd.DataFrame({"email": ["hello@example.com"]})
        rule.apply(df)
        # Should have suffix
        assert ":" in df["email"].iloc[0]

    def test_deterministic(self):
        rule = AnonymizationRule(column="id", salt=b"key")
        df1 = pd.DataFrame({"id": ["value"]})
        df2 = pd.DataFrame({"id": ["value"]})
        rule.apply(df1)
        rule.apply(df2)
        assert df1["id"].iloc[0] == df2["id"].iloc[0]


class TestBalanceConfig:
    def test_defaults(self):
        cfg = BalanceConfig(column="label")
        assert cfg.column == "label"
        assert cfg.strategy == "undersample"


class TestStratifiedSplitConfig:
    def test_valid_splits(self):
        cfg = StratifiedSplitConfig(column="label", splits={"train": 0.7, "test": 0.3})
        result = cfg.normalised_splits()
        assert result["train"] == 0.7

    def test_zero_total_raises(self):
        cfg = StratifiedSplitConfig(column="l", splits={})
        with pytest.raises(ValueError, match="positive"):
            cfg.normalised_splits()

    def test_over_one_raises(self):
        cfg = StratifiedSplitConfig(column="l", splits={"a": 0.6, "b": 0.6})
        with pytest.raises(ValueError, match="exceed"):
            cfg.normalised_splits()

    def test_default_shuffle(self):
        cfg = StratifiedSplitConfig(column="l", splits={"a": 1.0})
        assert cfg.shuffle is True


class TestSyntheticAugmentationConfig:
    def test_defaults(self):
        cfg = SyntheticAugmentationConfig()
        assert cfg.samples == 0
        assert cfg.noise_scale == 0.01

    def test_custom(self):
        cfg = SyntheticAugmentationConfig(samples=100, noise_scale=0.05)
        assert cfg.samples == 100


class TestSLAConfig:
    def test_within_budget(self):
        cfg = SLAConfig(target_seconds=1.0)
        assert cfg.ensure_within_budget(0.5) is True

    def test_over_budget_non_strict(self):
        cfg = SLAConfig(target_seconds=1.0, strict=False)
        assert cfg.ensure_within_budget(2.0) is False

    def test_over_budget_strict_raises(self):
        cfg = SLAConfig(target_seconds=1.0, strict=True)
        with pytest.raises(PipelineSLAError):
            cfg.ensure_within_budget(2.0)

    def test_exactly_at_budget(self):
        cfg = SLAConfig(target_seconds=1.0)
        assert cfg.ensure_within_budget(1.0) is True


class TestPipelineContext:
    def test_minimal(self):
        ctx = PipelineContext(dataset="ds1")
        assert ctx.dataset == "ds1"
        assert ctx.metadata == {}
        assert ctx.backfill is False

    def test_with_metadata(self):
        ctx = PipelineContext(dataset="ds1", metadata={"source": "api"})
        assert ctx.metadata["source"] == "api"

    def test_full(self):
        ctx = PipelineContext(
            dataset="ds1",
            metadata={},
            backfill=True,
            feature_view="fv1",
            offline_dataset="od1",
        )
        assert ctx.backfill is True
        assert ctx.feature_view == "fv1"


class TestExceptions:
    def test_pipeline_error(self):
        assert issubclass(PipelineError, RuntimeError)

    def test_configuration_error(self):
        assert issubclass(PipelineConfigurationError, PipelineError)

    def test_execution_error(self):
        assert issubclass(PipelineExecutionError, PipelineError)

    def test_sla_error(self):
        assert issubclass(PipelineSLAError, PipelineExecutionError)
