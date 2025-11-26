from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.architecture_audit import ArchitectureAudit, run_audit


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def sample_project(tmp_path: Path) -> list[Path]:
    package_root = tmp_path / "pkg"
    _write(
        package_root / "__init__.py",
        "__all__ = ['a', 'b', 'models', 'other_models', 'inventory']\n",
    )
    _write(
        package_root / "a.py",
        "from dataclasses import dataclass\n"
        "from . import b\n"
        "from . import missing_module\n"
        "\n"
        "@dataclass\n"
        "class Quote:\n"
        "    id: int\n"
        "    price: float\n",
    )
    _write(
        package_root / "b.py",
        "from . import a\n",
    )
    _write(
        package_root / "models.py",
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Order:\n"
        "    id: int\n"
        "    value: float\n",
    )
    _write(
        package_root / "other_models.py",
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Order:\n"
        "    id: int\n"
        "    amount: float\n",
    )
    _write(
        package_root / "inventory.py",
        "from typing import TypedDict\n"
        "\n"
        "class Product(TypedDict):\n"
        "    id: int\n"
        "    stock: int\n",
    )
    _write(
        package_root / "inventory_sync.py",
        "from typing import TypedDict\n"
        "\n"
        "class Product(TypedDict):\n"
        "    id: int\n"
        "    quantity: int\n",
    )
    _write(
        package_root / "usage.py",
        "from pkg import b\n",
    )
    return [package_root]


def test_architecture_audit_detects_cycles_and_conflicts(
    sample_project: list[Path],
) -> None:
    auditor = ArchitectureAudit(sample_project)
    report = auditor.analyze()

    module_names = set(report.modules)
    assert module_names >= {"pkg.a", "pkg.b", "pkg.models", "pkg.other_models"}

    assert any({"pkg.a", "pkg.b"}.issubset(set(cycle)) for cycle in report.cycles)

    conflict_types = {(conf.type, conf.identifier) for conf in report.conflicts}
    assert ("dataclass", "Order") in conflict_types
    assert ("typeddict", "Product") in conflict_types

    assert report.dangling_dependencies.get("pkg.a") == {"pkg.missing_module"}

    usage_imports = report.modules["pkg.usage"].imports
    assert "pkg.b" in usage_imports


def test_run_audit_cli_wrapper(sample_project: list[Path]) -> None:
    report = run_audit([str(sample_project[0])])
    output = json.dumps(report.to_dict())
    assert '"modules"' in output
    assert '"conflicts"' in output
