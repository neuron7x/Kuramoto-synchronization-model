# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Canonical dictionaries for venues/instruments and normalization helpers.

The ingestion and execution boundaries frequently receive heterogeneous
identifiers coming from external providers.  Centralising the mapping logic
here makes sure the rest of the codebase can rely on consistent, canonical
codes.  The helpers intentionally take a permissive approach – they normalise
capitalisation, trim whitespace, standardise separators and map well-known
aliases, while still returning the original code for unknown venues so that
callers can decide how strict to be.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Iterable, List, Mapping, Sequence

__all__ = [
    "normalize_symbol",
    "normalize_venue",
]

# -- Venue canonicalisation ----------------------------------------------------

_CANONICAL_VENUES: Mapping[str, Sequence[str]] = {
    "BINANCE": ("BINANCE", "BINANCE-SPOT", "BINANCE GLOBAL"),
    "BINANCE_FUTURES": (
        "BINANCE_FUTURES",
        "BINANCE-FUTURES",
        "BINANCE PERP",
        "BINANCEUSDM",
    ),
    "COINBASE": ("COINBASE", "COINBASE-PRO", "GDAX"),
    "KRAKEN": ("KRAKEN",),
    "BITFINEX": ("BITFINEX",),
    "POLYGON": ("POLYGON", "POLYGON.IO"),
    "ALPACA": ("ALPACA", "ALPACA-MARKETS"),
    "CSV": ("CSV",),
}

_VENUE_LOOKUP: Dict[str, str] = {}
for canonical, aliases in _CANONICAL_VENUES.items():
    for alias in aliases:
        _VENUE_LOOKUP[alias.upper()] = canonical


def normalize_venue(venue: str) -> str:
    """Return the canonical venue code for *venue*.

    Unknown venues are upper-cased and stripped but otherwise returned
    unchanged.  This keeps the mapping future-proof while still providing
    consistent casing for recognised identifiers.
    """

    cleaned = venue.strip().upper()
    if not cleaned:
        raise ValueError("venue must be a non-empty string")
    return _VENUE_LOOKUP.get(cleaned, cleaned)


# -- Instrument canonicalisation -----------------------------------------------

_SEPARATORS = {"/", "-", "_", ":"}
_DERIVATIVE_SUFFIXES = {
    "PERP",
    "PERPETUAL",
    "SWAP",
    "FUT",
    "FUTURE",
    "FUTURES",
    "QUARTER",
    "THISWEEK",
    "NEXTWEEK",
}
_KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "CAD",
    "CHF",
    "BTC",
    "ETH",
    "BNB",
    "BUSD",
    "TRY",
    "BRL",
)

_SYMBOL_ALIAS_TO_COMPONENTS: Mapping[str, Sequence[str]] = {
    "BTCUSD": ("BTC", "USD"),
    "BTCUSDT": ("BTC", "USDT"),
    "XBTUSD": ("XBT", "USD"),
    "ETHUSD": ("ETH", "USD"),
    "ETHUSDT": ("ETH", "USDT"),
    "SOLUSD": ("SOL", "USD"),
    "SOLUSDT": ("SOL", "USDT"),
    "AAPLUSD": ("AAPL", "USD"),
}


def _infer_kind(symbol: str, hint: object | None) -> str:
    if isinstance(hint, Enum):
        candidate = getattr(hint, "value", str(hint))
    elif hint is None:
        candidate = ""
    else:
        candidate = str(hint)
    lowered = candidate.strip().lower()
    if lowered in {"future", "futures", "derivative", "derivatives", "perp"}:
        return "derivatives"
    if lowered:
        return "spot"
    upper_symbol = symbol.upper()
    if any(suffix in upper_symbol for suffix in _DERIVATIVE_SUFFIXES):
        return "derivatives"
    return "spot"


def _split_known_alias(symbol: str) -> Sequence[str] | None:
    alias = _SYMBOL_ALIAS_TO_COMPONENTS.get(symbol)
    if alias is not None:
        return list(alias)
    return None


def _split_by_known_quotes(symbol: str) -> Sequence[str] | None:
    for quote in _KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            if base:  # pragma: no cover - length guard above ensures base is truthy
                return [base, quote]
    return None


def _expand_parts(parts: Iterable[str]) -> List[str]:
    expanded: List[str] = []
    for part in parts:
        alias = _split_known_alias(part)
        if alias:
            expanded.extend(alias)
            continue
        quote_split = _split_by_known_quotes(part)
        if quote_split:
            expanded.extend(quote_split)
            continue
        expanded.append(part)
    return expanded


def _split_symbol_components(symbol: str) -> List[str]:
    alias_split = _split_known_alias(symbol)
    if alias_split:
        return list(alias_split)

    for sep in _SEPARATORS:
        if sep in symbol:
            raw_parts = [part for part in symbol.split(sep) if part]
            if raw_parts:
                return _expand_parts(raw_parts)

    quote_split = _split_by_known_quotes(symbol)
    if quote_split:
        return list(quote_split)

    return [symbol]


def normalize_symbol(symbol: str, *, instrument_type_hint: object | None = None) -> str:
    """Normalise *symbol* into a canonical representation.

    The function:

    * strips whitespace and upper-cases the code
    * resolves common aliases (``btc_usdt`` -> ``BTC/USDT``)
    * enforces ``/`` for spot pairs and ``-`` for derivative contracts
    * preserves single-leg instruments (e.g. equities like ``AAPL``)
    """

    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("symbol must be a non-empty string")

    components = _split_symbol_components(cleaned)
    kind = _infer_kind(cleaned, instrument_type_hint)

    if len(components) == 1:
        return components[0]

    if kind == "derivatives":
        base = components[0]
        quote = components[1] if len(components) > 1 else ""
        suffix = components[2:] if len(components) > 2 else []
        joined = "-".join([comp for comp in [base, quote, *suffix] if comp])
        return joined

    base = components[0]
    quote = components[1] if len(components) > 1 else ""
    return "/".join([comp for comp in [base, quote] if comp])
