from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pytest

from core.neuro.training import TrainingBatch, TrainingComponent, TrainingConfig, TrainingStepResult
from core.neuro.training_scenarios import (
    CostGuardrailConfig,
    DistributedRunConfig,
    DriftMonitorConfig,
    ExperimentConfig,
    GPUAutoscalePolicy,
    RegressionCheckConfig,
    ReportingConfig,
    TestGenerationConfig,
    TrainingScenarioRunner,
    ValidationRule,
    ValidationSuiteConfig,
)
from src.data.experiment_registry import ExperimentRegistry
from observability.drift import FeatureSnapshot


class LinearComponent(TrainingComponent):
    """Lightweight linear regressor for scenario integration tests."""

    def __init__(self, *, lr: float = 0.1) -> None:
        self.weight = np.zeros(1, dtype=np.float32)
        self.bias = 0.0
        self.lr = float(lr)
        self._grad_weight = np.zeros_like(self.weight)
        self._grad_bias = 0.0

    def forward_backward(self, batch: TrainingBatch, precision) -> TrainingStepResult:
        x = np.asarray(batch.inputs, dtype=np.float32).reshape(-1, 1)
        y = np.asarray(batch.targets, dtype=np.float32).reshape(-1, 1)
        preds = x * self.weight + self.bias
        diff = preds - y
        loss = float(np.mean(diff ** 2))
        grad_weight = float((x * diff).mean())
        grad_bias = float(diff.mean())
        self._grad_weight += grad_weight
        self._grad_bias += grad_bias
        metrics = {"mse": loss}
        return TrainingStepResult(loss=loss, metrics=metrics)

    def optimizer_step(self) -> None:
        self.weight -= self.lr * self._grad_weight
        self.bias -= self.lr * self._grad_bias
        self._grad_weight = np.zeros_like(self._grad_weight)
        self._grad_bias = 0.0

    def zero_grad(self) -> None:
        self._grad_weight = np.zeros_like(self._grad_weight)
        self._grad_bias = 0.0

    def state_dict(self):
        return {"weight": self.weight.copy(), "bias": float(self.bias)}

    def load_state_dict(self, state):
        if "weight" in state:
            self.weight = np.asarray(state["weight"], dtype=np.float32).copy()
        if "bias" in state:
            self.bias = float(state["bias"])
        self._grad_weight = np.zeros_like(self.weight)
        self._grad_bias = 0.0


def _build_dataset(samples: int = 12) -> list[dict[str, object]]:
    rng = np.random.default_rng(123)
    data: list[dict[str, object]] = []
    for _ in range(samples):
        x = rng.normal()
        noise = rng.normal(scale=0.1)
        y = 2.0 * x + 0.5 + noise
        data.append({"inputs": np.array([x], dtype=np.float32), "target": np.array([y], dtype=np.float32)})
    return data


def _validation_fn(component: LinearComponent, dataset: Iterable[dict[str, object]]) -> dict[str, float]:
    errors = []
    for entry in dataset:
        x = float(entry["inputs"][0])
        y = float(entry["target"][0])
        pred = component.weight[0] * x + component.bias
        errors.append((pred - y) ** 2)
    return {"mse": float(np.mean(errors))}


@pytest.mark.parametrize("resume", [False, True])
def test_training_scenario_runs_end_to_end(tmp_path: Path, resume: bool) -> None:
    dataset = _build_dataset()
    validation_dataset = list(dataset)
    registry = ExperimentRegistry(tmp_path / "registry")

    training_config = TrainingConfig(
        epochs=1,
        batch_size=4,
        checkpoint_interval=2,
        checkpoint_directory=tmp_path / "checkpoints",
        mixed_precision=True,
        gradient_accumulation_steps=2,
    )

    experiment_config = ExperimentConfig(
        experiment_name="linear-demo",
        training=training_config,
        workspace=tmp_path / "workspace",
        seed=42,
        hyperparameters={"lr": 0.1},
        distributed=DistributedRunConfig(enabled=False),
        gpu_autoscale=GPUAutoscalePolicy(enabled=True, min_workers=1, max_workers=2),
        cost_guardrail=CostGuardrailConfig(enabled=True, limit=5.0, period_hours=1.0, cost_per_gpu_hour=0.1),
        reporting=ReportingConfig(enable_markdown=True, enable_dashboard=True),
        test_generation=TestGenerationConfig(enable=True, output_dir=tmp_path / "generated_tests"),
        drift=DriftMonitorConfig(enabled=True),
        validations=ValidationSuiteConfig(rules=(ValidationRule(metric="mse", upper=5.0),)),
        regressions=(RegressionCheckConfig(metric="val_mse", tolerance=1.0, direction="min"),),
        resume=resume,
    )

    component = LinearComponent()
    runner = TrainingScenarioRunner(component, experiment_config, registry)
    drift_snapshot = FeatureSnapshot(
        name="feature_x",
        reference=[float(entry["inputs"][0]) for entry in dataset[:10]],
        current=[float(entry["inputs"][0]) for entry in dataset[2:12]],
    )

    result = runner.run(
        dataset,
        validation_dataset=validation_dataset,
        validation_fn=_validation_fn,
        drift_snapshots=[drift_snapshot],
    )

    summary_data = json.loads(result.artifacts.summary_path.read_text(encoding="utf-8"))
    assert summary_data["experiment"]["run_id"] == result.run_record.run_id
    assert result.validations[0].metric == "mse"
    assert result.autoscale_plan is not None
    assert result.cost_report is not None
    assert result.unit_test_explanation is not None

    if resume:
        # Ensure checkpoint resume metadata captured
        assert result.summary.start_epoch >= 0

    assert result.artifacts.test_path is not None
    generated_test = result.artifacts.test_path.read_text(encoding="utf-8")
    assert result.run_record.run_id in generated_test

    runs = registry.list_runs("linear-demo")
    assert runs
