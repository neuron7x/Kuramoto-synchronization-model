from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tools.audit.render_stats_md import generate
from tools.audit.serotonin_test_stats import collect_serotonin_stats
from tools.audit.thermo_test_stats import collect_thermo_stats


def _write_python(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _make_minimal_package(base: Path) -> None:
    _write_python(base / "src/tradepulse/__init__.py", "")
    _write_python(base / "src/tradepulse/core/__init__.py", "")
    _write_python(base / "src/tradepulse/core/neuro/__init__.py", "")
    _write_python(
        base / "src/tradepulse/core/neuro/serotonin/__init__.py",
        '__version__ = "9.9.9"\n',
    )
    _write_python(
        base / "runtime/thermo_config.py",
        '__version__ = "1.2.3"\n',
    )


def _make_tests(base: Path) -> None:
    _write_python(
        base / "tests/test_serotonin_dummy.py",
        "def test_ok():\n    assert True\n",
    )
    _write_python(
        base / "tests/test_thermo_dummy.py",
        "def test_ok():\n    assert True\n",
    )


def test_serotonin_stats_collects_counts(tmp_path: Path) -> None:
    _make_tests(tmp_path)
    stats = collect_serotonin_stats(tmp_path)
    assert stats["collected_tests_count"] == 1
    assert stats["test_files"] == ["tests/test_serotonin_dummy.py"]
    timestamp = datetime.fromisoformat(stats["last_run_timestamp"])
    assert timestamp.tzinfo is not None
    assert timestamp.tzinfo.utcoffset(timestamp) == timezone.utc.utcoffset(timestamp)


def test_thermo_stats_collects_counts(tmp_path: Path) -> None:
    _make_tests(tmp_path)
    stats = collect_thermo_stats(tmp_path)
    assert stats["collected_tests_count"] == 1
    assert stats["test_files"] == ["tests/test_thermo_dummy.py"]
    timestamp = datetime.fromisoformat(stats["last_run_timestamp"])
    assert timestamp.tzinfo is not None
    assert timestamp.tzinfo.utcoffset(timestamp) == timezone.utc.utcoffset(timestamp)


def test_render_stats_md_uses_versions_and_counts(tmp_path: Path) -> None:
    _make_minimal_package(tmp_path)
    _make_tests(tmp_path)
    output_dir = tmp_path / "docs/_generated"
    generate(tmp_path, output_dir)

    serotonin_md = (output_dir / "serotonin_stats.md").read_text(encoding="utf-8")
    thermo_md = (output_dir / "thermo_stats.md").read_text(encoding="utf-8")

    assert "9.9.9" in serotonin_md
    assert "1.2.3" in thermo_md
    assert "tests/test_serotonin_dummy.py" in serotonin_md
    assert "tests/test_thermo_dummy.py" in thermo_md
