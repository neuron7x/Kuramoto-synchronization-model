# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Guardrail to prevent stub code from shipping in the tradepulse package."""

from __future__ import annotations

import re
from pathlib import Path


def test_no_stub_markers_in_tradepulse_package() -> None:
    """Ensure runtime package ships without placeholders or TODOs."""
    root = Path(__file__).resolve().parents[2] / "src" / "tradepulse"
    pattern = re.compile(r"(NotImplementedError|stub|skeleton|TODO|FIXME|TBD)", re.IGNORECASE)

    matches: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            matches.append(f"{path.relative_to(root)}:{match.group(0)}")

    assert not matches, "Found stub markers in tradepulse package:\n" + "\n".join(matches)
