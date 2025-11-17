# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import pytest

from tests.util.exchanges import (
    get_exchange_info_or_symbols,
    get_server_time,
    load_adapter_or_http_client,
)

EXCHANGES = ("binance", "coinbase", "kraken")


@pytest.mark.parametrize("exchange", EXCHANGES)
def test_public_time_recorded(exchange):
    subj = load_adapter_or_http_client(exchange)
    ts = get_server_time(subj)
    assert isinstance(ts, int) and ts > 0


@pytest.mark.parametrize("exchange", EXCHANGES)
def test_public_symbols_recorded(exchange):
    subj = load_adapter_or_http_client(exchange)
    info = get_exchange_info_or_symbols(subj)
    assert (
        "symbols" in info
        and isinstance(info["symbols"], list)
        and len(info["symbols"]) > 0
    )
