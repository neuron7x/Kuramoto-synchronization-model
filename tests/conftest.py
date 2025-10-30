# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

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


@pytest.fixture(scope="session", autouse=True)
def configure_audit_trails(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Isolate audit log files during the test run."""

    tmp_dir = tmp_path_factory.mktemp("audit_trails")
    get_access_audit_trail(tmp_dir / "access.jsonl")
    get_system_audit_trail(tmp_dir / "system.jsonl")
    yield
    get_access_audit_trail("observability/audit/access.jsonl")
    get_system_audit_trail("observability/audit/system.jsonl")
