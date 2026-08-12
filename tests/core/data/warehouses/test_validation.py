# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for warehouse identifier validation helpers."""

from __future__ import annotations

import httpx
import pytest

from core.data.warehouses._validators import ensure_identifier, ensure_timezone, literal
from core.data.warehouses.clickhouse import ClickHouseConfig, ClickHouseWarehouse
from core.data.warehouses.timescale import TimescaleConfig


def test_ensure_identifier_accepts_valid_names() -> None:
    assert ensure_identifier("alpha_01", label="identifier") == "alpha_01"


@pytest.mark.parametrize("value", ["", "drop table", "alpha-1", "1starts_with_digit"])
def test_ensure_identifier_rejects_invalid_names(value: str) -> None:
    with pytest.raises(ValueError):
        ensure_identifier(value, label="identifier")


@pytest.mark.parametrize("timezone", ["UTC", "Europe/London"])
def test_ensure_timezone_accepts_known_zones(timezone: str) -> None:
    assert ensure_timezone(timezone) == timezone


@pytest.mark.parametrize("timezone", ["", "UTC;DROP", "Europe/Lo'ndon"])
def test_ensure_timezone_rejects_invalid_zones(timezone: str) -> None:
    with pytest.raises(ValueError):
        ensure_timezone(timezone)


def test_literal_rejects_quotes() -> None:
    with pytest.raises(ValueError):
        literal("bad'value")


def test_clickhouse_config_validation_applies() -> None:
    with pytest.raises(ValueError):
        ClickHouseConfig(database="bad name")


def test_clickhouse_bootstrap_uses_sanitised_identifiers() -> None:
    client = httpx.Client(base_url="http://example.com")
    cfg = ClickHouseConfig(
        database="geosync", raw_table="ticks", rollup_table="bars"
    )
    warehouse = ClickHouseWarehouse(client, config=cfg)
    statements = warehouse.bootstrap_statements()
    for statement in statements:
        assert "DROP" not in statement.sql.upper()
    client.close()


def test_timescale_config_validation_applies() -> None:
    with pytest.raises(ValueError):
        TimescaleConfig(schema="bad-name")
