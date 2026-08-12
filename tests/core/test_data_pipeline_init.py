# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.pipeline.DataPipeline initialization and methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.data.pipeline import (
    DataPipeline,
    DataPipelineConfig,
    DataPipelineResult,
    PipelineConfigurationError,
    SourceOfTruthSpec,
)


def _mock_source(name="src", priority=100):
    return SourceOfTruthSpec(name=name, loader=lambda ctx: pd.DataFrame(), priority=priority)


class TestDataPipelineInit:
    def test_empty_sources_raises(self):
        cfg = DataPipelineConfig(sources=(), schema_registry={})
        with pytest.raises(PipelineConfigurationError, match="source"):
            DataPipeline(cfg)

    def test_valid_init(self):
        cfg = DataPipelineConfig(sources=(_mock_source(),), schema_registry={})
        pipeline = DataPipeline(cfg)
        assert pipeline is not None

    def test_custom_random_seed(self):
        cfg = DataPipelineConfig(sources=(_mock_source(),), schema_registry={}, random_seed=42)
        pipeline = DataPipeline(cfg)
        # rng is initialised
        assert pipeline._rng is not None


class TestDataPipelineConfig:
    def test_defaults(self):
        cfg = DataPipelineConfig(sources=(_mock_source(),), schema_registry={})
        assert cfg.quality_gates == {}
        assert cfg.toxicity_filter is None
        assert cfg.anonymization_rules == ()
        assert cfg.random_seed == 7_211_203

    def test_resolve_schema_missing_raises(self):
        cfg = DataPipelineConfig(sources=(_mock_source(),), schema_registry={})
        with pytest.raises(PipelineConfigurationError, match="No schema"):
            cfg.resolve_schema("nonexistent")

    def test_resolve_schema_found(self):
        mock_schema = MagicMock()
        cfg = DataPipelineConfig(
            sources=(_mock_source(),),
            schema_registry={"ds1": mock_schema},
        )
        assert cfg.resolve_schema("ds1") is mock_schema

    def test_resolve_quality_gate_missing_returns_none(self):
        cfg = DataPipelineConfig(sources=(_mock_source(),), schema_registry={})
        assert cfg.resolve_quality_gate("ds1") is None

    def test_resolve_quality_gate_found(self):
        mock_gate = MagicMock()
        cfg = DataPipelineConfig(
            sources=(_mock_source(),),
            schema_registry={},
            quality_gates={"ds1": mock_gate},
        )
        assert cfg.resolve_quality_gate("ds1") is mock_gate


class TestDataPipelineResult:
    def test_creation(self):
        result = DataPipelineResult(
            dataset="ds1",
            source="src",
            clean_frame=pd.DataFrame(),
            quarantined_frame=pd.DataFrame(),
            toxic_frame=pd.DataFrame(),
            synthetic_frame=pd.DataFrame(),
            stratified_splits={},
            drift_summaries=(),
            backfill_result=None,
            duration_seconds=0.5,
            sla_met=True,
            metadata={},
        )
        assert result.dataset == "ds1"
        assert result.source == "src"
        assert result.sla_met is True
        assert result.duration_seconds == 0.5
