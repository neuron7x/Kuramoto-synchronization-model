from __future__ import annotations

from pathlib import Path


def test_tradepulse_import_resolves_to_src() -> None:
    import tradepulse

    pkg_path = Path(tradepulse.__file__).resolve()
    assert Path("src/tradepulse").resolve() in pkg_path.parents
