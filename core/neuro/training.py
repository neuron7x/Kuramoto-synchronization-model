# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High-efficiency training utilities for GeoSync models.

This module implements a flexible training loop that focuses on
performance-sensitive workloads.  The design goals were:

* **Deterministic behaviour** – explicit state management and pure-Python
  defaults make the implementation easy to reason about and test.
* **Battle-tested techniques** – gradient accumulation, mixed precision,
  asynchronous prefetch, caching, and checkpointing mirror patterns used in
  modern large-scale training setups.
* **Observability** – fine-grained profiling exposes memory, compute and I/O
  metrics so that bottlenecks are visible to orchestration layers.

The resulting components are framework-agnostic.  A caller only needs to supply
`TrainingComponent` callbacks that know how to perform a single
forward/backward/step cycle for their specific model.
"""

from __future__ import annotations

import contextlib
import copy
import json
import math
import os
import pickle
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, MutableMapping, Sequence

import numpy as np

__all__ = [
    "TrainingSample",
    "TrainingBatch",
    "TrainingStepResult",
    "TrainingConfig",
    "TrainingProfiler",
    "ProfileSnapshot",
    "MixedPrecisionContext",
    "TrainingComponent",
    "AsyncDataLoader",
    "CheckpointManager",
    "TrainingEngine",
    "TrainingSummary",
]


# ---------------------------------------------------------------------------
# Helper data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TrainingSample:
    """A single training example produced by a dataset iterator."""

    inputs: Any
    target: Any
    metadata: MutableMapping[str, Any] = field(default_factory=dict)
    priority: float | None = None


@dataclass(slots=True)
class TrainingBatch:
    """Mini-batch wrapper delivered to the training component."""

    inputs: Any
    targets: Any
    metadata: MutableMapping[str, Any] = field(default_factory=dict)

    def cast(self, dtype: np.dtype | None) -> "TrainingBatch":
        """Return a batch where floating point arrays adopt ``dtype``."""

        if dtype is None:
            return self

        def _cast(value: Any) -> Any:
            if isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.floating):
                return value.astype(dtype)
            if isinstance(value, (list, tuple)):
                array = np.asarray(value)
                if np.issubdtype(array.dtype, np.floating):
                    return array.astype(dtype)
            return value

        inputs = _cast(self.inputs)
        targets = _cast(self.targets)
        metadata: MutableMapping[str, Any] = copy.copy(self.metadata)
        return TrainingBatch(inputs=inputs, targets=targets, metadata=metadata)


@dataclass(slots=True)
class TrainingStepResult:
    """Outcome of a single optimisation step."""

    loss: float
    metrics: Mapping[str, float] = field(default_factory=dict)
    should_checkpoint: bool = False


@dataclass(slots=True)
class TrainingConfig:
    """Configuration parameters governing the training loop."""

    epochs: int = 1
    batch_size: int = 32
    gradient_accumulation_steps: int = 1
    mixed_precision: bool = False
    mixed_precision_dtype: str = "float16"
    loss_scale: float = 1024.0
    max_sequence_length: int | None = None
    checkpoint_interval: int | None = None
    checkpoint_directory: Path | str | None = None
    keep_last_checkpoints: int = 2
    limit_batches: int | None = None
    prefetch_batches: int = 2
    cache_dataset: bool = True
    cache_limit: int | None = None
    reuse_dataloader: bool = True
    enable_padding: bool = False
    priority_key: str | Callable[[TrainingSample], float] | None = "priority"
    profile_memory: bool = True
    profile_compute: bool = True
    profile_io: bool = True

    def __post_init__(self) -> None:
        if self.epochs <= 0:
            raise ValueError("epochs must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.gradient_accumulation_steps <= 0:
            raise ValueError("gradient_accumulation_steps must be positive")
        if self.keep_last_checkpoints <= 0:
            raise ValueError("keep_last_checkpoints must be positive")
        if self.prefetch_batches < 0:
            raise ValueError("prefetch_batches must be non-negative")
        if self.limit_batches is not None and self.limit_batches <= 0:
            raise ValueError("limit_batches must be positive when provided")
        if self.max_sequence_length is not None and self.max_sequence_length <= 0:
            raise ValueError("max_sequence_length must be positive when provided")
        if self.checkpoint_interval is not None and self.checkpoint_interval <= 0:
            raise ValueError("checkpoint_interval must be positive when provided")
        if self.mixed_precision_dtype not in {"float16", "bfloat16"}:
            raise ValueError("mixed_precision_dtype must be 'float16' or 'bfloat16'")


# ---------------------------------------------------------------------------
# Precision helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MixedPrecisionContext:
    """Information exposed to callers when mixed precision is active."""

    enabled: bool
    target_dtype: np.dtype | None
    loss_scale: float

    def cast(self, array: np.ndarray) -> np.ndarray:
        if not self.enabled or self.target_dtype is None:
            return array
        if not np.issubdtype(array.dtype, np.floating):
            return array
        return array.astype(self.target_dtype)


def _determine_precision_dtype(config: TrainingConfig) -> np.dtype | None:
    if not config.mixed_precision:
        return None
    if config.mixed_precision_dtype == "float16":
        return np.float16
    if hasattr(np, "bfloat16"):
        return np.dtype(getattr(np, "bfloat16"))
    return np.float32


# ---------------------------------------------------------------------------
# Profiling utilities
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProfileSnapshot:
    """Metrics captured for a single optimisation step."""

    step: int
    wall_time: float
    memory_peak_bytes: int | None
    io_time: float


class TrainingProfiler:
    """Collect fine-grained metrics for each training step."""

    def __init__(
        self,
        *,
        profile_memory: bool,
        profile_compute: bool,
        profile_io: bool,
    ) -> None:
        self._profile_memory = profile_memory
        self._profile_compute = profile_compute
        self._profile_io = profile_io
        self._snapshots: list[ProfileSnapshot] = []

    @contextlib.contextmanager
    def measure_step(self, step: int, *, io_time: float = 0.0) -> Iterator[None]:
        wall_start = time.perf_counter() if self._profile_compute else None
        if self._profile_memory:
            import tracemalloc

            tracemalloc.start()
        try:
            yield
        finally:
            wall_time = (
                (time.perf_counter() - wall_start) if wall_start is not None else float("nan")
            )
            memory_peak: int | None = None
            if self._profile_memory:
                import tracemalloc

                current, peak = tracemalloc.get_traced_memory()
                memory_peak = max(int(current), int(peak))
                tracemalloc.stop()
            recorded_io = float(io_time if self._profile_io else 0.0)
            self._snapshots.append(
                ProfileSnapshot(
                    step=step,
                    wall_time=wall_time,
                    memory_peak_bytes=memory_peak,
                    io_time=recorded_io,
                )
            )

    def report(self) -> dict[str, Any]:
        if not self._snapshots:
            return {"steps": 0}

        wall_times = [snap.wall_time for snap in self._snapshots if not math.isnan(snap.wall_time)]
        memory_peaks = [
            snap.memory_peak_bytes for snap in self._snapshots if snap.memory_peak_bytes
        ]
        io_times = [snap.io_time for snap in self._snapshots]

        return {
            "steps": len(self._snapshots),
            "wall_time_total": float(sum(wall_times)) if wall_times else None,
            "wall_time_avg": (float(sum(wall_times) / len(wall_times)) if wall_times else None),
            "memory_peak_max": int(max(memory_peaks)) if memory_peaks else None,
            "io_time_total": float(sum(io_times)) if self._profile_io else None,
        }


# ---------------------------------------------------------------------------
# Dataset management
# ---------------------------------------------------------------------------


def _clone_sample(sample: TrainingSample) -> TrainingSample:
    return TrainingSample(
        inputs=copy.deepcopy(sample.inputs),
        target=copy.deepcopy(sample.target),
        metadata=copy.deepcopy(sample.metadata),
        priority=sample.priority,
    )


def _normalise_sample(item: Any) -> TrainingSample:
    if isinstance(item, TrainingSample):
        return _clone_sample(item)

    if isinstance(item, Mapping):
        metadata = dict(item.get("metadata", {}))
        priority = item.get("priority")
        if "inputs" in item and "target" in item:
            return TrainingSample(
                inputs=item["inputs"],
                target=item["target"],
                metadata=metadata,
                priority=priority,
            )
        if "input" in item and "label" in item:
            return TrainingSample(
                inputs=item["input"],
                target=item["label"],
                metadata=metadata,
                priority=priority,
            )
        raise ValueError("Mapping sample must contain 'inputs'/'target' keys")

    if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
        if len(item) == 2:
            data, target = item
            return TrainingSample(inputs=data, target=target)
        if len(item) == 3:
            data, target, metadata = item
            if not isinstance(metadata, MutableMapping):
                metadata = dict(metadata)
            return TrainingSample(inputs=data, target=target, metadata=metadata)

    raise TypeError("Unsupported sample format")


def _limit_sequence_length(value: Any, *, max_length: int, enable_padding: bool) -> Any:
    if max_length <= 0:
        return value

    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value
        sliced = value[..., :max_length]
        if enable_padding and sliced.shape[-1] < max_length:
            pad_width = [(0, 0)] * value.ndim
            pad_width[-1] = (0, max_length - sliced.shape[-1])
            return np.pad(sliced, pad_width, mode="constant")
        return sliced

    if isinstance(value, (list, tuple)):
        truncated = list(value)[:max_length]
        if enable_padding and len(truncated) < max_length:
            padded = truncated + [0] * (max_length - len(truncated))
            return np.asarray(padded)
        return truncated

    return value


class _MaterialisedDataset:
    """Materialise streaming datasets when caching is enabled."""

    def __init__(
        self,
        dataset: Iterable[Any],
        *,
        cache: bool,
        cache_limit: int | None,
    ) -> None:
        self._dataset = dataset
        self._cache_enabled = cache
        self._cache_limit = cache_limit
        self._cache: list[TrainingSample] | None = None
        self._cache_complete: bool | None = None
        self._lock = threading.Lock()

    def __iter__(self) -> Iterator[TrainingSample]:
        with self._lock:
            cache = self._cache
            cache_complete = self._cache_complete
        if cache is not None:
            for sample in cache:
                yield _clone_sample(sample)
            # Stream any remaining samples beyond the cached prefix.
            if self._cache_enabled and not cache_complete:
                skip = len(cache)
                for index, item in enumerate(self._dataset):
                    if index < skip:
                        continue
                    yield _normalise_sample(item)
            return

        produced: list[TrainingSample] = [] if self._cache_enabled else []
        cache_complete = True
        count = 0
        for item in self._dataset:
            sample = _normalise_sample(item)
            if self._cache_enabled and (self._cache_limit is None or count < self._cache_limit):
                produced.append(_clone_sample(sample))
                count += 1
            elif self._cache_enabled:
                cache_complete = False
            yield sample

        if self._cache_enabled:
            with self._lock:
                if self._cache is None:
                    self._cache = produced
                    self._cache_complete = cache_complete


class AsyncDataLoader:
    """Asynchronous mini-batch loader with priority-aware prefetch."""

    def __init__(
        self,
        dataset: Iterable[Any],
        *,
        batch_size: int,
        sequence_length: int | None,
        prefetch_batches: int,
        enable_padding: bool,
        priority_key: str | Callable[[TrainingSample], float] | None,
        reuse: bool,
        cache_dataset: bool,
        cache_limit: int | None,
    ) -> None:
        self._dataset = _MaterialisedDataset(
            dataset,
            cache=cache_dataset,
            cache_limit=cache_limit,
        )
        self._batch_size = batch_size
        self._sequence_length = sequence_length
        self._prefetch_batches = max(0, prefetch_batches)
        self._enable_padding = enable_padding
        self._priority_key = priority_key
        self._reuse = reuse
        self._consumed = False
        self._lock = threading.Lock()

    def __iter__(self) -> Iterator[TrainingBatch]:
        with self._lock:
            if self._consumed and not self._reuse:
                raise RuntimeError("DataLoader marked as one-shot and cannot be reused")
            self._consumed = True

        if self._priority_key is None:
            queue_cls: type[queue.Queue] = queue.Queue
        else:
            queue_cls = queue.PriorityQueue

        max_queue_items = self._prefetch_batches * max(1, self._batch_size)
        batch_queue: queue.Queue[Any] = queue_cls(maxsize=max_queue_items or 0)
        stop_token = object()
        counter = 0
        io_time_accumulator = 0.0
        last_io_time = 0.0
        io_lock = threading.Lock()

        def _priority(sample: TrainingSample) -> float:
            if callable(self._priority_key):
                return float(self._priority_key(sample))
            if isinstance(self._priority_key, str):
                if self._priority_key in sample.metadata:
                    return float(sample.metadata[self._priority_key])
            if sample.priority is not None:
                return float(sample.priority)
            return 0.0

        def _worker() -> None:
            nonlocal counter
            start_time = time.perf_counter()
            for item in self._dataset:
                sample = item
                if self._sequence_length is not None:
                    sample.inputs = _limit_sequence_length(
                        sample.inputs,
                        max_length=self._sequence_length,
                        enable_padding=self._enable_padding,
                    )
                if (
                    isinstance(sample.target, (np.ndarray, list, tuple))
                    and self._sequence_length is not None
                ):
                    sample.target = _limit_sequence_length(
                        sample.target,
                        max_length=self._sequence_length,
                        enable_padding=self._enable_padding,
                    )
                elapsed = time.perf_counter() - start_time
                with io_lock:
                    nonlocal io_time_accumulator
                    io_time_accumulator += elapsed
                if isinstance(batch_queue, queue.PriorityQueue):
                    batch_queue.put((-_priority(sample), counter, sample))
                else:
                    batch_queue.put(sample)
                counter += 1
                start_time = time.perf_counter()
            if isinstance(batch_queue, queue.PriorityQueue):
                batch_queue.put((math.inf, math.inf, stop_token))
            else:
                batch_queue.put(stop_token)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        batch_buffer: list[TrainingSample] = []
        while True:
            item = batch_queue.get()
            if isinstance(batch_queue, queue.PriorityQueue):
                _, _, item = item
                if item is stop_token:
                    break
            elif item is stop_token:
                break
            batch_buffer.append(item)
            if len(batch_buffer) >= self._batch_size:
                with io_lock:
                    batch_io = io_time_accumulator - last_io_time
                    last_io_time = io_time_accumulator
                yield self._collate_batch(batch_buffer, batch_io)
                batch_buffer = []
        if batch_buffer:
            with io_lock:
                batch_io = io_time_accumulator - last_io_time
                last_io_time = io_time_accumulator
            yield self._collate_batch(batch_buffer, batch_io)
        thread.join()

    def _collate_batch(
        self,
        samples: Sequence[TrainingSample],
        io_time: float,
    ) -> TrainingBatch:
        inputs = [sample.inputs for sample in samples]
        targets = [sample.target for sample in samples]

        def _stack(items: Sequence[Any]) -> Any:
            if not items:
                return items
            first = items[0]
            if isinstance(first, np.ndarray):
                return np.stack([np.asarray(item) for item in items])
            if isinstance(first, (list, tuple)):
                return np.stack([np.asarray(item) for item in items])
            return list(items)

        batch_inputs = _stack(inputs)
        batch_targets = _stack(targets)
        metadata: dict[str, Any] = {"io_time": io_time, "size": len(samples)}
        return TrainingBatch(inputs=batch_inputs, targets=batch_targets, metadata=metadata)


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------


class CheckpointManager:
    """Persist and manage rolling training checkpoints."""

    def __init__(self, directory: Path | str, *, keep_last: int) -> None:
        self._directory = Path(directory).expanduser().resolve()
        self._directory.mkdir(parents=True, exist_ok=True)
        self._keep_last = keep_last
        self._index_path = self._directory / "checkpoints.json"
        self._lock = threading.Lock()
        if not self._index_path.exists():
            self._index_path.write_text(json.dumps({"checkpoints": []}), encoding="utf-8")

    def _load_index(self) -> list[str]:
        payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        checkpoints = payload.get("checkpoints", [])
        return [str(entry) for entry in checkpoints]

    def _store_index(self, entries: Sequence[str]) -> None:
        payload = json.dumps({"checkpoints": list(entries)}, indent=2)
        tmp_path = self._index_path.with_suffix(".tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self._index_path)

    def save(
        self,
        *,
        step: int,
        epoch: int,
        state_dict: Mapping[str, Any],
        metrics: Mapping[str, float],
    ) -> Path:
        timestamp = time.time()
        checkpoint_name = f"step{step:08d}-epoch{epoch:04d}-{int(timestamp)}.pkl"
        checkpoint_path = self._directory / checkpoint_name
        payload = {
            "step": step,
            "epoch": epoch,
            "timestamp": timestamp,
            "state": state_dict,
            "metrics": dict(metrics),
        }
        tmp_path = checkpoint_path.with_suffix(".tmp")
        with tmp_path.open("wb") as handle:
            pickle.dump(payload, handle)
        os.replace(tmp_path, checkpoint_path)

        with self._lock:
            entries = self._load_index()
            entries.append(checkpoint_path.name)
            if len(entries) > self._keep_last:
                for obsolete in entries[: -self._keep_last]:
                    obsolete_path = self._directory / obsolete
                    if obsolete_path.exists():
                        obsolete_path.unlink()
                entries = entries[-self._keep_last :]
            self._store_index(entries)

        return checkpoint_path


# ---------------------------------------------------------------------------
# Training engine
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TrainingSummary:
    """Aggregated outcome of a training run."""

    epochs_completed: int
    steps: int
    loss_history: list[float]
    metrics_history: list[Mapping[str, float]]
    profiling: Mapping[str, Any]
    checkpoints: list[Path]


class TrainingComponent:
    """Behaviour required from models trained with :class:`TrainingEngine`."""

    def forward_backward(
        self,
        batch: TrainingBatch,
        precision: MixedPrecisionContext,
    ) -> TrainingStepResult:  # pragma: no cover - interface
        raise NotImplementedError

    def optimizer_step(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def zero_grad(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def state_dict(self) -> Mapping[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


class TrainingEngine:
    """Coordinate high-efficiency training with rich instrumentation."""

    def __init__(
        self,
        component: TrainingComponent,
        config: TrainingConfig,
    ) -> None:
        self._component = component
        self._config = config
        self._precision = MixedPrecisionContext(
            enabled=config.mixed_precision,
            target_dtype=_determine_precision_dtype(config),
            loss_scale=float(config.loss_scale),
        )
        self._profiler = TrainingProfiler(
            profile_memory=config.profile_memory,
            profile_compute=config.profile_compute,
            profile_io=config.profile_io,
        )
        self._checkpoint_manager: CheckpointManager | None = None
        if config.checkpoint_directory is not None:
            self._checkpoint_manager = CheckpointManager(
                config.checkpoint_directory,
                keep_last=config.keep_last_checkpoints,
            )

    def _build_loader(self, dataset: Iterable[Any]) -> AsyncDataLoader:
        return AsyncDataLoader(
            dataset,
            batch_size=self._config.batch_size,
            sequence_length=self._config.max_sequence_length,
            prefetch_batches=self._config.prefetch_batches,
            enable_padding=self._config.enable_padding,
            priority_key=self._config.priority_key,
            reuse=self._config.reuse_dataloader,
            cache_dataset=self._config.cache_dataset,
            cache_limit=self._config.cache_limit,
        )

    def fit(self, dataset: Iterable[Any]) -> TrainingSummary:
        config = self._config
        loader = self._build_loader(dataset)
        grad_accum = int(config.gradient_accumulation_steps)
        loss_history: list[float] = []
        metrics_history: list[Mapping[str, float]] = []
        checkpoints: list[Path] = []

        global_step = 0
        for epoch in range(config.epochs):
            self._component.zero_grad()
            batch_in_epoch = 0
            for batch in loader:
                if config.limit_batches is not None and batch_in_epoch >= config.limit_batches:
                    break
                global_step += 1
                batch_in_epoch += 1
                cast_batch = batch.cast(self._precision.target_dtype)
                with self._profiler.measure_step(
                    global_step,
                    io_time=float(batch.metadata.get("io_time", 0.0)),
                ):
                    result = self._component.forward_backward(cast_batch, self._precision)
                loss_history.append(float(result.loss))
                metrics_history.append(dict(result.metrics))

                if global_step % grad_accum == 0:
                    self._component.optimizer_step()
                    self._component.zero_grad()

                should_ckpt = False
                if config.checkpoint_interval is not None:
                    if global_step % config.checkpoint_interval == 0:
                        should_ckpt = True
                if result.should_checkpoint:
                    should_ckpt = True
                if should_ckpt and self._checkpoint_manager is not None:
                    checkpoint = self._checkpoint_manager.save(
                        step=global_step,
                        epoch=epoch,
                        state_dict=self._component.state_dict(),
                        metrics=result.metrics,
                    )
                    checkpoints.append(checkpoint)

            if batch_in_epoch % grad_accum != 0:
                self._component.optimizer_step()
                self._component.zero_grad()

        summary = TrainingSummary(
            epochs_completed=config.epochs,
            steps=global_step,
            loss_history=loss_history,
            metrics_history=metrics_history,
            profiling=self._profiler.report(),
            checkpoints=checkpoints,
        )
        return summary
