from fastapi.testclient import TestClient

from sandbox.market.app import MarketService, create_app
from sandbox.settings import MarketSettings


def test_market_prices_endpoint_returns_deterministic_series() -> None:
    settings = MarketSettings(symbols=("btcusd",), price_window=12)
    service = MarketService(settings)
    app = create_app(service)
    client = TestClient(app)

    response = client.get("/prices/btcusd")
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "btcusd"
    assert len(payload["points"]) == 12
    first = payload["points"][0]["price"]
    response_repeat = client.get("/prices/btcusd")
    assert response_repeat.json()["points"][0]["price"] == first


def test_market_returns_404_for_unknown_symbol() -> None:
    app = create_app(MarketService(MarketSettings(symbols=("ethusd",), price_window=5)))
    client = TestClient(app)

    response = client.get("/prices/unknown")
    assert response.status_code == 404
