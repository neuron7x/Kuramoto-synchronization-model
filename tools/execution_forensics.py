# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Offline execution-cost evidence from explicitly normalized fill records.

Boundary
--------
No market access, account credentials, strategy recommendations, portfolio
PnL, or inferred funding. A missing financial observation stays ``null``; it
is never replaced by zero. The report is deterministic and content-addressed;
its digest detects change, it does not authenticate anything.

Invariants (each has a refusing test in ``tests/unit/test_execution_forensics.py``)
------------------------------------------------------------------------------------
* Lexical canon. Every amount must match ``(0|[1-9][0-9]*)(\\.[0-9]+)?`` and
  every timestamp must match ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``. Exponents,
  underscores, signs, the basic ISO form, UTC offsets, date-only values and
  sub-microsecond fractions are refused, so one byte string has exactly one
  meaning and ``source_sha256`` binds that meaning.
* Exact arithmetic. Totals are computed in a ``decimal`` context that traps
  ``Inexact`` and ``Rounded``. A figure the context cannot carry exactly is
  refused, never rounded.
* Provenance travels with the value. A cross-asset fee valuation needs its
  conversion source; an arrival benchmark needs its timestamp (not after the
  fill) and its source. Without them the quantity is unknown and every total
  that depends on it is ``null``.
* No cross-quote aggregation. Groups are keyed by ``(venue, symbol, quote)``
  and nothing is summed across groups.
* Replay. ``--verify`` recomputes the report from the current bytes of the CSV
  and of this module and compares it with the saved report.

Exit codes (CLI): ``0`` success, ``2`` input refused, ``3`` verification failed.
The report contract is ``schemas/execution_forensics_report.schema.json``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, Inexact, InvalidOperation, Rounded, localcontext
from pathlib import Path
from typing import Final, TypedDict

SCHEMA_VERSION: Final = "execution-forensics/0.1"
METHOD_VERSION: Final = "GEOSYNC_EXECUTION_FORENSICS_V0_1"
SCHEMA_PATH: Final = "schemas/execution_forensics_report.schema.json"
CLAIM_TIER: Final = "Instrumented"
MAX_SOURCE_BYTES: Final = 50_000_000
EXACT_DIGITS: Final = 50
HEADERS: Final[tuple[str, ...]] = (
    "venue",
    "symbol",
    "quote_asset",
    "trade_id",
    "order_id",
    "executed_at_utc",
    "side",
    "quantity",
    "price",
    "fee_amount",
    "fee_asset",
    "fee_quote_value",
    "fee_conversion_source",
    "arrival_price",
    "arrival_at_utc",
    "arrival_source",
)
SIDES: Final = frozenset({"BUY", "SELL"})

_DECIMAL_RE: Final = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")
_UTC_RE: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z"
)
_VENUE_RE: Final = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_SYMBOL_RE: Final = re.compile(r"[A-Z0-9][A-Z0-9_./-]*")
_ASSET_RE: Final = re.compile(r"[A-Z0-9]+")
_ID_RE: Final = re.compile(r"[\x21-\x7e]+")
_EXACT: Final = Context(prec=EXACT_DIGITS, traps=[Inexact, Rounded, InvalidOperation])


class EvidenceInputError(ValueError):
    """Input cannot support unambiguous cost calculations."""


# --------------------------------------------------------------------------- lexical canon


def _decimal(value: str, field: str) -> Decimal:
    if _DECIMAL_RE.fullmatch(value) is None:
        raise EvidenceInputError(f"{field}: non-canonical decimal {value!r}")
    return Decimal(value)


def _positive(number: Decimal, field: str) -> Decimal:
    if number <= 0:
        raise EvidenceInputError(f"{field}: must be positive")
    return number


def _utc(value: str, field: str) -> datetime:
    if _UTC_RE.fullmatch(value) is None:
        raise EvidenceInputError(f"{field}: timestamp must be YYYY-MM-DDTHH:MM:SS[.ffffff]Z")
    try:
        naive = datetime.fromisoformat(value[:-1])
    except ValueError as exc:
        raise EvidenceInputError(f"{field}: {exc}") from exc
    return naive.replace(tzinfo=timezone.utc)


def _token(fields: Mapping[str, str], name: str, pattern: re.Pattern[str], line: int) -> str:
    value = fields[name]
    if pattern.fullmatch(value) is None:
        raise EvidenceInputError(f"row {line}: {name} must match {pattern.pattern}")
    return value


def _amount(number: Decimal | None) -> str | None:
    return None if number is None else _amount_known(number)


# --------------------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class Fee:
    """A fee whose quote valuation, when known, carries its conversion source."""

    amount: Decimal
    asset: str
    quote_value: Decimal | None
    conversion_source: str | None


@dataclass(frozen=True, slots=True)
class Arrival:
    """A reference price observed no later than the fill, with its source."""

    price: Decimal
    at: datetime
    source: str


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
    fee: Fee | None
    arrival: Arrival | None


def _parse_fee(fields: Mapping[str, str], line: int) -> Fee | None:
    amount_raw = fields["fee_amount"]
    asset = fields["fee_asset"]
    quote_raw = fields["fee_quote_value"]
    source = fields["fee_conversion_source"]
    if not amount_raw:
        if asset or quote_raw or source:
            raise EvidenceInputError(
                f"row {line}: fee amount is missing but fee metadata is present"
            )
        return None
    amount = _decimal(amount_raw, f"row {line} fee_amount")
    if _ASSET_RE.fullmatch(asset) is None:
        raise EvidenceInputError(f"row {line}: valid fee_asset required for a known fee")
    quote_value = None if not quote_raw else _decimal(quote_raw, f"row {line} fee_quote_value")
    if asset == fields["quote_asset"]:
        if quote_value is not None and quote_value != amount:
            raise EvidenceInputError(f"row {line}: quote-asset fee conversion disagrees with fee")
        if source:
            raise EvidenceInputError(f"row {line}: quote-asset fee needs no conversion source")
        return Fee(amount=amount, asset=asset, quote_value=amount, conversion_source=None)
    if (quote_value is None) != (not source):
        raise EvidenceInputError(f"row {line}: cross-asset fee valuation and source must coexist")
    return Fee(
        amount=amount, asset=asset, quote_value=quote_value, conversion_source=source or None
    )


def _parse_arrival(fields: Mapping[str, str], line: int, executed_at: datetime) -> Arrival | None:
    price_raw = fields["arrival_price"]
    at_raw = fields["arrival_at_utc"]
    source = fields["arrival_source"]
    if not price_raw:
        if at_raw or source:
            raise EvidenceInputError(f"row {line}: orphan arrival metadata")
        return None
    if not at_raw or not source:
        raise EvidenceInputError(f"row {line}: arrival price, time and source must be complete")
    price = _positive(_decimal(price_raw, f"row {line} arrival_price"), f"row {line} arrival_price")
    at = _utc(at_raw, f"row {line} arrival_at_utc")
    if at > executed_at:
        raise EvidenceInputError(f"row {line}: arrival benchmark is from the future")
    return Arrival(price=price, at=at, source=source)


def _parse_row(row: Mapping[str, str], line: int) -> Fill:
    fields = {key: value.strip(" \t\r\n") for key, value in row.items()}
    side = fields["side"]
    if side not in SIDES:
        raise EvidenceInputError(f"row {line}: side must be BUY or SELL")
    executed_at = _utc(fields["executed_at_utc"], f"row {line} executed_at_utc")
    return Fill(
        venue=_token(fields, "venue", _VENUE_RE, line),
        symbol=_token(fields, "symbol", _SYMBOL_RE, line),
        quote_asset=_token(fields, "quote_asset", _ASSET_RE, line),
        trade_id=_token(fields, "trade_id", _ID_RE, line),
        order_id=_token(fields, "order_id", _ID_RE, line),
        executed_at=executed_at,
        side=side,
        quantity=_positive(
            _decimal(fields["quantity"], f"row {line} quantity"), f"row {line} quantity"
        ),
        price=_positive(_decimal(fields["price"], f"row {line} price"), f"row {line} price"),
        fee=_parse_fee(fields, line),
        arrival=_parse_arrival(fields, line, executed_at),
    )


# --------------------------------------------------------------------------- loading


def _check_header(fieldnames: Sequence[str] | None) -> None:
    if fieldnames is None:
        raise EvidenceInputError("CSV has no header row")
    if tuple(fieldnames) == HEADERS:
        return
    missing = sorted(set(HEADERS) - set(fieldnames))
    extra = sorted(set(fieldnames) - set(HEADERS))
    raise EvidenceInputError(
        "CSV columns differ from canonical contract (exact names and order required): "
        f"missing={missing} extra={extra}"
    )


def _register(
    fill: Fill,
    seen: set[tuple[str, str, str]],
    arrivals: dict[tuple[str, str, str], Arrival],
    line: int,
) -> None:
    identity = (fill.venue, fill.symbol, fill.trade_id)
    if identity in seen:
        raise EvidenceInputError(f"row {line}: duplicate trade id within venue/symbol")
    seen.add(identity)
    if fill.arrival is None:
        return
    order_key = (fill.venue, fill.symbol, fill.order_id)
    if arrivals.setdefault(order_key, fill.arrival) != fill.arrival:
        raise EvidenceInputError(f"row {line}: conflicting arrival benchmark for one order")


def parse_fills(raw: bytes) -> list[Fill]:
    """Parse canonical CSV bytes into validated fills; refuse anything ambiguous."""
    if not raw:
        raise EvidenceInputError("source is empty")
    if len(raw) > MAX_SOURCE_BYTES:
        raise EvidenceInputError(f"source exceeds the {MAX_SOURCE_BYTES} byte limit")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceInputError("source must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    _check_header(reader.fieldnames)
    fills: list[Fill] = []
    seen: set[tuple[str, str, str]] = set()
    arrivals: dict[tuple[str, str, str], Arrival] = {}
    for row in reader:
        line = reader.line_num
        if None in row or None in row.values():
            raise EvidenceInputError(f"row {line}: malformed column count")
        fill = _parse_row({str(key): str(value) for key, value in row.items()}, line)
        _register(fill, seen, arrivals, line)
        fills.append(fill)
    if not fills:
        raise EvidenceInputError("CSV contains no fills")
    return fills


# --------------------------------------------------------------------------- report


class GroupReport(TypedDict):
    venue: str
    symbol: str
    quote_asset: str
    fill_count: int
    notional_quote: str
    buy_notional_quote: str
    sell_notional_quote: str
    fee_totals_native_by_asset: dict[str, str]
    fee_conversion_sources: list[str]
    arrival_sources: list[str]
    fee_quote_total: str | None
    arrival_slippage_quote: str | None
    execution_shortfall_plus_fees_quote: str | None
    missing_fee_valuation_fills: int
    missing_arrival_benchmark_fills: int
    evidence_state: str


class Report(TypedDict):
    schema_version: str
    method_version: str
    claim_tier: str
    artifact_role: str
    source_sha256: str
    method_source_sha256: str
    fill_count: int
    groups: list[GroupReport]
    portfolio_pnl_quote: None
    funding_quote: None
    portfolio_aggregation: str
    claim_boundary: str
    report_sha256: str


def _exact_sum(values: Iterable[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total += value
    return total


def _total_or_unknown(values: Iterable[Decimal | None]) -> Decimal | None:
    """Exact sum, or ``None`` when any term is unknown: unknown is not zero."""
    total = Decimal(0)
    for value in values:
        if value is None:
            return None
        total += value
    return total


def _signed_slippage(fill: Fill) -> Decimal | None:
    """Quote units lost versus arrival; positive is adverse for both sides."""
    if fill.arrival is None:
        return None
    adverse = fill.price - fill.arrival.price
    if fill.side == "SELL":
        adverse = -adverse
    return adverse * fill.quantity


def _amount_known(number: Decimal) -> str:
    return format(number.normalize(_EXACT), "f") if number != 0 else "0"


def _fee_quote(fill: Fill) -> Decimal | None:
    return None if fill.fee is None else fill.fee.quote_value


def _native_fee_totals(fills: Sequence[Fill]) -> dict[str, str]:
    native: dict[str, Decimal] = defaultdict(Decimal)
    for fill in fills:
        if fill.fee is not None:
            native[fill.fee.asset] += fill.fee.amount
    return {asset: _amount_known(native[asset]) for asset in sorted(native)}


def _provenance(fills: Sequence[Fill]) -> tuple[list[str], list[str]]:
    """Distinct declared sources, sorted: provenance is part of the content-addressed evidence."""
    fee_sources = {f.fee.conversion_source for f in fills if f.fee is not None}
    arrival_sources = {f.arrival.source for f in fills if f.arrival is not None}
    return sorted(s for s in fee_sources if s is not None), sorted(arrival_sources)


def _group(venue: str, symbol: str, quote_asset: str, fills: Sequence[Fill]) -> GroupReport:
    fee_sources, arrival_sources = _provenance(fills)
    buy = _exact_sum(f.quantity * f.price for f in fills if f.side == "BUY")
    sell = _exact_sum(f.quantity * f.price for f in fills if f.side == "SELL")
    fee_quote = _total_or_unknown(_fee_quote(f) for f in fills)
    slippage = _total_or_unknown(_signed_slippage(f) for f in fills)
    cost = None if fee_quote is None or slippage is None else fee_quote + slippage
    state = "PARTIAL_UNKNOWN_COST" if cost is None else "COMPLETE_EXECUTION_COMPONENTS"
    return {
        "venue": venue,
        "symbol": symbol,
        "quote_asset": quote_asset,
        "fill_count": len(fills),
        "notional_quote": _amount_known(buy + sell),
        "buy_notional_quote": _amount_known(buy),
        "sell_notional_quote": _amount_known(sell),
        "fee_totals_native_by_asset": _native_fee_totals(fills),
        "fee_conversion_sources": fee_sources,
        "arrival_sources": arrival_sources,
        "fee_quote_total": _amount(fee_quote),
        "arrival_slippage_quote": _amount(slippage),
        "execution_shortfall_plus_fees_quote": _amount(cost),
        "missing_fee_valuation_fills": sum(_fee_quote(f) is None for f in fills),
        "missing_arrival_benchmark_fills": sum(f.arrival is None for f in fills),
        "evidence_state": state,
    }


def canonical_json(obj: object) -> bytes:
    """RFC 8785-style bytes: sorted keys, no whitespace, UTF-8, no NaN, no floats used."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def report_digest(report: Mapping[str, object]) -> str:
    """SHA-256 of the canonical report body, excluding ``report_sha256`` itself."""
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def method_source_sha256() -> str:
    """Digest of this module's exact bytes: the method the report was computed with."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def build_report(fills: Sequence[Fill], source_sha256: str) -> Report:
    partitions: dict[tuple[str, str, str], list[Fill]] = defaultdict(list)
    for fill in fills:
        partitions[(fill.venue, fill.symbol, fill.quote_asset)].append(fill)
    report: Report = {
        "schema_version": SCHEMA_VERSION,
        "method_version": METHOD_VERSION,
        "claim_tier": CLAIM_TIER,
        "artifact_role": "offline_execution_cost_evidence",
        "source_sha256": source_sha256,
        "method_source_sha256": method_source_sha256(),
        "fill_count": len(fills),
        "groups": [_group(*key, partitions[key]) for key in sorted(partitions)],
        "portfolio_pnl_quote": None,
        "funding_quote": None,
        "portfolio_aggregation": "NOT_ALLOWED_ACROSS_DISTINCT_QUOTE_ASSETS",
        "claim_boundary": "OFFLINE_EXECUTION_COMPONENTS_ONLY_NOT_TRADING_ALPHA_OR_PNL",
        "report_sha256": "",
    }
    report["report_sha256"] = report_digest(report)
    return report


def analyze_bytes(raw: bytes) -> Report:
    """Deterministic report from CSV bytes; every arithmetic step is exact or refused."""
    try:
        with localcontext(_EXACT):
            return build_report(parse_fills(raw), hashlib.sha256(raw).hexdigest())
    except (Inexact, Rounded) as exc:
        raise EvidenceInputError(
            f"exact arithmetic budget of {EXACT_DIGITS} significant digits exceeded"
        ) from exc


def analyze(source: Path) -> Report:
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise EvidenceInputError(f"source exceeds the {MAX_SOURCE_BYTES} byte limit")
    return analyze_bytes(source.read_bytes())


def verify_report(saved: object, computed: Mapping[str, object]) -> list[str]:
    """Reasons the saved report is not a faithful replay of ``computed``; empty means PASS."""
    if not isinstance(saved, dict):
        return ["saved report is not a JSON object"]
    reasons: list[str] = []
    if saved.get("report_sha256") != report_digest(saved):
        reasons.append("saved report digest does not match its own body")
    for key in ("source_sha256", "method_source_sha256", "method_version", "schema_version"):
        if saved.get(key) != computed[key]:
            reasons.append(f"{key} differs")
    if not reasons and saved != dict(computed):
        reasons.append("report content differs")
    return reasons


# --------------------------------------------------------------------------- CLI


def _verify_cli(saved_path: Path, report: Report) -> int:
    try:
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: saved report unreadable: {exc}", file=sys.stderr)
        return 3
    reasons = verify_report(saved, report)
    if reasons:
        print("FAIL: " + "; ".join(reasons), file=sys.stderr)
        return 3
    print("PASS: report matches input and exact method bytes")
    return 0


def _write_cli(out: Path, fills: Path, body: str, digest: str) -> int:
    if out.resolve() == fills.resolve():
        print("EVIDENCE_INPUT_ERROR: report cannot overwrite its input CSV", file=sys.stderr)
        return 2
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as handle:
            handle.write(body)
    except OSError as exc:
        print(f"EVIDENCE_INPUT_ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"CREATED {out}: {digest}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, read-only, strict execution cost audit")
    parser.add_argument("--fills", type=Path, required=True, help="Canonical fill CSV")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--out", type=Path, help="Create JSON report (refuses to overwrite)")
    action.add_argument("--verify", type=Path, help="Replay a saved report against data and method")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.fills)
    except (EvidenceInputError, OSError) as exc:
        print(f"EVIDENCE_INPUT_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.verify is not None:
        return _verify_cli(args.verify, report)
    body = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out is None:
        sys.stdout.write(body)
        return 0
    return _write_cli(args.out, args.fills, body, report["report_sha256"])


if __name__ == "__main__":
    raise SystemExit(main())
