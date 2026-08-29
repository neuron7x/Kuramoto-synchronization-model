"""D-002L-P1 secondary Treasury announcement reconstruction oracle.

The oracle is deliberately *refusal-only*.  It can detect a mismatch between
an official TreasuryDirect Calculated New Cash/Pay Down primary registry and
independent official Treasury offering-announcement records, but it can never
by itself authorize D002L-P1 TERMINAL_PASS.

No market outcome (TGCR/IOER/IORB), fitted coefficient, p-value, or GeoSync
feature is accepted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "D002L-P1-ANNOUNCEMENT-ORACLE-v1"
AUTHORITY = "SECONDARY_REFUSAL_ONLY"
ALLOWED_HOSTS = {
    "treasurydirect.gov",
    "www.treasurydirect.gov",
    "fiscaldata.treasury.gov",
}
FORBIDDEN_TOKENS = {
    "tgcr",
    "ioer",
    "iorb",
    "outcome",
    "beta_coupon",
    "p_value",
    "pvalue",
    "standard_error",
    "confidence_interval",
    "geosync",
    "kuramoto",
    "phase_coherence",
}


class D002LTreasuryOracleError(ValueError):
    """Fail-closed secondary-oracle error."""


@dataclass(frozen=True)
class AnnouncementRecord:
    settlement_date: date
    security_type: str
    cusip: str
    offering_million: Decimal
    publicly_held_maturing_million: Decimal
    source_url: str
    source_sha256: str
    source_document_id: str


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _parse_date(value: Any) -> date:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise D002LTreasuryOracleError(f"INVALID_SETTLEMENT_DATE:{text!r}")


def _decimal(value: Any, *, field: str) -> Decimal:
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        out = Decimal(text)
    except InvalidOperation as exc:
        raise D002LTreasuryOracleError(f"INVALID_DECIMAL:{field}:{value!r}") from exc
    if not out.is_finite():
        raise D002LTreasuryOracleError(f"NONFINITE_DECIMAL:{field}")
    return -out if negative else out


def _assert_no_forbidden_fields(mapping: Mapping[str, Any]) -> None:
    leaked: list[str] = []
    for raw in mapping:
        key = re.sub(r"[^a-z0-9]+", "_", str(raw).lower()).strip("_")
        padded = f"_{key}_"
        if any(f"_{token}_" in padded for token in FORBIDDEN_TOKENS):
            leaked.append(str(raw))
    if leaked:
        raise D002LTreasuryOracleError(f"OUTCOME_OR_MODEL_FIELD_FORBIDDEN:{sorted(leaked)}")


def _is_coupon_security(value: str) -> bool:
    text = _norm(value)
    if "bill" in text:
        return False
    return any(token in text for token in ("note", "bond", "frn", "floating rate", "tips"))


def _validate_source_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise D002LTreasuryOracleError(f"UNOFFICIAL_ORACLE_SOURCE_URL:{value}")
    if not (
        "/instit/annceresult/press/preanre/" in parsed.path
        or "/static-data/published-reports/auctions-query/announcements/" in parsed.path
    ):
        raise D002LTreasuryOracleError(f"UNSUPPORTED_OFFICIAL_ANNOUNCEMENT_PATH:{value}")


def structured_record_from_announcement_text(
    text: str,
    *,
    source_url: str,
    source_sha256: str,
    source_document_id: str,
) -> dict[str, Any]:
    """Extract locked oracle fields from pdftotext-style Treasury announcement text."""
    _validate_source_url(source_url)
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256.lower()):
        raise D002LTreasuryOracleError("INVALID_SOURCE_SHA256:announcement_text")
    flat = re.sub(r"\s+", " ", text).strip()
    patterns = {
        "security_type": r"Term and Type of Security\s*:?[ ]*(.+?)[ ]+Offering Amount\b",
        "offering": r"Offering Amount\s*:?[ ]*\$([0-9,]+)",
        "cusip": r"CUSIP Number\s*:?[ ]*([0-9A-Z]{9})\b",
        "issue_date": r"(?<!Original )Issue Date\s*:?[ ]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        "maturing": (
            r"Estimated Amount of Maturing Coupon Securities Held by the Public"
            r"\s*:?[ ]*\$([0-9,]+)"
        ),
    }
    found: dict[str, str] = {}
    for field, pattern in patterns.items():
        match = re.search(pattern, flat, flags=re.IGNORECASE)
        if not match:
            raise D002LTreasuryOracleError(f"ANNOUNCEMENT_FIELD_NOT_FOUND:{field}")
        found[field] = match.group(1).strip()
    offering_million = _decimal(found["offering"], field="offering") / Decimal("1000000")
    maturing_million = _decimal(found["maturing"], field="maturing") / Decimal("1000000")
    return {
        "settlement_date": _parse_date(found["issue_date"]).isoformat(),
        "security_type": found["security_type"],
        "cusip": found["cusip"].upper(),
        "offering_million": format(offering_million, "f"),
        "publicly_held_maturing_million": format(maturing_million, "f"),
        "source_url": source_url,
        "source_sha256": source_sha256.lower(),
        "source_document_id": source_document_id,
    }


def parse_announcement_records(payload: bytes | str) -> list[AnnouncementRecord]:
    """Parse structured extraction records from retained official announcements.

    The caller retains the official PDF/HTML bytes separately.  Each record
    therefore includes the SHA-256 of its source document; a bare hand-entered
    number without a retained source digest is refused.
    """
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise D002LTreasuryOracleError("ORACLE_RECORDS_NOT_UTF8") from exc
    else:
        text = payload
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise D002LTreasuryOracleError(f"INVALID_ORACLE_JSON:{exc.msg}") from exc
    if not isinstance(obj, list) or not obj:
        raise D002LTreasuryOracleError("ORACLE_RECORDS_MUST_BE_NONEMPTY_LIST")

    required = {
        "settlement_date",
        "security_type",
        "cusip",
        "offering_million",
        "publicly_held_maturing_million",
        "source_url",
        "source_sha256",
        "source_document_id",
    }
    seen_docs: set[str] = set()
    seen_issue_keys: set[tuple[date, str]] = set()
    records: list[AnnouncementRecord] = []
    for idx, row in enumerate(obj, start=1):
        if not isinstance(row, dict):
            raise D002LTreasuryOracleError(f"ORACLE_ROW_NOT_OBJECT:{idx}")
        _assert_no_forbidden_fields(row)
        missing = sorted(required - set(row))
        if missing:
            raise D002LTreasuryOracleError(f"ORACLE_FIELDS_MISSING:row={idx}:{missing}")
        doc_id = str(row["source_document_id"]).strip()
        if not doc_id:
            raise D002LTreasuryOracleError(f"EMPTY_SOURCE_DOCUMENT_ID:row={idx}")
        if doc_id in seen_docs:
            raise D002LTreasuryOracleError(f"DUPLICATE_SOURCE_DOCUMENT_ID:{doc_id}")
        seen_docs.add(doc_id)
        source_sha = str(row["source_sha256"]).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
            raise D002LTreasuryOracleError(f"INVALID_SOURCE_SHA256:{doc_id}")
        source_url = str(row["source_url"]).strip()
        _validate_source_url(source_url)
        security_type = str(row["security_type"]).strip()
        if not _is_coupon_security(security_type):
            raise D002LTreasuryOracleError(f"NON_COUPON_ANNOUNCEMENT:{doc_id}:{security_type}")
        settlement = _parse_date(row["settlement_date"])
        cusip = re.sub(r"\s+", "", str(row["cusip"]).upper())
        if not re.fullmatch(r"[0-9A-Z]{9}", cusip):
            raise D002LTreasuryOracleError(f"INVALID_CUSIP:{doc_id}:{cusip}")
        issue_key = (settlement, cusip)
        if issue_key in seen_issue_keys:
            raise D002LTreasuryOracleError(
                f"DUPLICATE_SETTLEMENT_CUSIP:{settlement.isoformat()}:{cusip}"
            )
        seen_issue_keys.add(issue_key)
        offering = _decimal(row["offering_million"], field="offering_million")
        maturing = _decimal(
            row["publicly_held_maturing_million"],
            field="publicly_held_maturing_million",
        )
        if offering <= 0 or maturing < 0:
            raise D002LTreasuryOracleError(f"INVALID_ORACLE_AMOUNTS:{doc_id}")
        records.append(
            AnnouncementRecord(
                settlement_date=settlement,
                security_type=security_type,
                cusip=cusip,
                offering_million=offering,
                publicly_held_maturing_million=maturing,
                source_url=source_url,
                source_sha256=source_sha,
                source_document_id=doc_id,
            )
        )
    return records


def reconstruct_by_settlement_date(records: Sequence[AnnouncementRecord]) -> dict[str, dict[str, Any]]:
    """Aggregate coupon offerings and one consistent date-level maturing amount."""
    grouped: dict[date, list[AnnouncementRecord]] = {}
    for record in records:
        grouped.setdefault(record.settlement_date, []).append(record)
    result: dict[str, dict[str, Any]] = {}
    for settlement in sorted(grouped):
        day = grouped[settlement]
        maturing_values = {r.publicly_held_maturing_million for r in day}
        if len(maturing_values) != 1:
            vals = sorted(str(v) for v in maturing_values)
            raise D002LTreasuryOracleError(
                f"INCONSISTENT_PUBLICLY_HELD_MATURING:{settlement.isoformat()}:{vals}"
            )
        maturing = next(iter(maturing_values))
        offering = sum((r.offering_million for r in day), Decimal(0))
        net = offering - maturing
        result[settlement.isoformat()] = {
            "settlement_date": settlement.isoformat(),
            "announcement_count": len(day),
            "total_offering_million_usd": str(offering.normalize()),
            "total_publicly_held_maturing_million_usd": str(maturing.normalize()),
            "net_new_cash_or_pay_down_million_usd": str(net.normalize()),
            "cusips": sorted(r.cusip for r in day),
            "source_document_ids": sorted(r.source_document_id for r in day),
            "source_sha256s": sorted(r.source_sha256 for r in day),
        }
    return result


def deterministic_oracle_sample_dates(registry: Mapping[str, Any]) -> list[str]:
    """Select first+last eligible coupon event per year, exposure-only and deterministic."""
    if registry.get("schema_version") != "D002L-EXPOSURE-REGISTRY-v1":
        raise D002LTreasuryOracleError("WRONG_PRIMARY_REGISTRY_SCHEMA")
    if registry.get("confirmatory_outcomes_ingested") is not False:
        raise D002LTreasuryOracleError("PRIMARY_REGISTRY_OUTCOME_FIREWALL_BROKEN")
    events = registry.get("events")
    if not isinstance(events, list) or not events:
        raise D002LTreasuryOracleError("PRIMARY_REGISTRY_EVENTS_MISSING")
    by_year: dict[int, list[date]] = {}
    for event in events:
        if not isinstance(event, dict):
            raise D002LTreasuryOracleError("PRIMARY_EVENT_NOT_OBJECT")
        _assert_no_forbidden_fields(event)
        if not event.get("eligible"):
            continue
        d = _parse_date(event.get("settlement_date"))
        if 2014 <= d.year <= 2026:
            by_year.setdefault(d.year, []).append(d)
    required_years = set(range(2014, 2027))
    if set(by_year) != required_years:
        raise D002LTreasuryOracleError(
            f"PRIMARY_REGISTRY_YEAR_COVERAGE_INVALID:{sorted(required_years - set(by_year))}"
        )
    selected: list[date] = []
    for year in sorted(by_year):
        dates = sorted(set(by_year[year]))
        selected.append(dates[0])
        if dates[-1] != dates[0]:
            selected.append(dates[-1])
    return [d.isoformat() for d in selected]


def _event_map(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for event in registry["events"]:
        key = str(event["settlement_date"])
        if key in out:
            raise D002LTreasuryOracleError(f"DUPLICATE_PRIMARY_EVENT_DATE:{key}")
        out[key] = event
    return out


def crosscheck_registry(
    registry: Mapping[str, Any],
    records: Sequence[AnnouncementRecord],
) -> dict[str, Any]:
    """Cross-check deterministic sample dates; any mismatch is a hard refusal."""
    required_dates = deterministic_oracle_sample_dates(registry)
    oracle = reconstruct_by_settlement_date(records)
    primary = _event_map(registry)
    missing = [d for d in required_dates if d not in oracle]
    if missing:
        raise D002LTreasuryOracleError(f"ORACLE_REQUIRED_DATES_MISSING:{missing}")

    checks: list[dict[str, Any]] = []
    for d in required_dates:
        p = primary[d]
        o = oracle[d]
        comparisons = {
            "total_offering_million_usd": (
                Decimal(str(p["total_offering_million_usd"])),
                Decimal(str(o["total_offering_million_usd"])),
            ),
            "total_publicly_held_maturing_million_usd": (
                Decimal(str(p["total_publicly_held_maturing_million_usd"])),
                Decimal(str(o["total_publicly_held_maturing_million_usd"])),
            ),
            "coupon_net_new_cash_or_pay_down_million_usd": (
                Decimal(str(p["coupon_net_new_cash_or_pay_down_million_usd"])),
                Decimal(str(o["net_new_cash_or_pay_down_million_usd"])),
            ),
        }
        mismatches = {
            field: {"primary": str(values[0]), "oracle": str(values[1])}
            for field, values in comparisons.items()
            if values[0] != values[1]
        }
        if mismatches:
            raise D002LTreasuryOracleError(f"PRIMARY_ORACLE_DIVERGENCE:{d}:{mismatches}")
        checks.append(
            {
                "settlement_date": d,
                "status": "MATCH",
                "announcement_count": o["announcement_count"],
                "source_document_ids": o["source_document_ids"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "study_id": "D-002L",
        "node_id": "D002L-P1",
        "authority": AUTHORITY,
        "can_authorize_p1_terminal_pass": False,
        "can_refuse_p1": True,
        "required_sample_rule": "first_and_last_eligible_coupon_settlement_per_year_2014_2026",
        "required_sample_dates": required_dates,
        "matched_sample_count": len(checks),
        "checks": checks,
        "status": "ORACLE_MATCH",
        "confirmatory_outcomes_ingested": False,
        "claim_boundary": (
            "Secondary Treasury exposure-source integrity check only. A match does not establish "
            "P1 authenticity/completeness and cannot authorize lineage advance."
        ),
    }


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
