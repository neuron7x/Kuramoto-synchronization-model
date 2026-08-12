# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import os
import time

import pytest
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tests.util.exchanges import (
    get_authenticated_balance,
    get_exchange_info_or_symbols,
    get_server_time,
    load_adapter_or_http_client,
)

EXCHANGE = os.getenv("EXCHANGE", "").lower()
CANARY = os.getenv("EXCHANGE_CANARY") == "1"

pytestmark = [
    pytest.mark.canary,
    pytest.mark.skipif(not CANARY, reason="Set EXCHANGE_CANARY=1 to run live canaries"),
]

SUPPORTED = ("binance", "coinbase", "kraken")


@pytest.fixture(scope="module")
def subject():
    if EXCHANGE not in SUPPORTED:
        pytest.skip(f"Unsupported or unspecified EXCHANGE: {EXCHANGE}")
    return load_adapter_or_http_client(EXCHANGE)


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
)
def _checked_time(subj):
    server_ts = get_server_time(subj)
    now = int(time.time() * 1000)
    assert abs(server_ts - now) < 5 * 60 * 1000
    return server_ts


def test_time_live(subject):
    _checked_time(subject)


def test_symbols_or_exchange_info_live(subject):
    info = get_exchange_info_or_symbols(subject)
    assert isinstance(info, dict) and len(info.get("symbols", [])) >= 5


@pytest.mark.live_balance
def test_authenticated_balance_live_readonly(subject):
    bal = get_authenticated_balance(subject)
    assert isinstance(bal, dict)
    sensitive_keys = {"apiKey", "secret", "signature"}
    flat = " ".join(map(str, bal.values()))
    for sk in sensitive_keys:
        assert sk not in flat.lower()
