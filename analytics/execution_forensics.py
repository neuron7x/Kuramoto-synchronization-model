# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Offline execution-cost evidence from explicitly normalized fill records.

No market access, account credentials, strategy recommendations, portfolio PnL,
or inferred funding. Missing financial observations remain unknown, never zero.
The output is deterministic and content-addressed; its hash is not a signature.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Sequence

METHOD_VERSION = "GEOSYNC_EXECUTION_FORENSICS_V0_1"
MAX_SOURCE_BYTES = 50_000_000
HEADERS = (
    "venue", "symbol", "quote_asset", "trade_id", "order_id",
    "executed_at_utc", "side", "quantity", "price",
    "fee_amount", "fee_asset", "fee_quote_value", "fee_conversion_source",
    "arrival_price", "arrival_at_utc", "arrival_source",
)


class EvidenceInputError(ValueError):
    """Input cannot support unambiguous cost calculations."""


def _decimal(value: str, field: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise EvidenceInputError(f"{field}: invalid decimal") from exc
    if not number.is_finite() or (positive and number <= 0) or (not positive and number < 0):
        raise EvidenceInputError(f"{field}: non-finite or invalid sign")
    return number


def _optional_decimal(value: str, field: str) -> Decimal | None:
    return None if not value.strip() else _decimal(value, field)


def _utc(value: str, field: str) -> datetime:
    if not value.endswith("Z"):
        raise EvidenceInputError(f"{field}: explicit UTC Z timestamp required")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceInputError(f"{field}: invalid timestamp") from exc
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise EvidenceInputError(f"{field}: timezone must be UTC")
    return dt


def _amount(number: Decimal | None) -> str | None:
    return None if number is None else format(number.normalize(), "f")


def _digest(obj: object) -> str:
    body = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Fill:
    venue: str
    symbol: str
    quote_asset: str
    trade_id: str
    order_id: str
    executed_at: datetime
    side: str
    quantity: Decimal
    price: Decimal
    fee_amount: Decimal | None
    fee_asset: str | None
    fee_quote_value: Decimal | None
    arrival_price: Decimal | None
    arrival_at: datetime | None
    arrival_source: str | None


def _parse_row(row: dict[str, str], line: int) -> Fill:
    fields = {k: (v or "").strip() for k, v in row.items()}
    for name in ("venue", "symbol", "quote_asset", "trade_id", "order_id", "side"):
        if not fields[name]:
            raise EvidenceInputError(f"row {line}: {name} required")
    if fields["side"] not in {"BUY", "SELL"}:
        raise EvidenceInputError(f"row {line}: side must be BUY or SELL")
    if fields["symbol"] != fields["symbol"].upper() or fields["quote_asset"] != fields["quote_asset"].upper():
        raise EvidenceInputError(f"row {line}: symbol and quote_asset must be uppercase")

    executed_at = _utc(fields["executed_at_utc"], f"row {line} executed_at_utc")
    quantity = _decimal(fields["quantity"], f"row {line} quantity", positive=True)
    price = _decimal(fields["price"], f"row {line} price", positive=True)

    fee_amount = _optional_decimal(fields["fee_amount"], f"row {line} fee_amount")
    fee_asset = fields["fee_asset"] or None
    fee_quote_raw = _optional_decimal(fields["fee_quote_value"], f"row {line} fee_quote_value")
    fee_conversion_source = fields["fee_conversion_source"]
    if fee_amount is None:
        if fee_asset or fee_quote_raw is not None or fee_conversion_source:
            raise EvidenceInputError(f"row {line}: fee amount is missing but fee metadata is present")
        fee_quote = None
    else:
        if not fee_asset or fee_asset != fee_asset.upper():
            raise EvidenceInputError(f"row {line}: valid fee_asset required for a known fee")
        if fee_asset == fields["quote_asset"]:
            if fee_quote_raw is not None and fee_quote_raw != fee_amount:
                raise EvidenceInputError(f"row {line}: quote-asset fee conversion disagrees with fee")
            if fee_conversion_source:
                raise EvidenceInputError(f"row {line}: quote-asset fee needs no conversion source")
            fee_quote = fee_amount
        else:
            if (fee_quote_raw is None) != (not fee_conversion_source):
                raise EvidenceInputError(f"row {line}: cross-asset fee valuation and source must coexist")
            fee_quote = fee_quote_raw  # Unknown without a sourced conversion.

    arrival_price = _optional_decimal(fields["arrival_price"], f"row {line} arrival_price")
    arrival_at_raw = fields["arrival_at_utc"]
    arrival_source = fields["arrival_source"] or None
    if arrival_price is None:
        if arrival_at_raw or arrival_source:
            raise EvidenceInputError(f"row {line}: orphan arrival metadata")
        arrival_at = None
    else:
        if arrival_price <= 0 or not arrival_at_raw or not arrival_source:
            raise EvidenceInputError(f"row {line}: arrival price, time and source must be complete")
        arrival_at = _utc(arrival_at_raw, f"row {line} arrival_at_utc")
        if arrival_at > executed_at:
            raise EvidenceInputError(f"row {line}: arrival benchmark is from the future")

    return Fill(
        venue=fields["venue"].lower(), symbol=fields["symbol"],
        quote_asset=fields["quote_asset"], trade_id=fields["trade_id"],
        order_id=fields["order_id"], executed_at=executed_at, side=fields["side"],
        quantity=quantity, price=price, fee_amount=fee_amount, fee_asset=fee_asset,
        fee_quote_value=fee_quote, arrival_price=arrival_price,
        arrival_at=arrival_at, arrival_source=arrival_source,
    )


def load_fills(source: Path) -> tuple[list[Fill], str]:
    raw = source.read_bytes()
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise EvidenceInputError("source is empty or exceeds the 50 MB MVP limit")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceInputError("source must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise EvidenceInputError("missing or duplicated CSV columns")
    if set(reader.fieldnames) != set(HEADERS):
        raise EvidenceInputError(
            f"CSV columns differ from canonical contract: "
            f"missing={sorted(set(HEADERS)-set(reader.fieldnames))} "
            f"extra={sorted(set(reader.fieldnames)-set(HEADERS))}"
        )

    fills: list[Fill] = []
    seen: set[tuple[str, str, str]] = set()
    order_arrivals: dict[tuple[str, str, str], tuple[Decimal, datetime, str]] = {}
    for number, row in enumerate(reader, start=2):
        if None in row or any(v is None for v in row.values()):
            raise EvidenceInputError(f"row {number}: malformed column count")
        fill = _parse_row(row, number)
        identity = (fill.venue, fill.symbol, fill.trade_id)
        if identity in seen:
            raise EvidenceInputError(f"row {number}: duplicate trade id within venue/symbol")
        seen.add(identity)
        if fill.arrival_price is not None:
            order_key = (fill.venue, fill.symbol, fill.order_id)
            arrival = (fill.arrival_price, fill.arrival_at, fill.arrival_source)
            if order_key in order_arrivals and order_arrivals[order_key] != arrival:
                raise EvidenceInputError(f"row {number}: conflicting arrival benchmark for one order")
            order_arrivals[order_key] = arrival  # type: ignore[assignment]
        fills.append(fill)
    if not fills:
        raise EvidenceInputError("CSV contains no fills")
    return fills, hashlib.sha256(raw).hexdigest()


def _group(fills: Sequence[Fill]) -> dict[str, object]:
    total_notional = sum((f.quantity * f.price for f in fills), Decimal(0))
    buy_notional = sum((f.quantity * f.price for f in fills if f.side == "BUY"), Decimal(0))
    fee_amounts: dict[str, Decimal] = defaultdict(Decimal)
    for f in fills:
        if f.fee_amount is not None and f.fee_asset is not None:
            fee_amounts[f.fee_asset] += f.fee_amount
    missing_fee = sum(f.fee_quote_value is None for f in fills)
    missing_arrival = sum(f.arrival_price is None for f in fills)
    fee_quote = (
        sum((f.fee_quote_value for f in fills if f.fee_quote_value is not None), Decimal(0))
        if not missing_fee else None
    )
    slippage = (
        sum(
            ((f.price - f.arrival_price) * f.quantity * (1 if f.side == "BUY" else -1)
             for f in fills if f.arrival_price is not None),
            Decimal(0),
        )
        if not missing_arrival else None
    )
    cost = fee_quote + slippage if fee_quote is not None and slippage is not None else None
    return {
        "fill_count": len(fills),
        "notional_quote": _amount(total_notional),
        "buy_notional_quote": _amount(buy_notional),
        "sell_notional_quote": _amount(total_notional - buy_notional),
        "fee_totals_native_by_asset": {asset: _amount(fee_amounts[asset]) for asset in sorted(fee_amounts)},
        "fee_quote_total": _amount(fee_quote),
        "arrival_slippage_quote": _amount(slippage),
        "execution_shortfall_plus_fees_quote": _amount(cost),
        "missing_fee_valuation_fills": missing_fee,
        "missing_arrival_benchmark_fills": missing_arrival,
        "evidence_state": "COMPLETE_EXECUTION_COMPONENTS" if cost is not None else "PARTIAL_UNKNOWN_COST",
    }


def analyze(source: Path) -> dict[str, object]:
    fills, data_sha = load_fills(source)
    partitions: dict[tuple[str, str, str], list[Fill]] = defaultdict(list)
    for f in fills:
        partitions[(f.venue, f.symbol, f.quote_asset)].append(f)
    groups = [
        {"venue": venue, "symbol": symbol, "quote_asset": quote, **_group(partitions[(venue, symbol, quote)])}
        for venue, symbol, quote in sorted(partitions)
    ]
    report: dict[str, object] = {
        "schema_version": "execution-forensics/0.1",
        "method_version": METHOD_VERSION,
        "source_sha256": data_sha,
        "method_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fill_count": len(fills),
        "groups": groups,
        "portfolio_pnl_quote": None,
        "funding_quote": None,
        "portfolio_aggregation": "NOT_ALLOWED_ACROSS_DISTINCT_QUOTE_ASSETS",
        "claim_boundary": "OFFLINE_EXECUTION_COMPONENTS_ONLY_NOT_TRADING_ALPHA_OR_PNL",
    }
    report["report_sha256"] = _digest(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, read-only, strict execution cost audit")
    parser.add_argument("--fills", type=Path, required=True, help="Canonical fill CSV, no API credentials")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--out", type=Path, help="Create JSON report (refuses to overwrite)")
    action.add_argument("--verify", type=Path, help="Verify prior report against current data and code")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.fills)
        if args.verify:
            saved = json.loads(args.verify.read_text(encoding="utf-8"))
            if saved != report:
                print("FAIL: report/data/method digest mismatch", file=sys.stderr)
                return 3
            print("PASS: report matches input and exact method bytes")
            return 0
        body = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.out:
            if args.out.resolve() == args.fills.resolve():
                raise EvidenceInputError("report cannot overwrite its input CSV")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as output:
                output.write(body)
            print(f"CREATED {args.out}: {report['report_sha256']}")
        else:
            print(body, end="")
        return 0
    except (EvidenceInputError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"EVIDENCE_INPUT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
