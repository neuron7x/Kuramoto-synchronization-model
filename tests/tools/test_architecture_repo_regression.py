from __future__ import annotations

from pathlib import Path

from tools.architecture.scanner import ArchitectureScanner

EXPECTED_ROOT_PACKAGES = {
    "core",
    "execution",
    "backtest",
    "analytics",
    "application",
    "tradepulse",
    "tradepulse_agent",
}
EXPECTED_MODULE_BASELINE = 1800  # Baseline module count captured on 2025-12-19; update if the repo size shifts materially.
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
