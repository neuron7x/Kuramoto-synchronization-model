import importlib


def test_market_feed_module_importable() -> None:
    module = importlib.import_module("core.data.market_feed")
    assert hasattr(module, "MarketFeedRecord")
    assert hasattr(module, "validate_recording")
