# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

# SPDX-License-Identifier: MIT
import io
import os
import threading
import time
from pathlib import Path

import pytest

from scripts.runtime import (
    AutomationContext,
    AutomationRunner,
    AutomationStep,
    ChecksumMismatchError,
    ProgressBar,
    StepStatus,
    TransferError,
    compute_checksum,
    create_artifact_manager,
    transfer_with_resume,
    verify_checksum,
)
from scripts.runtime.pathfinder import find_resources
from scripts.runtime.task_queue import task_queue


def test_artifact_manager_creates_timestamped_directory(tmp_path: Path) -> None:
    manager = create_artifact_manager("demo", root=tmp_path)
    path = manager.directory
    assert path.parent == tmp_path / "demo"
    # Timestamp formatted like 20240101T000000Z
    assert path.name.endswith("Z")


def test_checksum_roundtrip(tmp_path: Path) -> None:
    sample = tmp_path / "payload.bin"
    sample.write_bytes(b"geosync" * 8)
    digest = compute_checksum(sample)
    verify_checksum(sample, digest)
    with pytest.raises(ChecksumMismatchError):
        verify_checksum(sample, "deadbeef")


def test_transfer_with_resume_local_file(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    payload = os.urandom(128 * 1024)
    source.write_bytes(payload)

    destination = tmp_path / "dest.bin"
    # Simulate an interrupted transfer by copying the first half
    destination.write_bytes(payload[: len(payload) // 2])

    progress_stream = io.StringIO()
    progress = ProgressBar(total=None, label="transfer", stream=progress_stream)
    transfer_with_resume(source, destination, progress=progress)

    assert destination.read_bytes() == payload


def test_transfer_with_resume_restarts_when_server_ignores_range(
    tmp_path: Path,
) -> None:
    url = "https://example.test/data.bin"
    payload = os.urandom(32 * 1024)
    destination = tmp_path / "dest.bin"
    destination.write_bytes(payload[: len(payload) // 2])

    class _StubResponse:
        def __init__(self, status_code: int, headers: dict[str, str], data: bytes = b"") -> None:
            self.status_code = status_code
            self.headers = headers
            self._data = data

        def iter_content(self, chunk_size: int):  # type: ignore[override]
            for index in range(0, len(self._data), chunk_size):
                yield self._data[index : index + chunk_size]

        def close(self) -> None:
            return None

    class _StubSession:
        def head(self, _url: str, **_kwargs: object) -> _StubResponse:
            return _StubResponse(200, {"Content-Length": str(len(payload))})

        def get(
            self, _url: str, *, stream: bool, headers: dict[str, str], timeout: int
        ) -> _StubResponse:
            assert stream and timeout
            # Simulate a server that ignores the Range request and restarts from 0
            assert headers.get("Range") == f"bytes={len(payload) // 2}-"
            return _StubResponse(200, {"Content-Length": str(len(payload))}, payload)

    session = _StubSession()
    transfer_with_resume(url, destination, session=session)

    assert destination.read_bytes() == payload


def test_transfer_with_resume_rejects_incorrect_resume_offset(tmp_path: Path) -> None:
    url = "https://example.test/data.bin"
    payload = os.urandom(16 * 1024)
    destination = tmp_path / "dest.bin"
    destination.write_bytes(payload[: len(payload) // 2])

    class _StubResponse:
        def __init__(self, status_code: int, headers: dict[str, str], data: bytes = b"") -> None:
            self.status_code = status_code
            self.headers = headers
            self._data = data

        def iter_content(self, chunk_size: int):  # type: ignore[override]
            for index in range(0, len(self._data), chunk_size):
                yield self._data[index : index + chunk_size]

        def close(self) -> None:
            return None

    class _StubSession:
        def head(self, _url: str, **_kwargs: object) -> _StubResponse:
            return _StubResponse(200, {"Content-Length": str(len(payload))})

        def get(
            self, _url: str, *, stream: bool, headers: dict[str, str], timeout: int
        ) -> _StubResponse:
            assert headers.get("Range") == f"bytes={len(payload) // 2}-"
            return _StubResponse(
                206,
                {
                    "Content-Range": "bytes 1-15/16",
                    "Content-Length": str(len(payload) - 1),
                },
                payload[1:],
            )

    with pytest.raises(TransferError):
        transfer_with_resume(url, destination, session=_StubSession())


def test_task_queue_limits_parallelism(tmp_path: Path) -> None:
    # Ensure that the task_queue helper executes tasks respecting the worker limit.
    lock = threading.Lock()
    active = 0
    peak = 0

    def _worker(duration: float) -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(duration)
        with lock:
            active -= 1

    with task_queue(max_workers=2) as queue:
        queue.submit(_worker, 0.1)
        queue.submit(_worker, 0.1)
        queue.submit(_worker, 0.1)

    assert peak <= 2


def test_find_resources(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "a.txt").write_text("hello", encoding="utf-8")
    (nested / "b.txt").write_text("world", encoding="utf-8")

    results = list(find_resources("*.txt", [nested]))
    assert {path.name for path in results} == {"a.txt", "b.txt"}


def test_automation_runner_executes_steps_in_dependency_order() -> None:
    context = AutomationContext()
    order: list[str] = []

    def prepare(ctx: AutomationContext) -> int:
        order.append("prepare")
        ctx.data["base"] = 1
        return 1

    def process(ctx: AutomationContext) -> int:
        order.append("process")
        base = ctx.require_output("prepare")
        return base + 1

    def finalize(ctx: AutomationContext) -> int:
        order.append("finalize")
        processed = ctx.require_output("process")
        return processed * 2

    runner = AutomationRunner(
        [
            AutomationStep("prepare", prepare),
            AutomationStep("process", process, dependencies=("prepare",)),
            AutomationStep("finalize", finalize, dependencies=("process",)),
        ]
    )

    report = runner.run(context)

    assert order == ["prepare", "process", "finalize"]
    assert report.succeeded
    assert context.require_output("finalize") == 4


def test_automation_runner_retries_on_failure() -> None:
    attempts = {"count": 0}

    def flaky(_ctx: AutomationContext) -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient failure")
        return "ok"

    runner = AutomationRunner([AutomationStep("flaky", flaky, retry_attempts=1)])

    report = runner.run()
    result = report.results["flaky"]

    assert result.status is StepStatus.SUCCEEDED
    assert result.attempts == 2
    assert attempts["count"] == 2


def test_automation_runner_blocks_dependents_after_critical_failure() -> None:
    def fail(_ctx: AutomationContext) -> None:
        raise RuntimeError("boom")

    def dependent(_ctx: AutomationContext) -> None:
        raise AssertionError("dependent should not run")

    runner = AutomationRunner(
        [
            AutomationStep("fail", fail, critical=True),
            AutomationStep("dependent", dependent, dependencies=("fail",)),
        ]
    )

    report = runner.run()

    assert report.results["fail"].status is StepStatus.FAILED
    assert report.results["dependent"].status is StepStatus.BLOCKED
    assert not report.succeeded


def test_automation_runner_respects_skip_predicate() -> None:
    context = AutomationContext()
    context.data["skip_optional"] = True

    runner = AutomationRunner(
        [
            AutomationStep(
                "optional",
                lambda _ctx: 1,
                skip_if=lambda ctx: ctx.data.get("skip_optional", False),
            )
        ]
    )

    report = runner.run(context)

    assert report.results["optional"].status is StepStatus.SKIPPED
    assert report.succeeded


def test_automation_runner_detects_cycles() -> None:
    with pytest.raises(ValueError):
        AutomationRunner(
            [
                AutomationStep("a", lambda _ctx: None, dependencies=("b",)),
                AutomationStep("b", lambda _ctx: None, dependencies=("a",)),
            ]
        )
