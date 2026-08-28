# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed guards for D-002L-P1 exposure-registry implementation.

These tests validate the compiler and phase firewall. Synthetic source fixtures
exercise schema and event logic only; they are not scientific evidence and may
never advance the D-002L lineage.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from research.systemic_risk.d002l_exposure_registry import (
    CALIBRATION_START,
    CONFIRMATORY_END,
    D002LExposureError,
    LOCKED_DATASET,
    LOCKED_PUBLISHER,
    LOCKED_SOURCE_URL,
    SourceRow,
    blocked_result,
    build_events,
    compile_registry,
    parse_source_bytes,
    sha256_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG = REPO_ROOT / "docs/governance/D002L_PREREGISTRATION.yaml"
SOURCE_PLAN = REPO_ROOT / "artifacts/d002l/prereg/d002l_source_plan_v1.json"
ESTIMAND = REPO_ROOT / "artifacts/d002l/prereg/d002l_primary_estimand_contract_v1.json"
D002J_PREREG = REPO_ROOT / "docs/governance/D002J_PREREGISTRATION.yaml"
D002K_PREREG = REPO_ROOT / "docs/governance/D002K_PREREGISTRATION.yaml"
CONTRACT = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_source_contract_v1.json"
STATUS = REPO_ROOT / "artifacts/d002l/exposure/d002l_p1_execution_status_v1.json"
P0_VERDICT = REPO_ROOT / "artifacts/governance/verdicts/d002l_p0_verdict_v1.json"
P1_VERDICT = REPO_ROOT / "artifacts/governance/verdicts/d002l_p1_verdict_v1.json"
FIXTURE_CSV = REPO_ROOT / "tests/fixtures/d002l/treasury_cash_paydown_synthetic.csv"
FIXTURE_HTML = REPO_ROOT / "tests/fixtures/d002l/treasury_cash_paydown_synthetic.html"

D002L_PREREG_SHA = "6a081f50088a4c461e60d73887566e2b25d1dd549c760dd56b153fbe94b8b927"
D002L_SOURCE_PLAN_SHA = "a95933555b20e2ce2ae412ee363fa58e989ef10bac6645a33dcefb589a72a2b7"
D002L_ESTIMAND_SHA = "7e92843c7d36b1b873261db990fbeea2b2cf9d324e3c55c8bb50ce22c4acfdfe"
D002J_PREREG_SHA = "f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0"
D002K_PREREG_SHA = "2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prov(raw: bytes) -> dict[str, object]:
    return {
        "source_id": "TREASURY_CASH_PAYDOWN",
        "publisher": LOCKED_PUBLISHER,
        "dataset": LOCKED_DATASET,
        "source_url": LOCKED_SOURCE_URL,
        "retrieved_at_utc": "2026-08-28T13:00:00Z",
        "content_sha256": sha256_bytes(raw),
        "revision_or_vintage_status": "point_in_time_web_snapshot",
        "retrieval_complete": True,
        "retrieval_scope": "full_historical_table_snapshot",
        "coverage_start": CALIBRATION_START.isoformat(),
        "coverage_end": CONFIRMATORY_END.isoformat(),
    }


def _row(d: date, typ: str, offering: str, maturing: str, net: str, n: int) -> SourceRow:
    return SourceRow(d, typ, Decimal(offering), Decimal(maturing), Decimal(net), n)


def test_p0_and_ancestor_preregistrations_are_byte_exact() -> None:
    assert _sha(PREREG) == D002L_PREREG_SHA
    assert _sha(SOURCE_PLAN) == D002L_SOURCE_PLAN_SHA
    assert _sha(ESTIMAND) == D002L_ESTIMAND_SHA
    assert _sha(D002J_PREREG) == D002J_PREREG_SHA
    assert _sha(D002K_PREREG) == D002K_PREREG_SHA


def test_p1_source_contract_exists_and_is_not_scientific_pass() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "D002L-P1-SOURCE-CONTRACT-v1"
    assert payload["status"] == "HARDENED_AWAITING_DIRECT_SOURCE_COMPLETE_EXECUTION"
    assert payload["lineage_policy"]["blocked_source_access_is_pass"] is False
    assert payload["lineage_policy"]["canonical_run_authorized"] is False


def test_locked_source_is_exact_p0_source() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))["locked_source"]
    assert payload["url"] == LOCKED_SOURCE_URL
    assert payload["publisher"] == LOCKED_PUBLISHER
    assert payload["dataset"] == LOCKED_DATASET


def test_csv_fixture_compiles_deterministically() -> None:
    raw = FIXTURE_CSV.read_bytes()
    a = compile_registry(raw, _prov(raw), format_hint="csv")
    b = compile_registry(raw, _prov(raw), format_hint="csv")
    assert a == b
    assert a["confirmatory_outcomes_ingested"] is False
    assert a["canonical_run_authorized"] is False
    assert a["next_phase_authorized"] == "D002L-P2"


def test_html_locked_table_parser_works() -> None:
    raw = FIXTURE_HTML.read_bytes()
    rows = parse_source_bytes(raw, format_hint="html")
    assert len(rows) == 13
    assert rows[0].security_type == "Coupons"
    assert rows[0].net_new_cash_or_pay_down_million == Decimal("10000")


def test_non_coupon_rows_are_not_events() -> None:
    raw = FIXTURE_CSV.read_bytes()
    registry = compile_registry(raw, _prov(raw), format_hint="csv")
    first = next(e for e in registry["events"] if e["settlement_date"] == "2014-09-02")
    assert first["source_security_types"] == ["Coupons"]
    assert first["coupon_net_new_cash_or_pay_down_million_usd"] == "15000"


def test_component_coupon_rows_aggregate_same_date() -> None:
    rows = [
        _row(date(2020, 1, 15), "Notes", "20", "10", "10", 1),
        _row(date(2020, 1, 15), "Bonds", "30", "20", "10", 2),
        _row(date(2020, 1, 15), "FRNs", "15", "10", "5", 3),
        _row(date(2020, 1, 15), "TIPS", "25", "15", "10", 4),
    ]
    event = build_events(rows)[0]
    assert event["coupon_row_mode"] == "SUM_COMPONENTS"
    assert event["coupon_net_new_cash_or_pay_down_million_usd"] == "35"
    assert event["source_security_types"] == ["Notes", "Bonds", "FRNs", "TIPS"]


def test_direct_coupon_plus_components_refuses_double_count() -> None:
    rows = [
        _row(date(2020, 1, 15), "Coupons", "50", "30", "20", 1),
        _row(date(2020, 1, 15), "Notes", "20", "10", "10", 2),
    ]
    with pytest.raises(D002LExposureError, match="AMBIGUOUS_COUPON_DOUBLE_COUNT_RISK"):
        build_events(rows)


def test_duplicate_direct_coupon_rows_refuse() -> None:
    rows = [
        _row(date(2020, 1, 15), "Coupons", "50", "30", "20", 1),
        _row(date(2020, 1, 15), "Coupons", "50", "30", "20", 2),
    ]
    with pytest.raises(D002LExposureError, match="DUPLICATE_DIRECT_COUPON_ROWS"):
        build_events(rows)


def test_parentheses_parse_as_paydown_negative() -> None:
    raw = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        '01/15/2020,Coupons,"20,000","25,000","(5,000)"\n'
    ).encode()
    rows = parse_source_bytes(raw, format_hint="csv")
    assert rows[0].net_new_cash_or_pay_down_million == Decimal("-5000")


def test_zero_exposure_is_ineligible_not_silently_dropped() -> None:
    events = build_events([_row(date(2020, 1, 15), "Coupons", "30", "30", "0", 1)])
    assert len(events) == 1
    assert events[0]["eligible"] is False
    assert "ZERO_EXPOSURE_FORBIDDEN_BY_P0" in events[0]["exclusion_reasons"]


def test_temporal_partitions_are_frozen() -> None:
    rows = [
        _row(date(2014, 9, 2), "Coupons", "2", "1", "1", 1),
        _row(date(2019, 1, 1), "Coupons", "3", "1", "2", 2),
        _row(date(2026, 8, 20), "Coupons", "4", "1", "3", 3),
        _row(date(2026, 8, 25), "Coupons", "5", "1", "4", 4),
        _row(date(2026, 8, 28), "Coupons", "6", "1", "5", 5),
    ]
    parts = {e["settlement_date"]: e["partition"] for e in build_events(rows)}
    assert parts["2014-09-02"] == "CALIBRATION_POWER_ONLY"
    assert parts["2019-01-01"] == "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY"
    assert parts["2026-08-20"] == "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY"
    assert parts["2026-08-25"] == "PREREGISTRATION_GAP_EXCLUDED"
    assert parts["2026-08-28"] == "FUTURE_ACCUMULATION_ONLY"


def test_outcome_header_leakage_refuses() -> None:
    raw = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,"
        "Net New Cash or (Pay Down),TGCR\n"
        "01/15/2020,Coupons,20,10,10,1.5\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="CONFIRMATORY_OUTCOME_FIELD_FORBIDDEN_AT_P1"):
        parse_source_bytes(raw, format_hint="csv")


def test_unofficial_source_url_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["source_url"] = "https://example.invalid/mirror.csv"
    with pytest.raises(D002LExposureError, match="UNOFFICIAL_OR_UNLOCKED_SOURCE_URL"):
        compile_registry(raw, prov, format_hint="csv")


def test_raw_digest_mismatch_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["content_sha256"] = "0" * 64
    with pytest.raises(D002LExposureError, match="RAW_CONTENT_SHA256_MISMATCH"):
        compile_registry(raw, prov, format_hint="csv")


def test_partial_retrieval_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["retrieval_complete"] = False
    with pytest.raises(D002LExposureError, match="SOURCE_RETRIEVAL_NOT_COMPLETE"):
        compile_registry(raw, prov, format_hint="csv")


def test_wrong_retrieval_scope_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["retrieval_scope"] = "page_1_only"
    with pytest.raises(D002LExposureError, match="RETRIEVAL_SCOPE_NOT_FULL_HISTORICAL_TABLE"):
        compile_registry(raw, prov, format_hint="csv")


def test_late_coverage_start_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["coverage_start"] = "2015-01-01"
    with pytest.raises(D002LExposureError, match="SOURCE_COVERAGE_START_TOO_LATE"):
        compile_registry(raw, prov, format_hint="csv")


def test_early_coverage_end_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["coverage_end"] = "2025-12-31"
    with pytest.raises(D002LExposureError, match="SOURCE_COVERAGE_END_TOO_EARLY"):
        compile_registry(raw, prov, format_hint="csv")


def test_missing_required_field_refuses() -> None:
    raw = (
        "Date,Security Type,Total Offering,Net New Cash or (Pay Down)\n"
        "01/15/2020,Coupons,20,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="REQUIRED_FIELDS_MISSING"):
        parse_source_bytes(raw, format_hint="csv")


def test_nonnumeric_amount_refuses() -> None:
    raw = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "01/15/2020,Coupons,twenty,10,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="INVALID_NUMERIC_FIELD"):
        parse_source_bytes(raw, format_hint="csv")


def test_missing_calendar_year_refuses_source_complete_claim() -> None:
    raw = FIXTURE_CSV.read_text(encoding="utf-8")
    raw = "\n".join(line for line in raw.splitlines() if "/2022," not in line).encode()
    prov = _prov(raw)
    with pytest.raises(D002LExposureError, match="COUPON_EVENT_YEAR_GAPS"):
        compile_registry(raw, prov, format_hint="csv")


def test_confirmatory_exposure_variance_required() -> None:
    raw = FIXTURE_CSV.read_text(encoding="utf-8")
    lines = raw.splitlines()
    header, body = lines[0], lines[1:]
    rewritten = [header]
    for line in body:
        # Keep calibration values untouched; force every 2019-2026 confirmatory
        # Coupons row to the same net exposure of 25,000 million.
        if any(f"/{year}" in line for year in range(2019, 2027)) and ",Coupons," in line and "08/25/2026" not in line and "08/28/2026" not in line:
            cols = list(__import__("csv").reader([line]))[0]
            maturing = int(cols[3].replace(",", ""))
            cols[2] = f"{maturing + 25_000:,}"
            cols[-1] = "25,000"
            out = __import__("io").StringIO()
            w = __import__("csv").writer(out, lineterminator="")
            w.writerow(cols)
            line = out.getvalue()
        rewritten.append(line)
    raw2 = "\n".join(rewritten).encode()
    with pytest.raises(D002LExposureError, match="CONFIRMATORY_EXPOSURE_VARIANCE_NONPOSITIVE"):
        compile_registry(raw2, _prov(raw2), format_hint="csv")


def test_blocked_source_access_is_not_pass_and_cannot_advance() -> None:
    status = blocked_result("OFFICIAL_SOURCE_FETCH_FAILED:URLError:DNS")
    assert status["status"] == "NOT_EXECUTED"
    assert status["decision"] == "BLOCKED_SOURCE_ACCESS"
    assert status["source_complete_registry"] is False
    assert status["lineage_advance_allowed"] is False
    assert status["next_legal_node"] is None
    assert status["confirmatory_outcomes_ingested"] is False


def test_blocked_execution_artifact_if_present_is_fail_closed() -> None:
    if not STATUS.exists():
        pytest.skip("official retrieval attempt artifact not generated yet")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    assert status["status"] != "TERMINAL_PASS"
    assert status["lineage_advance_allowed"] is False
    assert status["source_complete_registry"] is False


def test_lineage_remains_at_p0_until_real_p1_source_complete_pass() -> None:
    p0 = json.loads(P0_VERDICT.read_text(encoding="utf-8"))
    assert p0["node_id"] == "D002L-P0"
    assert p0["status"] == "TERMINAL_PASS"
    assert p0["allowed_next_nodes"] == ["D002L-P1"]
    assert not P1_VERDICT.exists(), "blocked/untested P1 must not mint a terminal-pass verdict"


def test_synthetic_fixture_is_explicitly_non_scientific() -> None:
    paths = [FIXTURE_CSV, FIXTURE_HTML]
    assert all("synthetic" in p.name for p in paths)
    doc = (REPO_ROOT / "docs/research/D002L_P1_SOURCE_EXPOSURE_REGISTRY.md").read_text(encoding="utf-8")
    assert "not scientific evidence" in doc.lower()


def test_cash_identity_mismatch_refuses() -> None:
    raw = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "01/15/2020,Coupons,20,10,11\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="CASH_IDENTITY_MISMATCH"):
        parse_source_bytes(raw, format_hint="csv")


def test_declared_coverage_must_equal_actual_raw_dates() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["coverage_start"] = "2014-08-01"
    with pytest.raises(D002LExposureError, match="DECLARED_COVERAGE_START_MISMATCH"):
        compile_registry(raw, prov, format_hint="csv")


def test_monthly_coupon_gap_refuses_full_snapshot_claim() -> None:
    text = FIXTURE_CSV.read_text(encoding="utf-8")
    # Remove one otherwise valid coupon settlement month while retaining all years.
    raw = "\n".join(line for line in text.splitlines() if not line.startswith("06/15/2022,Coupons"))
    raw = (raw + "\n").encode()
    with pytest.raises(D002LExposureError, match="COUPON_EVENT_MONTH_GAPS"):
        compile_registry(raw, _prov(raw), format_hint="csv")


def test_sparse_one_row_per_year_cannot_claim_full_history() -> None:
    import csv as _csv
    import io as _io
    out = _io.StringIO()
    w = _csv.writer(out, lineterminator="\n")
    w.writerow(["Date", "Security Type", "Total Offering", "Total Publicly Held Maturing", "Net New Cash or (Pay Down)"])
    for year in range(2014, 2027):
        d = "09/02/2014" if year == 2014 else ("08/20/2026" if year == 2026 else f"06/15/{year}")
        offering = 50_000 + year
        maturing = 30_000
        w.writerow([d, "Coupons", offering, maturing, offering - maturing])
    raw = out.getvalue().encode()
    with pytest.raises(D002LExposureError, match="COUPON_EVENT_MONTH_GAPS"):
        compile_registry(raw, _prov(raw), format_hint="csv")


def test_offline_replay_cli_cannot_mint_terminal_pass(tmp_path: Path) -> None:
    import subprocess
    import sys
    raw = FIXTURE_CSV.read_bytes()
    raw_path = tmp_path / "raw.csv"
    prov_path = tmp_path / "prov.json"
    out_path = tmp_path / "registry.json"
    status_path = tmp_path / "status.json"
    raw_path.write_bytes(raw)
    prov_path.write_text(json.dumps(_prov(raw)), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/x10r_d002l_p1_exposure_registry.py"),
            "--raw", str(raw_path),
            "--provenance", str(prov_path),
            "--out", str(out_path),
            "--status-out", str(status_path),
        ],
        cwd=REPO_ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 20
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "OFFLINE_REPLAY_ONLY"
    assert status["lineage_advance_allowed"] is False
    assert status["source_authenticity_for_lineage_advance"] is False
    assert status["next_legal_node"] is None


def test_no_merge_markers_in_p1_files() -> None:
    targets = [
        REPO_ROOT / "research/systemic_risk/d002l_exposure_registry.py",
        REPO_ROOT / "scripts/x10r_d002l_p1_exposure_registry.py",
        CONTRACT,
        REPO_ROOT / "docs/research/D002L_P1_SOURCE_EXPOSURE_REGISTRY.md",
        Path(__file__),
    ]
    import re
    marker = re.compile(r"^(<{7}|>{7}|={7})(?: .*)?$", re.MULTILINE)
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert marker.search(text) is None


def _fixture_html_full() -> bytes:
    import csv as _csv
    import html as _html
    rows = list(_csv.reader(FIXTURE_CSV.read_text(encoding="utf-8").splitlines()))
    parts = ["<!doctype html><html><body><table>"]
    parts.append("<tr>" + "".join(f"<th>{_html.escape(x)}</th>" for x in rows[0]) + "</tr>")
    for row in rows[1:]:
        parts.append("<tr>" + "".join(f"<td>{_html.escape(x)}</td>" for x in row) + "</tr>")
    parts.append("</table></body></html>")
    return "\n".join(parts).encode()


def test_invalid_date_refuses() -> None:
    raw = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "not-a-date,Coupons,20,10,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="INVALID_SETTLEMENT_DATE"):
        parse_source_bytes(raw, format_hint="csv")


def test_missing_and_nonfinite_numeric_refuse() -> None:
    missing = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "01/15/2020,Coupons,,10,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="MISSING_NUMERIC_FIELD"):
        parse_source_bytes(missing, format_hint="csv")
    nonfinite = (
        "Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "01/15/2020,Coupons,NaN,10,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="NONFINITE_NUMERIC_FIELD"):
        parse_source_bytes(nonfinite, format_hint="csv")


def test_json_parser_variants_and_failures() -> None:
    row = {
        "Date": "01/15/2020",
        "Security Type": "Coupons",
        "Total Offering": "20",
        "Total Publicly Held Maturing": "10",
        "Net New Cash or (Pay Down)": "10",
    }
    for payload in ([row], {"data": [row]}, {"rows": [row]}, {"results": [row]}):
        rows = parse_source_bytes(json.dumps(payload).encode(), format_hint="json")
        assert rows[0].settlement_date == date(2020, 1, 15)
    with pytest.raises(D002LExposureError, match="INVALID_JSON"):
        parse_source_bytes(b"{bad", format_hint="json")
    with pytest.raises(D002LExposureError, match="JSON_ROWS_MUST_BE_LIST"):
        parse_source_bytes(b'{"x": 1}', format_hint="json")
    with pytest.raises(D002LExposureError, match="JSON_ROW_NOT_OBJECT"):
        parse_source_bytes(b'[1]', format_hint="json")


def test_html_missing_locked_table_and_short_rows_refuse_or_skip() -> None:
    with pytest.raises(D002LExposureError, match="LOCKED_TREASURY_TABLE_NOT_FOUND_IN_HTML"):
        parse_source_bytes(b"<html><table><tr><th>x</th></tr><tr><td>1</td></tr></table></html>", format_hint="html")
    html = b"""<table>
    <tr><th>Date</th><th>Security Type</th><th>Total Offering</th><th>Total Publicly Held Maturing</th><th>Net New Cash or (Pay Down)</th></tr>
    <tr><td>short</td></tr>
    </table>"""
    with pytest.raises(D002LExposureError, match="LOCKED_TREASURY_TABLE_NOT_FOUND_IN_HTML"):
        parse_source_bytes(html, format_hint="html")


def test_non_utf8_and_zero_rows_refuse() -> None:
    with pytest.raises(D002LExposureError, match="SOURCE_NOT_UTF8"):
        parse_source_bytes(b"\xff\xfe\xfa", format_hint="csv")
    header_only = b"Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
    with pytest.raises(D002LExposureError, match="SOURCE_HAS_ZERO_ROWS"):
        parse_source_bytes(header_only, format_hint="csv")


def test_provenance_identity_and_timestamp_fail_closed() -> None:
    raw = FIXTURE_CSV.read_bytes()
    cases = [
        ("source_id", "WRONG", "WRONG_SOURCE_ID"),
        ("publisher", "WRONG", "WRONG_PUBLISHER"),
        ("dataset", "WRONG", "WRONG_DATASET"),
        ("retrieved_at_utc", "not-time", "INVALID_RETRIEVED_AT_UTC"),
    ]
    for key, value, match in cases:
        prov = _prov(raw)
        prov[key] = value
        with pytest.raises(D002LExposureError, match=match):
            compile_registry(raw, prov, format_hint="csv")
    prov = _prov(raw)
    del prov["dataset"]
    with pytest.raises(D002LExposureError, match="PROVENANCE_FIELDS_MISSING"):
        compile_registry(raw, prov, format_hint="csv")


def test_declared_coverage_end_mismatch_refuses() -> None:
    raw = FIXTURE_CSV.read_bytes()
    prov = _prov(raw)
    prov["coverage_end"] = "2026-08-21"
    with pytest.raises(D002LExposureError, match="DECLARED_COVERAGE_END_MISMATCH"):
        compile_registry(raw, prov, format_hint="csv")


def test_zero_coupon_events_refuse() -> None:
    import csv as _csv
    import io as _io
    out = _io.StringIO()
    w = _csv.writer(out, lineterminator="\n")
    w.writerow(["Date", "Security Type", "Total Offering", "Total Publicly Held Maturing", "Net New Cash or (Pay Down)"])
    # Preserve declared coverage dates while supplying only Bills.
    w.writerow(["09/02/2014", "Bills", 20, 10, 10])
    w.writerow(["08/20/2026", "Bills", 30, 10, 20])
    raw = out.getvalue().encode()
    with pytest.raises(D002LExposureError, match="ZERO_COUPON_EVENTS"):
        compile_registry(raw, _prov(raw), format_hint="csv")


def test_fetch_official_snapshot_success_and_redirect_fail(monkeypatch) -> None:
    import research.systemic_risk.d002l_exposure_registry as mod

    class Response:
        def __init__(self, raw: bytes, url: str):
            self.raw = raw
            self.url = url
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def geturl(self):
            return self.url
        def read(self):
            return self.raw

    full_html = _fixture_html_full()
    monkeypatch.setattr(mod, "urlopen", lambda req, timeout: Response(full_html, LOCKED_SOURCE_URL))
    raw, prov = mod.fetch_official_snapshot(timeout_seconds=1)
    assert raw == full_html
    assert prov["coverage_start"] == CALIBRATION_START.isoformat()
    assert prov["coverage_end"] == CONFIRMATORY_END.isoformat()
    assert prov["content_sha256"] == sha256_bytes(full_html)

    monkeypatch.setattr(mod, "urlopen", lambda req, timeout: Response(full_html, "https://example.invalid/redirect"))
    with pytest.raises(D002LExposureError, match="UNEXPECTED_SOURCE_REDIRECT"):
        mod.fetch_official_snapshot(timeout_seconds=1)


def test_fetch_official_snapshot_network_failure_is_wrapped(monkeypatch) -> None:
    import research.systemic_risk.d002l_exposure_registry as mod
    def boom(req, timeout):
        raise OSError("network-down")
    monkeypatch.setattr(mod, "urlopen", boom)
    with pytest.raises(D002LExposureError, match="OFFICIAL_SOURCE_FETCH_FAILED:OSError"):
        mod.fetch_official_snapshot(timeout_seconds=1)


def test_cli_mocked_direct_fetch_can_pass_only_direct_mode(tmp_path: Path, monkeypatch) -> None:
    import scripts.x10r_d002l_p1_exposure_registry as cli
    full_html = _fixture_html_full()
    # Generate provenance exactly as the direct fetcher would, but without network.
    rows = parse_source_bytes(full_html, format_hint="html")
    dates = [r.settlement_date for r in rows]
    prov = {
        "source_id": "TREASURY_CASH_PAYDOWN",
        "publisher": LOCKED_PUBLISHER,
        "dataset": LOCKED_DATASET,
        "source_url": LOCKED_SOURCE_URL,
        "retrieved_at_utc": "2026-08-28T16:00:00Z",
        "fetch_started_at_utc": "2026-08-28T15:59:59Z",
        "content_sha256": sha256_bytes(full_html),
        "revision_or_vintage_status": "point_in_time_web_snapshot",
        "retrieval_complete": True,
        "retrieval_scope": "full_historical_table_snapshot",
        "coverage_start": min(dates).isoformat(),
        "coverage_end": max(dates).isoformat(),
        "http_source": "locked_treasurydirect_https_only",
    }
    monkeypatch.setattr(cli, "fetch_official_snapshot", lambda timeout_seconds: (full_html, prov))
    out = tmp_path / "registry.json"
    status = tmp_path / "status.json"
    raw_out = tmp_path / "raw.html"
    prov_out = tmp_path / "prov.json"
    monkeypatch.setattr(__import__("sys"), "argv", [
        "x10r_d002l_p1_exposure_registry.py", "--fetch-official",
        "--out", str(out), "--status-out", str(status),
        "--raw-out", str(raw_out), "--provenance-out", str(prov_out),
    ])
    assert cli.main() == 0
    st = json.loads(status.read_text(encoding="utf-8"))
    assert st["status"] == "TERMINAL_PASS"
    assert st["source_authenticity_for_lineage_advance"] is True
    assert st["lineage_advance_allowed"] is True
    assert st["next_legal_node"] == "D002L-P2"


def test_precalibration_event_is_explicitly_excluded() -> None:
    event = build_events([_row(date(2014, 8, 15), "Coupons", "20", "10", "10", 1)])[0]
    assert event["partition"] == "PRE_CALIBRATION_EXCLUDED"
    assert event["eligible"] is False
    assert "PRE_CALIBRATION_EXCLUDED" in event["exclusion_reasons"]


def test_load_provenance_valid_and_invalid(tmp_path: Path) -> None:
    from research.systemic_risk.d002l_exposure_registry import load_provenance
    path = tmp_path / "prov.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    assert load_provenance(path) == {"a": 1}
    path.write_text('[1]', encoding="utf-8")
    with pytest.raises(D002LExposureError, match="PROVENANCE_NOT_OBJECT"):
        load_provenance(path)
    path.write_text('{bad', encoding="utf-8")
    with pytest.raises(D002LExposureError, match="INVALID_PROVENANCE"):
        load_provenance(path)
    with pytest.raises(D002LExposureError, match="INVALID_PROVENANCE"):
        load_provenance(tmp_path / "missing.json")


def test_csv_without_header_refuses() -> None:
    with pytest.raises(D002LExposureError, match="CSV_HEADER_MISSING"):
        parse_source_bytes(b"", format_hint="csv")


def test_ambiguous_alias_duplicate_field_refuses() -> None:
    raw = (
        "Date,Settlement Date,Security Type,Total Offering,Total Publicly Held Maturing,Net New Cash or (Pay Down)\n"
        "01/15/2020,01/16/2020,Coupons,20,10,10\n"
    ).encode()
    with pytest.raises(D002LExposureError, match="AMBIGUOUS_DUPLICATE_FIELD:date"):
        parse_source_bytes(raw, format_hint="csv")


def test_zero_eligible_calibration_and_confirmatory_fail_directly() -> None:
    from research.systemic_risk.d002l_exposure_registry import validate_registry_completeness
    future = build_events([_row(date(2026, 8, 28), "Coupons", "20", "10", "10", 1)])
    with pytest.raises(D002LExposureError, match="ZERO_ELIGIBLE_CALIBRATION_EVENTS"):
        validate_registry_completeness(future)
    calibration = build_events([_row(date(2015, 1, 15), "Coupons", "20", "10", "10", 1)])
    with pytest.raises(D002LExposureError, match="ZERO_ELIGIBLE_CONFIRMATORY_EXPOSURE_EVENTS"):
        validate_registry_completeness(calibration)


def test_cli_offline_replay_direct_call_returns_20(tmp_path: Path, monkeypatch) -> None:
    import scripts.x10r_d002l_p1_exposure_registry as cli
    import sys
    raw = FIXTURE_CSV.read_bytes()
    raw_path = tmp_path / "raw.csv"
    prov_path = tmp_path / "prov.json"
    out = tmp_path / "registry.json"
    status = tmp_path / "status.json"
    raw_path.write_bytes(raw)
    prov_path.write_text(json.dumps(_prov(raw)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "cli", "--raw", str(raw_path), "--provenance", str(prov_path),
        "--out", str(out), "--status-out", str(status),
    ])
    assert cli.main() == 20
    st = json.loads(status.read_text(encoding="utf-8"))
    assert st["status"] == "OFFLINE_REPLAY_ONLY"
    assert st["lineage_advance_allowed"] is False


def test_cli_missing_offline_provenance_fails_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    import scripts.x10r_d002l_p1_exposure_registry as cli
    import sys
    raw_path = tmp_path / "raw.csv"
    raw_path.write_bytes(FIXTURE_CSV.read_bytes())
    status = tmp_path / "status.json"
    monkeypatch.setattr(sys, "argv", [
        "cli", "--raw", str(raw_path), "--out", str(tmp_path / "o.json"),
        "--status-out", str(status),
    ])
    assert cli.main() == 10
    st = json.loads(status.read_text(encoding="utf-8"))
    assert st["status"] == "NOT_EXECUTED"
    assert "--provenance is required" in st["reason"]
    assert "D002L-P1 BLOCKED" in capsys.readouterr().err


def test_cli_unexpected_exception_is_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import scripts.x10r_d002l_p1_exposure_registry as cli
    import sys
    def boom(timeout_seconds):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "fetch_official_snapshot", boom)
    status = tmp_path / "status.json"
    monkeypatch.setattr(sys, "argv", [
        "cli", "--fetch-official", "--out", str(tmp_path / "o.json"),
        "--status-out", str(status),
    ])
    assert cli.main() == 10
    st = json.loads(status.read_text(encoding="utf-8"))
    assert st["status"] == "NOT_EXECUTED"
    assert st["reason"] == "RuntimeError:boom"


def test_same_day_bill_control_is_preserved_in_coupon_event() -> None:
    raw = FIXTURE_CSV.read_bytes()
    registry = compile_registry(raw, _prov(raw), format_hint="csv")
    event = next(e for e in registry["events"] if e["settlement_date"] == "2014-09-02")
    assert event["same_day_bill_net_new_cash_or_pay_down_million_usd"] == "-5000"
    assert event["same_day_bill_net_new_cash_or_pay_down_usd"] == "-5000000000"
    assert event["b_t_scaled_100bn"] == "-0.05"
    assert event["bill_source_row_numbers"]


def test_missing_same_day_bill_means_zero_control_not_missing_value() -> None:
    event = build_events([_row(date(2020, 1, 15), "Coupons", "20", "10", "10", 1)])[0]
    assert event["same_day_bill_net_new_cash_or_pay_down_usd"] == "0"
    assert event["b_t_scaled_100bn"] == "0"
    assert event["bill_source_row_numbers"] == []


def test_duplicate_direct_bill_rows_refuse_control_double_count() -> None:
    rows = [
        _row(date(2020, 1, 15), "Coupons", "20", "10", "10", 1),
        _row(date(2020, 1, 15), "Bills", "30", "20", "10", 2),
        _row(date(2020, 1, 15), "Bills", "40", "20", "20", 3),
    ]
    with pytest.raises(D002LExposureError, match="DUPLICATE_DIRECT_BILL_ROWS"):
        build_events(rows)
