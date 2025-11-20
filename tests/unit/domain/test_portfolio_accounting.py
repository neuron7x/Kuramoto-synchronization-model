from __future__ import annotations

from decimal import Decimal

from domain import CurrencyExposureSnapshot, OrderSide, PortfolioAccounting


def _exposure_by_currency(
    snapshot: tuple[CurrencyExposureSnapshot, ...], currency: str
) -> CurrencyExposureSnapshot:
    for exposure in snapshot:
        if exposure.currency == currency:
            return exposure
    raise AssertionError(f"currency {currency} not found in exposures")


def test_portfolio_updates_position_and_pnl() -> None:
    accounting = PortfolioAccounting(base_currency="USD")
    accounting.apply_fill(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        currency="USD",
    )
    accounting.mark_to_market("AAPL", price=Decimal("110"))

    snapshot = accounting.snapshot()
    assert snapshot.realized_pnl_base == Decimal("0")
    assert snapshot.unrealized_pnl_base == Decimal("100")
    position = snapshot.positions[0]
    assert position.symbol == "AAPL"
    assert position.quantity == Decimal("10")
    assert position.average_price == Decimal("100")
    assert position.unrealized_pnl_base == Decimal("100")
    assert snapshot.total_equity == Decimal("100")


def test_realized_pnl_and_fees_tracking() -> None:
    accounting = PortfolioAccounting(base_currency="USD")
    accounting.apply_fill(
        symbol="ETH",
        side=OrderSide.BUY,
        quantity=Decimal("2"),
        price=Decimal("50"),
        currency="USD",
        fee=Decimal("1"),
    )
    accounting.apply_fill(
        symbol="ETH",
        side=OrderSide.SELL,
        quantity=Decimal("2"),
        price=Decimal("55"),
        currency="USD",
        fee=Decimal("1"),
    )

    snapshot = accounting.snapshot()
    assert snapshot.realized_pnl_base == Decimal("8")  # (55-50)*2 - 2 fees
    assert snapshot.fees_paid_base == Decimal("2")
    assert snapshot.fees_paid["USD"] == Decimal("2")
    position = snapshot.positions[0]
    assert position.realized_pnl_base == Decimal("8")
    assert snapshot.cash_balances["USD"] == Decimal("8")


def test_multi_currency_exposures_are_consistent() -> None:
    accounting = PortfolioAccounting(base_currency="USD")
    accounting.update_fx_rate("EUR", Decimal("1.1"))
    accounting.apply_fill(
        symbol="BMW",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("50"),
        currency="EUR",
    )
    accounting.mark_to_market("BMW", price=Decimal("55"))

    snapshot = accounting.snapshot()
    exposure = _exposure_by_currency(snapshot.currency_exposures, "EUR")
    assert exposure.cash == Decimal("-500")
    assert exposure.positions == Decimal("550")
    assert exposure.net == Decimal("50")
    assert exposure.net_base == Decimal("55")
    assert snapshot.unrealized_pnl_base == Decimal("55")
    assert snapshot.total_equity == Decimal("55")


def test_corporate_actions_affect_cash_and_records() -> None:
    accounting = PortfolioAccounting(base_currency="USD")
    accounting.apply_fill(
        symbol="TSLA",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        price=Decimal("100"),
        currency="USD",
    )
    accounting.apply_split(symbol="TSLA", ratio=Decimal("2"))
    accounting.record_dividend(symbol="TSLA", amount=Decimal("2"), currency="USD")

    snapshot = accounting.snapshot()
    position = snapshot.positions[0]
    assert position.quantity == Decimal("2")
    assert position.average_price == Decimal("50")
    assert snapshot.cash_balances["USD"] == Decimal("-98")
    assert snapshot.realized_pnl_base == Decimal("2")
    action_types = {action.action_type for action in snapshot.corporate_actions}
    assert {"split", "dividend"}.issubset(action_types)


def test_updating_fx_rate_revalues_unrealized_pnl() -> None:
    accounting = PortfolioAccounting(base_currency="USD")
    accounting.update_fx_rate("JPY", Decimal("0.009"))
    accounting.apply_fill(
        symbol="SONY",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("10000"),
        currency="JPY",
    )
    accounting.mark_to_market("SONY", price=Decimal("10100"))
    initial_snapshot = accounting.snapshot()
    assert initial_snapshot.unrealized_pnl_base == Decimal("9")

    accounting.update_fx_rate("JPY", Decimal("0.01"))
    updated_snapshot = accounting.snapshot()
    assert updated_snapshot.unrealized_pnl_base == Decimal("10")
