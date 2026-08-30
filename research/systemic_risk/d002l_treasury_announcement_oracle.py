"""D-002L Treasury offering-announcement corroboration oracle.

This module is an *independent official-source cross-check* for P1 exposure
rows.  It reconstructs a coupon settlement from Treasury offering
announcements and compares the reconstruction to a primary
``Calculated New Cash/Pay Down Amounts`` row.

Authority boundary
------------------
The oracle can detect corruption, omission, double counting, date drift and
arithmetic mismatch.  It can NEVER mint D002L-P1 TERMINAL_PASS and can NEVER
substitute for the P0-locked cash-pay/down primary dataset.  This remains true
even when every announcement has raw-byte SHA-256 evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "D002L-TREASURY-ANNOUNCEMENT-ORACLE-v1"
EVIDENCE_PARSED = "PARSED_OFFICIAL_PDF_TEXT"
EVIDENCE_RAW = "RAW_BYTE_ATTESTED"
ALLOWED_EVIDENCE_MODES = {EVIDENCE_PARSED, EVIDENCE_RAW}

OFFICIAL_HOSTS = {
    "www.treasurydirect.gov",
    "treasurydirect.gov",
    "fiscaldata.treasury.gov",
}

OFFICIAL_PATH_PREFIXES = (
    "/instit/annceresult/press/preanre/",
    "/static-data/published-reports/auctions-query/announcements/",
)

COUPON_SECURITY_TOKENS = ("note", "bond", "frn", "tips")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CUSIP_RE = re.compile(r"^[0-9A-Z]{9}$")


class D002LAnnouncementOracleError(ValueError):
    """Fail-closed offering-announcement oracle error."""


AUTHORITY_DIAGNOSTIC = "DIAGNOSTIC_CORROBORATION_ONLY"
AUTHORITY_REFUSAL = "SECONDARY_REFUSAL_ONLY"


def classify_oracle_authority(oracle: Mapping[str, Any]) -> str:
    """Return the maximum scientific authority allowed by the evidence.

    Parsed/mixed official content can corroborate and surface discrepancies but
    cannot itself refuse P1.  Refusal authority is available only when every
    announcement is raw-byte attested *and* the expected CUSIP set is exact.
    Neither class can authorize P1 PASS or substitute the locked primary table.
    """
    if bool(oracle.get("can_authorize_p1_terminal_pass")) or bool(
        oracle.get("can_substitute_primary_cash_paydown_dataset")
    ):
        raise D002LAnnouncementOracleError("ORACLE_AUTHORITY_ESCALATION_DETECTED")
    if (
        oracle.get("evidence_strength") == EVIDENCE_RAW
        and oracle.get("announcement_set_completeness") == "DECLARED_CUSIP_SET_EXACT"
    ):
        return AUTHORITY_REFUSAL
    return AUTHORITY_DIAGNOSTIC


@dataclass(frozen=True)
class AnnouncementRecord:
    source_url: str
    evidence_mode: str
    term_and_type: str
    cusip: str
    issue_date: date
    offering_amount_usd: Decimal
    maturing_coupon_held_public_usd: Decimal
    maturing_date: date
    raw_content_sha256: str | None = None
    raw_bytes_retained: bool = False


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        if isinstance(value, Decimal):
            out = value
        else:
            text = str(value).strip().replace("$", "").replace(",", "")
            out = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise D002LAnnouncementOracleError(f"NONNUMERIC_{field.upper()}") from exc
    if not out.is_finite():
        raise D002LAnnouncementOracleError(f"NONFINITE_{field.upper()}")
    return out


def _date(value: Any, *, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise D002LAnnouncementOracleError(f"INVALID_{field.upper()}") from exc


def _assert_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise D002LAnnouncementOracleError("ANNOUNCEMENT_URL_NOT_HTTPS")
    if parsed.hostname not in OFFICIAL_HOSTS:
        raise D002LAnnouncementOracleError("ANNOUNCEMENT_URL_NOT_OFFICIAL_TREASURY")
    if not any(parsed.path.startswith(prefix) for prefix in OFFICIAL_PATH_PREFIXES):
        raise D002LAnnouncementOracleError("ANNOUNCEMENT_URL_OUTSIDE_LOCKED_ORACLE_SURFACE")
    if not parsed.path.lower().endswith(".pdf"):
        raise D002LAnnouncementOracleError("ANNOUNCEMENT_SOURCE_NOT_PDF")


def _assert_coupon_security(label: str) -> None:
    normalized = " ".join(label.lower().split())
    if not any(token in normalized for token in COUPON_SECURITY_TOKENS):
        raise D002LAnnouncementOracleError("NON_COUPON_ANNOUNCEMENT_IN_ORACLE")


def parse_record(obj: Mapping[str, Any]) -> AnnouncementRecord:
    required = {
        "source_url",
        "evidence_mode",
        "term_and_type",
        "cusip",
        "issue_date",
        "offering_amount_usd",
        "maturing_coupon_held_public_usd",
        "maturing_date",
    }
    missing = sorted(required - set(obj))
    if missing:
        raise D002LAnnouncementOracleError(f"ANNOUNCEMENT_FIELDS_MISSING:{','.join(missing)}")

    url = str(obj["source_url"]).strip()
    _assert_official_url(url)

    mode = str(obj["evidence_mode"]).strip()
    if mode not in ALLOWED_EVIDENCE_MODES:
        raise D002LAnnouncementOracleError("INVALID_ANNOUNCEMENT_EVIDENCE_MODE")

    label = str(obj["term_and_type"]).strip()
    _assert_coupon_security(label)

    cusip = str(obj["cusip"]).strip().upper()
    if not _CUSIP_RE.fullmatch(cusip):
        raise D002LAnnouncementOracleError("INVALID_CUSIP")

    offering = _decimal(obj["offering_amount_usd"], field="offering_amount_usd")
    maturing = _decimal(
        obj["maturing_coupon_held_public_usd"],
        field="maturing_coupon_held_public_usd",
    )
    if offering <= 0:
        raise D002LAnnouncementOracleError("OFFERING_AMOUNT_NOT_POSITIVE")
    if maturing < 0:
        raise D002LAnnouncementOracleError("MATURING_PUBLIC_AMOUNT_NEGATIVE")

    raw_sha = obj.get("raw_content_sha256")
    retained = bool(obj.get("raw_bytes_retained", False))
    if mode == EVIDENCE_RAW:
        if not retained:
            raise D002LAnnouncementOracleError("RAW_EVIDENCE_BYTES_NOT_RETAINED")
        if not isinstance(raw_sha, str) or not _SHA256_RE.fullmatch(raw_sha):
            raise D002LAnnouncementOracleError("RAW_EVIDENCE_SHA256_INVALID")
    else:
        if retained or raw_sha not in (None, ""):
            raise D002LAnnouncementOracleError("PARSED_EVIDENCE_CANNOT_CLAIM_RAW_ATTESTATION")
        raw_sha = None

    return AnnouncementRecord(
        source_url=url,
        evidence_mode=mode,
        term_and_type=label,
        cusip=cusip,
        issue_date=_date(obj["issue_date"], field="issue_date"),
        offering_amount_usd=offering,
        maturing_coupon_held_public_usd=maturing,
        maturing_date=_date(obj["maturing_date"], field="maturing_date"),
        raw_content_sha256=raw_sha,
        raw_bytes_retained=retained,
    )


def _exact_int(value: Decimal, *, field: str) -> int:
    integral = value.to_integral_value()
    if value != integral:
        raise D002LAnnouncementOracleError(f"NONINTEGER_DOLLAR_{field.upper()}")
    return int(integral)


def reconstruct_settlement(
    records: Sequence[AnnouncementRecord],
    *,
    settlement_date: date,
    expected_cusips: Iterable[str] | None = None,
) -> dict[str, Any]:
    if not records:
        raise D002LAnnouncementOracleError("EMPTY_ANNOUNCEMENT_SET")

    cusips = [r.cusip for r in records]
    duplicates = sorted({c for c in cusips if cusips.count(c) > 1})
    if duplicates:
        raise D002LAnnouncementOracleError(
            f"DUPLICATE_ANNOUNCEMENT_CUSIP:{','.join(duplicates)}"
        )

    for record in records:
        if record.issue_date != settlement_date:
            raise D002LAnnouncementOracleError("ISSUE_DATE_DOES_NOT_MATCH_SETTLEMENT")
        if record.maturing_date != settlement_date:
            raise D002LAnnouncementOracleError("MATURING_DATE_DOES_NOT_MATCH_SETTLEMENT")

    maturing_values = {r.maturing_coupon_held_public_usd for r in records}
    if len(maturing_values) != 1:
        raise D002LAnnouncementOracleError("INCONSISTENT_MATURING_PUBLIC_AMOUNT_ACROSS_ANNOUNCEMENTS")

    declared_expected = None
    completeness = "NOT_INDEPENDENTLY_PROVEN"
    if expected_cusips is not None:
        declared_expected = sorted({str(c).strip().upper() for c in expected_cusips})
        if set(cusips) != set(declared_expected):
            missing = sorted(set(declared_expected) - set(cusips))
            extra = sorted(set(cusips) - set(declared_expected))
            raise D002LAnnouncementOracleError(
                "ANNOUNCEMENT_SET_CUSIP_MISMATCH:"
                f"missing={','.join(missing)};extra={','.join(extra)}"
            )
        completeness = "DECLARED_CUSIP_SET_EXACT"

    offering = sum((r.offering_amount_usd for r in records), Decimal("0"))
    maturing = next(iter(maturing_values))
    net = offering - maturing

    modes = sorted({r.evidence_mode for r in records})
    evidence_strength = (
        EVIDENCE_RAW if modes == [EVIDENCE_RAW] else "PARSED_OR_MIXED_OFFICIAL_CORROBORATION"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "settlement_date": settlement_date.isoformat(),
        "announcement_count": len(records),
        "cusips": sorted(cusips),
        "expected_cusips": declared_expected,
        "announcement_set_completeness": completeness,
        "total_offering_usd": _exact_int(offering, field="total_offering_usd"),
        "total_publicly_held_maturing_usd": _exact_int(
            maturing, field="total_publicly_held_maturing_usd"
        ),
        "net_new_cash_or_pay_down_usd": _exact_int(
            net, field="net_new_cash_or_pay_down_usd"
        ),
        "evidence_modes": modes,
        "evidence_strength": evidence_strength,
        "official_announcement_urls": sorted(r.source_url for r in records),
        "authority_class": (
            AUTHORITY_REFUSAL
            if evidence_strength == EVIDENCE_RAW and completeness == "DECLARED_CUSIP_SET_EXACT"
            else AUTHORITY_DIAGNOSTIC
        ),
        "can_authorize_p1_terminal_pass": False,
        "can_substitute_primary_cash_paydown_dataset": False,
        "confirmatory_outcomes_ingested": False,
        "canonical_run_authorized": False,
    }


def _million_to_usd(value: Any, *, field: str) -> int:
    millions = _decimal(value, field=field)
    usd = millions * Decimal("1000000")
    return _exact_int(usd, field=field)


def crosscheck_primary_cash_paydown_row(
    primary_row: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    """Require exact event-level equality to a primary cash-pay/down row."""
    required = {
        "date",
        "security_type",
        "total_offering",
        "total_publicly_held_maturing",
        "net_new_cash_or_pay_down",
    }
    missing = sorted(required - set(primary_row))
    if missing:
        raise D002LAnnouncementOracleError(f"PRIMARY_ROW_FIELDS_MISSING:{','.join(missing)}")

    if str(primary_row["date"]).strip() != str(oracle["settlement_date"]):
        raise D002LAnnouncementOracleError("PRIMARY_ORACLE_DATE_MISMATCH")
    if str(primary_row["security_type"]).strip().lower() not in {"coupon", "coupons"}:
        raise D002LAnnouncementOracleError("PRIMARY_ROW_NOT_COUPONS")

    checks = {
        "total_offering_usd": _million_to_usd(primary_row["total_offering"], field="total_offering"),
        "total_publicly_held_maturing_usd": _million_to_usd(
            primary_row["total_publicly_held_maturing"], field="total_publicly_held_maturing"
        ),
        "net_new_cash_or_pay_down_usd": _million_to_usd(
            primary_row["net_new_cash_or_pay_down"], field="net_new_cash_or_pay_down"
        ),
    }
    mismatches = {
        key: {"primary": value, "oracle": int(oracle[key])}
        for key, value in checks.items()
        if value != int(oracle[key])
    }
    if mismatches:
        raise D002LAnnouncementOracleError(
            "PRIMARY_ORACLE_AMOUNT_MISMATCH:" + json.dumps(mismatches, sort_keys=True)
        )

    if checks["net_new_cash_or_pay_down_usd"] != (
        checks["total_offering_usd"] - checks["total_publicly_held_maturing_usd"]
    ):
        raise D002LAnnouncementOracleError("PRIMARY_ROW_CASH_IDENTITY_BROKEN")

    return {
        "status": "PASS_EXACT_EVENT_CROSSCHECK",
        "settlement_date": oracle["settlement_date"],
        "fields_matched": sorted(checks),
        "can_authorize_p1_terminal_pass": False,
        "can_substitute_primary_cash_paydown_dataset": False,
    }


def evaluate_primary_oracle_disposition(
    primary_row: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate a primary/oracle comparison without laundering evidence authority."""
    authority = classify_oracle_authority(oracle)
    try:
        crosscheck_primary_cash_paydown_row(primary_row, oracle)
    except D002LAnnouncementOracleError as exc:
        return {
            "status": (
                "REFUSE_PRIMARY_EVENT"
                if authority == AUTHORITY_REFUSAL
                else "DIAGNOSTIC_MISMATCH_NO_SCIENTIFIC_REFUSAL"
            ),
            "reason": str(exc),
            "oracle_authority_class": authority,
            "can_authorize_p1_terminal_pass": False,
            "can_substitute_primary_cash_paydown_dataset": False,
        }
    return {
        "status": "MATCH_NO_PROMOTION",
        "oracle_authority_class": authority,
        "can_authorize_p1_terminal_pass": False,
        "can_substitute_primary_cash_paydown_dataset": False,
    }


def load_manifest(path: Path) -> tuple[date, list[AnnouncementRecord], list[str] | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "D002L-ANNOUNCEMENT-ORACLE-EVIDENCE-v1":
        raise D002LAnnouncementOracleError("ORACLE_MANIFEST_SCHEMA_MISMATCH")
    target = _date(payload.get("settlement_date"), field="settlement_date")
    rows_obj = payload.get("announcements")
    if not isinstance(rows_obj, list):
        raise D002LAnnouncementOracleError("ORACLE_MANIFEST_ANNOUNCEMENTS_NOT_LIST")
    records = [parse_record(item) for item in rows_obj]
    expected = payload.get("expected_cusips")
    if expected is not None and not isinstance(expected, list):
        raise D002LAnnouncementOracleError("ORACLE_MANIFEST_EXPECTED_CUSIPS_NOT_LIST")
    return target, records, expected


def manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
