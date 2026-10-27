# SPDX-License-Identifier: MIT
"""Coverage debt paydown: execution analytics financial evidence invariants."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from analytics.execution_forensics import HEADERS, EvidenceInputError, analyze


def _source(tmp_path: Path, **override: str) -> Path:
    row = {
        "venue": "binance",
        "symbol": "BTCUSDT",
        "quote_asset": "USDT",
        "trade_id": "realistic_demo_only",
        "order_id": "order-1",
        "executed_at_utc": "2026-10-25T15:00:01Z",
        "side": "BUY",
        "quantity": "0.01",
        "price": "100",
        "fee_amount": "0",
        "fee_asset": "USDT",
        "fee_quote_value": "",
        "fee_conversion_source": "",
        "arrival_price": "101",
        "arrival_at_utc": "2026-10-25T15:00:00Z",
        "arrival_source": "declared_order_submit_snapshot",
    }
    row.update(override)
    p = tmp_path / "trades.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerow(row)
    return p


def test_explicit_zero_fee_and_favorable_fill_are_measured(tmp_path: Path) -> None:
    p = _source(tmp_path)
    report = analyze(p)
    group = report["groups"][0]
    assert group["fee_quote_total"] == "0"
    assert group["arrival_slippage_quote"] == "-0.01"
    assert group["execution_shortfall_plus_fees_quote"] == "-0.01"
    assert group["missing_fee_valuation_fills"] == 0
    assert group["evidence_state"] == "COMPLETE_EXECUTION_COMPONENTS"
    assert report["portfolio_pnl_quote"] is None  # execution cost is not PnL


def test_source_and_report_are_content_bound(tmp_path: Path) -> None:
    p = _source(tmp_path)
    report = analyze(p)
    assert report["source_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(report["method_source_sha256"]) == 64
    reported_digest = report.pop("report_sha256")
    canon = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    assert reported_digest == hashlib.sha256(canon).hexdigest()


def test_strict_event_time_disallows_future_reference(tmp_path: Path) -> None:
    p = _source(tmp_path, arrival_at_utc="2026-10-25T15:00:02Z")
    with pytest.raises(EvidenceInputError, match="future"):
        analyze(p)


def test_cross_asset_fee_without_conversion_does_not_invent_zero(tmp_path: Path) -> None:
    p = _source(tmp_path, fee_amount="0.00003", fee_asset="BNB")
    group = analyze(p)["groups"][0]
    assert group["fee_totals_native_by_asset"] == {"BNB": "0.00003"}
    assert group["fee_quote_total"] is None
    assert group["execution_shortfall_plus_fees_quote"] is None
    assert group["evidence_state"] == "PARTIAL_UNKNOWN_COST"


def test_non_numeric_financial_input_fails_closed(tmp_path: Path) -> None:
    p = _source(tmp_path, fee_amount="Infinity")
    with pytest.raises(EvidenceInputError, match="invalid sign"):
        analyze(p)
