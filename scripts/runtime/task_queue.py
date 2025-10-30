"""Concurrency helpers for script orchestration."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import signal
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from typing import Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")


class TaskQueue:
    """Thread-based worker pool with a hard limit on concurrency."""

    def __init__(self, max_workers: int) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="scripts"
        )
        self._futures: set[Future[object]] = set()
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def submit(self, fn: Callable[..., T], /, *args, **kwargs) -> Future[T]:
        if self._stopped.is_set():
            raise RuntimeError("TaskQueue is shutting down; refusing new work")
        future: Future[T] = self._executor.submit(fn, *args, **kwargs)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._futures.discard)
        return future

    def map(
        self, fn: Callable[[T], object], iterable: Iterable[T]
    ) -> list[Future[object]]:
        return [self.submit(fn, item) for item in iterable]

    def join(self) -> None:
        futures: set[Future[object]]
        with self._lock:
            futures = set(self._futures)
        wait(futures)

    def shutdown(self, *, cancel_futures: bool = False) -> None:
        self._stopped.set()
        self._executor.shutdown(
            wait=not cancel_futures,
            cancel_futures=cancel_futures,
        )

    def stop_accepting(self) -> None:
        self._stopped.set()


@contextmanager
def task_queue(max_workers: int) -> Iterator[TaskQueue]:
    """Context manager that installs signal handlers for graceful termination."""

    queue = TaskQueue(max_workers=max_workers)
    stop_event = threading.Event()

    def _handle_signal(signum: int, _frame) -> None:
        stop_event.set()
        queue.stop_accepting()
        queue.shutdown(cancel_futures=True)

    previous_handlers = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }
    for sig in previous_handlers:
        signal.signal(sig, _handle_signal)

    try:
        yield queue
        if not stop_event.is_set():
            queue.join()
    finally:
        queue.shutdown(cancel_futures=stop_event.is_set())
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
