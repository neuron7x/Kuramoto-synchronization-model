from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def test_metrics_module_imports_without_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure metrics module gracefully degrades when numpy is unavailable."""

    metrics_path = Path(__file__).resolve().parents[2] / "core" / "utils" / "metrics.py"
    spec = importlib.util.spec_from_file_location("core.utils.metrics_no_numpy", metrics_path)
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None

    original_numpy = sys.modules.pop("numpy", None)
    monkeypatch.setitem(sys.modules, "numpy", None)

    try:
        loader.exec_module(module)
    finally:
        # Restore the original numpy module (if any) and remove the temporary module reference.
        if original_numpy is not None:
            sys.modules["numpy"] = original_numpy
        else:
            sys.modules.pop("numpy", None)
        sys.modules.pop("core.utils.metrics_no_numpy", None)

    assert module._NUMPY_AVAILABLE is False
    assert module.np is None

    quantiles = module._fallback_quantiles([0.0, 0.25, 0.5, 0.75, 1.0], (0.5, 0.95, 0.99))
    assert quantiles[0.5] == pytest.approx(0.5)
    assert quantiles[0.95] == pytest.approx(0.95, rel=1e-9)
    assert quantiles[0.99] == pytest.approx(0.99, rel=1e-9)
