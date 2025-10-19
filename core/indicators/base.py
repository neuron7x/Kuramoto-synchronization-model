# SPDX-License-Identifier: MIT
"""Foundational feature/block interfaces for indicator transformers.

These contracts make the fractal composition of indicators explicit: every
feature exposes the same `transform` signature and every block orchestrates a
homogeneous list of features.  Any new indicator can therefore be plugged into
an existing block (or nested block) without bespoke glue code.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, MutableSequence, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Literal

from core.utils.metrics import get_metrics_collector
from observability.tracing import pipeline_span

FeatureInput = Any


@dataclass(slots=True)
class FeatureResult:
    """Canonical payload returned by every feature transformer."""

    name: str
    value: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)


class BaseFeature(ABC):
    """Structural contract for every indicator/feature transformer."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    def __call__(self, data: FeatureInput, **kwargs: Any) -> FeatureResult:
        return self.transform(data, **kwargs)

    @abstractmethod
    def transform(self, data: FeatureInput, **kwargs: Any) -> FeatureResult:
        """Produce a feature result from raw input."""

    def transform_with_metrics(
        self, data: FeatureInput, **kwargs: Any
    ) -> FeatureResult:
        """Transform with automatic metrics collection."""
        metrics = get_metrics_collector()
        feature_type = kwargs.get("feature_type", "generic")

        with pipeline_span(
            "features.transform", feature_name=self.name, feature_type=feature_type
        ):
            with metrics.measure_feature_transform(self.name, feature_type):
                result = self.transform(data, **kwargs)

        # Record the feature value if it's numeric
        if isinstance(result.value, (int, float)):
            metrics.record_feature_value(self.name, float(result.value))

        return result


class BaseBlock(ABC):
    """Composable container that orchestrates a homogeneous list of features."""

    def __init__(
        self,
        features: Sequence[BaseFeature] | None = None,
        *,
        name: str | None = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self._features: MutableSequence[BaseFeature] = list(features or [])

    @property
    def features(self) -> tuple[BaseFeature, ...]:
        return tuple(self._features)

    def register(self, feature: BaseFeature) -> None:
        self._features.append(feature)

    def add_feature(self, feature: BaseFeature) -> None:
        """Alias for :meth:`register` to match the higher-level API docs."""

        self.register(feature)

    def extend(self, features: Iterable[BaseFeature]) -> None:
        self._features.extend(features)

    def __call__(self, data: FeatureInput, **kwargs: Any) -> Mapping[str, Any]:
        return self.run(data, **kwargs)

    @abstractmethod
    def run(self, data: FeatureInput, **kwargs: Any) -> Mapping[str, Any]:
        """Execute the block over the input and return a feature mapping."""


class FeatureBlock(BaseBlock):
    """Minimal block that executes its child features sequentially."""

    def __init__(
        self,
        features: Sequence[BaseFeature] | str | None = None,
        *,
        name: str | None = None,
    ) -> None:
        block_name = name
        feature_sequence: Sequence[BaseFeature] | None

        if isinstance(features, str):
            if block_name is not None:
                raise TypeError(
                    "features must be an iterable of BaseFeature instances or None"
                )
            block_name = features
            feature_sequence = None
        elif features is None:
            feature_sequence = None
        else:
            if not isinstance(features, Iterable):
                raise TypeError(
                    "features must be an iterable of BaseFeature instances or None"
                )
            feature_sequence = tuple(features)

        if feature_sequence is not None and any(
            not isinstance(item, BaseFeature) for item in feature_sequence
        ):
            raise TypeError("features must contain BaseFeature instances")

        super().__init__(features=feature_sequence, name=block_name)

    def _iter_results(
        self, data: FeatureInput, kwargs: Mapping[str, Any]
    ) -> Iterable[FeatureResult]:
        for feature in self.features:
            yield feature.transform(data, **kwargs)

    def evaluate(
        self, data: FeatureInput, **kwargs: Any
    ) -> Mapping[str, FeatureResult]:
        """Run all features and return their full :class:`FeatureResult`s."""

        return {
            result.name: result
            for result in self._iter_results(data, kwargs)
        }

    def transform_all(
        self, data: FeatureInput, **kwargs: Any
    ) -> Mapping[str, FeatureResult]:
        """Alias for :meth:`evaluate` to align with the public documentation."""

        return self.evaluate(data, **kwargs)

    def run(self, data: FeatureInput, **kwargs: Any) -> Mapping[str, Any]:
        return {
            name: result.value
            for name, result in self.evaluate(data, **kwargs).items()
        }


class ParallelFeatureBlock(BaseBlock):
    """Block that executes features concurrently while sharing the same input buffer.

    The block supports both thread-based (asyncio) fan-out and process-based
    execution. Thread-based execution is typically sufficient when indicator
    computations release the Global Interpreter Lock (for example NumPy or
    CuPy heavy lifting). Process mode is available for CPU-bound pure Python
    features.

    Args:
        features: Iterable of feature instances to orchestrate.
        mode: ``"thread"`` to leverage :mod:`asyncio`/thread pools or
            ``"process"`` for a :class:`concurrent.futures.ProcessPoolExecutor`.
        max_workers: Optional hard limit for the executor.
    """

    def __init__(
        self,
        features: Sequence[BaseFeature] | None = None,
        *,
        name: str | None = None,
        mode: Literal["thread", "process"] = "thread",
        max_workers: int | None = None,
    ) -> None:
        super().__init__(features=features, name=name)
        self.mode = mode
        self.max_workers = max_workers

    def run(self, data: FeatureInput, **kwargs: Any) -> Mapping[str, Any]:
        if self.mode == "process":
            return self._run_process(data, **kwargs)
        return _run_block_thread(self.features, data, kwargs)

    def _run_process(self, data: FeatureInput, **kwargs: Any) -> Mapping[str, Any]:
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(_process_transform, feature, data, kwargs)
                for feature in self.features
            ]
            results = [future.result() for future in futures]
        return {result.name: result.value for result in results}


def _run_block_thread(
    features: Sequence[BaseFeature],
    data: FeatureInput,
    kwargs: Mapping[str, Any],
) -> Mapping[str, Any]:
    async def _runner() -> Mapping[str, Any]:
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None,
                partial(feature.transform, **dict(kwargs)),
                data,
            )
            for feature in features
        ]
        results = await asyncio.gather(*tasks)
        return {result.name: result.value for result in results}

    try:
        return asyncio.run(_runner())
    except RuntimeError as exc:
        message = str(exc)
        if (
            "event loop is running" not in message
            and "cannot be called from a running event loop" not in message
        ):
            raise
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(_runner())
        finally:
            asyncio.set_event_loop(None)
            new_loop.close()


def _process_transform(
    feature: BaseFeature, data: FeatureInput, kwargs: Mapping[str, Any]
) -> FeatureResult:
    """Execute ``feature.transform`` in a child process.

    The helper is module-level to ensure it is picklable for ``fork`` as well
    as ``spawn`` start methods.
    """

    return feature.transform(data, **dict(kwargs))


class BlockFeature(BaseFeature):
    """Adapter that exposes a :class:`BaseBlock` as a feature."""

    def __init__(
        self,
        block: BaseBlock,
        *,
        name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name or block.name)
        self._block = block
        self._metadata = dict(metadata or {})

    @property
    def block(self) -> BaseBlock:
        return self._block

    def transform(self, data: FeatureInput, **kwargs: Any) -> FeatureResult:
        values = self._block.run(data, **kwargs)
        metadata = {
            "block": self._block.name,
            "feature_count": len(self._block.features),
        }
        metadata.update(self._metadata)
        return FeatureResult(name=self.name, value=values, metadata=metadata)


class FunctionalFeature(BaseFeature):
    """Adapter that wraps a plain function into the feature interface."""

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(name)
        self._func = func
        self._metadata = dict(metadata or {})

    def transform(self, data: FeatureInput, **kwargs: Any) -> FeatureResult:
        value = self._func(data, **kwargs)
        return FeatureResult(name=self.name, value=value, metadata=self._metadata)


__all__ = [
    "BaseFeature",
    "BaseBlock",
    "BlockFeature",
    "FeatureBlock",
    "ParallelFeatureBlock",
    "FunctionalFeature",
    "FeatureResult",
]
