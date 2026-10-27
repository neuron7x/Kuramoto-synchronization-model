# SPDX-License-Identifier: MIT
"""Adversarial and positive controls for offline execution-cost evidence."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from analytics.execution_forensics import (
    HEADERS,
    EvidenceInputError,
    analyze,
    main,
)


def _fill(**changes: str) -> dict[str, str]:
    record = {
        "venue": "binance",
        "symbol": "BTCUSDT",
        "quote_asset": "USDT",
        "trade_id": "T1",
        "order_id": "O1",
        "executed_at_utc": "2026-10-20T10:00:01Z",
        "side": "BUY",
        "quantity": "0.1",
        "price": "60010",
        "fee_amount": "0.6",
        "fee_asset": "USDT",
        "fee_quote_value": "",
        "fee_conversion_source": "",
        "arrival_price": "60000",
        "arrival_at_utc": "2026-10-20T10:00:00Z",
        "arrival_source": "order_submission_snapshot",
    }
    record.update(changes)
    return record


def _csv(tmp_path: Path, *rows: dict[str, str], path: str = "fills.csv") -> Path:
    target = tmp_path / path
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_complete_cost_components_and_cross_asset_fee(tmp_path: Path) -> None:
    csv_path = _csv(
        tmp_path,
        _fill(),
        _fill(
            trade_id="T2", executed_at_utc="2026-10-20T10:00:02Z",
            quantity="0.2", price="60020",
            fee_amount="0.001", fee_asset="BNB", fee_quote_value="0.3",
            fee_conversion_source="exchange_fee_quote_valuation_at_execution",
        ),
    )
    report = analyze(csv_path)
    group = report["groups"][0]
    assert report["fill_count"] == 2
    assert group["notional_quote"] == "18005"
    assert group["fee_totals_native_by_asset"] == {"BNB": "0.001", "USDT": "0.6"}
    assert group["fee_quote_total"] == "0.9"
    assert group["arrival_slippage_quote"] == "5"
    assert group["execution_shortfall_plus_fees_quote"] == "5.9"
    assert group["evidence_state"] == "COMPLETE_EXECUTION_COMPONENTS"
    assert report["portfolio_pnl_quote"] is None
    assert report["funding_quote"] is None


def test_unknown_fee_is_not_zero_or_partial_total(tmp_path: Path) -> None:
    csv_path = _csv(
        tmp_path,
        _fill(),
        _fill(
            trade_id="T2", executed_at_utc="2026-10-20T10:00:02Z",
            fee_asset="BNB", fee_amount="0.01",
            fee_quote_value="", fee_conversion_source="",
        ),
    )
    group = analyze(csv_path)["groups"][0]
    assert group["fee_totals_native_by_asset"]["BNB"] == "0.01"
    assert group["missing_fee_valuation_fills"] == 1
    assert group["fee_quote_total"] is None
    assert group["execution_shortfall_plus_fees_quote"] is None


def test_unknown_arrival_is_not_zero_slippage(tmp_path: Path) -> None:
    path = _csv(tmp_path, _fill(arrival_price="", arrival_at_utc="", arrival_source=""))
    group = analyze(path)["groups"][0]
    assert group["fee_quote_total"] == "0.6"
    assert group["missing_arrival_benchmark_fills"] == 1
    assert group["arrival_slippage_quote"] is None
    assert group["execution_shortfall_plus_fees_quote"] is None


def test_sell_slippage_positive_for_unfavorable_price(tmp_path: Path) -> None:
    path = _csv(tmp_path, _fill(side="SELL", quantity="2", price="98", arrival_price="100"))
    group = analyze(path)["groups"][0]
    assert group["arrival_slippage_quote"] == "4"
    assert group["execution_shortfall_plus_fees_quote"] == "4.6"


def test_multi_quote_never_net_aggregated(tmp_path: Path) -> None:
    path = _csv(
        tmp_path, _fill(),
        _fill(
            trade_id="OTHER", order_id="O2", symbol="ETHBTC", quote_asset="BTC",
            price="0.04", quantity="2", fee_amount="0.00002", fee_asset="BTC",
            arrival_price="", arrival_at_utc="", arrival_source="",
        ),
    )
    report = analyze(path)
    assert len(report["groups"]) == 2
    assert report["portfolio_aggregation"] == "NOT_ALLOWED_ACROSS_DISTINCT_QUOTE_ASSETS"
    assert report["portfolio_pnl_quote"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "NaN"},
        {"price": "Infinity"},
        {"quantity": "-0.1"},
        {"quantity": "0"},
        {"fee_amount": "-1"},
        {"side": "HOLD"},
        {"executed_at_utc": "2026-10-20T10:00:01"},
        {"arrival_at_utc": "2026-10-20T10:00:03Z"},
        {"arrival_at_utc": ""},
        {"arrival_source": ""},
        {"fee_asset": ""},
        {"fee_asset": "BNB", "fee_quote_value": "0.5", "fee_conversion_source": ""},
        {"fee_asset": "USDT", "fee_quote_value": "0.7"},
        {"fee_amount": "", "fee_asset": "USDT"},
    ],
)
def test_malformed_or_fabricated_evidence_fails(tmp_path: Path, changes: dict[str, str]) -> None:
    path = _csv(tmp_path, _fill(**changes))
    with pytest.raises(EvidenceInputError):
        analyze(path)


def test_duplicate_trade_rejected(tmp_path: Path) -> None:
    path = _csv(tmp_path, _fill(), _fill())
    with pytest.raises(EvidenceInputError, match="duplicate trade"):
        analyze(path)


def test_conflicting_arrival_benchmark_within_order_rejected(tmp_path: Path) -> None:
    path = _csv(
        tmp_path, _fill(),
        _fill(trade_id="T2", executed_at_utc="2026-10-20T10:00:02Z", arrival_price="60005"),
    )
    with pytest.raises(EvidenceInputError, match="conflicting arrival"):
        analyze(path)


def test_wrong_schema_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wrong.csv"
    path.write_text("trade,price\nT1,60000\n", encoding="utf-8")
    with pytest.raises(EvidenceInputError, match="columns differ"):
        analyze(path)


def test_replay_and_tamper_detection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _csv(tmp_path, _fill())
    report_path = tmp_path / "report.json"
    assert main(["--fills", str(path), "--out", str(report_path)]) == 0
    assert main(["--fills", str(path), "--verify", str(report_path)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert main(["--fills", str(path), "--out", str(report_path)]) == 2
    assert analyze(path) == analyze(path)
    altered = path.read_text(encoding="utf-8").replace("60010", "60011")
    path.write_text(altered, encoding="utf-8")
    assert main(["--fills", str(path), "--verify", str(report_path)]) == 3


def test_never_overwrite_input(tmp_path: Path) -> None:
    path = _csv(tmp_path, _fill())
    before = path.read_bytes()
    assert main(["--fills", str(path), "--out", str(path)]) == 2
    assert path.read_bytes() == before


def test_utf8_and_source_size_gate(tmp_path: Path) -> None:
    path = tmp_path / "binary.csv"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(EvidenceInputError, match="UTF-8"):
        analyze(path)
