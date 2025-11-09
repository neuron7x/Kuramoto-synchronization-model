# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Live-trading exchange connector implementations."""
from __future__ import annotations

import logging
from typing import Mapping

from .base import RESTWebSocketConnector, SlidingWindowRateLimiter
from .binance import PLUGIN as BINANCE_PLUGIN
from .binance import BinanceRESTConnector
from .coinbase import PLUGIN as COINBASE_PLUGIN
from .coinbase import CoinbaseRESTConnector
from .kraken import PLUGIN as KRAKEN_PLUGIN
from .kraken import KrakenRESTConnector
from .plugin import (
    AdapterCheckResult,
    AdapterContract,
    AdapterDiagnostic,
    AdapterFactory,
    AdapterPlugin,
    AdapterRegistry,
)

logger = logging.getLogger("execution.adapters")


# Global registry initialised with built-in adapters. Additional adapters can be
# discovered dynamically via entry points or by calling ``registry.register``.
registry = AdapterRegistry()

for plugin in (BINANCE_PLUGIN, COINBASE_PLUGIN, KRAKEN_PLUGIN):
    try:
        registry.register(plugin, override=True)
    except ValueError:  # pragma: no cover - defensive guard
        logger.debug("Adapter %s already registered", plugin.contract.identifier)

# Attempt entry-point discovery eagerly so downstream code can immediately
# resolve external adapters. Failures are logged at debug level to avoid noisy
# startup in minimal environments.
try:  # pragma: no cover - exercised indirectly
    registry.discover()
except Exception as exc:  # pragma: no cover - defensive guard
    logger.debug("Adapter discovery failed during import", exc_info=exc)


def available_adapters() -> Mapping[str, AdapterContract]:
    """Return read-only mapping of registered adapter contracts."""

    return registry.contracts()


def load_adapter(identifier_or_path: str, /, **kwargs):
    """Instantiate an adapter using either a registry identifier or dotted path."""

    return registry.load(identifier_or_path, **kwargs)


def get_adapter_factory(identifier: str) -> AdapterFactory:
    """Retrieve the factory callable associated with an adapter."""

    return registry.get_factory(identifier)


def get_adapter_class(identifier: str):
    """Return the registered implementation class when available."""

    return registry.get_implementation(identifier)


__all__ = [
    "AdapterCheckResult",
    "AdapterContract",
    "AdapterDiagnostic",
    "AdapterFactory",
    "AdapterPlugin",
    "AdapterRegistry",
    "RESTWebSocketConnector",
    "SlidingWindowRateLimiter",
    "BinanceRESTConnector",
    "CoinbaseRESTConnector",
    "KrakenRESTConnector",
    "available_adapters",
    "get_adapter_class",
    "get_adapter_factory",
    "load_adapter",
    "registry",
]
