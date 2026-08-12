# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync connectors module - Exchange and data source connections.

This module provides access to exchange connectors and data source
integrations through the geosync namespace.

Example:
    >>> from geosync.connectors import test_connection
    >>> test_connection()
"""

from __future__ import annotations

__CANONICAL__ = True

import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def test_connection(exchange: str = "binance") -> bool:
    """Test connectivity to an exchange.

    Args:
        exchange: Name of the exchange to test (e.g., "binance", "kraken").

    Returns:
        True if connection test succeeds, False otherwise.

    Example:
        >>> from geosync.connectors import test_connection
        >>> test_connection("binance")
        True
    """
    try:
        import ccxt

        exchange_class = getattr(ccxt, exchange, None)
        if exchange_class is None:
            logger.warning(f"Unknown exchange: {exchange}")
            return False

        client = exchange_class()
        # Test by fetching markets - this doesn't require authentication
        client.load_markets()
        logger.info(f"Successfully connected to {exchange}")
        return True
    except Exception as exc:
        logger.error(f"Connection test failed for {exchange}: {exc}")
        return False


def list_supported_exchanges() -> list[str]:
    """Return a list of supported exchanges.

    Returns:
        List of exchange names supported by the platform.

    Example:
        >>> from geosync.connectors import list_supported_exchanges
        >>> exchanges = list_supported_exchanges()
        >>> "binance" in exchanges
        True
    """
    try:
        import ccxt

        return sorted(ccxt.exchanges)
    except ImportError:
        logger.warning("ccxt not installed - limited exchange support")
        return []


def get_exchange_info(exchange: str) -> Mapping[str, Any]:
    """Get information about an exchange.

    Args:
        exchange: Name of the exchange.

    Returns:
        Dictionary containing exchange metadata.
    """
    try:
        import ccxt

        exchange_class = getattr(ccxt, exchange, None)
        if exchange_class is None:
            return {"error": f"Unknown exchange: {exchange}"}

        client = exchange_class()
        return {
            "id": client.id,
            "name": client.name,
            "countries": getattr(client, "countries", []),
            "urls": getattr(client, "urls", {}),
            "has": {k: v for k, v in getattr(client, "has", {}).items() if v},
        }
    except Exception as exc:
        return {"error": str(exc)}


__all__ = [
    "test_connection",
    "list_supported_exchanges",
    "get_exchange_info",
]
