# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression tests for the dependency determinism gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "tools" / "deps" / "check_operational_dependency_determinism.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dep_det", GATE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["dep_det"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed_repo(
    root: Path,
    *,
    action: str,
    constraints: str,
    requirements_dev: str,
    requirements_scan: str,
) -> None:
    action_path = root / ".github" / "actions" / "setup-geosync"
    action_path.mkdir(parents=True)
    (action_path / "action.yml").write_text(action, encoding="utf-8")
    constraints_path = root / "constraints"
    constraints_path.mkdir()
    (constraints_path / "security.txt").write_text(constraints, encoding="utf-8")
    (root / "requirements-dev.txt").write_text(requirements_dev, encoding="utf-8")
    (root / "requirements-scan.txt").write_text(requirements_scan, encoding="utf-8")


def _action_pins(pip: str = "26.1.1", setuptools: str = "78.1.1") -> str:
    return f"pip=={pip}\nsetuptools=={setuptools}\nwheel==0.46.2\n"


def _constraints() -> str:
    return dedent(
        """
        aiohttp==3.14.1
        cryptography==49.0.0
        fastapi>=0.138.0,<1.0.0
        Jinja2==3.1.6
        pandera==0.31.1
        pyarrow==24.0.0
        pydantic==2.13.4
        pydantic-settings==2.14.2
        PyJWT==2.13.0
        python-multipart==0.0.32
        PyYAML==6.0.3
        requests==2.34.2
        SQLAlchemy==2.0.51
        setuptools>=78.1.1
        starlette>=1.3.1
        strawberry-graphql==0.318.1
        tornado>=6.5.7
        wheel>=0.46.2
        """
    )


def _scan() -> str:
    return dedent(
        """
        aiohttp>=3.14.1
        cryptography>=49.0.0
        fastapi>=0.138.0,<1.0.0
        Jinja2>=3.1.6
        pandera>=0.31.1,<1.0.0
        pyarrow>=24.0.0
        pydantic>=2.13.4,<3.0.0
        pydantic-settings>=2.14.2,<3.0.0
        PyJWT[crypto]>=2.13.0
        python-multipart>=0.0.32
        PyYAML>=6.0.3
        requests>=2.34.2
        SQLAlchemy>=2.0.51
        starlette>=1.3.1
        strawberry-graphql[fastapi]>=0.318.1
        tornado>=6.5.7
        """
    )


def test_live_repo_dependency_determinism_gate_is_clean() -> None:
    gate = _load()
    assert gate.check(ROOT) == []


def test_live_repo_dependency_determinism_self_test_is_clean() -> None:
    gate = _load()
    assert gate.self_test(ROOT) == []


def test_gate_rejects_stale_bootstrap_toolchain(tmp_path: Path) -> None:
    gate = _load()
    _seed_repo(
        tmp_path,
        action=_action_pins(pip="25.0.1", setuptools="75.8.0"),
        constraints=_constraints(),
        requirements_dev="pip>=26.1.1\n",
        requirements_scan=_scan(),
    )
    errors = gate.check(tmp_path)
    assert any("pip==25.0.1" in error for error in errors)
    assert any("setuptools==75.8.0" in error for error in errors)


def test_gate_rejects_scan_manifest_below_security_constraint(tmp_path: Path) -> None:
    gate = _load()
    weak_scan = _scan().replace("requests>=2.34.2", "requests>=2.32.5")
    _seed_repo(
        tmp_path,
        action=_action_pins(),
        constraints=_constraints(),
        requirements_dev="pip>=26.1.1\n",
        requirements_scan=weak_scan,
    )
    errors = gate.check(tmp_path)
    assert any("requests>=2.32.5" in error for error in errors)
    assert any("below security constraint floor 2.34.2" in error for error in errors)


def test_gate_rejects_missing_critical_scan_floor(tmp_path: Path) -> None:
    gate = _load()
    missing_scan = _scan().replace("python-multipart>=0.0.32\n", "")
    _seed_repo(
        tmp_path,
        action=_action_pins(),
        constraints=_constraints(),
        requirements_dev="pip>=26.1.1\n",
        requirements_scan=missing_scan,
    )
    errors = gate.check(tmp_path)
    assert any("missing explicit scan floor" in error for error in errors)
    assert any("python-multipart" in error for error in errors)
