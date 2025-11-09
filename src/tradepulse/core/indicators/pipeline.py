# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""High-performance indicator pipeline orchestration utilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Literal
from weakref import finalize as _finalize

import numpy as np

from ..utils.memory import ArrayPool
from .base import BaseFeature, FeatureResult


@dataclass(slots=True)
class PipelineResult:
    """Container with both feature values and the shared input buffer."""

    values: Mapping[str, Any]
    buffer: np.ndarray
    _cleanup: Callable[[], None] | None = field(default=None, repr=False)
    _finalizer: Any | None = field(default=None, repr=False)

    def release(self) -> None:
        """Return the buffer to the originating pool (idempotent)."""

        if self._cleanup is not None:
            cleanup = self._cleanup
            self._cleanup = None
            if self._finalizer is not None:
                self._finalizer.detach()
                self._finalizer = None
            cleanup()

    def __del__(self) -> None:  # pragma: no cover - best-effort safety net
        self.release()


class IndicatorPipeline:
    """Execute a sequence of indicators using a shared float32 buffer."""

    def __init__(
        self,
        features: Sequence[BaseFeature],
        *,
        dtype: np.dtype | str = np.float32,
        pool: ArrayPool | None = None,
        execution: Literal["sequential", "thread", "process"] = "sequential",
        max_workers: int | None = None,
        executor: Executor | None = None,
        warm_start: bool = True,
    ) -> None:
        if not features:
            raise ValueError("IndicatorPipeline requires at least one feature")
        self._features = tuple(features)
        self._dtype = np.dtype(dtype)
        self._pool = pool or ArrayPool(self._dtype)
        if execution not in {"sequential", "thread", "process"}:
            raise ValueError(f"Unsupported execution mode '{execution}'")
        if execution == "sequential" and executor is not None:
            raise ValueError("Custom executor is only valid for parallel execution")
        self._execution = execution
        self._max_workers = max_workers
        self._executor: Executor | None = executor
        self._owns_executor = executor is None and execution != "sequential"
        self._warm_start = warm_start and execution != "sequential"
        self._prewarmed = False
        if self._owns_executor and self._execution != "sequential":
            self._executor = self._create_executor()
        if self._warm_start:
            self._ensure_executor_ready()

    @property
    def features(self) -> tuple[BaseFeature, ...]:
        return self._features

    def _prepare_buffer(
        self, data: np.ndarray | Sequence[float]
    ) -> tuple[np.ndarray, bool]:
        array = np.asarray(data)
        borrowed = False
        if array.dtype != self._dtype or not array.flags.c_contiguous:
            buffer = self._pool.acquire(array.shape, dtype=self._dtype)
            np.copyto(buffer, array, casting="unsafe")
            array = buffer
            borrowed = True
        return array, borrowed

    def _create_executor(self) -> Executor:
        if self._execution == "thread":
            return ThreadPoolExecutor(
                max_workers=self._max_workers, thread_name_prefix="indicator-pipeline"
            )
        if self._execution == "process":
            return ProcessPoolExecutor(max_workers=self._max_workers)
        raise RuntimeError("Executor requested for sequential pipeline")

    def _ensure_executor_ready(self) -> None:
        if self._execution == "sequential":
            return
        if self._executor is None:
            self._executor = self._create_executor()
            self._owns_executor = True
        if self._warm_start and not self._prewarmed and self._executor is not None:
            future = self._executor.submit(_noop)
            try:
                future.result()
            finally:
                self._prewarmed = True

    def run(self, data: np.ndarray | Sequence[float], **kwargs: Any) -> PipelineResult:
        buffer, borrowed = self._prepare_buffer(data)
        values: dict[str, Any] = {}
        try:
            if self._execution == "sequential":
                for feature in self._features:
                    result = feature.transform(buffer, **kwargs)
                    values[result.name] = result.value
            else:
                self._ensure_executor_ready()
                if self._executor is None:
                    raise RuntimeError("Parallel execution requires an executor")
                tasks: list[Future[FeatureResult]] = []
                for feature in self._features:
                    tasks.append(
                        self._executor.submit(_run_feature, feature, buffer, kwargs)
                    )
                for future in tasks:
                    result = future.result()
                    values[result.name] = result.value
        except Exception:
            if borrowed:
                self._pool.release(buffer)
            raise

        cleanup: Callable[[], None] | None = None
        if borrowed:
            cleanup = partial(self._pool.release, buffer)

        finalizer = None
        if cleanup is not None:
            finalizer = _finalize(buffer, cleanup)

        result = PipelineResult(
            values=values, buffer=buffer, _cleanup=cleanup, _finalizer=finalizer
        )
        return result

    def close(self, *, wait: bool = False) -> None:
        """Release any executor resources owned by the pipeline."""

        if self._owns_executor and self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None
        self._prewarmed = False

    def __enter__(self) -> IndicatorPipeline:
        return self

    def __exit__(
        self, exc_type, exc, tb
    ) -> None:  # noqa: ANN001 - context manager contract
        self.close(wait=exc_type is None)

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        self.close(wait=False)


def _run_feature(
    feature: BaseFeature, data: np.ndarray, kwargs: Mapping[str, Any]
) -> FeatureResult:
    if kwargs:
        return feature.transform(data, **dict(kwargs))
    return feature.transform(data)


def _noop() -> None:
    return None


__all__ = ["IndicatorPipeline", "PipelineResult"]
