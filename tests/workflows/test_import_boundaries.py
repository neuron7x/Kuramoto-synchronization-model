"""Import-linter contract tests.

Two contracts:

1. The shipping `.importlinter` config is in good shape:
   `lint-imports` exits 0 on the current tree.

2. An intentional cross-layer import injected into a temporary tree fails
   the contract — i.e. the contracts actually catch what they claim to
   catch. This is the load-bearing regression case for architectural
   boundary enforcement.

The injection test runs `lint-imports` against a temporary copy of the
repository with one extra import added; it does NOT mutate the live tree.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IMPORTLINTER_CFG = REPO_ROOT / ".importlinter"


def _has_lint_imports() -> bool:
    return shutil.which("lint-imports") is not None


@pytest.fixture(scope="module")
def lint_imports_available() -> bool:
    return _has_lint_imports()


def _run_lint_imports(cwd: Path) -> subprocess.CompletedProcess[str]:
    # Force UTF-8 decoding: lint-imports prints a box-drawing banner, which a
    # subprocess inheriting an ascii locale (as on some CI runners) cannot decode
    # under text=True's default encoding. errors="replace" keeps the captured
    # output usable for the assertions below.
    return subprocess.run(
        ["lint-imports", "--no-cache"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _expected_contract_count(repo_root: Path) -> int:
    """Number of contracts declared in .importlinter (derived, not hardcoded)."""
    config = (repo_root / ".importlinter").read_text(encoding="utf-8")
    return sum(1 for line in config.splitlines() if line.startswith("[importlinter:contract:"))


def test_importlinter_config_exists() -> None:
    assert IMPORTLINTER_CFG.exists(), f".importlinter not found at {IMPORTLINTER_CFG}"


def test_shipping_contracts_are_kept(lint_imports_available: bool) -> None:
    """`lint-imports` exits 0 on the current tree."""
    if not lint_imports_available:
        pytest.skip("lint-imports CLI not on PATH")
    result = _run_lint_imports(REPO_ROOT)
    assert result.returncode == 0, (
        f"lint-imports failed unexpectedly:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    expected = _expected_contract_count(REPO_ROOT)
    assert (
        f"Contracts: {expected} kept, 0 broken" in result.stdout
    ), f"expected exactly {expected} contracts kept and 0 broken; got:\n{result.stdout}"


def test_intentional_violation_is_detected(tmp_path: Path, lint_imports_available: bool) -> None:
    """Inject a cross-layer import that is NOT on the ignore list and
    confirm `lint-imports` flags it.

    We pick `core.physics -> application` because:
      - Contract 2 (core.physics-hardened) forbids it.
      - There are no current `core.physics -> application` imports, so the
        injection produces a fresh violation that the ignore list does not
        suppress.
    """
    if not lint_imports_available:
        pytest.skip("lint-imports CLI not on PATH")

    # Copy the parts of the tree that lint-imports needs.  Keep the copy
    # minimal: source packages + the contract config.
    copy_root = tmp_path / "repo"
    copy_root.mkdir()
    for entry in (
        "core",
        "application",
        "execution",
        "runtime",
        "apps",
        "interfaces",
        "libs",
    ):
        src = REPO_ROOT / entry
        if src.exists():
            shutil.copytree(
                src,
                copy_root / entry,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
    shutil.copy(IMPORTLINTER_CFG, copy_root / ".importlinter")

    # Inject a cross-layer import that violates Contract 2.
    inject_path = copy_root / "core" / "physics" / "_injected_for_lintest.py"
    # The application package always exists; pick a real public symbol so the
    # graph builder accepts the edge.
    inject_path.write_text(
        "# Intentional violation for the import-boundary regression test.\n"
        "from application import api  # noqa: F401  (test-only injection)\n",
        encoding="utf-8",
    )

    result = _run_lint_imports(copy_root)
    assert result.returncode != 0, (
        "lint-imports should have flagged the injected core.physics -> "
        "application import but exited 0:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "core.physics" in combined and "application" in combined, (
        "expected the violation report to mention core.physics and application; got:\n" + combined
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
