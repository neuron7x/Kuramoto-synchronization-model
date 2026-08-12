# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import logging
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import pytest
import yaml  # type: ignore[import-untyped]

_BOOTSTRAP_LOGGER = logging.getLogger("tests.bootstrap")
_PANDAS_DATETIME_CAPI = "_pandas_datetime_CAPI"


@dataclass(frozen=True)
class _LoadedModule:
    module: ModuleType
    name: str
    previous: ModuleType | None


# ---------------------------------------------------------------------------
# Pandas compatibility gate
# ---------------------------------------------------------------------------
# GeoSync pins ``pandas>=2.3.3``. Older builds missing the private
# ``_pandas_datetime_CAPI`` sentinel trigger an import-time AttributeError in
# some third-party extensions we still rely on; we keep a targeted guard
# rather than suppressing the error globally. We also assert that
# ``pd.Timestamp.now(tz=...)`` works end-to-end so that the test session
# aborts with a clear message instead of failing deep inside a fixture.
_PANDAS_MIN = (2, 3, 0)


def _parse_pandas_version(raw: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in raw.split(".")[:3] if part.isdigit())
    except ValueError as exc:  # pragma: no cover - defensive: malformed pandas version
        raise pytest.UsageError(f"Unable to parse installed pandas version {raw!r}") from exc


def _ensure_pandas_compatible(raw: str, version: tuple[int, ...]) -> None:
    if version < _PANDAS_MIN:
        raise pytest.UsageError(
            f"GeoSync test suite requires pandas >= {'.'.join(map(str, _PANDAS_MIN))}, "
            f"got {raw}"
        )

    if not hasattr(pd, _PANDAS_DATETIME_CAPI):  # pragma: no cover - environment guard
        # Preserve the historical workaround verbatim: a subset of our extension
        # dependencies read this attribute on import. Removing the shim silently
        # regresses test collection on fresh venvs, so we keep it until pandas
        # itself exposes the symbol again. ``setattr`` sidesteps the
        # ``attr-defined`` complaint on pandas builds that no longer expose the
        # sentinel statically while keeping the runtime effect identical.
        setattr(pd, _PANDAS_DATETIME_CAPI, None)

    try:
        pd.Timestamp.now(tz="UTC")
    except Exception as exc:  # pragma: no cover - environment smoke test
        raise pytest.UsageError(
            "pandas Timestamp smoke-test failed — tz-aware timestamp cannot be "
            f"constructed with pandas {raw}. Reinstall a clean build."
        ) from exc


_PANDAS_RAW = importlib.metadata.version("pandas")
_PANDAS_VERSION = _parse_pandas_version(_PANDAS_RAW)
_ensure_pandas_compatible(_PANDAS_RAW, _PANDAS_VERSION)
_BOOTSTRAP_LOGGER.info("pandas compatibility gate passed (pandas=%s)", _PANDAS_RAW)


def _load_module_from_path(module_name: str, path: Path, label: str) -> _LoadedModule:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {label} from {path}")

    module = importlib.util.module_from_spec(spec)
    registered_name = spec.name
    previous = sys.modules.get(registered_name)

    # ``registered_name`` must be present before ``exec_module`` so that the
    # loader can honour ``__package__``. The session-scoped restoration fixture
    # below removes this controlled bootstrap mutation after the test run.
    sys.modules[registered_name] = module
    spec.loader.exec_module(module)
    return _LoadedModule(module=module, name=registered_name, previous=previous)


def _restore_module_registration(name: str, previous: ModuleType | None) -> None:
    if previous is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = previous


_audit_loaded = _load_module_from_path(
    "geosync_observability_audit_trail",
    Path("observability/audit/trail.py"),
    "audit trail module",
)
_AUDIT_MODULE_NAME = _audit_loaded.name
_PRE_AUDIT_MODULE = _audit_loaded.previous
get_access_audit_trail = _audit_loaded.module.get_access_audit_trail
get_system_audit_trail = _audit_loaded.module.get_system_audit_trail

# Production-like environment variables are injected through the ``_test_env``
# session-scoped autouse fixture below so that the change is restored at the
# end of the session. The plain ``setdefault`` form used prior to Sprint 3
# leaked state into any subsequent in-process pytest invocation.
_TEST_ENV_DEFAULTS: dict[str, str] = {
    # Non-production placeholders — the real secrets come from the
    # environment in CI and from a developer's local .env otherwise.
    # ``pragma: allowlist secret`` keeps detect-secrets from treating
    # the well-known test-vector value as a leaked credential.
    "GEOSYNC_TWO_FACTOR_SECRET": "JBSWY3DPEHPK3PXP",  # pragma: allowlist secret
    "THERMO_DUAL_SECRET": "test-secret",  # pragma: allowlist secret
}


def _public_fixture_exports(module: ModuleType) -> dict[str, Any]:
    return {name: getattr(module, name) for name in dir(module) if not name.startswith("__")}


# Surface the shared fixtures from ``tests/fixtures/conftest.py`` at this
# higher-level conftest so ``autouse=True`` fixtures (e.g. ``_set_seed``)
# propagate to every test module.
#
# We deliberately do *not* use ``pytest_plugins = ("tests.fixtures.conftest",)``
# here: pytest already auto-loads that file as a conftest for tests under
# ``tests/fixtures/``, and registering it a second time via ``pytest_plugins``
# triggers pluggy's ``Plugin already registered under a different name`` error.
# The importlib.util load-by-path below mirrors the auto-discovery behaviour
# without double registration. The ``sys.modules`` write is recorded for
# restoration by ``_sys_modules_registrations``.
_fixture_loaded = _load_module_from_path(
    "geosync_tests_fixtures",
    Path(__file__).parent / "fixtures" / "conftest.py",
    "fixtures",
)
_FIXTURE_MODULE_NAME = _fixture_loaded.name
_PRE_FIXTURE_MODULE = _fixture_loaded.previous
globals().update(_public_fixture_exports(_fixture_loaded.module))


def _restore_environment(previous: dict[str, str | None]) -> None:
    for key, original in previous.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


@pytest.fixture(scope="session", autouse=True)
def _test_env() -> Iterator[None]:
    """Apply production-like env defaults for the session and restore after.

    Sprint 3 remediation: the previous ``os.environ.setdefault(...)`` lived
    at import time and never restored itself, so a second in-process
    pytest run (e.g. ``pytest-xdist``'s master + worker) inherited the
    test values. A session-scoped autouse fixture records originals and
    undoes the change on teardown, eliminating that leak.
    """
    previous: dict[str, str | None] = {k: os.environ.get(k) for k in _TEST_ENV_DEFAULTS}
    for key, value in _TEST_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    try:
        yield
    finally:
        _restore_environment(previous)


@pytest.fixture(scope="session", autouse=True)
def _sys_modules_registrations() -> Iterator[None]:
    """Restore ``sys.modules`` entries created at collection time."""
    try:
        yield
    finally:
        for name, previous in (
            (_AUDIT_MODULE_NAME, _PRE_AUDIT_MODULE),
            (_FIXTURE_MODULE_NAME, _PRE_FIXTURE_MODULE),
        ):
            _restore_module_registration(name, previous)


_LEVEL_DESCRIPTIONS: dict[str, str] = {
    "L0": "Static analysis and supply-chain guardrails executed prior to Python runtime",
    "L1": "Hermetic unit tests with no external I/O, networking, or persistent side effects",
    "L2": "Contract, schema, RBAC, and audit-surface validation covering public interfaces",
    "L3": "Cross-module integration flows spanning GeoSync analytics, execution, and risk",
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
    fallback_roots: tuple[str, ...]


_CONFIG_PATH = Path(__file__).with_name("test_levels.yaml")


def _normalize(path: Path) -> Path:
    try:
        return path.resolve()
    except FileNotFoundError:
        return path


def _ensure_level(name: str) -> str:
    if name not in _LEVEL_DESCRIPTIONS:
        raise pytest.UsageError(f"Unknown GeoSync level '{name}' referenced in {_CONFIG_PATH}.")
    return name


def _coerce_path_patterns(raw_patterns: Any, level: str) -> tuple[str, ...]:
    if not isinstance(raw_patterns, Sequence) or isinstance(raw_patterns, (str, bytes)):
        raise pytest.UsageError(f"Patterns for level {level} must be a sequence in {_CONFIG_PATH}.")
    return tuple(
        PurePosixPath(str(pattern).strip()).as_posix().lstrip("./")
        for pattern in raw_patterns
        if str(pattern).strip()
    )


def _coerce_fallback_roots(raw_roots: Any) -> tuple[str, ...]:
    if not isinstance(raw_roots, Sequence) or isinstance(raw_roots, (str, bytes)):
        raise pytest.UsageError(f"fallback_roots in {_CONFIG_PATH} must be a sequence of paths.")
    return tuple(
        PurePosixPath(str(root).strip()).as_posix().strip("/")
        for root in raw_roots
        if str(root).strip()
    )


def _load_level_rules(raw_levels: Any) -> tuple[_LevelRule, ...]:
    rules: list[_LevelRule] = []
    for entry in raw_levels:
        if not isinstance(entry, dict) or "level" not in entry:
            raise pytest.UsageError(
                f"Invalid rule entry {entry!r} in {_CONFIG_PATH}; expected mapping with 'level'."
            )
        level = _ensure_level(str(entry["level"]))
        rules.append(_LevelRule(level=level, patterns=_coerce_path_patterns(entry.get("patterns", []), level)))
    return tuple(rules)


def _load_level_overrides(root: Path, raw_overrides: Any) -> dict[Path, str]:
    if not isinstance(raw_overrides, dict):
        raise pytest.UsageError(f"overrides in {_CONFIG_PATH} must be a mapping of paths to levels.")

    overrides: dict[Path, str] = {}
    for location, level_name in raw_overrides.items():
        if not isinstance(location, str):
            raise pytest.UsageError(
                f"Override path keys must be strings in {_CONFIG_PATH}, got {location!r}."
            )
        overrides[_normalize(root / location)] = _ensure_level(str(level_name))
    return overrides


def _load_level_config(root: Path) -> _LevelConfig:
    if not _CONFIG_PATH.exists():
        raise pytest.UsageError(
            "tests/test_levels.yaml is missing; please provide the GeoSync test level map."
        )

    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    fallback_level = raw.get("fallback_level")
    if fallback_level is not None:
        fallback_level = _ensure_level(str(fallback_level))

    return _LevelConfig(
        overrides=_load_level_overrides(root, raw.get("overrides", {})),
        rules=_load_level_rules(raw.get("levels", [])),
        fallback_level=fallback_level,
        fallback_roots=_coerce_fallback_roots(raw.get("fallback_roots", ["tests"])),
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


def _relative_test_path(root: Path, normalized: Path) -> PurePosixPath:
    try:
        return PurePosixPath(normalized.relative_to(root).as_posix())
    except ValueError:
        return PurePosixPath(normalized.as_posix())


def _matches_fallback_root(relative: PurePosixPath, fallback_roots: Iterable[str]) -> bool:
    relative_posix = relative.as_posix()
    return any(
        relative_posix == root or relative_posix.startswith(f"{root}/")
        for root in fallback_roots
    )


def _determine_level(root: Path, path: Path) -> str:
    config = _cached_level_config(root)
    normalized = _normalize(path)

    override_level = config.overrides.get(normalized)
    if override_level is not None:
        return override_level

    relative = _relative_test_path(root, normalized)
    matched_level = _match_patterns(relative, config.rules)
    if matched_level is not None:
        return matched_level

    if config.fallback_level is not None and _matches_fallback_root(relative, config.fallback_roots):
        return config.fallback_level

    raise pytest.UsageError(
        "Unable to classify test {path} with GeoSync level. "
        "Update tests/test_levels.yaml with an explicit mapping or add a pytest marker.".format(
            path=path
        )
    )


def pytest_configure(config: pytest.Config) -> None:
    for marker, description in _LEVEL_DESCRIPTIONS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")


@pytest.fixture(scope="session", autouse=True)
def configure_audit_trails(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Isolate audit log files during the test run."""

    tmp_dir = tmp_path_factory.mktemp("audit_trails")
    get_access_audit_trail(tmp_dir / "access.jsonl")
    get_system_audit_trail(tmp_dir / "system.jsonl")
    yield
    get_access_audit_trail("observability/audit/access.jsonl")
    get_system_audit_trail("observability/audit/system.jsonl")


@pytest.fixture(autouse=True)
def _ensure_logging_propagation() -> Iterator[None]:
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
def _reset_kill_switch() -> Iterator[None]:
    """Reset kill switch singleton before each test.

    This ensures that tests don't interfere with each other through
    the kill switch state.
    """
    from runtime.kill_switch import KillSwitchManager

    KillSwitchManager.reset_instance()
    yield
    KillSwitchManager.reset_instance()


def _declared_levels(item: pytest.Item) -> list[str]:
    return [mark.name for mark in item.iter_markers() if mark.name in _LEVEL_DESCRIPTIONS]


def _resolve_item_level(item: pytest.Item, level_from_config: str, existing_levels: Sequence[str]) -> str:
    if not existing_levels:
        item.add_marker(level_from_config)
        return level_from_config

    unique_levels = {level.upper() for level in existing_levels}
    if len(unique_levels) > 1:
        raise pytest.UsageError(
            f"Test {item.nodeid} has conflicting GeoSync levels: {sorted(unique_levels)}"
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
    return declared_level


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = _normalize(Path(config.rootpath))
    for item in items:
        level = _resolve_item_level(
            item=item,
            level_from_config=_determine_level(root, Path(item.fspath)),
            existing_levels=_declared_levels(item),
        )
        item.user_properties.append(("geosync_level", level))


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


def scrub_request(request: Any) -> Any:
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


def _cleanse_sensitive_body(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: ("REDACTED" if key in sensitive_body_keys else _cleanse_sensitive_body(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_cleanse_sensitive_body(value) for value in obj]
    return obj


def scrub_response(response: Any) -> Any:
    ctype = response["headers"].get("Content-Type", [""])[0]
    if "application/json" in ctype:
        try:
            data = json.loads(response["body"]["string"])
            response["body"]["string"] = json.dumps(_cleanse_sensitive_body(data)).encode()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Body is not decodable/scrubable JSON; leave the recorded response
            # untouched rather than corrupt the cassette.
            return response
    return response


def _is_adapter_test(request: pytest.FixtureRequest) -> bool:
    return request.path.suffix == ".py" and "tests/adapters" in request.path.as_posix()


def _cassette_name(nodeid: str) -> str:
    return nodeid.replace("::", "__").replace("/", "_").replace("\\", "_") + ".yaml"


@pytest.fixture(autouse=True)
def _vcr_adapter_tests(request: pytest.FixtureRequest) -> Iterator[None]:
    """Auto-apply VCR to adapter tests."""
    # Only apply VCR to tests in tests/adapters directory
    if _is_adapter_test(request):
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

        with vcr_default.use_cassette(_cassette_name(request.node.nodeid)):
            yield
    else:
        yield
