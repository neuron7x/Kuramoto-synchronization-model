# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

import pandas as pd
import pytest
import yaml

if not hasattr(pd, "_pandas_datetime_CAPI"):  # pragma: no cover - import-time guard
    pd._pandas_datetime_CAPI = None

from observability.audit.trail import (
    get_access_audit_trail,
    get_system_audit_trail,
)

os.environ.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "JBSWY3DPEHPK3PXP")
os.environ.setdefault("THERMO_DUAL_SECRET", "test-secret")

_fixture_path = Path(__file__).parent / "fixtures" / "conftest.py"
spec = importlib.util.spec_from_file_location(
    "tradepulse_tests_fixtures", _fixture_path
)
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load fixtures from {_fixture_path}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

globals().update(
    {name: getattr(module, name) for name in dir(module) if not name.startswith("__")}
)


_LEVEL_DESCRIPTIONS: dict[str, str] = {
    "L0": "Static analysis and supply-chain guardrails executed prior to Python runtime",
    "L1": "Hermetic unit tests with no external I/O, networking, or persistent side effects",
    "L2": "Contract, schema, RBAC, and audit-surface validation covering public interfaces",
    "L3": "Cross-module integration flows spanning TradePulse analytics, execution, and risk",
    "L4": "End-to-end regression of the trading lifecycle, including portfolio and orders",
    "L5": "Resilience, chaos, thermodynamic stability, and progressive rollout simulations",
    "L6": "Infrastructure readiness checks (Terraform, networking, policy enforcement)",
    "L7": "Dashboard UI, accessibility, and signal rendering quality gates",
    "UNSTABLE": "Quarantined suites with known flakiness that still surface elevated risk",
}


@dataclass(frozen=True)
class _LevelRule:
    level: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class _LevelConfig:
    overrides: dict[Path, str]
    rules: tuple[_LevelRule, ...]
    fallback_level: str | None


_CONFIG_PATH = Path(__file__).with_name("test_levels.yaml")


def _normalize(path: Path) -> Path:
    try:
        return path.resolve()
    except FileNotFoundError:
        return path


def _load_level_config(root: Path) -> _LevelConfig:
    if not _CONFIG_PATH.exists():
        raise pytest.UsageError(
            "tests/test_levels.yaml is missing; please provide the TradePulse test level map."
        )

    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}

    def _ensure_level(name: str) -> str:
        if name not in _LEVEL_DESCRIPTIONS:
            raise pytest.UsageError(
                f"Unknown TradePulse level '{name}' referenced in {_CONFIG_PATH}."
            )
        return name

    fallback_level = raw.get("fallback_level")
    if fallback_level is not None:
        fallback_level = _ensure_level(str(fallback_level))

    rules: list[_LevelRule] = []
    for entry in raw.get("levels", []):
        if not isinstance(entry, dict) or "level" not in entry:
            raise pytest.UsageError(
                f"Invalid rule entry {entry!r} in {_CONFIG_PATH}; expected mapping with 'level'."
            )
        level = _ensure_level(str(entry["level"]))
        patterns = entry.get("patterns", [])
        if not isinstance(patterns, Sequence) or isinstance(patterns, (str, bytes)):
            raise pytest.UsageError(
                f"Patterns for level {level} must be a sequence in {_CONFIG_PATH}."
            )
        normalized_patterns = tuple(
            PurePosixPath(str(pattern).strip()).as_posix().lstrip("./")
            for pattern in patterns
            if str(pattern).strip()
        )
        rules.append(_LevelRule(level=level, patterns=normalized_patterns))

    overrides_raw = raw.get("overrides", {})
    if not isinstance(overrides_raw, dict):
        raise pytest.UsageError(
            f"overrides in {_CONFIG_PATH} must be a mapping of paths to levels."
        )

    overrides: dict[Path, str] = {}
    for location, level_name in overrides_raw.items():
        if not isinstance(location, str):
            raise pytest.UsageError(
                f"Override path keys must be strings in {_CONFIG_PATH}, got {location!r}."
            )
        level = _ensure_level(str(level_name))
        overrides[_normalize(root / location)] = level

    return _LevelConfig(
        overrides=overrides, rules=tuple(rules), fallback_level=fallback_level
    )


@lru_cache(maxsize=1)
def _cached_level_config(root: Path) -> _LevelConfig:
    return _load_level_config(root)


def _match_patterns(relative: PurePosixPath, rules: Iterable[_LevelRule]) -> str | None:
    for rule in rules:
        for pattern in rule.patterns:
            if relative.match(pattern):
                return rule.level
    return None


def _determine_level(root: Path, path: Path) -> str:
    config = _cached_level_config(root)
    normalized = _normalize(path)

    override_level = config.overrides.get(normalized)
    if override_level is not None:
        return override_level

    try:
        relative = PurePosixPath(normalized.relative_to(root).as_posix())
    except ValueError:
        relative = PurePosixPath(normalized.as_posix())

    matched_level = _match_patterns(relative, config.rules)
    if matched_level is not None:
        return matched_level

    if (
        config.fallback_level is not None
        and relative.parts
        and relative.parts[0] == "tests"
    ):
        return config.fallback_level

    raise pytest.UsageError(
        "Unable to classify test {path} with TradePulse level. "
        "Update tests/test_levels.yaml with an explicit mapping or add a pytest marker.".format(
            path=path
        )
    )


def pytest_configure(config: pytest.Config) -> None:  # type: ignore[override]
    for marker, description in _LEVEL_DESCRIPTIONS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")


@pytest.fixture(scope="session", autouse=True)
def configure_audit_trails(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Isolate audit log files during the test run."""

    tmp_dir = tmp_path_factory.mktemp("audit_trails")
    get_access_audit_trail(tmp_dir / "access.jsonl")
    get_system_audit_trail(tmp_dir / "system.jsonl")
    yield
    get_access_audit_trail("observability/audit/access.jsonl")
    get_system_audit_trail("observability/audit/system.jsonl")


@pytest.fixture(autouse=True)
def _ensure_logging_propagation() -> None:
    """Ensure loggers propagate to root for caplog capture.

    Some tests rely on caplog to capture log messages, but the StructuredLogger
    may have handlers that prevent propagation. This fixture ensures the
    key loggers used in tests have propagation enabled.
    """
    loggers_to_fix = [
        "core.data.async_ingestion",
        "core.data.ingestion",
        "core.data",
        "core",
    ]
    for name in loggers_to_fix:
        logger = logging.getLogger(name)
        logger.propagate = True
    yield


@pytest.fixture(autouse=True)
def _reset_kill_switch() -> None:
    """Reset kill switch singleton before each test.

    This ensures that tests don't interfere with each other through
    the kill switch state.
    """
    from runtime.kill_switch import KillSwitchManager

    KillSwitchManager.reset_instance()
    yield
    KillSwitchManager.reset_instance()


def pytest_collection_modifyitems(  # type: ignore[override]
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    root = _normalize(Path(config.rootpath))
    for item in items:
        existing_levels = [
            mark.name
            for mark in item.iter_markers()
            if mark.name in _LEVEL_DESCRIPTIONS
        ]

        level_from_config = _determine_level(root, Path(item.fspath))

        if existing_levels:
            unique_levels = {level.upper() for level in existing_levels}
            if len(unique_levels) > 1:
                raise pytest.UsageError(
                    f"Test {item.nodeid} has conflicting TradePulse levels: {sorted(unique_levels)}"
                )
            (declared_level,) = unique_levels
            if declared_level != level_from_config:
                raise pytest.UsageError(
                    "Test {nodeid} is marked as {declared} but mapped to {computed} in tests/test_levels.yaml. "
                    "Update the marker or adjust the mapping.".format(
                        nodeid=item.nodeid,
                        declared=declared_level,
                        computed=level_from_config,
                    )
                )
            level = declared_level
        else:
            level = level_from_config
            item.add_marker(level)

        item.user_properties.append(("tradepulse_level", level))


# VCR configuration for recording HTTP interactions
# VCR is imported lazily to avoid requiring it for all tests

sensitive_headers = [
    "X-MBX-APIKEY",
    "CB-ACCESS-KEY",
    "CB-ACCESS-SIGN",
    "CB-ACCESS-PASSPHRASE",
    "CB-ACCESS-TIMESTAMP",
    "API-Key",
    "API-Sign",
    "Authorization",
]
sensitive_query = ["timestamp", "signature", "recvWindow"]
sensitive_body_keys = ["apiKey", "secret", "signature", "passphrase"]


def scrub_request(request):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    u = urlsplit(request.uri)
    q = []
    for k, v in parse_qsl(u.query, keep_blank_values=True):
        if k in sensitive_query:
            q.append((k, "REDACTED"))
        else:
            q.append((k, v))
    request.uri = urlunsplit((u.scheme, u.netloc, u.path, urlencode(q), u.fragment))
    for h in list(request.headers.keys()):
        if h in sensitive_headers:
            request.headers[h] = "REDACTED"
    return request


def scrub_response(response):
    import json

    ctype = response["headers"].get("Content-Type", [""])[0]
    if "application/json" in ctype:
        try:
            data = json.loads(response["body"]["string"])

            def cleanse(obj):
                if isinstance(obj, dict):
                    return {
                        k: ("REDACTED" if k in sensitive_body_keys else cleanse(v))
                        for k, v in obj.items()
                    }
                if isinstance(obj, list):
                    return [cleanse(x) for x in obj]
                return obj

            data = cleanse(data)
            response["body"]["string"] = json.dumps(data).encode()
        except Exception:
            pass
    return response


@pytest.fixture(autouse=True)
def _vcr_adapter_tests(request):
    """Auto-apply VCR to adapter tests."""
    # Only apply VCR to tests in tests/adapters directory
    if (
        request.fspath.strpath.endswith(".py")
        and "tests/adapters" in request.fspath.strpath
    ):
        try:
            import vcr
        except ImportError:
            pytest.skip("vcrpy is required for adapter tests")

        vcr_default = vcr.VCR(
            cassette_library_dir="tests/fixtures/recordings",
            record_mode=os.getenv("VCR_RECORD", "once"),
            filter_headers=[(h, "REDACTED") for h in sensitive_headers],
            before_record_request=scrub_request,
            before_record_response=scrub_response,
            decode_compressed_response=True,
        )

        cassette_name = (
            request.node.nodeid.replace("::", "__").replace("/", "_").replace("\\", "_")
            + ".yaml"
        )
        with vcr_default.use_cassette(cassette_name):
            yield
    else:
        yield
