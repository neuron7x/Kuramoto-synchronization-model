# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pytest

from core.neuro.training import (
    AsyncDataLoader,
    TrainingBatch,
    TrainingComponent,
    TrainingConfig,
    TrainingEngine,
    TrainingSample,
    TrainingStepResult,
)


class QuadraticComponent(TrainingComponent):
    """Minimal differentiable component used for integration tests."""

    def __init__(self, dim: int, *, lr: float = 0.05) -> None:
        self.weights = np.zeros(dim, dtype=np.float32)
        self.lr = float(lr)
        self._grad = np.zeros(dim, dtype=np.float32)
        self.optimizer_steps = 0
        self.forward_calls = 0
        self.batch_dtypes: list[np.dtype] = []
        self.sequence_lengths: list[int] = []

    def forward_backward(self, batch: TrainingBatch, precision) -> TrainingStepResult:
        inputs = np.asarray(batch.inputs, dtype=np.float32)
        targets = np.asarray(batch.targets, dtype=np.float32)
        self._ensure_dim(inputs.shape[-1])
        self.batch_dtypes.append(np.asarray(batch.inputs).dtype)
        self.sequence_lengths.append(inputs.shape[-1])
        preds = inputs @ self.weights
        diff = preds - targets
        loss = float(np.mean(diff**2))
        grad = (inputs.T @ diff) / inputs.shape[0]
        self._grad += grad.astype(np.float32)
        self.forward_calls += 1
        grad_norm = float(np.linalg.norm(self._grad))
        metrics = {"grad_norm": grad_norm}
        # Trigger checkpoint if gradient norm explodes for edge cases.
        should_ckpt = not math.isfinite(grad_norm)
        return TrainingStepResult(loss=loss, metrics=metrics, should_checkpoint=should_ckpt)

    def optimizer_step(self) -> None:
        self.weights -= self.lr * self._grad
        self.optimizer_steps += 1
        self._grad.fill(0.0)

    def zero_grad(self) -> None:
        self._grad.fill(0.0)

    def state_dict(self):
        return {"weights": self.weights.copy()}

    def _ensure_dim(self, dim: int) -> None:
        if self.weights.shape[0] == dim:
            return
        if dim < self.weights.shape[0]:
            self.weights = self.weights[:dim].copy()
            self._grad = self._grad[:dim].copy()
        else:
            pad = np.zeros(dim - self.weights.shape[0], dtype=np.float32)
            self.weights = np.concatenate([self.weights, pad])
            self._grad = np.concatenate([self._grad, np.zeros_like(pad)])


def _build_dataset(samples: int, *, dim: int, noise: float = 0.0) -> list[dict[str, object]]:
    rng = np.random.default_rng(42)
    weight = rng.standard_normal(dim)
    data: list[dict[str, object]] = []
    for _ in range(samples):
        vec = rng.standard_normal(dim)
        target = float(vec @ weight + rng.normal(0.0, noise))
        data.append({"inputs": vec.astype(np.float32), "target": target})
    return data


def test_mixed_precision_batches_are_cast() -> None:
    dataset = _build_dataset(samples=8, dim=6)
    component = QuadraticComponent(dim=6)
    config = TrainingConfig(epochs=1, batch_size=4, mixed_precision=True)
    engine = TrainingEngine(component, config)

    engine.fit(dataset)

    assert component.batch_dtypes, "no batches observed"
    assert set(component.batch_dtypes) == {np.dtype(np.float16)}


def test_gradient_accumulation_limits_optimizer_steps() -> None:
    dataset = _build_dataset(samples=6, dim=4)
    component = QuadraticComponent(dim=4)
    config = TrainingConfig(
        epochs=1,
        batch_size=2,
        gradient_accumulation_steps=3,
    )
    engine = TrainingEngine(component, config)

    summary = engine.fit(dataset)

    assert summary.steps == 3
    assert component.optimizer_steps == 1


def test_sequence_limit_truncates_batches() -> None:
    dataset = _build_dataset(samples=4, dim=10)
    component = QuadraticComponent(dim=10)
    config = TrainingConfig(
        epochs=1,
        batch_size=2,
        max_sequence_length=5,
    )
    engine = TrainingEngine(component, config)

    engine.fit(dataset)

    assert component.sequence_lengths
    assert all(length == 5 for length in component.sequence_lengths)


def test_checkpointing_creates_files(tmp_path: Path) -> None:
    dataset = _build_dataset(samples=6, dim=3)
    component = QuadraticComponent(dim=3)
    config = TrainingConfig(
        epochs=1,
        batch_size=2,
        checkpoint_interval=2,
        checkpoint_directory=tmp_path,
        keep_last_checkpoints=1,
    )
    engine = TrainingEngine(component, config)

    summary = engine.fit(dataset)

    assert summary.checkpoints, "checkpoint list should not be empty"
    files = sorted(tmp_path.glob("*.pkl"))
    assert len(files) == 1


def test_priority_queue_orders_batches() -> None:
    samples = [
        TrainingSample(
            inputs=np.array([priority], dtype=np.float32),
            target=0.0,
            metadata={"priority": priority},
        )
        for priority in (0.1, 0.5, 0.3, 0.9)
    ]
    loader = AsyncDataLoader(
        samples,
        batch_size=1,
        sequence_length=None,
        prefetch_batches=len(samples),
        enable_padding=False,
        priority_key="priority",
        reuse=True,
        cache_dataset=False,
        cache_limit=None,
    )

    batches = list(loader)
    observed = [float(batch.inputs.squeeze()) for batch in batches]
    assert observed[0] == pytest.approx(0.9)


def test_dataset_cache_reuses_source_across_epochs() -> None:
    class CountingDataset:
        def __init__(self, base: Iterable[dict[str, object]]) -> None:
            self.base = list(base)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            yield from self.base

    dataset = CountingDataset(_build_dataset(samples=6, dim=4))
    component = QuadraticComponent(dim=4)
    config = TrainingConfig(epochs=2, batch_size=3, cache_dataset=True)
    engine = TrainingEngine(component, config)

    engine.fit(dataset)

    assert dataset.iterations == 1


def test_dataloader_reuse_guard() -> None:
    samples = _build_dataset(samples=2, dim=2)
    loader = AsyncDataLoader(
        samples,
        batch_size=1,
        sequence_length=None,
        prefetch_batches=0,
        enable_padding=False,
        priority_key=None,
        reuse=False,
        cache_dataset=False,
        cache_limit=None,
    )

    list(loader)
    with pytest.raises(RuntimeError):
        list(loader)


def test_profiler_records_metrics() -> None:
    dataset = _build_dataset(samples=4, dim=3)
    component = QuadraticComponent(dim=3)
    config = TrainingConfig(epochs=1, batch_size=2)
    engine = TrainingEngine(component, config)

    summary = engine.fit(dataset)

    assert summary.profiling["steps"] == summary.steps
    assert "wall_time_total" in summary.profiling
