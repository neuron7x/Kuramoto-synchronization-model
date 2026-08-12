"""T8: no TODO / FIXME / HACK / XXX stale markers in the module."""

from __future__ import annotations

import re
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[3] / "core" / "cross_asset_kuramoto"
PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")


def test_no_stale_markers_in_module() -> None:
    offenders: list[str] = []
    for path in sorted(MODULE_DIR.rglob("*.py")):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if PATTERN.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "stale markers:\n" + "\n".join(offenders)
