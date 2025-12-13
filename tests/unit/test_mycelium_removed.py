# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Ensure legacy mycelium_fractal_net package is fully detached."""

from __future__ import annotations

from pathlib import Path


def _scan(directory: Path, *, ignore: set[Path]) -> list[str]:
    hits: list[str] = []
    for path in directory.rglob("*.py"):
        if path.resolve() in ignore:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "mycelium_fractal_net" in text:
            hits.append(f"{path.relative_to(directory)}")
    return hits


def test_mycelium_package_not_present() -> None:
    """Fail if mycelium_fractal_net is referenced in runtime or tests."""
    repo_root = Path(__file__).resolve().parents[2]
    ignore = {Path(__file__).resolve()}
    occurrences = _scan(repo_root / "src", ignore=ignore) + _scan(
        repo_root / "tests", ignore=ignore
    )
    assert not occurrences, f"Found mycelium references: {occurrences}"
