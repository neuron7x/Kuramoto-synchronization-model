# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

from tools.architecture.scanner import ArchitectureScanner

EXPECTED_ROOT_PACKAGES = {
    "core",
    "execution",
    "backtest",
    "analytics",
    "application",
    "geosync",
    "geosync_agent",
}
EXPECTED_MODULE_BASELINE = (
    1800  # Baseline module count captured on 2025-12-19; update if the repo size shifts materially.
)
# Use an 80% floor to catch substantial drops while allowing normal growth or small reorganisations.
MINIMUM_MODULE_COUNT_FLOOR = int(EXPECTED_MODULE_BASELINE * 0.8)


def test_repository_architecture_regression_guard() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = ArchitectureScanner(repo_root).scan()

    assert report.cycles == [], f"Dependency cycles detected: {report.cycles}"
    assert len(report.modules) >= MINIMUM_MODULE_COUNT_FLOOR

    package_roots = {name.split(".")[0] for name in report.modules}
    missing = EXPECTED_ROOT_PACKAGES.difference(package_roots)
    assert not missing, f"Missing expected root packages: {sorted(missing)}"


def test_architecture_scanner_skips_broken_symlinks(tmp_path: Path) -> None:
    package_root = tmp_path / "pkg"
    package_root.mkdir()
    (package_root / "__init__.py").write_text("")
    (package_root / "module.py").write_text("import os\n")

    # Simulate legacy symlink pointing to a removed file.
    broken_link = package_root / "orphaned.py"
    broken_link.symlink_to(tmp_path / "missing.py")

    report = ArchitectureScanner(tmp_path, include=[package_root]).scan()

    assert "pkg.module" in report.modules
    assert "pkg.orphaned" not in report.modules
