# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.ml modules (pipeline + quantization)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

try:
    from core.ml.pipeline import (
        ABTestManager,
        FeatureEngineeringDAG,
        FeatureNode,
        MLExperimentManager,
        MockTrial,
        ModelDriftDetector,
        OptunaTuner,
        PipelineContext,
        detect_model_drift,
        record_online_learning_event,
        shadow_mode_inference,
    )
except ImportError:
    pytest.skip("core.ml.pipeline not importable", allow_module_level=True)

try:
    from core.ml.quantization import (
        QuantizationConfig,
        UniformAffineQuantizer,
    )
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)


class TestFeatureEngineeringDAG:
    def test_register_and_run(self):
        dag = FeatureEngineeringDAG()
        dag.register(FeatureNode(name="f1", compute=lambda ctx: {"x": 1}))
        ctx = PipelineContext(training_frame=None)
        features = dag.run(ctx)
        assert "f1" in features

    def test_duplicate_raises(self):
        dag = FeatureEngineeringDAG()
        dag.register(FeatureNode(name="a", compute=lambda c: {}))
        with pytest.raises(ValueError):
            dag.register(FeatureNode(name="a", compute=lambda c: {}))

    def test_dependency_order(self):
        order = []
        dag = FeatureEngineeringDAG()
        dag.register(
            FeatureNode(
                name="b",
                compute=lambda c: (order.append("b"), {})[1],
                dependencies=("a",),
            )
        )
        dag.register(FeatureNode(name="a", compute=lambda c: (order.append("a"), {})[1]))
        dag.run(PipelineContext(training_frame=None))
        assert order == ["a", "b"]

    def test_cyclic_raises(self):
        dag = FeatureEngineeringDAG()
        dag.register(FeatureNode(name="x", compute=lambda c: {}, dependencies=("y",)))
        dag.register(FeatureNode(name="y", compute=lambda c: {}, dependencies=("x",)))
        with pytest.raises(RuntimeError, match="Cyclic"):
            dag.run(PipelineContext(training_frame=None))


class TestMockTrial:
    def test_suggest_float(self):
        t = MockTrial()
        assert t.suggest_float("lr", 0.0, 1.0) == 0.5

    def test_suggest_int(self):
        t = MockTrial()
        assert t.suggest_int("n", 0, 10) == 5

    def test_suggest_categorical(self):
        t = MockTrial()
        assert t.suggest_categorical("opt", ["adam", "sgd"]) == "adam"


class TestABTestManager:
    def test_record_and_lift(self):
        ab = ABTestManager()
        for v in [1.0, 2.0, 3.0]:
            ab.record_metric("control", v)
        for v in [2.0, 3.0, 4.0]:
            ab.record_metric("treatment", v)
        assert ab.lift("control", "treatment") == pytest.approx(1.0)

    def test_lift_empty(self):
        assert ABTestManager().lift("a", "b") == 0.0


class TestModelDriftDetector:
    def test_no_drift(self):
        d = ModelDriftDetector(threshold=0.2)
        expected = list(range(100))
        assert not d.is_drifted(expected, expected)

    def test_drift_detected(self):
        d = ModelDriftDetector(threshold=0.01)
        expected = [float(x) for x in range(100)]
        observed = [float(x + 50) for x in range(100)]
        assert d.is_drifted(expected, observed)

    def test_psi_empty(self):
        d = ModelDriftDetector()
        assert d.psi([], []) == 0.0

    def test_detect_model_drift_util(self):
        d = ModelDriftDetector(threshold=0.2)
        data = [float(x) for x in range(100)]
        drifted, psi = detect_model_drift(d, expected_scores=data, observed_scores=data)
        assert not drifted
        assert psi >= 0.0


class TestMLExperimentManager:
    def test_context_manager_no_mlflow(self):
        mgr = MLExperimentManager("test")
        with mgr:
            mgr.log_params({"a": 1})
            mgr.log_metrics({"loss": 0.5})

    def test_log_artifact_no_mlflow(self):
        mgr = MLExperimentManager("test")
        mgr.log_artifact_json("name", {"k": "v"})


class TestShadowModeInference:
    def test_basic(self):
        model_a = MagicMock()
        model_b = MagicMock()
        model_a.predict.return_value = 1.0
        model_b.predict.return_value = 1.5
        results = shadow_mode_inference(model_a, model_b, ["input1"])
        assert len(results) == 1
        assert results[0]["delta"] == pytest.approx(0.5)


class TestRecordOnlineLearningEvent:
    def test_record(self):
        storage = {}
        record_online_learning_event(storage, model_id="m1", payload={"x": 1})
        assert "m1" in storage
        assert len(storage["m1"]) == 1


class TestOptunaTuner:
    def test_without_optuna(self):
        tuner = OptunaTuner(objective=lambda p: p.get("x", 0.5), n_trials=5)
        with patch("core.ml.pipeline.optuna", None):
            result = tuner.optimise(lambda trial: {"x": trial.suggest_float("x", 0, 1)})
        assert "x" in result


class TestQuantization:
    pytestmark = pytest.mark.skipif(
        UniformAffineQuantizer is None, reason="quantization not importable"
    )

    def test_default_config(self):
        cfg = QuantizationConfig()
        assert cfg.target_dtype == "int8"

    def test_invalid_dtype(self):
        with pytest.raises(ValueError):
            QuantizationConfig(target_dtype="int16")

    def test_invalid_scheme(self):
        with pytest.raises(ValueError):
            QuantizationConfig(scheme="weird")

    def test_quantize_int8(self):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="int8"))
        arr = np.random.default_rng(1).normal(0, 1, 100).astype(np.float32)
        q.calibrate(arr)
        result = q.quantize(arr)
        assert result.quantized.dtype == np.int8
        assert result.error_metrics["mse"] >= 0

    def test_quantize_float16(self):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="float16"))
        arr = np.random.default_rng(2).normal(0, 1, 50).astype(np.float32)
        result = q.quantize(arr)
        assert result.quantized.dtype == np.float16

    def test_fallback_on_degenerate(self):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="int8", allow_fallback=True))
        arr = np.zeros(10, dtype=np.float32)
        result = q.quantize(arr)
        assert result.fallback_used is True

    def test_as_dict(self):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="float16"))
        result = q.quantize(np.array([1.0, 2.0, 3.0], dtype=np.float32))
        d = result.as_dict()
        assert "latency_ms" in d
        assert "dtype" in d

    def test_calibrate_empty_raises(self):
        q = UniformAffineQuantizer()
        with pytest.raises(ValueError):
            q.calibrate(np.array([], dtype=np.float32))

    def test_no_fallback_raises(self):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="int8", allow_fallback=False))
        with pytest.raises(RuntimeError):
            q.quantize(np.zeros(10, dtype=np.float32))

    @pytest.mark.parametrize("size", [1, 10, 1000])
    def test_various_sizes(self, size):
        q = UniformAffineQuantizer(QuantizationConfig(target_dtype="int8"))
        arr = np.random.default_rng(3).normal(0, 1, size).astype(np.float32)
        q.calibrate(arr)
        result = q.quantize(arr)
        assert result.quantized.shape == (size,)
