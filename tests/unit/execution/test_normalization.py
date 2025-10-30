# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for exchange lot and tick mapping in the normalizer."""

from __future__ import annotations

import pytest

from execution.normalization import (
    NormalizationError,
    SymbolNormalizer,
    SymbolSpecification,
)


def _build_normalizer() -> SymbolNormalizer:
    specs = {
        "ETHUSDT": SymbolSpecification(
            symbol="ETHUSDT",
            min_qty=0.01,
            min_notional=10.0,
            step_size=0.01,
            tick_size=0.05,
        )
    }
    symbol_map = {"ETH-USD": "ETHUSDT", "ethusd": "ETHUSDT"}
    return SymbolNormalizer(symbol_map=symbol_map, specifications=specs)


def test_symbol_normalizer_alias_rounding() -> None:
    normalizer = _build_normalizer()

    spec = normalizer.specification("eth_usd")
    assert spec is not None and spec.symbol == "ETHUSDT"

    rounded_qty = normalizer.round_quantity("ETH-USD", 1.234)
    assert rounded_qty == pytest.approx(1.23)

    rounded_price = normalizer.round_price("ethusd", 2010.027)
    assert rounded_price == pytest.approx(2010.05)


def test_symbol_normalizer_alias_validation_constraints() -> None:
    normalizer = _build_normalizer()

    with pytest.raises(NormalizationError):
        normalizer.validate("ETH_USD", 0.005, 2000.0)

    with pytest.raises(NormalizationError):
        normalizer.validate("ETH-USD", 0.01, 900.0)

    normalizer.validate("ETHUSDT", 0.02, 2000.0)


def test_symbol_normalizer_detects_step_alignment_issues() -> None:
    normalizer = _build_normalizer()

    with pytest.raises(NormalizationError, match="step size"):
        normalizer.validate("ETHUSDT", 0.0150000001, 2010.0)

    with pytest.raises(NormalizationError, match="tick size"):
        normalizer.validate("ETHUSDT", 0.02, 2010.051)

    # Small floating point noise around valid increments should be tolerated.
    normalizer.validate("ETHUSDT", 0.020000000000001, 2010.0000000004)


def test_symbol_normalizer_rounding_is_stable() -> None:
    normalizer = _build_normalizer()

    # Values near tick/step boundaries should round deterministically.
    assert normalizer.round_quantity("ETHUSDT", 0.0150000001) == pytest.approx(0.02)
    assert normalizer.round_quantity("ETHUSDT", 0.0149999998) == pytest.approx(0.01)
    assert normalizer.round_price("ETHUSDT", 2010.0249999997) == pytest.approx(2010.0)
    assert normalizer.round_price("ETHUSDT", 2010.0250000002) == pytest.approx(2010.05)


def test_symbol_normalizer_enforces_minuscule_steps() -> None:
    spec = SymbolSpecification(
        symbol="NANOCAP",
        min_qty=0.0,
        min_notional=0.0,
        step_size=1e-13,
        tick_size=1e-13,
    )
    normalizer = SymbolNormalizer(specifications={spec.symbol: spec})

    # Perfectly aligned quantities and prices should still validate.
    normalizer.validate("NANOCAP", 2e-13, 3e-13)

    # Misaligned values below the tolerance threshold must be rejected.
    with pytest.raises(NormalizationError, match="step size"):
        normalizer.validate("NANOCAP", 1.5e-13, 3e-13)
    with pytest.raises(NormalizationError, match="tick size"):
        normalizer.validate("NANOCAP", 2e-13, 3.4e-13)
