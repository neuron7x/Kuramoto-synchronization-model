from __future__ import annotations

from pathlib import Path

from tools.patch_makefile_geosync_coverage import NEW, OLD, EXPECTED_REPLACEMENTS, main, patch_text


def _makefile_text() -> str:
    block = f"pytest tests/ \\\n\t\t{OLD} \\\n\t\t--cov-report=xml\n"
    return block * EXPECTED_REPLACEMENTS


def test_patch_text_replaces_expected_surface() -> None:
    patched, count = patch_text(_makefile_text())

    assert count == EXPECTED_REPLACEMENTS
    # OLD is a prefix of NEW, so it necessarily remains a substring after
    # the append. The real invariant is that every shortcut now carries
    # the geosync coverage flag.
    assert "--cov=geosync" in patched
    assert patched.count(NEW) == EXPECTED_REPLACEMENTS


def test_check_mode_reports_needed_patch(tmp_path: Path, capsys) -> None:
    target = tmp_path / "Makefile"
    target.write_text(_makefile_text(), encoding="utf-8")

    assert main([str(target), "--check"]) == 1
    assert capsys.readouterr().out.strip() == f"needs_patch:{EXPECTED_REPLACEMENTS}"


def test_write_mode_is_idempotent(tmp_path: Path, capsys) -> None:
    target = tmp_path / "Makefile"
    target.write_text(_makefile_text(), encoding="utf-8")

    assert main([str(target)]) == 0
    assert capsys.readouterr().out.strip() == f"patched:{EXPECTED_REPLACEMENTS}"
    assert main([str(target), "--check"]) == 0
    assert capsys.readouterr().out.strip() == "ok"
    assert main([str(target)]) == 0
    assert capsys.readouterr().out.strip() == "unchanged"
