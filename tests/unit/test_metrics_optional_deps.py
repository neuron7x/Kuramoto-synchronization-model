# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _exec_metrics_without_numpy(monkeypatch: pytest.MonkeyPatch) -> object:
    """Import ``core.utils.metrics`` with numpy forced absent, then restore.

    The numpy override is applied with ``monkeypatch.setitem`` while numpy is
    still present, so monkeypatch captures the *real* module object, and undone
    synchronously with ``monkeypatch.undo()`` in ``finally`` (rather than at
    fixture teardown) so ``sys.modules`` is consistent the instant this helper
    returns.

    Why this care is needed: an earlier version did
    ``original = sys.modules.pop("numpy", None)`` and *then*
    ``monkeypatch.setitem(sys.modules, "numpy", None)``. Popping first made
    monkeypatch record numpy as ABSENT, so its teardown DELETED
    ``sys.modules["numpy"]`` — silently overriding the manual restore. The next
    ``import numpy`` re-imported a fresh module object whose ``random``
    attribute was never bound (``numpy.random`` was still cached in
    ``sys.modules``), so any later ``np.random.<attr>`` recursed forever inside
    numpy's lazy ``__getattr__`` (``import numpy.random as random`` →
    ``getattr(numpy, "random")`` → ``__getattr__`` → …). Unrelated downstream
    tests (e.g. ``tests/validation/test_gaussian_null_sufficiency.py``) then
    died with ``RecursionError``.
    """
    metrics_path = Path(__file__).resolve().parents[2] / "core" / "utils" / "metrics.py"
    spec = importlib.util.spec_from_file_location("core.utils.metrics_no_numpy", metrics_path)
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert loader is not None

    monkeypatch.setitem(sys.modules, "numpy", None)
    try:
        loader.exec_module(module)
    finally:
        # Restore numpy NOW (not at fixture teardown) and drop the temp module.
        monkeypatch.undo()
        sys.modules.pop("core.utils.metrics_no_numpy", None)
    return module


def test_metrics_module_imports_without_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure metrics module gracefully degrades when numpy is unavailable."""

    module = _exec_metrics_without_numpy(monkeypatch)

    assert module._NUMPY_AVAILABLE is False
    assert module.np is None

    quantiles = module._fallback_quantiles([0.0, 0.25, 0.5, 0.75, 1.0], (0.5, 0.95, 0.99))
    assert quantiles[0.5] == pytest.approx(0.5)
    assert quantiles[0.95] == pytest.approx(0.95, rel=1e-9)
    assert quantiles[0.99] == pytest.approx(0.99, rel=1e-9)


def test_no_numpy_degradation_leaves_numpy_random_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the no-numpy import path must not corrupt ``sys.modules``.

    Pins the contract whose breach produced the ``RecursionError`` in the main
    validation suite (run 28126273069): after exercising the numpy-absent
    branch, ``numpy`` must still be the real, cached module and ``np.random``
    must resolve without recursing through numpy's lazy ``__getattr__``.
    """
    import numpy as np

    real_numpy = sys.modules.get("numpy")

    _exec_metrics_without_numpy(monkeypatch)

    # The cached top-level module object must be intact (not deleted/replaced).
    assert sys.modules.get("numpy") is real_numpy
    # numpy.random must still be reachable as a bound attribute — the failure
    # mode was an infinite getattr loop on this exact access.
    rng = np.random.default_rng(7)
    draws = rng.standard_normal(4)
    assert draws.shape == (4,)
    assert bool(np.all(np.isfinite(draws)))
