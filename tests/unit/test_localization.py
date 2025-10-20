from __future__ import annotations

from __future__ import annotations

import pytest

from core.localization import get_localization_catalog, negotiate_locale, validate_timezone


def test_negotiate_locale_prefers_specific_locale() -> None:
    catalog = get_localization_catalog()
    rules = negotiate_locale(["uk-UA"], catalog=catalog)

    assert rules.locale == "uk-UA"
    assert rules.currency == "UAH"
    assert rules.datetime["timeZoneName"] == "short"
    assert rules.resolve_currency("XBT") == "USD"


def test_negotiate_locale_falls_back_to_defaults() -> None:
    catalog = get_localization_catalog()
    rules = negotiate_locale(["xx-ZZ"], catalog=catalog)

    assert rules.locale in {"en-US", "en-us"}
    assert rules.currency == "USD"
    assert rules.symbols["decimal"] in {".", ","}


def test_validate_timezone_warns_for_invalid(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        tz = validate_timezone("Not/AZone")
    assert tz == "UTC"
    assert any("timezone" in record.message for record in caplog.records)


def test_resolve_currency_override_priority() -> None:
    catalog = get_localization_catalog()
    rules = negotiate_locale(["ja-JP"], catalog=catalog)

    assert rules.resolve_currency(override="CAD") == "CAD"
    assert rules.resolve_currency("ETH") == "USD"
    assert rules.resolve_currency("unused") == "JPY"
