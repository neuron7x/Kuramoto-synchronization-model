"""Closure tests for the version SSOT gate — REL-008.

POSITIVE: against the real repository, every bound surface agrees → exit 0.
NEGATIVE: in an isolated tmp copy, perturbing any single surface → non-zero.

The negative cases prove the gate is *falsifiable* — a silent drift on any one
surface must flip the verdict red. A gate that cannot go red is not a gate.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "ci" / "check_version_ssot.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_version_ssot", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


# --------------------------------------------------------------------------- #
# POSITIVE
# --------------------------------------------------------------------------- #
def test_positive_real_repo_all_surfaces_agree() -> None:
    """The live repository must pass fail-closed at exit 0."""
    rc = gate.main(["--repo-root", str(REPO_ROOT)])
    assert rc == 0, "real repo SSOT surfaces diverged"


def test_canonical_version_is_wellformed() -> None:
    canonical = gate.read_canonical_version(REPO_ROOT)
    assert gate._VERSION_RE.match(canonical), canonical
    # SSOT must equal CITATION.cff (the intended-release signal).
    results = {r.name: r for r in gate.check(REPO_ROOT)[1]}
    assert results["CITATION.cff:version"].ok


# --------------------------------------------------------------------------- #
# NEGATIVE fixture — an isolated, perturbable copy of the four file surfaces.
# --------------------------------------------------------------------------- #
_SURFACE_FILES = ("VERSION", "CITATION.cff", "pyproject.toml", "CHANGELOG.md")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    for name in _SURFACE_FILES:
        shutil.copy2(REPO_ROOT / name, tmp_path / name)
    return tmp_path


def test_negative_baseline_copy_still_passes(tmp_repo: Path) -> None:
    """Sanity: an unperturbed copy passes (isolates the perturbation as cause)."""
    assert gate.main(["--repo-root", str(tmp_repo)]) == 0


def test_negative_perturb_version_file(tmp_repo: Path) -> None:
    (tmp_repo / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    # SSOT itself moved; now every other surface diverges from it.
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1


def test_negative_perturb_citation(tmp_repo: Path) -> None:
    path = tmp_repo / "CITATION.cff"
    text = path.read_text(encoding="utf-8")
    # Perturb ONLY the top-level `version:` (a leading-anchored line).
    perturbed = text.replace("\nversion: 1.1.0", "\nversion: 9.9.9", 1)
    assert perturbed != text, "fixture assumption broke: version line not found"
    path.write_text(perturbed, encoding="utf-8")
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1


def test_negative_perturb_scm_fallback(tmp_repo: Path) -> None:
    path = tmp_repo / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    perturbed = text.replace('fallback_version = "1.1.0"', 'fallback_version = "0.0.1"')
    assert perturbed != text, "fixture assumption broke: fallback_version not found"
    path.write_text(perturbed, encoding="utf-8")
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1


def test_negative_remove_changelog_heading(tmp_repo: Path) -> None:
    path = tmp_repo / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    perturbed = text.replace("## [1.1.0]", "## [1.1.0-REMOVED]")
    assert perturbed != text, "fixture assumption broke: 1.1.0 heading not found"
    path.write_text(perturbed, encoding="utf-8")
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1


def test_negative_missing_ssot_fails_closed(tmp_repo: Path) -> None:
    (tmp_repo / "VERSION").unlink()
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1


def test_negative_empty_ssot_fails_closed(tmp_repo: Path) -> None:
    (tmp_repo / "VERSION").write_text("", encoding="utf-8")
    assert gate.main(["--repo-root", str(tmp_repo)]) == 1
