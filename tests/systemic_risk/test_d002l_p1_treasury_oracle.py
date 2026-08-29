from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest

from research.systemic_risk.d002l_treasury_oracle import (
    AUTHORITY,
    AnnouncementRecord,
    D002LTreasuryOracleError,
    crosscheck_registry,
    deterministic_oracle_sample_dates,
    parse_announcement_records,
    reconstruct_by_settlement_date,
    sha256_bytes,
    structured_record_from_announcement_text,
)

OFFICIAL = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/2026/A_20260506_3.pdf"
SHA = "a" * 64


def row(*, day="2026-05-15", cusip="912810UU0", offering="25", maturing="83", doc="doc-1", security="30-Year Bond", url=OFFICIAL):
    return {
        "settlement_date": day,
        "security_type": security,
        "cusip": cusip,
        "offering_million": offering,
        "publicly_held_maturing_million": maturing,
        "source_url": url,
        "source_sha256": SHA,
        "source_document_id": doc,
    }


def rec(day: str, idx: int, *, offering="100", maturing="40") -> AnnouncementRecord:
    y = int(day[:4])
    cusip = f"{y % 100:02d}{idx:07d}"
    return AnnouncementRecord(
        settlement_date=date.fromisoformat(day),
        security_type="2-Year Note",
        cusip=cusip,
        offering_million=Decimal(offering),
        publicly_held_maturing_million=Decimal(maturing),
        source_url=f"https://www.treasurydirect.gov/instit/annceresult/press/preanre/{y}/A_{y}_{idx}.pdf",
        source_sha256=f"{idx % 16:x}" * 64,
        source_document_id=f"doc-{y}-{idx}",
    )


def full_registry() -> dict:
    events = []
    for y in range(2014, 2027):
        for month in (1, 12):
            events.append({
                "settlement_date": f"{y}-{month:02d}-15",
                "eligible": True,
                "total_offering_million_usd": "100",
                "total_publicly_held_maturing_million_usd": "40",
                "coupon_net_new_cash_or_pay_down_million_usd": "60",
            })
    return {
        "schema_version": "D002L-EXPOSURE-REGISTRY-v1",
        "confirmatory_outcomes_ingested": False,
        "events": events,
    }


def full_records() -> list[AnnouncementRecord]:
    out = []
    i = 1
    for y in range(2014, 2027):
        for month in (1, 12):
            out.append(rec(f"{y}-{month:02d}-15", i))
            i += 1
    return out


def test_structured_extract_uses_non_original_issue_date_and_units() -> None:
    text = """
    TREASURY OFFERING ANNOUNCEMENT
    Term and Type of Security 30-Year Bond
    Offering Amount $25,000,000,000
    CUSIP Number 912810UU0
    Original Issue Date February 15, 2026
    Issue Date May 15, 2026
    Estimated Amount of Maturing Coupon Securities Held by the Public $83,284,000,000
    """
    got = structured_record_from_announcement_text(
        text, source_url=OFFICIAL, source_sha256=SHA, source_document_id="doc"
    )
    assert got["settlement_date"] == "2026-05-15"
    assert got["offering_million"] == "25000"
    assert got["publicly_held_maturing_million"] == "83284"
    assert got["cusip"] == "912810UU0"


def test_extract_rejects_unofficial_host_and_invalid_digest() -> None:
    text = "Term and Type of Security 2-Year Note Offering Amount $1,000,000 CUSIP Number 912810UU0 Issue Date May 15, 2026 Estimated Amount of Maturing Coupon Securities Held by the Public $2,000,000"
    with pytest.raises(D002LTreasuryOracleError, match="UNOFFICIAL_ORACLE_SOURCE_URL"):
        structured_record_from_announcement_text(text, source_url="https://evil.example/instit/annceresult/press/preanre/x.pdf", source_sha256=SHA, source_document_id="x")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_SOURCE_SHA256"):
        structured_record_from_announcement_text(text, source_url=OFFICIAL, source_sha256="bad", source_document_id="x")


def test_extract_rejects_official_host_wrong_path() -> None:
    with pytest.raises(D002LTreasuryOracleError, match="UNSUPPORTED_OFFICIAL_ANNOUNCEMENT_PATH"):
        structured_record_from_announcement_text("x", source_url="https://www.treasurydirect.gov/random/x.pdf", source_sha256=SHA, source_document_id="x")


def test_parse_rejects_non_utf8_nonlist_and_missing_fields() -> None:
    with pytest.raises(D002LTreasuryOracleError, match="ORACLE_RECORDS_NOT_UTF8"):
        parse_announcement_records(b"\xff\xfe")
    with pytest.raises(D002LTreasuryOracleError, match="ORACLE_RECORDS_MUST_BE_NONEMPTY_LIST"):
        parse_announcement_records("{}")
    with pytest.raises(D002LTreasuryOracleError, match="ORACLE_FIELDS_MISSING"):
        parse_announcement_records(json.dumps([{"settlement_date": "2026-01-01"}]))


def test_parse_rejects_outcome_or_model_leakage() -> None:
    r = row(); r["TGCR"] = 4.2
    with pytest.raises(D002LTreasuryOracleError, match="OUTCOME_OR_MODEL_FIELD_FORBIDDEN"):
        parse_announcement_records(json.dumps([r]))


def test_parse_rejects_duplicate_document_id() -> None:
    a = row(doc="same", cusip="912810UU0")
    b = row(doc="same", cusip="912810UV8")
    with pytest.raises(D002LTreasuryOracleError, match="DUPLICATE_SOURCE_DOCUMENT_ID"):
        parse_announcement_records(json.dumps([a, b]))


def test_parse_rejects_duplicate_settlement_cusip() -> None:
    a = row(doc="a")
    b = row(doc="b")
    with pytest.raises(D002LTreasuryOracleError, match="DUPLICATE_SETTLEMENT_CUSIP"):
        parse_announcement_records(json.dumps([a, b]))


def test_parse_rejects_bill_invalid_sha_and_invalid_amounts() -> None:
    with pytest.raises(D002LTreasuryOracleError, match="NON_COUPON_ANNOUNCEMENT"):
        parse_announcement_records(json.dumps([row(security="13-Week Bill")]))
    bad = row(); bad["source_sha256"] = "0" * 63
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_SOURCE_SHA256"):
        parse_announcement_records(json.dumps([bad]))
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_ORACLE_AMOUNTS"):
        parse_announcement_records(json.dumps([row(offering="0")]))


def test_parse_accepts_official_fiscaldata_archive_path() -> None:
    url = "https://fiscaldata.treasury.gov/static-data/published-reports/auctions-query/announcements/x.pdf"
    got = parse_announcement_records(json.dumps([row(url=url)]))
    assert len(got) == 1


def test_reconstruct_sums_offerings_and_subtracts_maturing_exactly_once() -> None:
    rs = [
        rec("2026-05-15", 1, offering="25", maturing="83"),
        rec("2026-05-15", 2, offering="58", maturing="83"),
        rec("2026-05-15", 3, offering="42", maturing="83"),
    ]
    got = reconstruct_by_settlement_date(rs)["2026-05-15"]
    assert Decimal(got["total_offering_million_usd"]) == Decimal("125")
    assert Decimal(got["total_publicly_held_maturing_million_usd"]) == Decimal("83")
    assert Decimal(got["net_new_cash_or_pay_down_million_usd"]) == Decimal("42")


def test_reconstruct_rejects_inconsistent_date_level_maturing() -> None:
    rs = [rec("2026-05-15", 1, maturing="83"), rec("2026-05-15", 2, maturing="84")]
    with pytest.raises(D002LTreasuryOracleError, match="INCONSISTENT_PUBLICLY_HELD_MATURING"):
        reconstruct_by_settlement_date(rs)


def test_deterministic_sample_is_first_last_per_year() -> None:
    got = deterministic_oracle_sample_dates(full_registry())
    assert len(got) == 26
    assert got[:2] == ["2014-01-15", "2014-12-15"]
    assert got[-2:] == ["2026-01-15", "2026-12-15"]


def test_sample_refuses_missing_year_outcome_firewall_and_bad_event() -> None:
    r = full_registry(); r["events"] = [e for e in r["events"] if not e["settlement_date"].startswith("2020-")]
    with pytest.raises(D002LTreasuryOracleError, match="PRIMARY_REGISTRY_YEAR_COVERAGE_INVALID"):
        deterministic_oracle_sample_dates(r)
    r = full_registry(); r["confirmatory_outcomes_ingested"] = True
    with pytest.raises(D002LTreasuryOracleError, match="PRIMARY_REGISTRY_OUTCOME_FIREWALL_BROKEN"):
        deterministic_oracle_sample_dates(r)
    r = full_registry(); r["events"][0]["p_value"] = 0.01
    with pytest.raises(D002LTreasuryOracleError, match="OUTCOME_OR_MODEL_FIELD_FORBIDDEN"):
        deterministic_oracle_sample_dates(r)


def test_crosscheck_match_is_refusal_only_not_authority() -> None:
    got = crosscheck_registry(full_registry(), full_records())
    assert got["status"] == "ORACLE_MATCH"
    assert got["authority"] == AUTHORITY == "SECONDARY_REFUSAL_ONLY"
    assert got["can_authorize_p1_terminal_pass"] is False
    assert got["can_refuse_p1"] is True
    assert got["confirmatory_outcomes_ingested"] is False
    assert got["matched_sample_count"] == 26


def test_crosscheck_refuses_primary_oracle_divergence() -> None:
    r = full_registry()
    r["events"][0]["coupon_net_new_cash_or_pay_down_million_usd"] = "61"
    with pytest.raises(D002LTreasuryOracleError, match="PRIMARY_ORACLE_DIVERGENCE"):
        crosscheck_registry(r, full_records())


def test_crosscheck_refuses_missing_required_oracle_date() -> None:
    records = full_records()[1:]
    with pytest.raises(D002LTreasuryOracleError, match="ORACLE_REQUIRED_DATES_MISSING"):
        crosscheck_registry(full_registry(), records)


def test_crosscheck_refuses_duplicate_primary_event_date() -> None:
    r = full_registry()
    r["events"].append(copy.deepcopy(r["events"][0]))
    with pytest.raises(D002LTreasuryOracleError, match="DUPLICATE_PRIMARY_EVENT_DATE"):
        crosscheck_registry(r, full_records())


def test_sha256_bytes_is_exact() -> None:
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_invalid_date_decimal_nonfinite_and_parenthesized_negative_are_refused() -> None:
    bad = row(day="not-a-date")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_SETTLEMENT_DATE"):
        parse_announcement_records(json.dumps([bad]))
    bad = row(offering="abc")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_DECIMAL"):
        parse_announcement_records(json.dumps([bad]))
    bad = row(offering="NaN")
    with pytest.raises(D002LTreasuryOracleError, match="NONFINITE_DECIMAL"):
        parse_announcement_records(json.dumps([bad]))
    bad = row(offering="(1)")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_ORACLE_AMOUNTS"):
        parse_announcement_records(json.dumps([bad]))


def test_structured_extract_refuses_missing_required_announcement_field() -> None:
    text = "Term and Type of Security 2-Year Note Offering Amount $1,000,000 CUSIP Number 912810UU0 Issue Date May 15, 2026"
    with pytest.raises(D002LTreasuryOracleError, match="ANNOUNCEMENT_FIELD_NOT_FOUND:maturing"):
        structured_record_from_announcement_text(text, source_url=OFFICIAL, source_sha256=SHA, source_document_id="x")


def test_parse_refuses_invalid_json_nonobject_empty_doc_bad_cusip_and_negative_maturing() -> None:
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_ORACLE_JSON"):
        parse_announcement_records("[")
    with pytest.raises(D002LTreasuryOracleError, match="ORACLE_ROW_NOT_OBJECT"):
        parse_announcement_records(json.dumps([42]))
    bad = row(doc="   ")
    with pytest.raises(D002LTreasuryOracleError, match="EMPTY_SOURCE_DOCUMENT_ID"):
        parse_announcement_records(json.dumps([bad]))
    bad = row(cusip="BAD")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_CUSIP"):
        parse_announcement_records(json.dumps([bad]))
    bad = row(maturing="-1")
    with pytest.raises(D002LTreasuryOracleError, match="INVALID_ORACLE_AMOUNTS"):
        parse_announcement_records(json.dumps([bad]))


def test_sample_refuses_wrong_schema_missing_events_and_nonobject_event() -> None:
    with pytest.raises(D002LTreasuryOracleError, match="WRONG_PRIMARY_REGISTRY_SCHEMA"):
        deterministic_oracle_sample_dates({"schema_version": "wrong", "confirmatory_outcomes_ingested": False, "events": []})
    with pytest.raises(D002LTreasuryOracleError, match="PRIMARY_REGISTRY_EVENTS_MISSING"):
        deterministic_oracle_sample_dates({"schema_version": "D002L-EXPOSURE-REGISTRY-v1", "confirmatory_outcomes_ingested": False, "events": []})
    r = full_registry(); r["events"][0] = 7
    with pytest.raises(D002LTreasuryOracleError, match="PRIMARY_EVENT_NOT_OBJECT"):
        deterministic_oracle_sample_dates(r)


def test_sample_skips_ineligible_and_out_of_range_and_supports_single_date_year() -> None:
    r = full_registry()
    r["events"] = [e for e in r["events"] if e["settlement_date"] != "2014-12-15"]
    r["events"].append({"settlement_date": "2013-12-15", "eligible": True})
    r["events"].append({"settlement_date": "2027-01-15", "eligible": True})
    r["events"].append({"settlement_date": "2026-06-15", "eligible": False})
    got = deterministic_oracle_sample_dates(r)
    assert got.count("2014-01-15") == 1
    assert "2014-12-15" not in got
    assert "2013-12-15" not in got and "2027-01-15" not in got
