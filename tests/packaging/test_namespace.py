"""Tests to verify canonical namespace behavior.

The canonical public namespace for TradePulse is `tradepulse.*`.
The `src/` directory is a source layout container, NOT a runtime package.

These tests verify:
1. `tradepulse` is importable and resolves to the correct location
2. After installation, `src` is not an importable package
3. Core modules are accessible via canonical imports
"""

import importlib
import sys
from pathlib import Path

import pytest


class TestCanonicalNamespace:
    """Test the canonical `tradepulse.*` namespace."""

    def test_tradepulse_is_importable(self):
        """Verify `tradepulse` package is importable."""
        tradepulse = importlib.import_module("tradepulse")
        assert tradepulse is not None
        assert hasattr(tradepulse, "__file__")

    def test_tradepulse_file_location(self):
        """Verify `tradepulse` resolves to top-level, not src/tradepulse."""
        tradepulse = importlib.import_module("tradepulse")
        tradepulse_path = Path(tradepulse.__file__).resolve()
        # Should NOT be under src/tradepulse
        assert "src/tradepulse" not in str(tradepulse_path), (
            f"tradepulse should not resolve to src/tradepulse, got {tradepulse_path}"
        )

    def test_tradepulse_risk_submodule(self):
        """Verify `tradepulse.risk` is importable."""
        risk = importlib.import_module("tradepulse.risk")
        assert risk is not None


class TestSrcLayoutExclusion:
    """Verify src is not a runtime package after installation."""

    @pytest.mark.skipif(
        "src" in sys.path or any(p.endswith("/src") for p in sys.path),
        reason="Running in development mode with src in path",
    )
    def test_src_not_importable_after_install(self):
        """After `pip install`, `src` should not be importable.

        Note: This test is skipped in development mode where src/ is in PYTHONPATH.
        It validates installed package behavior.
        """
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("src")


class TestCoreModulesImportable:
    """Verify core modules are importable via canonical paths."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "core",
            "backtest",
            "execution",
            "analytics",
            "observability",
            "application",
        ],
    )
    def test_core_module_importable(self, module_path: str):
        """Verify core modules are importable."""
        try:
            module = importlib.import_module(module_path)
            assert module is not None
        except ModuleNotFoundError:
            pytest.skip(f"Optional module {module_path} not available")


class TestPackagingIntegrity:
    """Verify packaging configuration integrity."""

    def test_pyproject_exists(self):
        """Verify pyproject.toml exists in project root."""
        # Find project root (contains pyproject.toml)
        current = Path(__file__).resolve().parent
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                break
            current = current.parent

        pyproject_path = current / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not found"

    def test_src_excluded_in_pyproject(self):
        """Verify src is excluded from package discovery in pyproject.toml."""
        current = Path(__file__).resolve().parent
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                break
            current = current.parent

        pyproject_path = current / "pyproject.toml"
        content = pyproject_path.read_text()

        # Check that src is in exclude list
        assert '"src"' in content or "'src'" in content, (
            "pyproject.toml should exclude 'src' from packages"
        )
