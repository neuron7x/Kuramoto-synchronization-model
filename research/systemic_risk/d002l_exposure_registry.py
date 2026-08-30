"""D-002L-P1 Treasury coupon exposure-registry compiler.

The module is intentionally outcome-blind.  It accepts only an official
TreasuryDirect ``Calculated New Cash/Pay Down Amounts`` snapshot (HTML, CSV,
or JSON export of the locked table), records the raw content digest, validates
source-completeness metadata, and constructs one deterministic exposure event
per unique coupon settlement date.

D-002L-P1 MUST NOT ingest TGCR, IOER, IORB, the primary outcome, or any fitted
coefficient.  Any such field is treated as outcome leakage and fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen

SCHEMA_VERSION = "D002L-EXPOSURE-REGISTRY-v1"
SOURCE_CONTRACT_VERSION = "D002L-P1-SOURCE-CONTRACT-v1"
SOURCE_ID = "TREASURY_CASH_PAYDOWN"
LOCKED_SOURCE_URL = (
    "https://www.treasurydirect.gov/auctions/announcements-data-results/"
    "announcement-results-press-releases/cash-pay-down/"
)
LOCKED_PUBLISHER = "U.S. Department of the Treasury / TreasuryDirect"
LOCKED_DATASET = "Calculated New Cash/Pay Down Amounts"
MILLION_USD = Decimal("1000000")
EXPOSURE_SCALE_USD = Decimal("100000000000")
CALIBRATION_START = date(2014, 9, 2)
CALIBRATION_END = date(2018, 12, 31)
CONFIRMATORY_START = date(2019, 1, 1)
CONFIRMATORY_END = date(2026, 8, 20)
FUTURE_START = date(2026, 8, 28)

# A full Treasury coupon-settlement history must contain at least one coupon
# settlement in every calendar month of the locked calibration/confirmatory
# exposure window.  Treasury coupon securities settle every month.  This is a
# structural omission guard, not a claim that monthly presence alone proves
# byte-complete source retrieval.
REQUIRED_COUPON_MONTH_START = (2014, 9)
REQUIRED_COUPON_MONTH_END = (2026, 8)

REQUIRED_FIELDS = (
    "date",
    "security_type",
    "total_offering",
    "total_publicly_held_maturing",
    "net_new_cash_or_pay_down",
)

# These tokens are impossible to justify in a P1 exposure-only source.  The
# scanner works on canonicalized header names, not row values, to avoid false
# positives in free text.
FORBIDDEN_OUTCOME_HEADER_TOKENS = (
    "tgcr",
    "ioer",
    "iorb",
    "reserve_remuneration",
    "delta_tgcr",
    "outcome",
    "y_t",
    "beta_coupon",
    "p_value",
    "pvalue",
    "standard_error",
    "confidence_interval",
)

_COUPON_DIRECT = {"coupon", "coupons"}
_BILL_DIRECT = {"bill", "bills"}

_COUPON_COMPONENTS = {
    "note",
    "notes",
    "bond",
    "bonds",
    "frn",
    "frns",
    "floating rate note",
    "floating rate notes",
    "tips",
    "tips note",
    "tips notes",
    "tips bond",
    "tips bonds",
    "treasury inflation protected securities",
}

_HEADER_ALIASES = {
    "date": "date",
    "settlement date": "date",
    "settlement_date": "date",
    "security type": "security_type",
    "security_type": "security_type",
    "total offering": "total_offering",
    "total_offering": "total_offering",
    "total offering amount": "total_offering",
    "total publicly held maturing": "total_publicly_held_maturing",
    "total_publicly_held_maturing": "total_publicly_held_maturing",
    "total publicly held maturing amount": "total_publicly_held_maturing",
    "net new cash or pay down": "net_new_cash_or_pay_down",
    "net new cash or (pay down)": "net_new_cash_or_pay_down",
    "net_new_cash_or_pay_down": "net_new_cash_or_pay_down",
}


class D002LExposureError(ValueError):
    """Fail-closed D-002L-P1 exposure-registry error."""


@dataclass(frozen=True)
class SourceRow:
    settlement_date: date
    security_type: str
    total_offering_million: Decimal
    total_publicly_held_maturing_million: Decimal
    net_new_cash_or_pay_down_million: Decimal
    source_row_number: int


class _TableParser(HTMLParser):
    """Minimal deterministic HTML table extractor; no external dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row: list[str] | None = None
        self._table: list[list[str]] | None = None
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell and self._row is not None:
            text = " ".join("".join(self._cell_parts).split())
            self._row.append(text)
            self._in_cell = False
            self._cell_parts = []
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(cell.strip() for cell in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _norm_text(value: Any) -> str:
    text = str(value).strip().lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_header(value: Any) -> str:
    raw = _norm_text(value)
    raw = raw.replace("$", "").replace("(millions)", "").strip()
    raw = raw.rstrip(":")
    if raw in _HEADER_ALIASES:
        return _HEADER_ALIASES[raw]
    snake = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return _HEADER_ALIASES.get(snake, snake)


def _assert_no_outcome_headers(headers: Iterable[str]) -> None:
    canonical = {canonical_header(h) for h in headers}
    def matches(header: str, token: str) -> bool:
        # Require underscore-delimited token boundaries.  A raw substring
        # check would falsely classify ``security_type`` as containing ``y_t``.
        padded = f"_{header}_"
        return f"_{token}_" in padded

    leaked = sorted(
        h
        for h in canonical
        if any(matches(h, token) for token in FORBIDDEN_OUTCOME_HEADER_TOKENS)
    )
    if leaked:
        raise D002LExposureError(f"CONFIRMATORY_OUTCOME_FIELD_FORBIDDEN_AT_P1:{leaked}")


def _parse_date(value: Any) -> date:
    text = str(value).strip()
    formats = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise D002LExposureError(f"INVALID_SETTLEMENT_DATE:{text!r}")


def _parse_decimal_million(value: Any, *, field: str, row_number: int) -> Decimal:
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "null", "none", "-"}:
        raise D002LExposureError(f"MISSING_NUMERIC_FIELD:{field}:row={row_number}")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = text.replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        val = Decimal(text)
    except InvalidOperation as exc:
        raise D002LExposureError(
            f"INVALID_NUMERIC_FIELD:{field}:row={row_number}:value={value!r}"
        ) from exc
    if not val.is_finite():
        raise D002LExposureError(f"NONFINITE_NUMERIC_FIELD:{field}:row={row_number}")
    return -val if negative else val


def _normalize_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    _assert_no_outcome_headers(mapping.keys())
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        ck = canonical_header(key)
        if ck in out and out[ck] != value:
            raise D002LExposureError(f"AMBIGUOUS_DUPLICATE_FIELD:{ck}")
        out[ck] = value
    return out


def _records_from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise D002LExposureError("CSV_HEADER_MISSING")
    _assert_no_outcome_headers(reader.fieldnames)
    return [_normalize_mapping(row) for row in reader]


def _records_from_json(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise D002LExposureError(f"INVALID_JSON:{exc.msg}") from exc
    if isinstance(payload, dict):
        for key in ("data", "rows", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise D002LExposureError("JSON_ROWS_MUST_BE_LIST")
    records: list[dict[str, Any]] = []
    for i, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise D002LExposureError(f"JSON_ROW_NOT_OBJECT:row={i}")
        records.append(_normalize_mapping(row))
    return records


def _records_from_html(text: str) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(text)
    for table in parser.tables:
        for header_idx, header_row in enumerate(table):
            headers = [canonical_header(x) for x in header_row]
            if all(field in headers for field in REQUIRED_FIELDS):
                _assert_no_outcome_headers(headers)
                records: list[dict[str, Any]] = []
                for row in table[header_idx + 1 :]:
                    if len(row) < len(headers):
                        continue
                    records.append(
                        _normalize_mapping(dict(zip(headers, row[: len(headers)])))
                    )
                if records:
                    return records
    raise D002LExposureError("LOCKED_TREASURY_TABLE_NOT_FOUND_IN_HTML")


def parse_source_bytes(raw: bytes, *, format_hint: str | None = None) -> list[SourceRow]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise D002LExposureError("SOURCE_NOT_UTF8") from exc
    hint = (format_hint or "").lower().lstrip(".")
    stripped = text.lstrip()
    if hint in {"html", "htm"} or stripped.startswith("<"):
        records = _records_from_html(text)
    elif hint == "json" or stripped.startswith("[") or stripped.startswith("{"):
        records = _records_from_json(text)
    else:
        records = _records_from_csv(text)
    if not records:
        raise D002LExposureError("SOURCE_HAS_ZERO_ROWS")

    rows: list[SourceRow] = []
    for i, record in enumerate(records, start=1):
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            raise D002LExposureError(f"REQUIRED_FIELDS_MISSING:row={i}:{missing}")
        offering = _parse_decimal_million(
            record["total_offering"], field="total_offering", row_number=i
        )
        maturing = _parse_decimal_million(
            record["total_publicly_held_maturing"],
            field="total_publicly_held_maturing",
            row_number=i,
        )
        net_cash = _parse_decimal_million(
            record["net_new_cash_or_pay_down"],
            field="net_new_cash_or_pay_down",
            row_number=i,
        )
        # TreasuryDirect defines this table algebraically.  A mismatch means
        # truncation, transcription, schema confusion, or source corruption.
        if offering - maturing != net_cash:
            raise D002LExposureError(
                "CASH_IDENTITY_MISMATCH:"
                f"row={i}:offering_minus_maturing={offering - maturing}:net={net_cash}"
            )
        rows.append(
            SourceRow(
                settlement_date=_parse_date(record["date"]),
                security_type=str(record["security_type"]).strip(),
                total_offering_million=offering,
                total_publicly_held_maturing_million=maturing,
                net_new_cash_or_pay_down_million=net_cash,
                source_row_number=i,
            )
        )
    return rows


def _coupon_class(security_type: str) -> str | None:
    norm = _norm_text(security_type)
    if norm in _COUPON_DIRECT:
        return "DIRECT_COUPONS"
    if norm in _COUPON_COMPONENTS:
        return "COUPON_COMPONENT"
    return None


def _partition(d: date) -> str:
    if CALIBRATION_START <= d <= CALIBRATION_END:
        return "CALIBRATION_POWER_ONLY"
    if CONFIRMATORY_START <= d <= CONFIRMATORY_END:
        return "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY"
    if d >= FUTURE_START:
        return "FUTURE_ACCUMULATION_ONLY"
    if CONFIRMATORY_END < d < FUTURE_START:
        return "PREREGISTRATION_GAP_EXCLUDED"
    return "PRE_CALIBRATION_EXCLUDED"


def _decimal_str(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def build_events(rows: Sequence[SourceRow]) -> list[dict[str, Any]]:
    # Group every source row by settlement date so the locked confirmatory
    # nuisance control (same-day Bill net cash) is preserved alongside the
    # coupon exposure.  Only dates containing coupon exposure become D-002L
    # events.
    grouped: dict[date, list[SourceRow]] = {}
    for row in rows:
        grouped.setdefault(row.settlement_date, []).append(row)

    events: list[dict[str, Any]] = []
    for event_date in sorted(grouped):
        day_rows = grouped[event_date]
        coupon_rows = [r for r in day_rows if _coupon_class(r.security_type) is not None]
        if not coupon_rows:
            continue
        direct = [r for r in coupon_rows if _coupon_class(r.security_type) == "DIRECT_COUPONS"]
        components = [r for r in coupon_rows if _coupon_class(r.security_type) == "COUPON_COMPONENT"]
        if direct and components:
            raise D002LExposureError(
                f"AMBIGUOUS_COUPON_DOUBLE_COUNT_RISK:{event_date.isoformat()}"
            )
        if len(direct) > 1:
            raise D002LExposureError(
                f"DUPLICATE_DIRECT_COUPON_ROWS:{event_date.isoformat()}:n={len(direct)}"
            )
        selected = direct or components

        bill_rows = [r for r in day_rows if _norm_text(r.security_type) in _BILL_DIRECT]
        if len(bill_rows) > 1:
            raise D002LExposureError(
                f"DUPLICATE_DIRECT_BILL_ROWS:{event_date.isoformat()}:n={len(bill_rows)}"
            )

        net_million = sum((r.net_new_cash_or_pay_down_million for r in selected), Decimal(0))
        offering_million = sum((r.total_offering_million for r in selected), Decimal(0))
        maturing_million = sum(
            (r.total_publicly_held_maturing_million for r in selected), Decimal(0)
        )
        bill_net_million = sum(
            (r.net_new_cash_or_pay_down_million for r in bill_rows), Decimal(0)
        )
        net_usd = net_million * MILLION_USD
        bill_net_usd = bill_net_million * MILLION_USD
        partition = _partition(event_date)
        zero_exposure = net_usd == 0
        eligible = (
            not zero_exposure
            and partition
            in {
                "CALIBRATION_POWER_ONLY",
                "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY",
                "FUTURE_ACCUMULATION_ONLY",
            }
        )
        exclusion_reasons: list[str] = []
        if zero_exposure:
            exclusion_reasons.append("ZERO_EXPOSURE_FORBIDDEN_BY_P0")
        if partition in {"PRE_CALIBRATION_EXCLUDED", "PREREGISTRATION_GAP_EXCLUDED"}:
            exclusion_reasons.append(partition)
        events.append(
            {
                "event_id": f"D002L-EVT-{event_date.isoformat()}",
                "settlement_date": event_date.isoformat(),
                "security_type": "Coupons",
                "coupon_row_mode": "DIRECT_COUPONS" if direct else "SUM_COMPONENTS",
                "source_row_numbers": [r.source_row_number for r in selected],
                "source_security_types": [r.security_type for r in selected],
                "bill_source_row_numbers": [r.source_row_number for r in bill_rows],
                "total_offering_million_usd": _decimal_str(offering_million),
                "total_publicly_held_maturing_million_usd": _decimal_str(maturing_million),
                "coupon_net_new_cash_or_pay_down_million_usd": _decimal_str(net_million),
                "coupon_net_new_cash_or_pay_down_usd": _decimal_str(net_usd),
                "x_t_scaled_100bn": _decimal_str(net_usd / EXPOSURE_SCALE_USD),
                "same_day_bill_net_new_cash_or_pay_down_million_usd": _decimal_str(bill_net_million),
                "same_day_bill_net_new_cash_or_pay_down_usd": _decimal_str(bill_net_usd),
                "b_t_scaled_100bn": _decimal_str(bill_net_usd / EXPOSURE_SCALE_USD),
                "partition": partition,
                "eligible": eligible,
                "exclusion_reasons": exclusion_reasons,
            }
        )
    return events


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_provenance(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D002LExposureError(f"INVALID_PROVENANCE:{exc}") from exc
    if not isinstance(payload, dict):
        raise D002LExposureError("PROVENANCE_NOT_OBJECT")
    return payload


def validate_provenance(prov: Mapping[str, Any], *, raw_sha256: str) -> None:
    required = {
        "source_id",
        "publisher",
        "dataset",
        "source_url",
        "retrieved_at_utc",
        "content_sha256",
        "revision_or_vintage_status",
        "retrieval_complete",
        "coverage_start",
        "coverage_end",
        "retrieval_scope",
    }
    missing = sorted(required - set(prov))
    if missing:
        raise D002LExposureError(f"PROVENANCE_FIELDS_MISSING:{missing}")
    if prov["source_id"] != SOURCE_ID:
        raise D002LExposureError("WRONG_SOURCE_ID")
    if prov["publisher"] != LOCKED_PUBLISHER:
        raise D002LExposureError("WRONG_PUBLISHER")
    if prov["dataset"] != LOCKED_DATASET:
        raise D002LExposureError("WRONG_DATASET")
    if prov["source_url"] != LOCKED_SOURCE_URL:
        raise D002LExposureError("UNOFFICIAL_OR_UNLOCKED_SOURCE_URL")
    if prov["content_sha256"] != raw_sha256:
        raise D002LExposureError("RAW_CONTENT_SHA256_MISMATCH")
    if prov["retrieval_complete"] is not True:
        raise D002LExposureError("SOURCE_RETRIEVAL_NOT_COMPLETE")
    if prov["retrieval_scope"] != "full_historical_table_snapshot":
        raise D002LExposureError("RETRIEVAL_SCOPE_NOT_FULL_HISTORICAL_TABLE")
    try:
        datetime.fromisoformat(str(prov["retrieved_at_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise D002LExposureError("INVALID_RETRIEVED_AT_UTC") from exc
    coverage_start = _parse_date(prov["coverage_start"])
    coverage_end = _parse_date(prov["coverage_end"])
    if coverage_start > CALIBRATION_START:
        raise D002LExposureError("SOURCE_COVERAGE_START_TOO_LATE")
    if coverage_end < CONFIRMATORY_END:
        raise D002LExposureError("SOURCE_COVERAGE_END_TOO_EARLY")


def _month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    year, month = start
    out: list[tuple[int, int]] = []
    while (year, month) <= end:
        out.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return out


def validate_actual_source_coverage(
    rows: Sequence[SourceRow], provenance: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind declared source coverage to dates that actually exist in raw bytes."""
    if not rows:
        raise D002LExposureError("SOURCE_HAS_ZERO_ROWS")
    actual_start = min(row.settlement_date for row in rows)
    actual_end = max(row.settlement_date for row in rows)
    declared_start = _parse_date(provenance["coverage_start"])
    declared_end = _parse_date(provenance["coverage_end"])
    if actual_start != declared_start:
        raise D002LExposureError(
            f"DECLARED_COVERAGE_START_MISMATCH:declared={declared_start}:actual={actual_start}"
        )
    if actual_end != declared_end:
        raise D002LExposureError(
            f"DECLARED_COVERAGE_END_MISMATCH:declared={declared_end}:actual={actual_end}"
        )
    return {
        "actual_source_coverage_start": actual_start.isoformat(),
        "actual_source_coverage_end": actual_end.isoformat(),
    }


def validate_monthly_coupon_recurrence(events: Sequence[Mapping[str, Any]]) -> list[str]:
    """Reject gross historical omissions hidden behind a claimed full snapshot."""
    represented = {
        (d.year, d.month)
        for e in events
        for d in [date.fromisoformat(str(e["settlement_date"]))]
        if CALIBRATION_START <= d <= CONFIRMATORY_END
    }
    required = set(_month_range(REQUIRED_COUPON_MONTH_START, REQUIRED_COUPON_MONTH_END))
    missing = sorted(required - represented)
    if missing:
        labels = [f"{y:04d}-{m:02d}" for y, m in missing]
        raise D002LExposureError(f"COUPON_EVENT_MONTH_GAPS:{labels}")
    return [f"{y:04d}-{m:02d}" for y, m in sorted(represented & required)]


def validate_registry_completeness(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    calibration = [
        e for e in events if e["partition"] == "CALIBRATION_POWER_ONLY" and e["eligible"]
    ]
    confirmatory = [
        e
        for e in events
        if e["partition"] == "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY"
        and e["eligible"]
    ]
    if not calibration:
        raise D002LExposureError("ZERO_ELIGIBLE_CALIBRATION_EVENTS")
    if not confirmatory:
        raise D002LExposureError("ZERO_ELIGIBLE_CONFIRMATORY_EXPOSURE_EVENTS")

    # Gross omission guard: coupon settlements should recur. This is not a
    # proof of source completeness; it is a fail-closed structural sanity
    # check supporting the separately required full-historical snapshot flag.
    required_years = set(range(CALIBRATION_START.year, CONFIRMATORY_END.year + 1))
    represented_years = {
        date.fromisoformat(str(e["settlement_date"])).year
        for e in events
        if CALIBRATION_START <= date.fromisoformat(str(e["settlement_date"])) <= CONFIRMATORY_END
    }
    missing_years = sorted(required_years - represented_years)
    if missing_years:
        raise D002LExposureError(f"COUPON_EVENT_YEAR_GAPS:{missing_years}")

    represented_months = validate_monthly_coupon_recurrence(events)

    conf_values = [Decimal(str(e["coupon_net_new_cash_or_pay_down_usd"])) for e in confirmatory]
    if len(set(conf_values)) <= 1:
        raise D002LExposureError("CONFIRMATORY_EXPOSURE_VARIANCE_NONPOSITIVE")
    return {
        "eligible_calibration_event_count": len(calibration),
        "eligible_confirmatory_exposure_event_count": len(confirmatory),
        "represented_years": sorted(represented_years),
        "represented_required_months": represented_months,
        "confirmatory_exposure_unique_values": len(set(conf_values)),
    }


def compile_registry(raw: bytes, provenance: Mapping[str, Any], *, format_hint: str | None = None) -> dict[str, Any]:
    raw_sha = sha256_bytes(raw)
    validate_provenance(provenance, raw_sha256=raw_sha)
    rows = parse_source_bytes(raw, format_hint=format_hint)
    actual_coverage = validate_actual_source_coverage(rows, provenance)
    events = build_events(rows)
    if not events:
        raise D002LExposureError("ZERO_COUPON_EVENTS")
    completeness = validate_registry_completeness(events)
    return {
        "schema_version": SCHEMA_VERSION,
        "study_id": "D-002L",
        "node_id": "D002L-P1",
        "phase_contract": "source_and_exposure_event_registry_no_confirmatory_outcomes",
        "source": dict(provenance),
        "source_row_count": len(rows),
        "coupon_event_count": len(events),
        "events": events,
        "completeness": {**actual_coverage, **completeness},
        "confirmatory_outcomes_ingested": False,
        "canonical_run_authorized": False,
        "next_phase_authorized": "D002L-P2",
        "claim_boundary": (
            "Exposure registry only. No TGCR/IOER/IORB outcome ingestion, no coefficient fit, "
            "no confirmatory scoring, no GeoSync-feature promotion."
        ),
    }


def fetch_official_snapshot(*, timeout_seconds: int = 30) -> tuple[bytes, dict[str, Any]]:
    """Fetch the locked TreasuryDirect page only; never fall back to mirrors."""
    req = Request(
        LOCKED_SOURCE_URL,
        headers={"User-Agent": "GeoSync-D002L-P1/1.0 (+scientific provenance)"},
    )
    started = datetime.now(timezone.utc)
    try:
        with urlopen(req, timeout=timeout_seconds) as response:  # nosec B310: locked HTTPS URL
            final_url = response.geturl()
            if final_url.rstrip("/") != LOCKED_SOURCE_URL.rstrip("/"):
                raise D002LExposureError(f"UNEXPECTED_SOURCE_REDIRECT:{final_url}")
            raw = response.read()
    except Exception as exc:
        if isinstance(exc, D002LExposureError):
            raise
        raise D002LExposureError(f"OFFICIAL_SOURCE_FETCH_FAILED:{type(exc).__name__}:{exc}") from exc
    retrieved = datetime.now(timezone.utc)
    # Coverage is derived from parsed source rows, never invented.
    rows = parse_source_bytes(raw, format_hint="html")
    dates = [r.settlement_date for r in rows]
    prov = {
        "source_id": SOURCE_ID,
        "publisher": LOCKED_PUBLISHER,
        "dataset": LOCKED_DATASET,
        "source_url": LOCKED_SOURCE_URL,
        "retrieved_at_utc": retrieved.isoformat().replace("+00:00", "Z"),
        "fetch_started_at_utc": started.isoformat().replace("+00:00", "Z"),
        "content_sha256": sha256_bytes(raw),
        "revision_or_vintage_status": "point_in_time_web_snapshot",
        "retrieval_complete": True,
        "retrieval_scope": "full_historical_table_snapshot",
        "coverage_start": min(dates).isoformat(),
        "coverage_end": max(dates).isoformat(),
        "http_source": "locked_treasurydirect_https_only",
    }
    return raw, prov


def blocked_result(reason: str, *, attempt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "D002L-P1-EXECUTION-STATUS-v1",
        "study_id": "D-002L",
        "node_id": "D002L-P1",
        "status": "NOT_EXECUTED",
        "decision": "BLOCKED_SOURCE_ACCESS",
        "source_complete_registry": False,
        "reason": reason,
        "attempt": dict(attempt or {}),
        "canonical_run_authorized": False,
        "next_legal_node": None,
        "lineage_advance_allowed": False,
        "confirmatory_outcomes_ingested": False,
        "stop_condition": "P1 cannot produce a source-complete exposure registry => STOP",
    }
