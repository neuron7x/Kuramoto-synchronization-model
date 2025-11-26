# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Utilities for coordinating parallel strategy evaluations."""

from __future__ import annotations

import os
import threading
from concurrent.futures import FIRST_COMPLETED, Future, wait
from dataclasses import dataclass
from itertools import count
from queue import Empty, Full, PriorityQueue
from typing import Any, Callable, Dict, Mapping, Protocol, Sequence

from .evaluator import EvaluationResult, StrategyBatchEvaluator
from .strategy import Strategy


class _Evaluator(Protocol):
    def evaluate(
        self,
        strategies: Sequence[Strategy],
        data: Any,
        *,
        raise_on_error: bool = False,
    ) -> list[EvaluationResult]:
        """Execute the evaluation for *strategies* and return results."""


@dataclass(slots=True)
class StrategyFlow:
    """Container describing a batch of strategies to evaluate together."""

    name: str
    strategies: Sequence[Strategy]
    dataset: Any
    raise_on_error: bool = False
    priority: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("StrategyFlow.name must be a non-empty string")
        if isinstance(self.strategies, (str, bytes)):
            raise TypeError("StrategyFlow.strategies must not be a string")
        if not isinstance(self.strategies, Sequence):
            raise TypeError(
                "StrategyFlow.strategies must be a sequence of Strategy instances"
            )

        strategies = tuple(self.strategies)
        if not strategies:
            raise ValueError("StrategyFlow must include at least one strategy")
        for strategy in strategies:
            if not isinstance(strategy, Strategy):
                raise TypeError(
                    "StrategyFlow.strategies must contain Strategy instances"
                )
        object.__setattr__(self, "strategies", strategies)

        if not isinstance(self.priority, int):
            raise TypeError("StrategyFlow.priority must be an integer")


class StrategyOrchestrationError(RuntimeError):
    """Aggregate failure raised when one or more flows fail."""

    def __init__(
        self,
        errors: Mapping[str, BaseException],
        results: Mapping[str, Sequence[EvaluationResult]],
    ) -> None:
        self.errors: Dict[str, BaseException] = dict(errors)
        self.results: Dict[str, Sequence[EvaluationResult]] = dict(results)

        def _format_error(name: str, error: BaseException) -> str:
            detail = str(error)
            if not detail:
                detail = error.__class__.__name__
            return f"{name}: {detail}"

        message = ", ".join(
            _format_error(name, error) for name, error in self.errors.items()
        )
        super().__init__(
            f"Strategy orchestration failed for {len(self.errors)} flow(s): {message}"
        )


class StrategyOrchestrator:
    """Manage concurrent strategy evaluations with bounded parallelism."""

    def __init__(
        self,
        *,
        max_parallel: int | None = None,
        max_queue_size: int | None = None,
        evaluator_factory: Callable[[], _Evaluator] | _Evaluator | None = None,
        thread_name_prefix: str = "strategy-orchestrator",
    ) -> None:
        if max_parallel is not None and max_parallel <= 0:
            raise ValueError("max_parallel must be positive when provided")

        if max_queue_size is not None and max_queue_size < 0:
            raise ValueError("max_queue_size must be non-negative when provided")

        workers = max_parallel or min(32, (os.cpu_count() or 1) + 4)
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._pending: set[str] = set()
        self._shutdown = False
        self._sentinel = object()
        self._sequence = count()
        self._queue: PriorityQueue[
            tuple[int, int, StrategyFlow | object, Future | None]
        ]
        queue_size = 0 if max_queue_size in (None, 0) else max_queue_size
        self._queue = PriorityQueue(maxsize=queue_size)
        self._threads: list[threading.Thread] = []

        if evaluator_factory is None:
            self._factory: Callable[[], _Evaluator] = StrategyBatchEvaluator
        elif callable(evaluator_factory):
            self._factory = evaluator_factory
        elif hasattr(evaluator_factory, "evaluate"):
            self._factory = lambda: evaluator_factory
        else:  # pragma: no cover - defensive branch
            raise TypeError(
                "evaluator_factory must be callable or expose an 'evaluate' method"
            )

        for index in range(workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"{thread_name_prefix}-{index}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        """Terminate worker threads and reject new flows."""

        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        if cancel_pending:
            self._drain_pending()

        for _ in self._threads:
            # ``float('inf')`` ensures sentinels are consumed only after real work.
            self._queue.put((float("inf"), next(self._sequence), self._sentinel, None))

        if wait:
            for thread in self._threads:
                thread.join()

    def __enter__(self) -> "StrategyOrchestrator":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown(wait=True)

    # ------------------------------------------------------------------
    # Submission helpers
    def submit_flow(
        self,
        flow: StrategyFlow,
        *,
        timeout: float | None = None,
    ) -> Future[list[EvaluationResult]]:
        """Submit *flow* for asynchronous execution."""

        with self._lock:
            if self._shutdown:
                raise RuntimeError("StrategyOrchestrator has been shut down")
            if flow.name in self._active or flow.name in self._pending:
                raise RuntimeError(f"Flow '{flow.name}' is already running")
            self._pending.add(flow.name)

        future: Future[list[EvaluationResult]] = Future()
        task = (flow.priority, next(self._sequence), flow, future)

        try:
            self._queue.put(task, timeout=timeout)
        except Full as exc:  # pragma: no cover - defensive
            with self._lock:
                self._pending.discard(flow.name)
            raise TimeoutError(
                "Timed out while waiting to enqueue strategy flow"
            ) from exc

        if self._is_shutdown():
            self._reject_submitted_flow(flow.name, future, task)
            raise RuntimeError("StrategyOrchestrator has been shut down")

        return future

    def run_flows(
        self,
        flows: Sequence[StrategyFlow],
    ) -> Dict[str, list[EvaluationResult]]:
        """Execute *flows* concurrently and return collected results."""

        if not flows:
            return {}

        seen: set[str] = set()
        for flow in flows:
            if flow.name in seen:
                raise ValueError(f"Duplicate flow name detected: {flow.name}")
            seen.add(flow.name)

        futures: Dict[str, Future[list[EvaluationResult]]] = {
            flow.name: self.submit_flow(flow) for flow in flows
        }

        future_to_name: Dict[Future[list[EvaluationResult]], str] = {
            future: name for name, future in futures.items()
        }
        pending: set[Future[list[EvaluationResult]]] = set(future_to_name.keys())

        results: Dict[str, list[EvaluationResult]] = {}
        errors: Dict[str, BaseException] = {}
        cancel_pending = False

        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)

            for future in done:
                name = future_to_name.pop(future, None)
                if name is None:
                    continue

                try:
                    results[name] = future.result()
                except BaseException as exc:  # pragma: no cover - defensive
                    errors[name] = exc
                    cancel_pending = True

            if cancel_pending and pending:
                for future in list(pending):
                    future.cancel()
                cancel_pending = False

        if errors:
            raise StrategyOrchestrationError(errors, results)
        return results

    # ------------------------------------------------------------------
    # Introspection helpers
    def active_flows(self) -> frozenset[str]:
        """Return a snapshot of currently executing flow names."""

        with self._lock:
            return frozenset(self._active)

    # ------------------------------------------------------------------
    # Worker internals
    def _worker(self) -> None:
        while True:
            priority, sequence, flow, future = self._queue.get()
            try:
                if flow is self._sentinel:
                    return

                if not isinstance(flow, StrategyFlow):
                    raise TypeError(f"Expected StrategyFlow, got {type(flow).__name__}")
                if not isinstance(future, Future):
                    raise TypeError(f"Expected Future, got {type(future).__name__}")

                with self._lock:
                    self._pending.discard(flow.name)

                if not future.set_running_or_notify_cancel():
                    continue

                with self._lock:
                    self._active.add(flow.name)

                try:
                    evaluator = self._factory()
                    result = evaluator.evaluate(
                        flow.strategies,
                        flow.dataset,
                        raise_on_error=flow.raise_on_error,
                    )
                except BaseException as exc:  # pragma: no cover - forward to caller
                    future.set_exception(exc)
                else:
                    future.set_result(result)
                finally:
                    with self._lock:
                        self._active.discard(flow.name)
            finally:
                self._queue.task_done()

    def _is_shutdown(self) -> bool:
        with self._lock:
            return self._shutdown

    def _reject_submitted_flow(
        self,
        flow_name: str,
        future: Future[list[EvaluationResult]],
        task: tuple[int, int, StrategyFlow | object, Future | None],
    ) -> None:
        future.cancel()
        with self._lock:
            self._pending.discard(flow_name)

        to_requeue: list[tuple[int, int, StrategyFlow | object, Future | None]] = []
        removed = False
        while True:
            try:
                candidate = self._queue.get_nowait()
            except Empty:
                break

            if not removed and candidate == task:
                removed = True
            else:
                to_requeue.append(candidate)
            self._queue.task_done()

        for item in to_requeue:
            self._queue.put(item)

    def _drain_pending(self) -> None:
        while True:
            try:
                priority, sequence, flow, future = self._queue.get_nowait()
            except Empty:
                return

            try:
                if flow is self._sentinel:
                    # Re-insert the sentinel for other workers to observe.
                    self._queue.put((priority, sequence, flow, future))
                    return

                if not isinstance(flow, StrategyFlow):
                    raise TypeError(f"Expected StrategyFlow, got {type(flow).__name__}")
                if not isinstance(future, Future):
                    raise TypeError(f"Expected Future, got {type(future).__name__}")

                future.cancel()
                with self._lock:
                    self._pending.discard(flow.name)
            finally:
                self._queue.task_done()


__all__ = [
    "StrategyFlow",
    "StrategyOrchestrator",
    "StrategyOrchestrationError",
]
