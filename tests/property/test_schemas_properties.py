# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Optional

import pytest

try:
    from hypothesis import given
    from hypothesis import strategies as st
except Exception:  # pragma: no cover - hypothesis optional in runtime envs
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.utils.schemas import dataclass_to_json_schema, validate_against_schema


@dataclass
class PropertySample:
    timestamp: float
    price: float
    symbol: str
    tags: list[str]
    metadata: dict[str, int] = field(default_factory=dict)
    active: bool = True
    note: Optional[str] = None


SCHEMA = dataclass_to_json_schema(PropertySample)


_IDENTIFIER_CHARS = string.ascii_letters + string.digits + "_-"
_NOTE_CHARS = _IDENTIFIER_CHARS + " .:/"
_METADATA_KEYS = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta")
_SYMBOLS = ("BTCUSD", "ETHUSD", "AAPL", "MSFT", "EURUSD", "CL_F", "NQ_F")
_TAG_VALUES = ("ops", "latency", "risk", "alpha", "beta", "compliance", "infra")


@given(
    timestamp=st.floats(allow_nan=False, allow_infinity=False, width=32),
    price=st.floats(allow_nan=False, allow_infinity=False, width=32),
    symbol=st.sampled_from(_SYMBOLS),
    tags=st.lists(st.sampled_from(_TAG_VALUES), min_size=0, max_size=5),
    metadata=st.lists(
        st.tuples(st.sampled_from(_METADATA_KEYS), st.integers(min_value=0, max_value=1000)),
        min_size=0,
        max_size=5,
    ).map(lambda items: {key: value for key, value in items}),
    active=st.booleans(),
    note=st.one_of(st.none(), st.text(alphabet=_NOTE_CHARS, min_size=1, max_size=20)),
)
def test_generated_payloads_validate_against_schema(
    timestamp: float,
    price: float,
    symbol: str,
    tags: list[str],
    metadata: dict[str, int],
    active: bool,
    note: Optional[str],
) -> None:
    payload = {
        "timestamp": float(timestamp),
        "price": float(price),
        "symbol": symbol,
        "tags": tags,
        "metadata": metadata,
        "active": active,
    }
    if note is not None:
        payload["note"] = note

    assert validate_against_schema(payload, SCHEMA)
