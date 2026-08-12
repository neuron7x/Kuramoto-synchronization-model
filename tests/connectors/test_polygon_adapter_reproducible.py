# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reproducible Polygon adapter tests isolated from unrelated config imports."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec for {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_polygon_adapter_modules():
    repo_root = Path(__file__).resolve().parents[2]
    core_root = repo_root / "core"
    data_root = core_root / "data"
    adapters_root = data_root / "adapters"

    core_pkg = sys.modules.setdefault("core", types.ModuleType("core"))
    core_pkg.__path__ = [str(core_root)]

    data_pkg = sys.modules.setdefault("core.data", types.ModuleType("core.data"))
    data_pkg.__path__ = [str(data_root)]

    adapters_pkg = sys.modules.setdefault(
        "core.data.adapters", types.ModuleType("core.data.adapters")
    )
    adapters_pkg.__path__ = [str(adapters_root)]

    if "aiolimiter" not in sys.modules:
        aiolimiter = types.ModuleType("aiolimiter")

        class AsyncLimiter:  # pragma: no cover - test shim
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        aiolimiter.AsyncLimiter = AsyncLimiter
        sys.modules["aiolimiter"] = aiolimiter

    if "tenacity" not in sys.modules:
        tenacity = types.ModuleType("tenacity")

        class AsyncRetrying:  # pragma: no cover - test shim
            def __init__(self, **_kwargs) -> None:
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        def retry_if_exception_type(*_args, **_kwargs):
            return None

        def stop_after_attempt(*_args, **_kwargs):
            return None

        def wait_random_exponential(*_args, **_kwargs):
            return None

        tenacity.AsyncRetrying = AsyncRetrying
        tenacity.retry_if_exception_type = retry_if_exception_type
        tenacity.stop_after_attempt = stop_after_attempt
        tenacity.wait_random_exponential = wait_random_exponential
        sys.modules["tenacity"] = tenacity

    if "core.data.timeutils" not in sys.modules:
        timeutils = types.ModuleType("core.data.timeutils")

        def normalize_timestamp(value):
            if isinstance(value, (int, float)) and value > 1e12:
                value = value / 1000
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            return value

        timeutils.normalize_timestamp = normalize_timestamp
        sys.modules["core.data.timeutils"] = timeutils

    _load_module("core.data.catalog", data_root / "catalog.py")
    _load_module("core.data.models", data_root / "models.py")
    base = _load_module("core.data.adapters.base", adapters_root / "base.py")
    polygon = _load_module("core.data.adapters.polygon", adapters_root / "polygon.py")
    return base, polygon


class _Response:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self) -> dict[str, object]:
        return self._payload


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self._responses = responses
        self.calls = 0
        self.closed = False

    async def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]

    async def aclose(self) -> None:
        self.closed = True


def test_polygon_fetch_maps_payload_to_ticks_isolated_import() -> None:
    _, polygon = _load_polygon_adapter_modules()
    PolygonIngestionAdapter = polygon.PolygonIngestionAdapter

    client = _Client(
        responses=[
            _Response(
                {
                    "results": [
                        {"t": 1719878400000, "c": 100.1, "v": 12.0},
                        {"t": 1719878460, "c": 100.5, "v": 7.0},
                    ]
                }
            )
        ]
    )

    async def _run():
        adapter = PolygonIngestionAdapter(api_key="test", client=client)
        ticks = await adapter.fetch(symbol="AAPL", start="2024-01-01", end="2024-01-02")
        await adapter.aclose()
        return ticks

    ticks = asyncio.run(_run())

    assert len(ticks) == 2
    assert float(ticks[0].price) == 100.1
    assert ticks[0].timestamp == datetime(2024, 7, 2, 0, 0, tzinfo=timezone.utc)
    assert float(ticks[1].price) == 100.5
    assert client.closed is True


def test_polygon_fetch_retries_on_transient_error_isolated_import() -> None:
    _, polygon = _load_polygon_adapter_modules()
    PolygonIngestionAdapter = polygon.PolygonIngestionAdapter

    class _TransientClient(_Client):
        async def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("temporary")
            return _Response({"results": [{"t": 1719878400000, "c": 10.0, "v": 1.0}]})

    client = _TransientClient(responses=[])

    async def _run():
        adapter = PolygonIngestionAdapter(
            api_key="test",  # pragma: allowlist secret
            client=client,
        )
        attempts = {"count": 0}

        async def _retry_once(operation):
            try:
                attempts["count"] += 1
                return await operation()
            except TimeoutError:
                attempts["count"] += 1
                return await operation()

        adapter._run_with_policy = _retry_once  # type: ignore[method-assign]
        return await adapter.fetch(symbol="MSFT", start="2024-01-01", end="2024-01-02")

    ticks = asyncio.run(_run())

    assert len(ticks) == 1
    assert client.calls == 2
