"""Concrete provider registry — answers §0 "which provider gives bid/ask?".

The SYSTEM_ARTIFACT_v9.0 spec is silent on *which* provider the agent
should collect from. This module closes that gap by enumerating every
real market-data source that can deliver precursor-grade substrate for
Askar's target universe (XAUUSD, SPX, FX pairs, equity ETFs), with
honest availability flags.

By default, EVERY provider is ``configured=False, reachable=False``.
The agent therefore stays DORMANT on fresh-install boot and emits a
machine-auditable manifest of the exact credentials the operator
needs to plug in. This is the fail-closed behaviour the directive
requires — no infinite COLLECT loop, no silent fabrication.

To activate a provider, set the environment variable listed in each
descriptor and re-run the main loop. The registry will re-detect the
credential and flip ``configured = True``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agent.models import SourceDescriptor


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    """Declarative descriptor for a real microstructure vendor."""

    source_id: str
    provider: str
    transport: str  # "rest" | "websocket" | "file"
    covers_assets: tuple[str, ...]
    supports_bid_ask: bool
    supports_depth: bool
    supports_trades: bool
    env_var: str
    docs_url: str
    notes: str

    def is_configured(self) -> bool:
        return os.environ.get(self.env_var, "").strip() != ""

    def as_source_descriptor(self) -> SourceDescriptor:
        configured = self.is_configured()
        return SourceDescriptor(
            source_id=self.source_id,
            provider=self.provider,
            type=self.transport,
            assets=self.covers_assets,
            # Agent cannot verify auth or reachability without actually
            # firing a request, which would introduce side-effects here.
            # Downstream health_monitor performs real probing.
            auth_ok=configured,
            latency_ms=float("nan"),
            live=False,
            reachable=False,
            supports_bid_ask=self.supports_bid_ask,
            supports_depth=self.supports_depth,
            supports_trades=self.supports_trades,
            notes=(
                f"configured via {self.env_var}"
                if configured
                else f"not configured (set {self.env_var})"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "transport": self.transport,
            "covers_assets": list(self.covers_assets),
            "supports_bid_ask": self.supports_bid_ask,
            "supports_depth": self.supports_depth,
            "supports_trades": self.supports_trades,
            "env_var": self.env_var,
            "docs_url": self.docs_url,
            "notes": self.notes,
            "configured": self.is_configured(),
        }


#: Seven concrete vendors that actually serve Askar's universe.
PROVIDER_REGISTRY: tuple[ProviderCandidate, ...] = (
    ProviderCandidate(
        source_id="dukascopy_historical",
        provider="Dukascopy Bank SA",
        transport="file",
        covers_assets=(
            "XAUUSD",
            "XAGUSD",
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "USA_500_Index",
            "GER_40_Index",
        ),
        supports_bid_ask=True,
        supports_depth=False,
        supports_trades=False,
        env_var="DUKASCOPY_DOWNLOAD_DIR",
        docs_url="https://www.dukascopy.com/swiss/english/marketwatch/historical/",
        notes=(
            "Free tick-level bid/ask for FX, metals and indices back to 2003. "
            "Use the `dukascopy-python` package to materialise raw ticks "
            "into parquet. L1 only (no depth), but it IS the cleanest free "
            "source for XAUUSD bid/ask hourly."
        ),
    ),
    ProviderCandidate(
        source_id="oanda_v20",
        provider="OANDA Corp",
        transport="rest",
        covers_assets=(
            "XAUUSD",
            "XAGUSD",
            "EURUSD",
            "GBPUSD",
            "USDJPY",
            "AUDUSD",
            "USDCAD",
        ),
        supports_bid_ask=True,
        supports_depth=False,
        supports_trades=False,
        env_var="OANDA_API_TOKEN",
        docs_url="https://developer.oanda.com/rest-live-v20/introduction/",
        notes=(
            "Free practice account gives live FX + XAU/XAG bid/ask via "
            "/v3/instruments/{instrument}/candles?price=BA. L1 only but "
            "updates every 5 s. Paid production feed for live trading."
        ),
    ),
    ProviderCandidate(
        source_id="databento",
        provider="Databento Inc.",
        transport="rest",
        covers_assets=(
            "USA_500_Index",
            "SPDR_S_P_500_ETF",
            "ES_FUT",
            "NQ_FUT",
            "GC_FUT",
            "CL_FUT",
            "ZB_FUT",
        ),
        supports_bid_ask=True,
        supports_depth=True,
        supports_trades=True,
        env_var="DATABENTO_API_KEY",
        docs_url="https://databento.com/docs",
        notes=(
            "Institutional tick data for CME / ICE / NASDAQ. Full L2 book, "
            "trades, OFI derivable. Priced per-byte; ~$500-2000/month for "
            "the Askar universe. This is the reference L2 source."
        ),
    ),
    ProviderCandidate(
        source_id="polygon_io",
        provider="Polygon.io",
        transport="rest",
        covers_assets=(
            "SPDR_S_P_500_ETF",
            "QQQ",
            "VIX",
            "HYG",
            "TLT",
            "XAUUSD_via_GLD",
        ),
        supports_bid_ask=True,
        supports_depth=False,
        supports_trades=True,
        env_var="POLYGON_API_KEY",
        docs_url="https://polygon.io/docs",
        notes=(
            "US equities + options + FX + crypto. Tick data with NBBO "
            "bid/ask, trades, aggregate bars. $29-199/month. Cheaper than "
            "Databento, no L2 depth."
        ),
    ),
    ProviderCandidate(
        source_id="interactive_brokers",
        provider="Interactive Brokers LLC",
        transport="websocket",
        covers_assets=(
            "SPDR_S_P_500_ETF",
            "ES_FUT",
            "GC_FUT",
            "XAUUSD",
            "EURUSD",
            "USDJPY",
            "QQQ",
            "HYG",
            "VIX",
        ),
        supports_bid_ask=True,
        supports_depth=True,
        supports_trades=True,
        env_var="IBKR_GATEWAY_HOST",
        docs_url="https://interactivebrokers.github.io/tws-api/",
        notes=(
            "Full L2 depth across equities, futures, FX via TWS/Gateway. "
            "Requires funded IBKR account (~$10k minimum) + market-data "
            "subscriptions ($1-10/month per exchange). Covers Askar's "
            "universe end-to-end."
        ),
    ),
    ProviderCandidate(
        source_id="binance_futures",
        provider="Binance USDT-M Futures",
        transport="websocket",
        covers_assets=(
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
            "BNBUSDT",
        ),
        supports_bid_ask=True,
        supports_depth=True,
        supports_trades=True,
        env_var="BINANCE_WS_ENDPOINT",
        docs_url="https://binance-docs.github.io/apidocs/futures/en/",
        notes=(
            "Free public stream with full L2 depth, aggregate trades and "
            "funding rates. Covers crypto only — NOT Askar's equity/gold "
            "universe — but is the cheapest way to validate the pipeline "
            "end-to-end on real microstructure before wiring paid vendors."
        ),
    ),
    ProviderCandidate(
        source_id="askar_ots_raw_l2",
        provider="Ali H. Askar / OTS Capital",
        transport="internal_api",
        covers_assets=(
            "USA_500_Index",
            "SPDR_S_P_500_ETF",
            "XAUUSD",
            "EURUSD",
            "USDJPY",
        ),
        supports_bid_ask=True,
        supports_depth=True,
        supports_trades=True,
        env_var="ASKAR_L2_ENDPOINT",
        docs_url="internal — request directly from OTS Capital",
        notes=(
            "Askar's original claim was L2 data; what we received was "
            "resampled OHLC close bars. The agent should escalate this "
            "as a P0 stakeholder task: request raw tick/depth stream "
            "from OTS Capital's primary feed, not the bar export."
        ),
    ),
)


def active_sources() -> list[SourceDescriptor]:
    """Return SourceDescriptor list for providers with credentials present."""
    return [p.as_source_descriptor() for p in PROVIDER_REGISTRY if p.is_configured()]


def all_sources() -> list[SourceDescriptor]:
    """Return SourceDescriptor list for the entire registry (configured or not)."""
    return [p.as_source_descriptor() for p in PROVIDER_REGISTRY]


def provider_manifest() -> dict[str, Any]:
    """Manifest of all candidates — this is what the agent emits on DORMANT."""
    return {
        "total": len(PROVIDER_REGISTRY),
        "configured": sum(1 for p in PROVIDER_REGISTRY if p.is_configured()),
        "providers": [p.to_dict() for p in PROVIDER_REGISTRY],
    }


__all__ = [
    "ProviderCandidate",
    "PROVIDER_REGISTRY",
    "active_sources",
    "all_sources",
    "provider_manifest",
]
