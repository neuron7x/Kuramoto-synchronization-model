"""Schema Auditor (§4.C): inspect every asset/table for precursor-critical columns.

This module produces an ``AssetSchemaReport`` per asset given a
panel's column inventory. It is the single source of truth for
whether a substrate is OHLC-only or contains microstructure.
"""

from __future__ import annotations

from agent.models import AssetSchemaReport

# Exact column-name vocabulary for precursor-capable substrates.
BID_FIELDS = frozenset({"bid", "bid_price", "bid_l1", "best_bid"})
ASK_FIELDS = frozenset({"ask", "ask_price", "ask_l1", "best_ask"})
SPREAD_FIELDS = frozenset({"spread", "bid_ask_spread", "tick_spread"})
TRADE_FIELDS = frozenset({"trades", "trade", "trade_sign", "signed_volume"})
BID_DEPTH_FIELDS = frozenset({"bid_depth", "bid_size", "bid_qty", "volume_bid"})
ASK_DEPTH_FIELDS = frozenset({"ask_depth", "ask_size", "ask_qty", "volume_ask"})
OFI_FIELDS = frozenset({"ofi", "order_flow_imbalance", "queue_imbalance"})


def _has_any(fields: tuple[str, ...], vocabulary: frozenset[str]) -> bool:
    lowered = {f.lower() for f in fields}
    return bool(lowered & vocabulary)


def audit_asset(asset: str, fields: tuple[str, ...]) -> AssetSchemaReport:
    has_bid = _has_any(fields, BID_FIELDS)
    has_ask = _has_any(fields, ASK_FIELDS)
    has_trades = _has_any(fields, TRADE_FIELDS)
    has_bid_depth = _has_any(fields, BID_DEPTH_FIELDS)
    has_ask_depth = _has_any(fields, ASK_DEPTH_FIELDS)
    has_spread = _has_any(fields, SPREAD_FIELDS)
    has_ofi = _has_any(fields, OFI_FIELDS)

    can_derive_spread = has_bid and has_ask
    can_derive_ofi = has_bid and has_ask and has_bid_depth and has_ask_depth

    # A substrate is precursor-capable when it carries, for this asset,
    # at least one direct microstructure field beyond OHLC. Derivability
    # alone from bid/ask also counts because spread and mid can be
    # computed losslessly.
    precursor_capable = bool(
        has_bid or has_ask or has_spread or has_trades or has_bid_depth or has_ask_depth or has_ofi
    )

    return AssetSchemaReport(
        asset=asset,
        fields=tuple(fields),
        has_bid=has_bid,
        has_ask=has_ask,
        has_trades=has_trades,
        has_bid_depth=has_bid_depth,
        has_ask_depth=has_ask_depth,
        has_spread=has_spread,
        has_ofi=has_ofi,
        can_derive_spread=can_derive_spread,
        can_derive_ofi=can_derive_ofi,
        precursor_capable=precursor_capable,
    )


def audit_panel(columns: list[str]) -> list[AssetSchemaReport]:
    """Audit a panel whose columns are asset tickers (each a scalar close).

    This is the common case for ``data/askar_full/panel_hourly*.parquet``:
    every column is a single close-price series per asset. That is the
    textbook OHLC_CLOSE_ONLY input — no asset carries bid/ask/depth
    even though there may be 53 of them.
    """
    # Close-only panel → every asset's "fields" is just its own ticker.
    return [audit_asset(asset=col, fields=(col,)) for col in columns]


def is_ohlc_close_only(schemas: list[AssetSchemaReport]) -> bool:
    """True when EVERY asset lacks any microstructure field."""
    return all(not s.precursor_capable for s in schemas)


__all__ = [
    "BID_FIELDS",
    "ASK_FIELDS",
    "SPREAD_FIELDS",
    "TRADE_FIELDS",
    "BID_DEPTH_FIELDS",
    "ASK_DEPTH_FIELDS",
    "OFI_FIELDS",
    "audit_asset",
    "audit_panel",
    "is_ohlc_close_only",
]
