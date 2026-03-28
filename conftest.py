# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Pytest fixtures and environment setup.

This module performs two responsibilities:

* Ensure the repository root is importable so tests can resolve in-tree
  packages without installing them.
* Provide graceful fallbacks for optional plugins (e.g. ``pytest-cov``)
  that may be absent in constrained environments.  The CI workflow runs
  ``pytest`` with ``--cov``/``--cov-report`` switches; without the
  ``pytest-cov`` plugin, pytest would reject those flags.  We register
  lightweight no-op handlers so the options are accepted while keeping
  behaviour identical when ``pytest-cov`` is available.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import types
import warnings
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import pytest

try:
    from core.utils.determinism import THREAD_BOUND_ENV_VARS, apply_thread_determinism
except ImportError:  # pragma: no cover - fallback when optional deps missing
    _determinism_path = pathlib.Path(__file__).parent / "core" / "utils" / "determinism.py"
    if not _determinism_path.is_file():
        msg = f"Determinism helpers missing at {_determinism_path.as_posix()}"
        raise ImportError(msg)
    spec = importlib.util.spec_from_file_location(
        "_tradepulse_determinism", _determinism_path
    )
    if spec is None or spec.loader is None:
        msg = (
            f"Unable to load determinism helpers from {_determinism_path.as_posix()}"
        )
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    THREAD_BOUND_ENV_VARS = module.THREAD_BOUND_ENV_VARS
    apply_thread_determinism = module.apply_thread_determinism


class _FlakyTracker:
    """Collect execution metadata for tests marked as flaky."""

    def __init__(self, report_path: str | None) -> None:
        self._report_path = pathlib.Path(report_path).resolve() if report_path else None
        self._records: dict[str, dict[str, object]] = {}

    def register(self, item: pytest.Item) -> None:
        if item.nodeid in self._records:
            return
        marker = item.get_closest_marker("flaky")
        marker_payload: dict[str, object] | None = None
        if marker is not None:
            marker_payload = {
                "args": list(marker.args),
                "kwargs": marker.kwargs,
            }
        self._records[item.nodeid] = {
            "nodeid": item.nodeid,
            "location": {
                "path": str(pathlib.Path(item.location[0]).as_posix()),
                "line": item.location[1],
                "name": item.location[2],
            },
            "attempts": 0,
            "outcome": "deselected",
            "first_failure": None,
            "marker": marker_payload,
        }

    def record_call(self, item: pytest.Item, call: pytest.CallInfo[object]) -> None:
        record = self._records.get(item.nodeid)
        if record is None:
            return
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["outcome"] = call.outcome
        if call.excinfo is not None and record.get("first_failure") is None:
            record["first_failure"] = call.excinfo.exconly()

    def write_report(self) -> None:
        if self._report_path is None:
            return
        if not self._records:
            # Ensure the directory exists even when no flaky tests ran so the
            # workflow can still upload an empty manifest.
            self._report_path.parent.mkdir(parents=True, exist_ok=True)
            self._report_path.write_text("[]\n", encoding="utf-8")
            return
        payload: list[dict[str, object]] = []
        for nodeid in sorted(self._records):
            record = self._records[nodeid]
            attempts = int(record.get("attempts", 0))
            payload.append(
                {
                    "nodeid": record["nodeid"],
                    "location": record["location"],
                    "attempts": attempts,
                    "reruns": max(attempts - 1, 0),
                    "outcome": record["outcome"],
                    "first_failure": record.get("first_failure"),
                    "marker": record["marker"],
                }
            )
        self._report_path.parent.mkdir(parents=True, exist_ok=True)
        self._report_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

apply_thread_determinism(os.environ)

# ---------------------------------------------------------------------------
# Guard: detect whether PyTorch is actually importable (CUDA driver may be
# missing on CPU-only dev machines even though the package is installed).
# When torch cannot be loaded, we record the fact so that test-collection
# hooks can skip modules that unconditionally import it.
# ---------------------------------------------------------------------------
_TORCH_AVAILABLE = False
try:
    import torch as _torch_probe  # noqa: F401

    _TORCH_AVAILABLE = True
    del _torch_probe
except (ImportError, OSError, ValueError):
    pass

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.append(str(SRC))


if (
    "exchange_calendars" not in sys.modules
):  # pragma: no cover - optional dependency shim
    stub = types.ModuleType("exchange_calendars")

    class _BaseCalendar:
        def __init__(
            self,
            tz_key: str,
            open_time: time,
            close_time: time,
            weekend_closure: tuple[int, ...],
            holidays: tuple[date, ...] = (),
        ) -> None:
            self.tz = types.SimpleNamespace(key=tz_key)
            self._open_time = open_time
            self._close_time = close_time
            self._weekend_closure = weekend_closure
            self._holidays = holidays

        def _normalize(self, ts) -> datetime:
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(ZoneInfo(self.tz.key))

        def valid_days(self, start, end):  # noqa: D401 - mimic API
            """Return continuous range between ``start`` and ``end``."""

            return []

        def is_open_on_minute(self, ts):  # noqa: D401 - mirror API surface
            local = self._normalize(ts)
            if local.weekday() in self._weekend_closure:
                return False
            if local.date() in self._holidays:
                return False
            current = local.time()
            if self._open_time <= self._close_time:
                return self._open_time <= current < self._close_time
            return current >= self._open_time or current < self._close_time

        def minutes_in_range(self, start, end):  # noqa: D401 - mirror API surface
            start_local = self._normalize(start)
            end_local = self._normalize(end)
            if end_local < start_local:
                start_local, end_local = end_local, start_local
            minutes = []
            current = start_local
            step = timedelta(minutes=1)
            while current <= end_local:
                if self.is_open_on_minute(current):
                    minutes.append(current.astimezone(timezone.utc))
                current += step
            try:
                import pandas as pd  # local import to avoid mandatory dependency when unused

                if not minutes:
                    return pd.DatetimeIndex([], tz="UTC")
                return pd.DatetimeIndex(minutes)
            except Exception:  # pragma: no cover - fallback to list
                return minutes

    class _AlwaysOpenCalendar(_BaseCalendar):
        def __init__(self) -> None:
            super().__init__("UTC", time(0, 0), time(23, 59, 59), tuple())

        def is_open_on_minute(self, ts):  # noqa: D401 - mirror API surface
            """Always-open venues report every minute as tradable."""

            return True

    class _AlwaysOpenNamespace:
        AlwaysOpenCalendar = (
            _AlwaysOpenCalendar  # noqa: N803 - match third-party naming
        )

    class _ErrorsNamespace:
        class InvalidCalendarName(Exception):
            pass

    _CALENDARS: dict[str, _BaseCalendar] = {
        "ALWAYS_OPEN": _AlwaysOpenCalendar(),
        "XNYS": _BaseCalendar(
            "America/New_York",
            time(9, 30),
            time(16, 0),
            (5, 6),
            holidays=(date(2024, 7, 4),),
        ),
        "XNAS": _BaseCalendar(
            "America/New_York",
            time(9, 30),
            time(16, 0),
            (5, 6),
            holidays=(date(2024, 7, 4),),
        ),
        "CMES": _BaseCalendar(
            # Globex operates nearly 24/5; keep the stub open to mirror exchange_calendars'
            # lack of daily maintenance breaks.
            "America/Chicago",
            time(0, 0),
            time(23, 59, 59),
            (5,),
            holidays=(),
        ),
    }

    def _get_calendar(name: str):  # noqa: D401 - mimic API signature
        key = name.upper()
        return _CALENDARS.get(key, _AlwaysOpenCalendar())

    stub.always_open = _AlwaysOpenNamespace()
    stub.errors = _ErrorsNamespace()
    stub.ExchangeCalendar = object
    stub.get_calendar = _get_calendar
    stub.resolve_alias = lambda value: value  # type: ignore[assignment]
    sys.modules["exchange_calendars"] = stub


def _register_noop_cov_options(parser: "pytest.Parser") -> None:
    """Register ``--cov`` flags when ``pytest-cov`` is unavailable.

    When the real plugin is present it will have already added the
    options, in which case re-registering raises ``ValueError``—we
    silently ignore that scenario so the genuine implementation wins.
    """

    group = parser.getgroup("cov", "coverage reporting")
    options: Iterable[tuple[str, dict[str, object]]] = (
        (
            "--cov",
            {
                "action": "append",
                "dest": "tradepulse_cov",
                "metavar": "PATH",
                "default": [],
            },
        ),
        (
            "--cov-report",
            {
                "action": "append",
                "dest": "tradepulse_cov_report",
                "metavar": "TYPE",
                "default": [],
            },
        ),
    )
    for opt, kwargs in options:
        try:
            group.addoption(opt, **kwargs)
        except ValueError:
            # Option already registered (e.g. by pytest-cov); respect the original.
            pass


def pytest_addoption(parser):  # type: ignore[override]
    try:
        import pytest_cov.plugin  # noqa: F401  # type: ignore[attr-defined]
    except Exception:
        _register_noop_cov_options(parser)
    parser.addoption(
        "--flaky-report",
        action="store",
        default=None,
        help="Write a JSON manifest detailing reruns for tests marked as flaky.",
    )


def pytest_configure(config):  # type: ignore[override]
    if not hasattr(config, "_tradepulse_flaky_tracker"):
        config._tradepulse_flaky_tracker = _FlakyTracker(
            config.getoption("flaky_report")
        )
    if config.pluginmanager.hasplugin("pytest_cov"):
        return
    cov_targets = config.getoption("tradepulse_cov", default=None)
    cov_reports = config.getoption("tradepulse_cov_report", default=None)
    if cov_targets or cov_reports:
        from _pytest.warning_types import PytestWarning

        warnings.warn(
            "pytest-cov is not installed; coverage options are accepted but ignored.",
            PytestWarning,
            stacklevel=2,
        )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):  # type: ignore[override]
    """Provide a minimal ``pytest-asyncio`` fallback."""

    if pyfuncitem.config.pluginmanager.hasplugin("pytest_asyncio"):
        return None

    testfunction = pyfuncitem.obj
    if not asyncio.iscoroutinefunction(testfunction):
        return None

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        kwargs = {
            arg: pyfuncitem.funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames
        }
        loop.run_until_complete(testfunction(**kwargs))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
    return True


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    tracker = getattr(config, "_tradepulse_flaky_tracker", None)
    if tracker is None:
        return
    for item in items:
        if item.get_closest_marker("flaky") is not None:
            tracker.register(item)


def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[object]
) -> None:  # type: ignore[override]
    if call.when != "call":
        return
    tracker = getattr(item.config, "_tradepulse_flaky_tracker", None)
    if tracker is None or item.get_closest_marker("flaky") is None:
        return
    tracker.record_call(item, call)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # type: ignore[override]
    tracker = getattr(session.config, "_tradepulse_flaky_tracker", None)
    if tracker is not None:
        tracker.write_report()
