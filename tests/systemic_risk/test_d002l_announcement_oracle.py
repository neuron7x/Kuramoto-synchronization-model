from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path

import pytest

from research.systemic_risk.d002l_treasury_announcement_oracle import (
    D002LAnnouncementOracleError,
    EVIDENCE_PARSED,
    EVIDENCE_RAW,
    crosscheck_primary_cash_paydown_row,
    load_manifest,
    parse_record,
    reconstruct_settlement,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = REPO_ROOT / "artifacts/d002l/exposure/d002l_announcement_oracle_2024-05-31_v1.json"


def _loaded():
    target, records, expected = load_manifest(EVIDENCE)
    return target, records, expected


def test_known_official_20240531_reconstruction_is_exact() -> None:
    target, records, expected = _loaded()
    result = reconstruct_settlement(records, settlement_date=target, expected_cusips=expected)
    assert result["announcement_count"] == 6
    assert result["total_offering_usd"] == 243_000_000_000
    assert result["total_publicly_held_maturing_usd"] == 87_595_000_000
    assert result["net_new_cash_or_pay_down_usd"] == 155_405_000_000
    assert result["announcement_set_completeness"] == "DECLARED_CUSIP_SET_EXACT"


def test_evidence_capsule_expected_reconstruction_matches_code() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    target, records, expected = _loaded()
    result = reconstruct_settlement(records, settlement_date=target, expected_cusips=expected)
    assert payload["expected_reconstruction"] == {
        "total_offering_usd": result["total_offering_usd"],
        "total_publicly_held_maturing_usd": result["total_publicly_held_maturing_usd"],
        "net_new_cash_or_pay_down_usd": result["net_new_cash_or_pay_down_usd"],
    }


def test_oracle_never_authorizes_p1_or_substitutes_primary() -> None:
    target, records, expected = _loaded()
    result = reconstruct_settlement(records, settlement_date=target, expected_cusips=expected)
    assert result["can_authorize_p1_terminal_pass"] is False
    assert result["can_substitute_primary_cash_paydown_dataset"] is False
    assert result["canonical_run_authorized"] is False
    assert result["confirmatory_outcomes_ingested"] is False


def test_parsed_official_mode_is_corroboration_not_raw() -> None:
    _, records, _ = _loaded()
    assert {r.evidence_mode for r in records} == {EVIDENCE_PARSED}
    assert all(r.raw_content_sha256 is None for r in records)
    assert all(r.raw_bytes_retained is False for r in records)


def test_exact_primary_row_crosscheck_passes_but_does_not_promote() -> None:
    target, records, expected = _loaded()
    oracle = reconstruct_settlement(records, settlement_date=target, expected_cusips=expected)
    primary = {"date":"2024-05-31","security_type":"Coupons","total_offering":"243000","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155405"}
    check = crosscheck_primary_cash_paydown_row(primary, oracle)
    assert check["status"] == "PASS_EXACT_EVENT_CROSSCHECK"
    assert check["can_authorize_p1_terminal_pass"] is False


def test_primary_amount_mismatch_refuses() -> None:
    target, records, expected = _loaded()
    oracle = reconstruct_settlement(records, settlement_date=target, expected_cusips=expected)
    primary = {"date":"2024-05-31","security_type":"Coupons","total_offering":"242999","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155404"}
    with pytest.raises(D002LAnnouncementOracleError, match="PRIMARY_ORACLE_AMOUNT_MISMATCH"):
        crosscheck_primary_cash_paydown_row(primary, oracle)


def test_duplicate_cusip_refuses_double_count() -> None:
    target, records, expected = _loaded()
    with pytest.raises(D002LAnnouncementOracleError, match="DUPLICATE_ANNOUNCEMENT_CUSIP"):
        reconstruct_settlement([*records, records[0]], settlement_date=target, expected_cusips=expected)


def test_missing_expected_cusip_refuses() -> None:
    target, records, expected = _loaded()
    with pytest.raises(D002LAnnouncementOracleError, match="ANNOUNCEMENT_SET_CUSIP_MISMATCH"):
        reconstruct_settlement(records[:-1], settlement_date=target, expected_cusips=expected)


def test_issue_date_drift_refuses() -> None:
    target, records, expected = _loaded()
    bad = [replace(records[0], issue_date=date(2024, 5, 30)), *records[1:]]
    with pytest.raises(D002LAnnouncementOracleError, match="ISSUE_DATE_DOES_NOT_MATCH_SETTLEMENT"):
        reconstruct_settlement(bad, settlement_date=target, expected_cusips=expected)


def test_maturing_amount_disagreement_refuses() -> None:
    target, records, expected = _loaded()
    bad = [replace(records[0], maturing_coupon_held_public_usd=records[0].maturing_coupon_held_public_usd + 1), *records[1:]]
    with pytest.raises(D002LAnnouncementOracleError, match="INCONSISTENT_MATURING_PUBLIC_AMOUNT"):
        reconstruct_settlement(bad, settlement_date=target, expected_cusips=expected)


def _first_payload() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["announcements"][0].copy()


def test_unofficial_url_refuses() -> None:
    payload = _first_payload(); payload["source_url"] = "https://example.invalid/A.pdf"
    with pytest.raises(D002LAnnouncementOracleError, match="NOT_OFFICIAL_TREASURY"): parse_record(payload)


def test_non_https_official_url_refuses() -> None:
    payload = _first_payload(); payload["source_url"] = payload["source_url"].replace("https://", "http://")
    with pytest.raises(D002LAnnouncementOracleError, match="NOT_HTTPS"): parse_record(payload)


def test_non_coupon_announcement_refuses() -> None:
    payload = _first_payload(); payload["term_and_type"] = "13-Week Bill"
    with pytest.raises(D002LAnnouncementOracleError, match="NON_COUPON"): parse_record(payload)


def test_raw_mode_requires_retained_bytes_and_valid_sha() -> None:
    payload = _first_payload(); payload["evidence_mode"] = EVIDENCE_RAW
    with pytest.raises(D002LAnnouncementOracleError, match="RAW_EVIDENCE_BYTES_NOT_RETAINED"): parse_record(payload)
    payload["raw_bytes_retained"] = True; payload["raw_content_sha256"] = "bad"
    with pytest.raises(D002LAnnouncementOracleError, match="RAW_EVIDENCE_SHA256_INVALID"): parse_record(payload)


def test_parsed_mode_cannot_launder_raw_attestation() -> None:
    payload = _first_payload(); payload["raw_bytes_retained"] = True; payload["raw_content_sha256"] = "0" * 64
    with pytest.raises(D002LAnnouncementOracleError, match="CANNOT_CLAIM_RAW_ATTESTATION"): parse_record(payload)


def test_even_all_raw_attested_records_cannot_authorize_primary_pass() -> None:
    target, records, expected = _loaded()
    raw_records = [replace(r, evidence_mode=EVIDENCE_RAW, raw_content_sha256="a" * 64, raw_bytes_retained=True) for r in records]
    result = reconstruct_settlement(raw_records, settlement_date=target, expected_cusips=expected)
    assert result["evidence_strength"] == EVIDENCE_RAW
    assert result["can_authorize_p1_terminal_pass"] is False
    assert result["can_substitute_primary_cash_paydown_dataset"] is False


def test_parser_decimal_and_date_native_types_are_accepted() -> None:
    from decimal import Decimal
    payload = _first_payload(); payload["offering_amount_usd"] = Decimal("69000000000"); payload["issue_date"] = date(2024,5,31); payload["maturing_date"] = date(2024,5,31)
    record = parse_record(payload)
    assert record.offering_amount_usd == Decimal("69000000000") and record.issue_date == date(2024,5,31)


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity"])
def test_parser_rejects_invalid_numeric_values(value: str) -> None:
    payload = _first_payload(); payload["offering_amount_usd"] = value
    with pytest.raises(D002LAnnouncementOracleError): parse_record(payload)


def test_parser_rejects_invalid_date() -> None:
    payload = _first_payload(); payload["issue_date"] = "2024-99-99"
    with pytest.raises(D002LAnnouncementOracleError, match="INVALID_ISSUE_DATE"): parse_record(payload)


def test_parser_rejects_missing_fields_invalid_mode_and_bad_cusip() -> None:
    payload = _first_payload(); del payload["cusip"]
    with pytest.raises(D002LAnnouncementOracleError, match="ANNOUNCEMENT_FIELDS_MISSING"): parse_record(payload)
    payload = _first_payload(); payload["evidence_mode"] = "UNLOCKED"
    with pytest.raises(D002LAnnouncementOracleError, match="INVALID_ANNOUNCEMENT_EVIDENCE_MODE"): parse_record(payload)
    payload = _first_payload(); payload["cusip"] = "BAD"
    with pytest.raises(D002LAnnouncementOracleError, match="INVALID_CUSIP"): parse_record(payload)


def test_parser_rejects_official_but_wrong_surface_and_non_pdf() -> None:
    payload = _first_payload(); payload["source_url"] = "https://www.treasurydirect.gov/not-locked/A.pdf"
    with pytest.raises(D002LAnnouncementOracleError, match="OUTSIDE_LOCKED_ORACLE_SURFACE"): parse_record(payload)
    payload = _first_payload(); payload["source_url"] = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/A.txt"
    with pytest.raises(D002LAnnouncementOracleError, match="ANNOUNCEMENT_SOURCE_NOT_PDF"): parse_record(payload)


def test_parser_rejects_nonpositive_offering_and_negative_maturing() -> None:
    payload = _first_payload(); payload["offering_amount_usd"] = "0"
    with pytest.raises(D002LAnnouncementOracleError, match="OFFERING_AMOUNT_NOT_POSITIVE"): parse_record(payload)
    payload = _first_payload(); payload["maturing_coupon_held_public_usd"] = "-1"
    with pytest.raises(D002LAnnouncementOracleError, match="MATURING_PUBLIC_AMOUNT_NEGATIVE"): parse_record(payload)


def test_valid_raw_attestation_parses_without_promoting_authority() -> None:
    payload = _first_payload(); payload["evidence_mode"] = EVIDENCE_RAW; payload["raw_bytes_retained"] = True; payload["raw_content_sha256"] = "a"*64
    record = parse_record(payload)
    assert record.evidence_mode == EVIDENCE_RAW and record.raw_bytes_retained and record.raw_content_sha256 == "a"*64


def test_empty_set_and_maturing_date_drift_refuse() -> None:
    target, records, expected = _loaded()
    with pytest.raises(D002LAnnouncementOracleError, match="EMPTY_ANNOUNCEMENT_SET"): reconstruct_settlement([], settlement_date=target)
    bad=[replace(records[0],maturing_date=date(2024,5,30)),*records[1:]]
    with pytest.raises(D002LAnnouncementOracleError, match="MATURING_DATE_DOES_NOT_MATCH_SETTLEMENT"): reconstruct_settlement(bad,settlement_date=target,expected_cusips=expected)


def test_reconstruction_without_expected_cusips_is_explicitly_not_complete() -> None:
    target, records, _ = _loaded(); result=reconstruct_settlement(records,settlement_date=target,expected_cusips=None)
    assert result["expected_cusips"] is None and result["announcement_set_completeness"] == "NOT_INDEPENDENTLY_PROVEN"


def test_noninteger_dollar_reconstruction_refuses() -> None:
    from decimal import Decimal
    target, records, _ = _loaded(); bad=[replace(records[0],offering_amount_usd=records[0].offering_amount_usd+Decimal("0.5")),*records[1:]]
    with pytest.raises(D002LAnnouncementOracleError, match="NONINTEGER_DOLLAR_TOTAL_OFFERING_USD"): reconstruct_settlement(bad,settlement_date=target)


def test_primary_row_missing_date_security_and_cash_identity_guards() -> None:
    target, records, expected = _loaded(); oracle=reconstruct_settlement(records,settlement_date=target,expected_cusips=expected)
    with pytest.raises(D002LAnnouncementOracleError, match="PRIMARY_ROW_FIELDS_MISSING"): crosscheck_primary_cash_paydown_row({},oracle)
    primary={"date":"2024-05-30","security_type":"Coupons","total_offering":"243000","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155405"}
    with pytest.raises(D002LAnnouncementOracleError, match="PRIMARY_ORACLE_DATE_MISMATCH"): crosscheck_primary_cash_paydown_row(primary,oracle)
    primary["date"]="2024-05-31"; primary["security_type"]="Bills"
    with pytest.raises(D002LAnnouncementOracleError, match="PRIMARY_ROW_NOT_COUPONS"): crosscheck_primary_cash_paydown_row(primary,oracle)
    primary["security_type"]="Coupons"; primary["net_new_cash_or_pay_down"]="155404"; corrupt=dict(oracle); corrupt["net_new_cash_or_pay_down_usd"]=155_404_000_000
    with pytest.raises(D002LAnnouncementOracleError, match="PRIMARY_ROW_CASH_IDENTITY_BROKEN"): crosscheck_primary_cash_paydown_row(primary,corrupt)


def test_manifest_schema_shape_and_expected_cusip_guards(tmp_path: Path) -> None:
    payload=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    bad=dict(payload); bad["schema_version"]="WRONG"; p=tmp_path/"bad_schema.json"; p.write_text(json.dumps(bad))
    with pytest.raises(D002LAnnouncementOracleError, match="ORACLE_MANIFEST_SCHEMA_MISMATCH"): load_manifest(p)
    bad=dict(payload); bad["announcements"]="not-a-list"; p=tmp_path/"bad_rows.json"; p.write_text(json.dumps(bad))
    with pytest.raises(D002LAnnouncementOracleError, match="ANNOUNCEMENTS_NOT_LIST"): load_manifest(p)
    bad=dict(payload); bad["expected_cusips"]="not-a-list"; p=tmp_path/"bad_expected.json"; p.write_text(json.dumps(bad))
    with pytest.raises(D002LAnnouncementOracleError, match="EXPECTED_CUSIPS_NOT_LIST"): load_manifest(p)


def test_manifest_sha256_is_exact_content_digest() -> None:
    import hashlib
    from research.systemic_risk.d002l_treasury_announcement_oracle import manifest_sha256
    assert manifest_sha256(EVIDENCE) == hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()


def test_authority_lattice_parsed_is_diagnostic_only() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import AUTHORITY_DIAGNOSTIC, classify_oracle_authority
    target,records,expected=_loaded(); oracle=reconstruct_settlement(records,settlement_date=target,expected_cusips=expected)
    assert oracle["authority_class"] == AUTHORITY_DIAGNOSTIC and classify_oracle_authority(oracle) == AUTHORITY_DIAGNOSTIC


def test_authority_lattice_raw_complete_is_refusal_only() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import AUTHORITY_REFUSAL, classify_oracle_authority
    target,records,expected=_loaded(); raw=[replace(r,evidence_mode=EVIDENCE_RAW,raw_content_sha256="b"*64,raw_bytes_retained=True) for r in records]; oracle=reconstruct_settlement(raw,settlement_date=target,expected_cusips=expected)
    assert oracle["authority_class"] == AUTHORITY_REFUSAL and classify_oracle_authority(oracle) == AUTHORITY_REFUSAL and oracle["can_authorize_p1_terminal_pass"] is False


def test_raw_without_exact_expected_set_remains_diagnostic() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import AUTHORITY_DIAGNOSTIC
    target,records,_=_loaded(); raw=[replace(r,evidence_mode=EVIDENCE_RAW,raw_content_sha256="c"*64,raw_bytes_retained=True) for r in records]; oracle=reconstruct_settlement(raw,settlement_date=target,expected_cusips=None)
    assert oracle["authority_class"] == AUTHORITY_DIAGNOSTIC


def test_authority_escalation_flags_are_rejected() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import classify_oracle_authority
    target,records,expected=_loaded(); oracle=reconstruct_settlement(records,settlement_date=target,expected_cusips=expected); bad=dict(oracle); bad["can_authorize_p1_terminal_pass"]=True
    with pytest.raises(D002LAnnouncementOracleError, match="ORACLE_AUTHORITY_ESCALATION_DETECTED"): classify_oracle_authority(bad)


def test_parsed_mismatch_is_diagnostic_not_scientific_refusal() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import evaluate_primary_oracle_disposition
    target,records,expected=_loaded(); oracle=reconstruct_settlement(records,settlement_date=target,expected_cusips=expected); primary={"date":"2024-05-31","security_type":"Coupons","total_offering":"242999","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155404"}; d=evaluate_primary_oracle_disposition(primary,oracle)
    assert d["status"] == "DIAGNOSTIC_MISMATCH_NO_SCIENTIFIC_REFUSAL" and d["can_authorize_p1_terminal_pass"] is False


def test_raw_complete_mismatch_can_only_refuse_never_promote() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import evaluate_primary_oracle_disposition
    target,records,expected=_loaded(); raw=[replace(r,evidence_mode=EVIDENCE_RAW,raw_content_sha256="d"*64,raw_bytes_retained=True) for r in records]; oracle=reconstruct_settlement(raw,settlement_date=target,expected_cusips=expected); primary={"date":"2024-05-31","security_type":"Coupons","total_offering":"242999","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155404"}; d=evaluate_primary_oracle_disposition(primary,oracle)
    assert d["status"] == "REFUSE_PRIMARY_EVENT" and d["can_authorize_p1_terminal_pass"] is False


def test_exact_match_never_promotes_under_either_authority_class() -> None:
    from research.systemic_risk.d002l_treasury_announcement_oracle import evaluate_primary_oracle_disposition
    target,records,expected=_loaded(); primary={"date":"2024-05-31","security_type":"Coupons","total_offering":"243000","total_publicly_held_maturing":"87595","net_new_cash_or_pay_down":"155405"}; parsed=reconstruct_settlement(records,settlement_date=target,expected_cusips=expected)
    assert evaluate_primary_oracle_disposition(primary,parsed)["status"] == "MATCH_NO_PROMOTION"
    raw_records=[replace(r,evidence_mode=EVIDENCE_RAW,raw_content_sha256="e"*64,raw_bytes_retained=True) for r in records]; raw=reconstruct_settlement(raw_records,settlement_date=target,expected_cusips=expected); out=evaluate_primary_oracle_disposition(primary,raw)
    assert out["status"] == "MATCH_NO_PROMOTION" and out["can_authorize_p1_terminal_pass"] is False
