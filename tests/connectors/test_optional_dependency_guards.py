# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression guards: optional connector deps fail CLOSED, never crash-cascade.

Act Task 3 ("optional dependency failure must be a controlled error, not a crash
cascade") is already satisfied in code: ``ccxt``/``polygon`` are imported lazily
behind try/except. This locks that good state — the same ratchet doctrine the
package/import gates use — so a future edit cannot silently turn a guarded
optional import into a hard dependency that breaks the lightweight base install.

Each test hides an *installed* module via ``sys.modules[name] = None`` so the
lazy ``import`` inside the target re-executes and raises, proving the guard.
"""

from __future__ import annotations

import pytest


def test_base_retry_exceptions_survive_missing_ccxt(monkeypatch: pytest.MonkeyPatch) -> None:
    """base._default_retry_exceptions must degrade, not crash, without ccxt."""
    from core.data.adapters import base

    monkeypatch.setitem(__import__("sys").modules, "ccxt", None)
    exceptions = base._default_retry_exceptions()
    assert isinstance(exceptions, tuple)
    # ccxt.BaseError cannot be present when ccxt is unavailable.
    assert all(getattr(e, "__module__", "") != "ccxt" for e in exceptions)


def test_ccxt_factory_fails_closed_without_ccxt(monkeypatch: pytest.MonkeyPatch) -> None:
    """_load_exchange_factory must raise a controlled RuntimeError, not ImportError."""
    from core.data.adapters import ccxt as ccxt_adapter

    monkeypatch.setitem(__import__("sys").modules, "ccxt", None)
    monkeypatch.setitem(__import__("sys").modules, "ccxt.async_support", None)
    with pytest.raises(RuntimeError, match="ccxt must be installed"):
        ccxt_adapter._load_exchange_factory("binance")


def test_polygon_fetch_fails_closed_without_polygon(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_polygon_ohlcv must raise a controlled ImportError with an install hint."""
    from strategies import quantum_neural

    # The API-key check fires before the import guard; satisfy it so the test
    # reaches (and proves) the optional-dependency guard rather than the env check.
    monkeypatch.setenv("POLYGON_API_KEY", "test-key-not-used")
    monkeypatch.setitem(__import__("sys").modules, "polygon", None)
    with pytest.raises(ImportError, match="polygon-api-client"):
        quantum_neural.fetch_polygon_ohlcv("AAPL", days=1)
