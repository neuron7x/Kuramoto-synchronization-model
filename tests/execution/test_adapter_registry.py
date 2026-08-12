# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the execution adapter plugin registry."""

from __future__ import annotations

from importlib import import_module
from typing import Mapping

import pytest

from execution.adapters import (
    AdapterCheckResult,
    AdapterContract,
    AdapterDiagnostic,
    AdapterPlugin,
    AdapterRegistry,
    BinanceRESTConnector,
    KrakenRESTConnector,
    available_adapters,
    get_adapter_class,
    load_adapter,
)
from execution.connectors import ExecutionConnector

adapter_plugin_module = import_module("execution.adapters.plugin")


class _DummyConnector(ExecutionConnector):
    def __init__(self, *, sandbox: bool = True, token: str | None = None) -> None:
        super().__init__(sandbox=sandbox)
        self.token = token

    def place_order(
        self, order, *, idempotency_key: str | None = None
    ):  # pragma: no cover - dummy implementation
        raise NotImplementedError

    def cancel_order(self, order_id: str) -> bool:  # pragma: no cover - dummy implementation
        raise NotImplementedError

    def fetch_order(self, order_id: str):  # pragma: no cover - dummy implementation
        raise NotImplementedError

    def open_orders(self):  # pragma: no cover - dummy implementation
        return []

    def get_positions(self):  # pragma: no cover - dummy implementation
        return []


def test_registry_register_and_self_test() -> None:
    registry = AdapterRegistry()
    contract = AdapterContract(
        identifier="dummy.test",
        name="Dummy",
        provider="Unit Tests",
        version="1.0.0",
        description="Dummy connector for registry tests",
        transports={"rest": "https://example.com"},
        supports_sandbox=True,
        required_credentials=("token",),
        capabilities={"orders": True},
    )

    def _self_test() -> AdapterDiagnostic:
        return AdapterDiagnostic(
            adapter_id="dummy.test",
            checks=(AdapterCheckResult(name="init", status="passed", detail="Constructed"),),
        )

    plugin = AdapterPlugin(
        contract=contract,
        factory=_DummyConnector,
        implementation=_DummyConnector,
        self_test=_self_test,
        module=__name__,
    )

    registry.register(plugin)

    instance = registry.create("dummy.test", sandbox=False, token="abc")
    assert isinstance(instance, _DummyConnector)
    assert instance.token == "abc"
    assert instance.sandbox is False

    diagnostics = registry.self_test("dummy.test")
    assert diagnostics.passed

    contracts: Mapping[str, AdapterContract] = registry.contracts()
    assert contracts["dummy.test"].provider == "Unit Tests"


def test_registry_discover_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = AdapterRegistry()

    contract = AdapterContract(
        identifier="dummy.discovered",
        name="Discovered",
        provider="Unit Tests",
        version="0.1.0",
        description="Discovered connector",
    )

    plugin = AdapterPlugin(contract=contract, factory=_DummyConnector, module=__name__)

    class _EntryPoint:
        def __init__(self, name: str, group: str) -> None:
            self.name = name
            self.group = group

        def load(self):
            return plugin

    class _EntryPoints(list):
        def select(self, *, group: str):
            return _EntryPoints([ep for ep in self if ep.group == group])

    entry_points = _EntryPoints([_EntryPoint("dummy", "geosync.execution.adapters")])
    monkeypatch.setattr(adapter_plugin_module.metadata, "entry_points", lambda: entry_points)

    registry.discover()
    assert "dummy.discovered" in registry.identifiers()


def test_load_adapter_supports_dotted_paths() -> None:
    connector = load_adapter("execution.adapters.BinanceRESTConnector", sandbox=True)
    assert isinstance(connector, BinanceRESTConnector)
    kraken = load_adapter("execution.adapters.KrakenRESTConnector", sandbox=True)
    assert isinstance(kraken, KrakenRESTConnector)


def test_available_adapters_contains_builtins() -> None:
    contracts = available_adapters()
    assert "binance.spot" in contracts
    assert contracts["binance.spot"].provider == "Binance"
    klass = get_adapter_class("binance.spot")
    assert klass is BinanceRESTConnector
    assert "kraken.spot" in contracts
    assert contracts["kraken.spot"].provider == "Kraken"
    kraken_class = get_adapter_class("kraken.spot")
    assert kraken_class is KrakenRESTConnector
