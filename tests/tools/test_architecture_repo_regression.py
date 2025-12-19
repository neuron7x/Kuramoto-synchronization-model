from __future__ import annotations

from pathlib import Path

from tools.architecture.scanner import ArchitectureScanner


def test_repository_architecture_regression_guard() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report = ArchitectureScanner(repo_root).scan()

    assert report.cycles == [], f"Dependency cycles detected: {report.cycles}"
    assert len(report.modules) > 200

    expected_roots = {
        "core",
        "execution",
        "backtest",
        "analytics",
        "application",
        "tradepulse",
        "tradepulse_agent",
    }
    missing = expected_roots.difference(report.modules)
    assert not missing, f"Missing expected root packages: {sorted(missing)}"
