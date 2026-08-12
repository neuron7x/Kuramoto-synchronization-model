# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.neuro.training module."""

from __future__ import annotations

import pickle

import numpy as np
import pytest

try:
    from core.neuro.training import (
        CheckpointManager,
        MixedPrecisionContext,
        TrainingBatch,
        TrainingComponent,
        TrainingConfig,
        TrainingEngine,
        TrainingProfiler,
        TrainingSample,
        TrainingStepResult,
        _determine_precision_dtype,
        _normalise_sample,
    )
except ImportError:
    pytest.skip("core.neuro.training not importable", allow_module_level=True)


class TestTrainingSample:
    def test_create(self):
        s = TrainingSample(inputs=np.zeros(3), target=1)
        assert s.priority is None
        assert isinstance(s.metadata, dict)

    def test_metadata_defaults_empty(self):
        s = TrainingSample(inputs=0, target=0)
        assert s.metadata == {}


class TestTrainingBatch:
    def test_cast_noop_when_none(self):
        b = TrainingBatch(inputs=np.array([1.0, 2.0]), targets=np.array([3.0]))
        same = b.cast(None)
        assert same is b

    def test_cast_float16(self):
        b = TrainingBatch(
            inputs=np.array([1.0, 2.0], dtype=np.float64),
            targets=np.array([3.0], dtype=np.float64),
        )
        casted = b.cast(np.float16)
        assert casted.inputs.dtype == np.float16
        assert casted.targets.dtype == np.float16

    def test_cast_preserves_int(self):
        b = TrainingBatch(inputs=np.array([1, 2], dtype=np.int32), targets=np.array([3]))
        casted = b.cast(np.float16)
        assert casted.inputs.dtype == np.int32


class TestTrainingConfig:
    def test_default_creation(self):
        cfg = TrainingConfig()
        assert cfg.epochs == 1
        assert cfg.batch_size == 32

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("epochs", 0),
            ("epochs", -1),
            ("batch_size", 0),
            ("gradient_accumulation_steps", 0),
            ("keep_last_checkpoints", 0),
            ("prefetch_batches", -1),
        ],
    )
    def test_invalid_values_raise(self, field, bad_value):
        with pytest.raises(ValueError):
            TrainingConfig(**{field: bad_value})

    def test_invalid_limit_batches(self):
        with pytest.raises(ValueError):
            TrainingConfig(limit_batches=0)

    def test_invalid_precision_dtype(self):
        with pytest.raises(ValueError, match="mixed_precision_dtype"):
            TrainingConfig(mixed_precision_dtype="int8")

    def test_valid_bfloat16(self):
        cfg = TrainingConfig(mixed_precision_dtype="bfloat16")
        assert cfg.mixed_precision_dtype == "bfloat16"


class TestMixedPrecisionContext:
    def test_cast_disabled(self):
        ctx = MixedPrecisionContext(enabled=False, target_dtype=None, loss_scale=1.0)
        arr = np.array([1.0, 2.0])
        assert ctx.cast(arr) is arr

    def test_cast_enabled(self):
        ctx = MixedPrecisionContext(enabled=True, target_dtype=np.float16, loss_scale=1024.0)
        arr = np.array([1.0, 2.0], dtype=np.float64)
        result = ctx.cast(arr)
        assert result.dtype == np.float16

    def test_cast_int_unchanged(self):
        ctx = MixedPrecisionContext(enabled=True, target_dtype=np.float16, loss_scale=1024.0)
        arr = np.array([1, 2], dtype=np.int32)
        result = ctx.cast(arr)
        assert result.dtype == np.int32


class TestTrainingProfiler:
    def test_empty_report(self):
        p = TrainingProfiler(profile_memory=False, profile_compute=False, profile_io=False)
        assert p.report() == {"steps": 0}

    def test_measure_step(self):
        p = TrainingProfiler(profile_memory=False, profile_compute=True, profile_io=True)
        with p.measure_step(1, io_time=0.01):
            pass
        report = p.report()
        assert report["steps"] == 1
        assert report["wall_time_total"] is not None


class TestNormaliseSample:
    def test_from_training_sample(self):
        s = TrainingSample(inputs=1, target=2)
        result = _normalise_sample(s)
        assert result.inputs == 1 and result.target == 2

    def test_from_dict_inputs_target(self):
        result = _normalise_sample({"inputs": "x", "target": "y"})
        assert result.inputs == "x" and result.target == "y"

    def test_from_dict_input_label(self):
        result = _normalise_sample({"input": "a", "label": "b"})
        assert result.inputs == "a" and result.target == "b"

    def test_from_tuple_pair(self):
        result = _normalise_sample(("in", "out"))
        assert result.inputs == "in" and result.target == "out"

    def test_from_tuple_triple(self):
        result = _normalise_sample(("in", "out", {"k": "v"}))
        assert result.metadata == {"k": "v"}

    def test_unsupported_raises(self):
        with pytest.raises(TypeError):
            _normalise_sample(42)

    def test_bad_dict_raises(self):
        with pytest.raises(ValueError, match="inputs"):
            _normalise_sample({"foo": "bar"})


class TestCheckpointManager:
    def test_save_and_index(self, tmp_path):
        mgr = CheckpointManager(tmp_path / "ckpt", keep_last=2)
        p1 = mgr.save(step=1, epoch=0, state_dict={"w": 1}, metrics={"loss": 0.5})
        assert p1.exists()
        p2 = mgr.save(step=2, epoch=0, state_dict={"w": 2}, metrics={"loss": 0.3})
        p3 = mgr.save(step=3, epoch=0, state_dict={"w": 3}, metrics={"loss": 0.1})
        assert p3.exists()
        assert p2.exists()
        assert not p1.exists()

    def test_checkpoint_content(self, tmp_path):
        mgr = CheckpointManager(tmp_path / "ckpt2", keep_last=3)
        p = mgr.save(step=5, epoch=1, state_dict={"val": 42}, metrics={"acc": 0.9})
        with open(p, "rb") as f:
            data = pickle.load(f)
        assert data["step"] == 5
        assert data["state"]["val"] == 42


class TestDeterminePrecisionDtype:
    def test_disabled(self):
        cfg = TrainingConfig(mixed_precision=False)
        assert _determine_precision_dtype(cfg) is None

    def test_float16(self):
        cfg = TrainingConfig(mixed_precision=True, mixed_precision_dtype="float16")
        assert _determine_precision_dtype(cfg) == np.float16


class _DummyComponent(TrainingComponent):
    def __init__(self):
        self._step_count = 0
        self._zero_grad_count = 0
        self._optim_count = 0

    def forward_backward(self, batch, precision):
        self._step_count += 1
        return TrainingStepResult(loss=0.5 - self._step_count * 0.01)

    def optimizer_step(self):
        self._optim_count += 1

    def zero_grad(self):
        self._zero_grad_count += 1

    def state_dict(self):
        return {"step": self._step_count}


class TestTrainingEngine:
    def test_fit_basic(self):
        comp = _DummyComponent()
        cfg = TrainingConfig(
            epochs=1,
            batch_size=2,
            profile_memory=False,
            cache_dataset=False,
            prefetch_batches=0,
            reuse_dataloader=False,
        )
        engine = TrainingEngine(comp, cfg)
        dataset = [TrainingSample(inputs=np.zeros(4), target=0) for _ in range(6)]
        summary = engine.fit(dataset)
        assert summary.epochs_completed == 1
        assert summary.steps == 3
        assert len(summary.loss_history) == 3

    def test_fit_with_checkpoint(self, tmp_path):
        comp = _DummyComponent()
        cfg = TrainingConfig(
            epochs=1,
            batch_size=1,
            checkpoint_interval=2,
            checkpoint_directory=tmp_path / "ckpt",
            profile_memory=False,
            cache_dataset=False,
            prefetch_batches=0,
            reuse_dataloader=False,
        )
        engine = TrainingEngine(comp, cfg)
        dataset = [TrainingSample(inputs=np.zeros(2), target=0) for _ in range(4)]
        summary = engine.fit(dataset)
        assert len(summary.checkpoints) >= 1

    def test_fit_gradient_accumulation(self):
        comp = _DummyComponent()
        cfg = TrainingConfig(
            epochs=1,
            batch_size=1,
            gradient_accumulation_steps=2,
            profile_memory=False,
            cache_dataset=False,
            prefetch_batches=0,
            reuse_dataloader=False,
        )
        engine = TrainingEngine(comp, cfg)
        dataset = [TrainingSample(inputs=np.zeros(2), target=0) for _ in range(4)]
        engine.fit(dataset)
        assert comp._optim_count == 2
