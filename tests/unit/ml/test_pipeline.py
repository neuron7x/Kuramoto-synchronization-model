# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ML pipeline module."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from core.ml.pipeline import (
    ABTestManager,
    FeatureEngineeringDAG,
    FeatureNode,
    MLExperimentManager,
    MLPipeline,
    MockTrial,
    ModelDriftDetector,
    OptunaTuner,
    PipelineContext,
    PipelineResult,
    detect_model_drift,
    record_online_learning_event,
    shadow_mode_inference,
)


class TestFeatureNode:
    """Tests for FeatureNode dataclass."""

    def test_feature_node_creation(self) -> None:
        """Verify FeatureNode can be created."""

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {"result": 42}

        node = FeatureNode(
            name="test_feature",
            compute=compute_fn,
            dependencies=("dep1", "dep2"),
            description="Test feature node",
        )
        assert node.name == "test_feature"
        assert node.dependencies == ("dep1", "dep2")
        assert node.description == "Test feature node"

    def test_feature_node_default_dependencies(self) -> None:
        """Verify default dependencies is empty tuple."""

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {}

        node = FeatureNode(name="test", compute=compute_fn)
        assert node.dependencies == ()


class TestFeatureEngineeringDAG:
    """Tests for FeatureEngineeringDAG class."""

    def test_dag_register_node(self) -> None:
        """Verify node can be registered."""
        dag = FeatureEngineeringDAG()

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {}

        node = FeatureNode(name="node1", compute=compute_fn)
        dag.register(node)
        assert "node1" in dag.nodes

    def test_dag_register_duplicate_raises(self) -> None:
        """Verify duplicate registration raises ValueError."""
        dag = FeatureEngineeringDAG()

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {}

        node = FeatureNode(name="node1", compute=compute_fn)
        dag.register(node)

        with pytest.raises(ValueError, match="already registered"):
            dag.register(node)

    def test_dag_run_executes_nodes(self) -> None:
        """Verify DAG run executes nodes in order."""
        dag = FeatureEngineeringDAG()
        executed = []

        def compute_a(ctx: PipelineContext) -> Mapping[str, Any]:
            executed.append("a")
            return {"a_result": 1}

        def compute_b(ctx: PipelineContext) -> Mapping[str, Any]:
            executed.append("b")
            return {"b_result": 2}

        dag.register(FeatureNode(name="node_a", compute=compute_a))
        dag.register(FeatureNode(name="node_b", compute=compute_b, dependencies=("node_a",)))

        ctx = PipelineContext(training_frame=None)
        features = dag.run(ctx)

        assert "a" in executed
        assert "b" in executed
        assert executed.index("a") < executed.index("b")
        assert "node_a" in features
        assert "node_b" in features

    def test_dag_run_detects_cycle(self) -> None:
        """Verify DAG detects cyclic dependencies."""
        dag = FeatureEngineeringDAG()

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {}

        dag.register(FeatureNode(name="a", compute=compute_fn, dependencies=("b",)))
        dag.register(FeatureNode(name="b", compute=compute_fn, dependencies=("a",)))

        ctx = PipelineContext(training_frame=None)
        with pytest.raises(RuntimeError, match="Cyclic dependency"):
            dag.run(ctx)


class TestPipelineContext:
    """Tests for PipelineContext dataclass."""

    def test_context_creation(self) -> None:
        """Verify PipelineContext can be created."""
        ctx = PipelineContext(training_frame="train_data")
        assert ctx.training_frame == "train_data"
        assert ctx.validation_frame is None
        assert ctx.inference_frame is None
        assert ctx.params == {}
        assert ctx.feature_store == {}

    def test_context_with_all_frames(self) -> None:
        """Verify PipelineContext with all frames."""
        ctx = PipelineContext(
            training_frame="train",
            validation_frame="val",
            inference_frame="inf",
            params={"param1": 1},
        )
        assert ctx.training_frame == "train"
        assert ctx.validation_frame == "val"
        assert ctx.inference_frame == "inf"
        assert ctx.params["param1"] == 1


class TestMockTrial:
    """Tests for MockTrial class."""

    def test_suggest_float_returns_midpoint(self) -> None:
        """Verify suggest_float returns midpoint."""
        trial = MockTrial()
        result = trial.suggest_float("param", 0.0, 10.0)
        assert result == 5.0

    def test_suggest_float_log_returns_midpoint(self) -> None:
        """Verify suggest_float with log returns midpoint."""
        trial = MockTrial()
        result = trial.suggest_float("param", 0.1, 10.0, log=True)
        assert result == 5.05

    def test_suggest_int_returns_midpoint(self) -> None:
        """Verify suggest_int returns midpoint."""
        trial = MockTrial()
        result = trial.suggest_int("param", 0, 10)
        assert result == 5

    def test_suggest_categorical_returns_first(self) -> None:
        """Verify suggest_categorical returns first choice."""
        trial = MockTrial()
        result = trial.suggest_categorical("param", ["a", "b", "c"])
        assert result == "a"


class TestMLExperimentManager:
    """Tests for MLExperimentManager class."""

    def test_experiment_manager_creation(self) -> None:
        """Verify MLExperimentManager can be created."""
        manager = MLExperimentManager(experiment_name="Test")
        assert manager._experiment_name == "Test"

    def test_experiment_manager_context_protocol(self) -> None:
        """Verify MLExperimentManager works as context manager."""
        manager = MLExperimentManager()
        with manager:
            pass  # Just verify it works

    def test_log_params_without_mlflow(self) -> None:
        """Verify log_params doesn't raise without MLflow."""
        manager = MLExperimentManager()
        manager.log_params({"param1": 1, "param2": "value"})

    def test_log_metrics_without_mlflow(self) -> None:
        """Verify log_metrics doesn't raise without MLflow."""
        manager = MLExperimentManager()
        manager.log_metrics({"metric1": 0.5, "metric2": 0.9})

    def test_log_artifact_json_without_mlflow(self) -> None:
        """Verify log_artifact_json doesn't raise without MLflow."""
        manager = MLExperimentManager()
        manager.log_artifact_json("artifact_name", {"key": "value"})


class TestOptunaTuner:
    """Tests for OptunaTuner class."""

    def test_optuna_tuner_creation(self) -> None:
        """Verify OptunaTuner can be created."""

        def objective(params: Mapping[str, Any]) -> float:
            return params.get("x", 0.0)

        tuner = OptunaTuner(objective=objective, n_trials=10)
        assert tuner._n_trials == 10

    def test_optuna_tuner_optimise_without_optuna(self) -> None:
        """Verify optimise works without Optuna (uses MockTrial)."""

        def objective(params: Mapping[str, Any]) -> float:
            return params.get("x", 0.0)

        def search_space(trial) -> Mapping[str, Any]:
            return {"x": trial.suggest_float("x", 0.0, 10.0)}

        tuner = OptunaTuner(objective=objective, n_trials=5)
        # This should use MockTrial when Optuna is not available
        result = tuner.optimise(search_space)
        assert "x" in result


class TestABTestManager:
    """Tests for ABTestManager class."""

    def test_ab_test_manager_creation(self) -> None:
        """Verify ABTestManager can be created."""
        manager = ABTestManager()
        assert manager._metrics == {}

    def test_record_metric_creates_series(self) -> None:
        """Verify record_metric creates metric series."""
        manager = ABTestManager()
        manager.record_metric("control", 1.0)
        assert "control" in manager._metrics
        assert 1.0 in manager._metrics["control"]

    def test_record_metric_respects_max_points(self) -> None:
        """Verify record_metric respects max_points."""
        manager = ABTestManager()
        for i in range(10):
            manager.record_metric("variant", float(i), max_points=5)
        assert len(manager._metrics["variant"]) == 5

    def test_lift_with_no_data_returns_zero(self) -> None:
        """Verify lift returns 0 with no data."""
        manager = ABTestManager()
        result = manager.lift("control", "treatment")
        assert result == 0.0

    def test_lift_with_data(self) -> None:
        """Verify lift calculation."""
        manager = ABTestManager()
        for _ in range(5):
            manager.record_metric("control", 1.0)
        for _ in range(5):
            manager.record_metric("treatment", 2.0)
        result = manager.lift("control", "treatment")
        assert result == 1.0  # 2.0 - 1.0


class TestModelDriftDetector:
    """Tests for ModelDriftDetector class."""

    def test_drift_detector_creation(self) -> None:
        """Verify ModelDriftDetector can be created."""
        detector = ModelDriftDetector(threshold=0.25)
        assert detector._threshold == 0.25

    def test_psi_with_empty_data_returns_zero(self) -> None:
        """Verify PSI returns 0 with empty data."""
        detector = ModelDriftDetector()
        result = detector.psi([], [1.0, 2.0])
        assert result == 0.0
        result = detector.psi([1.0, 2.0], [])
        assert result == 0.0

    def test_psi_invalid_buckets_raises(self) -> None:
        """Verify PSI raises with invalid buckets."""
        detector = ModelDriftDetector()
        with pytest.raises(ValueError, match="buckets must be positive"):
            detector.psi([1.0], [1.0], buckets=0)

    def test_psi_with_same_distribution(self) -> None:
        """Verify PSI is low with same distribution."""
        detector = ModelDriftDetector()
        data = list(range(100))
        result = detector.psi(data, data)
        assert result < 0.1  # Should be very low for identical data

    def test_psi_with_different_distribution(self) -> None:
        """Verify PSI is higher with different distribution."""
        detector = ModelDriftDetector()
        expected = list(range(100))
        observed = list(range(50, 150))  # Shifted distribution
        result = detector.psi(expected, observed)
        assert result > 0.0

    def test_is_drifted_below_threshold(self) -> None:
        """Verify is_drifted returns False below threshold."""
        detector = ModelDriftDetector(threshold=0.5)
        data = list(range(100))
        result = detector.is_drifted(data, data)
        assert result is False

    def test_is_drifted_above_threshold(self) -> None:
        """Verify is_drifted returns True above threshold."""
        detector = ModelDriftDetector(threshold=0.01)
        expected = list(range(100))
        observed = list(range(100, 200))  # Completely shifted
        result = detector.is_drifted(expected, observed)
        assert result is True


class TestDetectModelDrift:
    """Tests for detect_model_drift function."""

    def test_detect_model_drift_returns_tuple(self) -> None:
        """Verify detect_model_drift returns tuple."""
        detector = ModelDriftDetector()
        data = list(range(50))
        result = detect_model_drift(detector, expected_scores=data, observed_scores=data)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], float)


class TestShadowModeInference:
    """Tests for shadow_mode_inference function."""

    def test_shadow_mode_inference_captures_divergence(self) -> None:
        """Verify shadow mode captures divergence."""

        class ModelA:
            def predict(self, x):
                return x

        class ModelB:
            def predict(self, x):
                return x + 1

        model_a = ModelA()
        model_b = ModelB()
        inputs = [1, 2, 3]

        results = shadow_mode_inference(model_a, model_b, inputs)

        assert len(results) == 3
        assert results[0]["primary"] == 1
        assert results[0]["shadow"] == 2
        assert results[0]["delta"] == 1


class TestRecordOnlineLearningEvent:
    """Tests for record_online_learning_event function."""

    def test_record_event_creates_storage(self) -> None:
        """Verify record_event creates storage entry."""
        storage: dict = {}
        record_online_learning_event(storage, model_id="model_1", payload={"data": "value"})
        assert "model_1" in storage
        assert len(storage["model_1"]) == 1
        assert storage["model_1"][0]["payload"] == {"data": "value"}

    def test_record_event_appends_to_existing(self) -> None:
        """Verify record_event appends to existing storage."""
        storage: dict = {"model_1": [{"payload": {"old": "data"}, "recorded_at": "ts"}]}
        record_online_learning_event(storage, model_id="model_1", payload={"new": "data"})
        assert len(storage["model_1"]) == 2


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_pipeline_result_creation(self) -> None:
        """Verify PipelineResult can be created."""
        result = PipelineResult(
            model="model_obj",
            metrics={"accuracy": 0.95},
            params={"learning_rate": 0.01},
        )
        assert result.model == "model_obj"
        assert result.metrics["accuracy"] == 0.95
        assert result.params["learning_rate"] == 0.01


class TestMLPipeline:
    """Tests for MLPipeline class."""

    @pytest.fixture
    def simple_dag(self) -> FeatureEngineeringDAG:
        """Create a simple DAG for testing."""
        dag = FeatureEngineeringDAG()

        def compute_fn(ctx: PipelineContext) -> Mapping[str, Any]:
            return {"computed": True}

        dag.register(FeatureNode(name="feature1", compute=compute_fn))
        return dag

    @pytest.fixture
    def train_fn(self):
        """Create a simple training function."""

        def _train(
            ctx: PipelineContext, params: Mapping[str, Any]
        ) -> tuple[Any, Mapping[str, float]]:
            return "trained_model", {"accuracy": 0.9}

        return _train

    def test_ml_pipeline_creation(self, simple_dag: FeatureEngineeringDAG, train_fn) -> None:
        """Verify MLPipeline can be created."""
        pipeline = MLPipeline(simple_dag, train_fn)
        assert pipeline._feature_dag is simple_dag
        assert pipeline._train_fn is train_fn

    def test_ml_pipeline_run_basic(self, simple_dag: FeatureEngineeringDAG, train_fn) -> None:
        """Verify MLPipeline run completes."""
        pipeline = MLPipeline(simple_dag, train_fn)
        ctx = PipelineContext(training_frame="data")

        result = pipeline.run(ctx)

        assert result.model == "trained_model"
        assert result.metrics["accuracy"] == 0.9

    def test_ml_pipeline_run_with_tuner(self, simple_dag: FeatureEngineeringDAG, train_fn) -> None:
        """Verify MLPipeline run with tuner."""

        def objective(params: Mapping[str, Any]) -> float:
            return 0.9

        def search_space(trial) -> Mapping[str, Any]:
            return {"lr": trial.suggest_float("lr", 0.001, 0.1)}

        tuner = OptunaTuner(objective=objective, n_trials=2)
        pipeline = MLPipeline(simple_dag, train_fn, tuner=tuner)
        ctx = PipelineContext(training_frame="data")

        result = pipeline.run(ctx, search_space=search_space)

        assert result.model == "trained_model"

    def test_ml_pipeline_run_with_drift_detection(self, simple_dag: FeatureEngineeringDAG) -> None:
        """Verify MLPipeline run with drift detection."""

        def train_fn_with_drift(
            ctx: PipelineContext, params: Mapping[str, Any]
        ) -> tuple[Any, Mapping[str, float]]:
            return "model", {"sharpe": 1.5}

        detector = ModelDriftDetector(threshold=0.5)
        pipeline = MLPipeline(simple_dag, train_fn_with_drift, drift_detector=detector)

        ctx = PipelineContext(
            training_frame="data",
            params={
                "baseline_scores": list(range(50)),
                "observed_scores": list(range(50)),
            },
        )

        result = pipeline.run(ctx)

        assert "drift_psi" in result.metrics
        assert "drift_alert" in result.metrics

    def test_ml_pipeline_run_with_ab_tester(self, simple_dag: FeatureEngineeringDAG) -> None:
        """Verify MLPipeline run with A/B tester."""

        def train_fn_for_ab(
            ctx: PipelineContext, params: Mapping[str, Any]
        ) -> tuple[Any, Mapping[str, float]]:
            return "model", {"sharpe": 1.5}

        ab_tester = ABTestManager()
        pipeline = MLPipeline(simple_dag, train_fn_for_ab, ab_tester=ab_tester)

        ctx = PipelineContext(
            training_frame="data",
            params={"ab_variant": "treatment"},
        )

        result = pipeline.run(ctx)

        assert "sharpe" in result.metrics
