# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""A governed coverage surface must point at code that exists.

`configs/quality/coverage_targets.toml` declares, per surface, a floor and the paths the
floor applies to. Nothing checked that those paths resolve — and four of them did not.
`ingestion` pointed at `ingestion/` and `data/`; `risk` pointed at `risk/` and
`geosync/core/risk`. None of those directories existed. Both surfaces carried a
`claim_risk = "critical"`/`"high"` label and a 90–95% target, and both measured nothing.

That is the worst failure mode a quality gate has: not a red gate, but a green one with no
subject. A floor over an empty set is satisfied vacuously, so the surface reads as governed
in every report while no line of code is under it. The same shape hid `geosync/risk/` — a
real risk package — from coverage governance entirely, because no surface claimed it.

The rule below is the cheapest possible closure: every declared path must exist. It cannot
tell you the floor is right, but it makes "governed" mean "governs something".
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "configs" / "quality" / "coverage_targets.toml"

_SURFACES: dict[str, dict] = tomllib.loads(TARGETS.read_text(encoding="utf-8"))["surfaces"]


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_every_surface_path_exists(surface: str) -> None:
    paths = list(_SURFACES[surface].get("paths", []))
    assert paths, f"surface {surface!r} declares no paths — it governs nothing"

    missing = [p for p in paths if not (ROOT / p).exists()]
    assert not missing, (
        f"coverage surface {surface!r} points at paths that do not exist: {missing}. "
        "A floor over a nonexistent path is satisfied vacuously; the surface reports as "
        "governed while measuring no code. Repoint it or delete it."
    )


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_every_surface_path_holds_python(surface: str) -> None:
    """Existence is not enough: the path must actually contain measurable Python."""
    for rel in _SURFACES[surface].get("paths", []):
        target = ROOT / rel
        if target.is_file():
            assert target.suffix == ".py", f"{surface}: {rel} is not a Python file"
            continue
        assert any(target.rglob("*.py")), (
            f"coverage surface {surface!r} declares {rel!r}, which holds no Python module. "
            "Coverage over a directory with no code is a vacuous floor."
        )
