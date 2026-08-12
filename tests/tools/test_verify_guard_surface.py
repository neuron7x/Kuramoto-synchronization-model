from __future__ import annotations

from scripts.verify_guard_surface import main


def test_verify_guard_surface_passes() -> None:
    assert main() == 0
