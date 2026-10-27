# SPDX-License-Identifier: MIT
"""Adversarial and positive controls for offline execution-cost evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from tools.execution_forensics import (
    EXACT_DIGITS,
    HEADERS,
    MAX_SOURCE_BYTES,
    SCHEMA_PATH,
    EvidenceInputError,
    analyze,
    analyze_bytes,
    canonical_json,
    main,
    parse_fills,
    report_digest,
    verify_report,
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
        {"fee_amount": "", "fee_asset": "", "fee_quote_value": "0.1", "fee_conversion_source": ""},
        {"fee_amount": "", "fee_asset": "", "fee_quote_value": "", "fee_conversion_source": "x"},
        {"arrival_price": "", "arrival_at_utc": "", "arrival_source": "orphan"},
        {"arrival_price": "", "arrival_at_utc": "2026-10-20T10:00:00Z", "arrival_source": ""},
        {"arrival_price": "60000", "arrival_at_utc": "", "arrival_source": "orphan"},
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


# --------------------------------------------------------------------------- lexical canon
# One byte string, one meaning: every spelling outside the canonical grammar is refused so
# that source_sha256 binds a unique interpretation of the data.

_SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "execution_forensics" / "fills_sample.csv"


def _csv_bytes(*rows: dict[str, str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", "1e3"),
        ("quantity", "1E3"),
        ("quantity", "1_000"),
        ("quantity", "+1"),
        ("quantity", ".5"),
        ("quantity", "5."),
        ("quantity", "01"),
        ("quantity", "0x10"),
        ("quantity", "١"),  # Arabic-Indic digit one: Decimal() would accept it
        ("quantity", "1,5"),
        ("price", "6e4"),
        ("fee_amount", "-0"),
        ("fee_amount", "-1"),
        ("fee_amount", "0.6 "),  # inner strip happens before matching; trailing NBSP does not
        ("executed_at_utc", "2026-10-20 10:00:01Z"),
        ("executed_at_utc", "20261020T100001Z"),
        ("executed_at_utc", "2026-10-20T10:00:01+00:00"),
        ("executed_at_utc", "2026-10-20Z"),
        ("executed_at_utc", "2026-10-20T10:00:01.1234567Z"),
        ("executed_at_utc", "2026-13-20T10:00:01Z"),
        ("executed_at_utc", "2026-10-20T24:00:00Z"),
        ("executed_at_utc", "2026-10-20T23:59:60Z"),
        ("executed_at_utc", "2026-10-20T10:00:01z"),
        ("arrival_at_utc", "2026-10-20T10:00:00.5+00:00"),
        ("venue", "Binance"),
        ("venue", ""),
        ("venue", "-binance"),
        ("symbol", "btcusdt"),
        ("symbol", ""),
        ("quote_asset", "usdt"),
        ("quote_asset", "US-DT"),
        ("trade_id", "T 1"),
        ("trade_id", ""),
        ("order_id", ""),
        ("side", "buy"),
        ("side", ""),
        ("fee_asset", "bnb"),
    ],
)
def test_non_canonical_lexeme_is_refused(field: str, value: str) -> None:
    row = _fill(**{field: value})
    if field == "fee_amount" and value == "0.6 ":
        row[field] = "0.6 "
    with pytest.raises(EvidenceInputError):
        analyze_bytes(_csv_bytes(row))


def test_outer_ascii_whitespace_is_formatting_not_meaning() -> None:
    padded = analyze_bytes(_csv_bytes(_fill(quantity=" 0.1 ", price="60010\t")))
    plain = analyze_bytes(_csv_bytes(_fill()))
    assert padded["groups"] == plain["groups"]
    assert padded["source_sha256"] != plain["source_sha256"]


def test_trailing_fractional_zeros_are_canonical_input_and_normalized_output() -> None:
    group = analyze_bytes(
        _csv_bytes(_fill(quantity="0.10000000", price="60010.00", fee_amount="0.60000000"))
    )["groups"][0]
    assert group["notional_quote"] == "6001"
    assert group["fee_quote_total"] == "0.6"
    assert group["fee_totals_native_by_asset"] == {"USDT": "0.6"}


def test_exact_arithmetic_refuses_to_round() -> None:
    quantity = "1." + "3" * (EXACT_DIGITS - 1)  # exactly EXACT_DIGITS significant digits
    with pytest.raises(EvidenceInputError, match="exact arithmetic"):
        analyze_bytes(_csv_bytes(_fill(quantity=quantity, price="7.7")))


def test_wide_but_representable_arithmetic_matches_fraction_oracle() -> None:
    quantity, price, arrival = "123456789.123456789012345", "98765.4321098765", "98760.5"
    group = analyze_bytes(_csv_bytes(_fill(quantity=quantity, price=price, arrival_price=arrival)))[
        "groups"
    ][0]
    notional = Fraction(quantity) * Fraction(price)
    slippage = (Fraction(price) - Fraction(arrival)) * Fraction(quantity)
    assert Fraction(group["notional_quote"]) == notional
    assert Fraction(group["arrival_slippage_quote"]) == slippage
    assert Fraction(group["execution_shortfall_plus_fees_quote"]) == slippage + Fraction("0.6")


def test_header_order_is_part_of_the_contract() -> None:
    reordered = (
        ",".join(reversed(HEADERS)) + "\n" + ",".join(reversed(list(_fill().values()))) + "\n"
    )
    with pytest.raises(EvidenceInputError, match="exact names and order"):
        analyze_bytes(reordered.encode("utf-8"))


def test_duplicate_header_name_rejected() -> None:
    duplicated = ",".join(("venue",) + HEADERS[1:-1] + ("venue",)) + "\n"
    with pytest.raises(EvidenceInputError, match="columns differ"):
        analyze_bytes(duplicated.encode("utf-8"))


@pytest.mark.parametrize("delta", [",extra", ""])
def test_row_width_mismatch_rejected(delta: str) -> None:
    header = ",".join(HEADERS)
    values = list(_fill().values())
    body = ",".join(values) + delta if delta else ",".join(values[:-1])
    with pytest.raises(EvidenceInputError, match="malformed column count"):
        analyze_bytes(f"{header}\n{body}\n".encode("utf-8"))


def test_empty_bom_only_and_header_only_sources_are_refused() -> None:
    with pytest.raises(EvidenceInputError, match="empty"):
        analyze_bytes(b"")
    with pytest.raises(EvidenceInputError, match="no header"):
        analyze_bytes("﻿".encode("utf-8"))
    with pytest.raises(EvidenceInputError, match="no fills"):
        analyze_bytes(_csv_bytes())


def test_bom_prefixed_source_is_accepted_and_hashed_as_is() -> None:
    raw = "﻿".encode("utf-8") + _csv_bytes(_fill())
    report = analyze_bytes(raw)
    assert report["fill_count"] == 1
    assert report["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_size_limit_refuses_without_reading_a_sparse_file(tmp_path: Path) -> None:
    huge = tmp_path / "huge.csv"
    huge.touch()
    os.truncate(huge, MAX_SOURCE_BYTES + 1)
    with pytest.raises(EvidenceInputError, match="byte limit"):
        analyze(huge)
    with pytest.raises(EvidenceInputError, match="byte limit"):
        analyze_bytes(b"x" * (MAX_SOURCE_BYTES + 1))


def test_buy_and_sell_slippage_are_antisymmetric_for_the_same_prices() -> None:
    buy = analyze_bytes(_csv_bytes(_fill(side="BUY", quantity="2", price="101", arrival_price="100")))
    sell = analyze_bytes(
        _csv_bytes(_fill(side="SELL", quantity="2", price="101", arrival_price="100"))
    )
    assert buy["groups"][0]["arrival_slippage_quote"] == "2"
    assert sell["groups"][0]["arrival_slippage_quote"] == "-2"
    assert buy["groups"][0]["buy_notional_quote"] == sell["groups"][0]["sell_notional_quote"] == "202"
    assert buy["groups"][0]["sell_notional_quote"] == sell["groups"][0]["buy_notional_quote"] == "0"


def test_arrival_price_zero_is_refused_not_treated_as_unknown() -> None:
    with pytest.raises(EvidenceInputError, match="must be positive"):
        analyze_bytes(_csv_bytes(_fill(arrival_price="0")))


def test_missing_fee_valuation_counts_absent_fee_and_unsourced_conversion() -> None:
    group = analyze_bytes(
        _csv_bytes(
            _fill(fee_amount="", fee_asset="", fee_quote_value="", fee_conversion_source=""),
            _fill(trade_id="T2", fee_amount="0.001", fee_asset="BNB"),
            _fill(trade_id="T3"),
        )
    )["groups"][0]
    assert group["missing_fee_valuation_fills"] == 2
    assert group["fee_totals_native_by_asset"] == {"BNB": "0.001", "USDT": "0.6"}
    assert group["fee_quote_total"] is None


def test_declared_provenance_is_part_of_the_report() -> None:
    group = analyze_bytes(
        _csv_bytes(
            _fill(),
            _fill(
                trade_id="T2",
                order_id="O2",
                fee_amount="0.001",
                fee_asset="BNB",
                fee_quote_value="0.3",
                fee_conversion_source="venue_statement_2026_10_20",
                arrival_source="order_book_snapshot_l1",
            ),
            _fill(trade_id="T3", fee_amount="0.002", fee_asset="BNB"),
        )
    )["groups"][0]
    assert group["fee_conversion_sources"] == ["venue_statement_2026_10_20"]
    assert group["arrival_sources"] == ["order_book_snapshot_l1", "order_submission_snapshot"]
    quote_only = analyze_bytes(_csv_bytes(_fill()))["groups"][0]
    assert quote_only["fee_conversion_sources"] == []
    blind = analyze_bytes(
        _csv_bytes(_fill(arrival_price="", arrival_at_utc="", arrival_source=""))
    )["groups"][0]
    assert blind["arrival_sources"] == []


def test_cross_asset_fee_with_sourced_zero_valuation_is_a_known_zero() -> None:
    group = analyze_bytes(
        _csv_bytes(
            _fill(
                fee_amount="0.001",
                fee_asset="BNB",
                fee_quote_value="0",
                fee_conversion_source="venue_rebate_statement",
            )
        )
    )["groups"][0]
    assert group["fee_quote_total"] == "0"
    assert group["missing_fee_valuation_fills"] == 0


def test_analyze_bytes_and_analyze_path_agree(tmp_path: Path) -> None:
    path = _csv(tmp_path, _fill(), _fill(trade_id="T2", executed_at_utc="2026-10-20T10:00:02Z"))
    assert analyze(path) == analyze_bytes(path.read_bytes())
    assert parse_fills(path.read_bytes()) == parse_fills(path.read_bytes())


def test_report_digest_covers_everything_but_itself() -> None:
    report = analyze_bytes(_csv_bytes(_fill()))
    assert report["report_sha256"] == report_digest(report)
    assert report["report_sha256"] == hashlib.sha256(
        canonical_json({k: v for k, v in report.items() if k != "report_sha256"})
    ).hexdigest()
    altered = dict(report)
    altered["fill_count"] = 2
    assert report_digest(altered) != report["report_sha256"]


def test_verify_report_names_each_reason() -> None:
    report = analyze_bytes(_csv_bytes(_fill()))
    assert verify_report(dict(report), report) == []
    assert verify_report(["not", "a", "dict"], report) == ["saved report is not a JSON object"]
    forged = dict(report)
    forged["report_sha256"] = "0" * 64
    assert "saved report digest does not match its own body" in verify_report(forged, report)
    other = analyze_bytes(_csv_bytes(_fill(price="60011")))
    assert verify_report(dict(other), report) == ["source_sha256 differs"]
    stale_method = dict(report)
    stale_method["method_source_sha256"] = "f" * 64
    stale_method["report_sha256"] = report_digest(stale_method)
    assert verify_report(stale_method, report) == ["method_source_sha256 differs"]
    content = dict(report)
    content["fill_count"] = 2
    content["report_sha256"] = report_digest(content)
    assert verify_report(content, report) == ["report content differs"]


def test_verify_cli_distinguishes_unreadable_and_mismatched_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fills = _csv(tmp_path, _fill())
    saved = tmp_path / "report.json"
    saved.write_text("{not json", encoding="utf-8")
    assert main(["--fills", str(fills), "--verify", str(saved)]) == 3
    assert "unreadable" in capsys.readouterr().err
    saved.write_text(json.dumps({"schema_version": "x"}), encoding="utf-8")
    assert main(["--fills", str(fills), "--verify", str(saved)]) == 3
    assert "source_sha256 differs" in capsys.readouterr().err
    assert main(["--fills", str(tmp_path / "missing.csv"), "--verify", str(saved)]) == 2


def test_stdout_mode_prints_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fills = _csv(tmp_path, _fill())
    assert main(["--fills", str(fills)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == analyze(fills)


def test_report_carries_no_json_numbers_except_counts() -> None:
    report = analyze_bytes(_csv_bytes(_fill(), _fill(trade_id="T2", fee_amount="0.01", fee_asset="BNB")))
    count_keys = {"fill_count", "missing_fee_valuation_fills", "missing_arrival_benchmark_fills"}

    def walk(node: object, key: str | None) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, bool) or isinstance(node, float):
            raise AssertionError(f"{key}: {node!r} is not a decimal string")
        elif isinstance(node, int):
            assert key in count_keys, f"{key}: integers are only allowed for counts"

    walk(report, None)
    assert report["claim_tier"] == "Instrumented"


def test_sample_fixture_is_pinned() -> None:
    raw = _SAMPLE.read_bytes()
    report = analyze_bytes(raw)
    group = report["groups"][0]
    assert report["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (group["notional_quote"], group["fee_quote_total"]) == ("18005", "0.9")
    assert (group["arrival_slippage_quote"], group["execution_shortfall_plus_fees_quote"]) == (
        "5",
        "5.9",
    )
    assert group["evidence_state"] == "COMPLETE_EXECUTION_COMPONENTS"


# --------------------------------------------------------------------------- schema contract


def _schema() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / SCHEMA_PATH
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_reports_conform_to_the_published_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    validator = jsonschema.Draft202012Validator(_schema())
    validator.check_schema(_schema())
    complete = analyze_bytes(_SAMPLE.read_bytes())
    partial = analyze_bytes(
        _csv_bytes(
            _fill(arrival_price="", arrival_at_utc="", arrival_source=""),
            _fill(trade_id="T2", order_id="O2", symbol="ETHBTC", quote_asset="BTC", price="0.04",
                  fee_amount="0.00002", fee_asset="BTC", arrival_price="0.05"),
            _fill(trade_id="T3", side="SELL", price="59000"),
        )
    )
    for report in (complete, partial):
        assert sorted(validator.iter_errors(report), key=str) == []


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda r: r.__setitem__("fill_count", 1.5),
        lambda r: r["groups"][0].__setitem__("arrival_slippage_quote", "-0"),
        lambda r: r["groups"][0].__setitem__("notional_quote", "18005.0"),
        lambda r: r["groups"][0].__setitem__("notional_quote", 18005),
        lambda r: r.__setitem__("portfolio_pnl_quote", "0"),
        lambda r: r.__setitem__("claim_tier", "Measured-Single"),
        lambda r: r.__setitem__("extra", "field"),
        lambda r: r["groups"][0]["fee_totals_native_by_asset"].__setitem__("bnb", "1"),
        lambda r: r.__setitem__("report_sha256", "not-a-digest"),
    ],
)
def test_schema_rejects_fabricated_shapes(corrupt: Callable[[dict[str, Any]], None]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    report = json.loads(json.dumps(analyze_bytes(_SAMPLE.read_bytes())))
    corrupt(report)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=report, schema=_schema())
