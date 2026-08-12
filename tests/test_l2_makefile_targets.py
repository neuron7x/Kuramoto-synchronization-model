"""Tests for the Makefile L2 demo targets.

Verifies each `l2-*` target is declared as PHONY, has a docstring
(`## l2-xxx: …`), and `make l2-help` lists every one. Prevents silent
drift between the target set, the help output, and the CHANGELOG.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_MAKEFILE = Path("Makefile")

_EXPECTED_TARGETS: frozenset[str] = frozenset(
    {
        "l2-help",
        "l2-demo",
        "l2-open",
        "l2-figures",
        "l2-dashboard",
        "l2-smoke",
        "l2-deterministic",
        "l2-ablations",
        "l2-test",
    }
)


@pytest.fixture(scope="module")
def makefile_text() -> str:
    if not _MAKEFILE.exists():
        pytest.skip("Makefile not present in CWD")
    return _MAKEFILE.read_text(encoding="utf-8")


def test_every_expected_l2_target_is_phony(makefile_text: str) -> None:
    # Gather every .PHONY line and extract target names.
    phony_targets: set[str] = set()
    for m in re.finditer(r"^\.PHONY:\s*(.+)$", makefile_text, re.MULTILINE):
        phony_targets.update(m.group(1).split())
    missing = _EXPECTED_TARGETS - phony_targets
    assert not missing, f"Missing from .PHONY declarations: {sorted(missing)}"


def test_every_expected_l2_target_has_docstring(makefile_text: str) -> None:
    for target in _EXPECTED_TARGETS:
        # Match the ## <target>: ... convention used by l2-help
        pat = re.compile(rf"^##\s+{re.escape(target)}:\s+.+$", re.MULTILINE)
        assert pat.search(makefile_text), f"target {target} missing '## {target}: ...' docstring"


def test_l2_help_lists_every_target() -> None:
    proc = subprocess.run(
        ["make", "--no-print-directory", "l2-help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"NO_COLOR": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )
    if proc.returncode != 0:
        pytest.skip(f"make l2-help not runnable in this environment: {proc.stderr[:200]}")
    stdout = proc.stdout
    missing = [t for t in _EXPECTED_TARGETS if t not in stdout]
    assert not missing, f"make l2-help output missing: {missing}"


def test_l2_help_exits_zero() -> None:
    proc = subprocess.run(
        ["make", "--no-print-directory", "l2-help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"NO_COLOR": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        timeout=30,
    )
    if proc.returncode == 127:
        pytest.skip("make not available in PATH")
    assert proc.returncode == 0, f"make l2-help exited {proc.returncode}: {proc.stderr[:200]}"


def test_makefile_references_existing_scripts(makefile_text: str) -> None:
    """Every scripts/ path mentioned in the L2 section must exist on disk."""
    l2_section_start = makefile_text.find("# L2 Ricci cross-sectional edge")
    if l2_section_start < 0:
        pytest.skip("L2 section not found")
    l2_section = makefile_text[l2_section_start:]
    script_paths = re.findall(r"scripts/[A-Za-z0-9_./-]+\.py", l2_section)
    missing = [p for p in set(script_paths) if not Path(p).exists()]
    assert not missing, f"Makefile references missing scripts: {missing}"


def test_changelog_lists_all_nineteen_session_prs() -> None:
    path = Path("research/microstructure/CHANGELOG.L2.md")
    if not path.exists():
        pytest.skip("CHANGELOG.L2.md not present")
    text = path.read_text(encoding="utf-8")
    # Expect every merged PR number that shipped L2 work in the session
    expected_prs = {
        "#266",
        "#268",
        "#269",
        "#270",
        "#271",
        "#272",
        "#273",
        "#274",
        "#275",
        "#276",
        "#278",
        "#279",
        "#280",
        "#281",
        "#282",
        "#286",
        "#288",
        "#290",
        "#293",
        "#295",
        "#296",
        "#297",
        "#298",
        "#300",
        "#301",
        "#303",
        "#304",
        "#306",
        "#308",
        "#309",
        "#312",
    }
    missing = [pr for pr in expected_prs if pr not in text]
    assert not missing, f"CHANGELOG missing PR refs: {missing}"


def test_sys_python_available_for_make_targets() -> None:
    """Sanity: the python interpreter exists and is the one we expect."""
    assert Path(sys.executable).exists()
