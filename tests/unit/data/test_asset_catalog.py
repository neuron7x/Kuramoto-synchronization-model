from datetime import datetime, timezone

import pytest

from core.data.asset_catalog import AssetCatalog, AssetStatus
from core.data.models import InstrumentType


def test_asset_catalog_register_and_resolve() -> None:
    catalog = AssetCatalog()
    record = catalog.create_asset(
        asset_id="btc",
        name="Bitcoin",
        primary_symbol="btcusdt",
        instrument_type=InstrumentType.SPOT,
        venue_symbols={"binance": "BTCUSDT", "coinbase": "btc-usd"},
    )

    assert record.primary_symbol == "BTC/USDT"
    assert catalog.resolve(" btcusdt ").asset_id == "btc"
    assert catalog.resolve("BTCUSD", venue="coinbase").asset_id == "btc"
    assert catalog.get_display_symbol("btc", venue="binance") == "BTC/USDT"
    assert catalog.get_display_symbol("btc") == "BTC/USDT"


def test_asset_catalog_update_symbol_tracks_history() -> None:
    catalog = AssetCatalog()
    catalog.create_asset(
        asset_id="sol",
        name="Solana",
        primary_symbol="solusd",
    )

    catalog.update_primary_symbol("sol", "SOLUSDC")

    assert catalog.resolve("SOLUSDC").asset_id == "sol"
    assert catalog.resolve("solusd").asset_id == "sol"
    with pytest.raises(KeyError):
        catalog.resolve("SOLUSD", include_historical=False)


def test_asset_catalog_synchronize_venue_symbol_records_history() -> None:
    catalog = AssetCatalog()
    catalog.create_asset(
        asset_id="btcp",
        name="BTC Perpetual",
        primary_symbol="btcusdt",
        instrument_type=InstrumentType.FUTURES,
        venue_symbols={"binance": "btcusdt"},
    )

    catalog.synchronize_venue_symbol("btcp", "binance", "btcusdt_perp")

    assert catalog.resolve("BTCUSDT_PERP", venue="binance").asset_id == "btcp"
    assert catalog.get_display_symbol("btcp", venue="binance") == "BTC-USDT-PERP"
    # Historical alias remains discoverable without the venue context.
    assert catalog.resolve("BTCUSDT").asset_id == "btcp"


def test_asset_catalog_mark_delisted_and_reactivate() -> None:
    catalog = AssetCatalog()
    catalog.create_asset(
        asset_id="aapl",
        name="Apple Inc.",
        primary_symbol="aapl",
    )

    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    catalog.mark_delisted("aapl", when=when)

    record = catalog.get("aapl")
    assert record.status == AssetStatus.DELISTED
    assert record.delisted_at == when

    catalog.mark_active("aapl")
    assert record.status == AssetStatus.ACTIVE
    assert record.delisted_at is None


def test_asset_catalog_update_name_trimmed() -> None:
    catalog = AssetCatalog()
    catalog.create_asset(
        asset_id="eth",
        name="Ethereum",
        primary_symbol="ethusd",
    )

    catalog.update_name("eth", "  Ethereum Network  ")

    assert catalog.get("eth").name == "Ethereum Network"


def test_asset_catalog_historical_ambiguity_raises() -> None:
    catalog = AssetCatalog()
    catalog.create_asset(
        asset_id="asset1",
        name="Asset One",
        primary_symbol="aaausd",
    )
    catalog.update_primary_symbol("asset1", "aaausdc")

    catalog.create_asset(
        asset_id="asset2",
        name="Asset Two",
        primary_symbol="bbbusd",
    )
    catalog.synchronize_venue_symbol("asset2", "binance", "AAaUsd")
    catalog.synchronize_venue_symbol("asset2", "binance", "BBBUSD")

    with pytest.raises(LookupError):
        catalog.resolve("AAaUsd")
