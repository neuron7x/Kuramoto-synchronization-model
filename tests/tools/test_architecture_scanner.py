# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import textwrap
from pathlib import Path

from tools.architecture.scanner import ArchitectureScanner


def _write(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def test_scanner_detects_dependencies(tmp_path: Path) -> None:
    package_root = tmp_path / "src" / "package"
    (package_root / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "package" / "__init__.py").write_text("", encoding="utf-8")

    module_a = package_root / "module_a.py"
    module_b = package_root / "module_b.py"
    module_c = package_root / "nested" / "module_c.py"
    module_c.parent.mkdir(parents=True, exist_ok=True)

    _write(
        module_a,
        """
        from . import module_b
        from .nested import module_c

        def run() -> tuple[object, object]:
            return module_b.VALUE, module_c.VALUE
        """,
    )
    _write(module_b, "VALUE = 1\n")
    _write(module_c, "VALUE = 2\n")

    scanner = ArchitectureScanner(tmp_path)
    report = scanner.scan()

    assert "package.module_a" in report.dependencies
    assert report.dependencies["package.module_a"] == {
        "package.module_b",
        "package.nested.module_c",
    }
    assert report.reverse_dependencies["package.module_b"] == {"package.module_a"}


def test_scanner_detects_cycles(tmp_path: Path) -> None:
    root = tmp_path / "core"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    _write(
        root / "a.py",
        """
        from . import b
        """,
    )
    _write(
        root / "b.py",
        """
        from . import a
        """,
    )

    scanner = ArchitectureScanner(tmp_path)
    report = scanner.scan()

    assert any({"core.a", "core.b"}.issubset(cycle) for cycle in report.cycles)


def test_modules_without_dependents(tmp_path: Path) -> None:
    pkg = tmp_path / "domain"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    _write(pkg / "a.py", "from . import b\n")
    _write(pkg / "b.py", "VALUE = 42\n")
    _write(pkg / "c.py", "VALUE = 99\n")

    scanner = ArchitectureScanner(tmp_path)
    report = scanner.scan()

    assert report.modules_without_dependents() == ["domain.a"]
    assert report.orphan_modules() == ["domain.c"]


def test_scanner_includes_nested_packages(tmp_path: Path) -> None:
    container = tmp_path / "libs"
    nested_pkg = container / "db"
    nested_pkg.mkdir(parents=True)
    (nested_pkg / "__init__.py").write_text("", encoding="utf-8")
    _write(nested_pkg / "models.py", "VALUE = 7\n")

    scanner = ArchitectureScanner(tmp_path)
    report = scanner.scan()

    assert "libs.db.models" in report.modules
