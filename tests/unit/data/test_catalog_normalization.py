# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from enum import Enum

import pytest

from core.data.catalog import normalize_symbol, normalize_venue


class InstrumentHint(Enum):
    FUTURE = "future"
    SPOT = "spot"


def test_normalize_venue_known_alias() -> None:
    assert normalize_venue("binance global") == "BINANCE"


def test_normalize_venue_unknown_returns_cleaned() -> None:
    assert normalize_venue(" custom ") == "CUSTOM"


def test_normalize_venue_rejects_blank() -> None:
    with pytest.raises(ValueError):
        normalize_venue("   ")


def test_normalize_symbol_spot_alias() -> None:
    assert normalize_symbol(" btcusdt ") == "BTC/USDT"


def test_normalize_symbol_derivative_with_hint() -> None:
    assert (
        normalize_symbol("ethusdt", instrument_type_hint=InstrumentHint.FUTURE)
        == "ETH-USDT"
    )


def test_normalize_symbol_with_string_hint() -> None:
    assert normalize_symbol("ethusdt", instrument_type_hint="spot") == "ETH/USDT"


def test_normalize_symbol_derivative_suffix_detection() -> None:
    assert normalize_symbol("btc_usdt_perp") == "BTC-USDT-PERP"


def test_normalize_symbol_single_leg() -> None:
    assert normalize_symbol("aapl") == "AAPL"


def test_normalize_symbol_known_quote_split() -> None:
    assert normalize_symbol("SOLUSD") == "SOL/USD"


def test_normalize_symbol_handles_custom_separator() -> None:
    assert (
        normalize_symbol("eth:usd", instrument_type_hint=InstrumentHint.SPOT)
        == "ETH/USD"
    )


def test_normalize_symbol_handles_unknown_quote_suffix() -> None:
    assert normalize_symbol("FOOBAR") == "FOOBAR"
