# SPDX-License-Identifier: MIT
"""Sandbox execution utilities for isolating strategy evaluations."""

from __future__ import annotations

import dataclasses
import importlib
import math
import os
import sys
import time
from multiprocessing.connection import Connection, wait
from typing import Any, Dict

try:  # pragma: no cover - ``resource`` is unavailable on Windows
    import resource
except ModuleNotFoundError:  # pragma: no cover - handled gracefully in runtime
    resource = None  # type: ignore[assignment]

from multiprocessing import get_all_start_methods, get_context
from multiprocessing.context import BaseContext
import tracemalloc

_PSUTIL_SPEC = importlib.util.find_spec("psutil")
psutil = importlib.import_module("psutil") if _PSUTIL_SPEC else None


@dataclasses.dataclass(frozen=True)
class SandboxLimits:
    """Resource governance configuration for :class:`StrategySandbox`."""

    cpu_time_seconds: float | None = 2.0
    """Soft CPU time cap enforced with :func:`resource.setrlimit` when available."""

    wall_time_seconds: float | None = 5.0
    """Maximum wall clock time before the sandbox process is terminated."""

    memory_bytes: int | None = 512 * 1024 * 1024
    """Address space limit applied via ``RLIMIT_AS`` when supported."""

    nice_base: int = 0
    """Base niceness increment to apply to sandbox processes (positive lowers priority)."""

    nice_step: int = 1
    """Incremental niceness applied per-priority level passed to :meth:`StrategySandbox.run`."""


@dataclasses.dataclass(frozen=True)
class SandboxResult:
    """Serializable payload returned from sandbox execution."""

    strategy: Any
    score: float


class StrategySandboxError(RuntimeError):
    """Raised when a strategy fails within the sandbox environment."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class StrategySandbox:
    """Execute strategies in isolated, resource-governed subprocesses."""

    def __init__(
        self, *, limits: SandboxLimits | None = None, start_method: str | None = None
    ) -> None:
        self._limits = limits or SandboxLimits()
        self._ctx = _resolve_context(start_method)

    # ------------------------------------------------------------------
    def run(self, strategy: Any, data: Any, *, priority: int = 0) -> SandboxResult:
        """Execute *strategy* against *data* inside an isolated sandbox.

        ``priority`` is an integer where larger positive values lower the CPU
        scheduling priority of the sandbox process. Negative values request
        higher priority and will be honoured when permitted by the OS.
        """

        parent_conn, child_conn = self._ctx.Pipe(duplex=False)
        limits = self._limits

        process = self._ctx.Process(
            target=_sandbox_worker,
            args=(child_conn, strategy, data, limits, priority),
            name=f"strategy-sandbox-{getattr(strategy, 'name', 'unknown')}",
        )
        process.daemon = False
        process.start()
        child_conn.close()

        try:
            payload = self._wait_for_payload(parent_conn, limits.wall_time_seconds)
        finally:
            parent_conn.close()

        if payload is None:
            self._terminate_process(process)
            raise StrategySandboxError(
                "Strategy execution timed out in sandbox", cause=TimeoutError()
            )

        process.join(timeout=0.0)
        if process.is_alive():
            self._terminate_process(process)

        status = payload.get("status")
        if status != "ok":
            error = payload.get("error")
            message = payload.get("message", "Strategy sandbox failed")
            if isinstance(error, BaseException):
                raise StrategySandboxError(message, cause=error) from error
            raise StrategySandboxError(message)

        result: SandboxResult = payload["result"]
        return result

    # ------------------------------------------------------------------
    def _wait_for_payload(
        self, conn: Connection, timeout: float | None
    ) -> Dict[str, Any] | None:
        if timeout is not None:
            timeout = max(0.0, float(timeout))

        start = time.monotonic()
        while True:
            remaining: float | None
            if timeout is None:
                remaining = None
            else:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    return None
                remaining = timeout - elapsed

            ready = wait([conn], timeout=remaining)
            if not ready:
                return None
            try:
                payload = conn.recv()
            except EOFError:
                return None
            if isinstance(payload, dict):
                return payload
            # Defensive: ignore unexpected payloads.

    def _terminate_process(self, process) -> None:
        try:
            if process.is_alive():
                process.kill()
        finally:
            process.join(timeout=0.0)


def _sandbox_worker(
    conn: Connection,
    strategy: Any,
    data: Any,
    limits: SandboxLimits,
    priority: int,
) -> None:
    guard = _MemoryUsageGuard(limits.memory_bytes)
    try:
        _apply_limits(limits, priority)
        guard.start()
        score = float(strategy.simulate_performance(data))
        guard.verify()

        result = SandboxResult(strategy=strategy, score=score)
        conn.send({"status": "ok", "result": result})
    except BaseException as exc:  # pragma: no cover - defensive guard
        conn.send({"status": "error", "error": exc, "message": str(exc)})
    finally:
        guard.stop()
        conn.close()


def _resolve_context(start_method: str | None) -> BaseContext:
    if start_method is not None:
        return get_context(start_method)

    available_methods = set(get_all_start_methods())

    if not _running_without_main_file() and "spawn" in available_methods:
        try:
            return get_context("spawn")
        except ValueError:  # pragma: no cover - defensive fallback
            pass

    try:
        ctx = get_context()
    except ValueError:
        ctx = None

    if ctx is not None and ctx.get_start_method() != "spawn":
        return ctx

    if _running_without_main_file() and "fork" in available_methods:
        return get_context("fork")

    if ctx is not None:
        return ctx

    for candidate in ("fork", "forkserver"):
        if candidate in available_methods:
            try:
                return get_context(candidate)
            except ValueError:  # pragma: no cover - defensive fallback
                continue

    if "spawn" in available_methods:
        return get_context("spawn")

    raise RuntimeError("No suitable multiprocessing context available for sandboxing")


def _running_without_main_file() -> bool:
    """Return ``True`` when the active ``__main__`` module lacks a real file."""

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True

    main_module = sys.modules.get("__main__")
    if main_module is None:
        return False

    main_file = getattr(main_module, "__file__", None)
    if not main_file:
        return True

    if isinstance(main_file, str) and main_file.startswith("<") and main_file.endswith(">"):
        return True

    return not os.path.exists(main_file)


def _apply_limits(limits: SandboxLimits, priority: int) -> None:
    _set_priority(limits, priority)
    if resource is None:
        return

    if limits.cpu_time_seconds is not None:
        cpu_seconds = max(1, int(math.ceil(limits.cpu_time_seconds)))
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except (ValueError, OSError):  # pragma: no cover - defensive fallback
            pass

    if limits.memory_bytes is not None:
        memory = max(1, int(limits.memory_bytes))
        for limit_name in ("RLIMIT_AS", "RLIMIT_DATA", "RLIMIT_RSS"):
            if not hasattr(resource, limit_name):
                continue
            try:
                limit = getattr(resource, limit_name)
                resource.setrlimit(limit, (memory, memory))
            except (ValueError, OSError):  # pragma: no cover - defensive fallback
                continue


def _set_priority(limits: SandboxLimits, priority: int) -> None:
    try:
        increment = limits.nice_base + limits.nice_step * priority
        if increment:
            os.nice(increment)
    except (AttributeError, OSError):  # pragma: no cover - unsupported platform
        pass


class _MemoryUsageGuard:
    """Best-effort enforcement of memory limits when rlimits are unavailable."""

    __slots__ = (
        "_limit",
        "_tracer_started",
        "_psutil_process",
        "_has_rusage",
        "_baseline_ru_maxrss",
        "_baseline_rss",
    )

    def __init__(self, limit: int | None) -> None:
        self._limit = int(limit) if limit is not None else None
        self._tracer_started = False
        self._psutil_process = None
        self._has_rusage = resource is not None and hasattr(resource, "getrusage")
        self._baseline_ru_maxrss: int | None = None
        self._baseline_rss: int | None = None

    def start(self) -> None:
        if self._limit is None:
            return

        if self._has_rusage:
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
            except (OSError, ValueError):  # pragma: no cover - unlikely platform issues
                self._has_rusage = False
            else:
                self._baseline_ru_maxrss = _ru_maxrss_to_bytes(
                    getattr(usage, "ru_maxrss", 0)
                )

        if psutil is not None:
            try:
                process = psutil.Process(os.getpid())
                info = process.memory_info()
            except Exception:  # pragma: no cover - psutil failed unexpectedly
                self._psutil_process = None
            else:
                self._psutil_process = process
                self._baseline_rss = info.rss

        if not tracemalloc.is_tracing():
            tracemalloc.start()
            self._tracer_started = True

    def verify(self) -> None:
        if self._limit is None:
            return

        limit = max(1, self._limit)
        observed = 0

        if self._tracer_started:
            try:
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
                self._tracer_started = False
            observed = max(observed, peak)

        if self._has_rusage:
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
            except (OSError, ValueError):  # pragma: no cover - transient failure
                self._has_rusage = False
            else:
                ru_maxrss = getattr(usage, "ru_maxrss", 0)
                peak_bytes = _ru_maxrss_to_bytes(ru_maxrss)
                baseline = self._baseline_ru_maxrss or 0
                if baseline < limit:
                    if peak_bytes > limit:
                        observed = max(observed, peak_bytes)
                elif peak_bytes - baseline > limit:
                    observed = max(observed, peak_bytes)

        process = self._psutil_process
        if process is not None:
            try:
                rss = process.memory_info().rss
            except Exception:  # pragma: no cover - psutil read failure
                self._psutil_process = None
            else:
                baseline_rss = self._baseline_rss or 0
                if baseline_rss < limit:
                    if rss > limit:
                        observed = max(observed, rss)
                elif rss - baseline_rss > limit:
                    observed = max(observed, rss)

        if observed > limit:
            raise MemoryError(
                f"Sandbox memory usage {observed} bytes exceeded limit {limit}"
            )

    def stop(self) -> None:
        if self._tracer_started:
            try:
                tracemalloc.stop()
            finally:
                self._tracer_started = False


def _ru_maxrss_to_bytes(value: int) -> int:
    if value <= 0:
        return 0
    if sys.platform.startswith("darwin") or sys.platform.startswith("ios"):
        return value
    return value * 1024


__all__ = [
    "SandboxLimits",
    "SandboxResult",
    "StrategySandbox",
    "StrategySandboxError",
]

