# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Iterable

import pytest

from observability.audit.trail import (
    get_access_audit_trail,
    get_system_audit_trail,
)

os.environ.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "JBSWY3DPEHPK3PXP")

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

_LEVEL_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "L5",
        (
            "tests/chaos",
            "tests/fuzz",
            "tests/nightly",
            "tests/performance",
            "tests/tacl",
        ),
    ),
    ("L4", ("tests/e2e", "tests/smoke")),
    (
        "L3",
        (
            "tests/admin",
            "tests/evolution",
            "tests/execution",
            "tests/hydrobrain_v2",
            "tests/integration",
            "tests/neuro",
            "tests/neuropro",
            "tests/sandbox",
            "tests/scripts",
            "tests/strategies",
            "tests/tools",
            "tests/workflows",
        ),
    ),
    (
        "L2",
        (
            "tests/api",
            "tests/contracts",
            "tests/interfaces",
            "tests/observability",
            "tests/protocol",
            "tests/sdk",
            "tests/security",
        ),
    ),
    (
        "L1",
        (
            "tests/analysis",
            "tests/analytics",
            "tests/core",
            "tests/data",
            "tests/generated",
            "tests/property",
            "tests/unit",
            "tests/utils",
        ),
    ),
]

_FILE_LEVEL_OVERRIDES: dict[str, str] = {
    "tests/e2e/test_progressive_rollout.py": "L5",
}


def _normalize(path: Path) -> Path:
    try:
        return path.resolve()
    except FileNotFoundError:
        return path


def _iter_rule_matches(root: Path, rules: Iterable[tuple[str, tuple[str, ...]]]):
    for level, locations in rules:
        for location in locations:
            candidate = _normalize(root / location)
            yield level, candidate


def _determine_level(root: Path, path: Path) -> str:
    normalized = _normalize(path)
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = None

    override_candidates = {str(path), str(normalized)}
    if relative is not None:
        override_candidates.add(relative)

    for candidate in override_candidates:
        if candidate in _FILE_LEVEL_OVERRIDES:
            return _FILE_LEVEL_OVERRIDES[candidate]

    for level, candidate in _iter_rule_matches(root, _LEVEL_RULES):
        if candidate == normalized or candidate in normalized.parents:
            return level

    if normalized.parent == _normalize(root / "tests"):
        return "L3"

    raise pytest.UsageError(
        f"Test {path} is missing a TradePulse level classification. "
        "Add the file to _LEVEL_RULES or _FILE_LEVEL_OVERRIDES to designate a level."
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


def pytest_collection_modifyitems(  # type: ignore[override]
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    root = _normalize(Path(config.rootpath))
    for item in items:
        level = _determine_level(root, Path(item.fspath))
        if not any(mark.name == level for mark in item.iter_markers()):
            item.add_marker(level)
        item.user_properties.append(("tradepulse_level", level))
