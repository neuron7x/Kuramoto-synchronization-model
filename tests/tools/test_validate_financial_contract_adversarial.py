from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_financial_contract import FinancialContractError, validate_contract

FIELDS = [
    "symbol",
    "venue",
    "ts_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "spread_bps",
    "fee_bps",
]
ROW = {
    "symbol": "BTC",
    "venue": "x",
    "ts_utc": "2026-05-26T00:00:00Z",
    "open": "100",
    "high": "110",
    "low": "90",
    "close": "101",
    "volume": "10",
    "spread_bps": "1",
    "fee_bps": "4",
}


def _contract(path: Path, expected_records: int = 1) -> None:
    path.write_text(
        "expected_records: "
        + str(expected_records)
        + "\n"
        + "required_fields:\n"
        + "".join("  - name: " + field + "\n" for field in FIELDS),
        encoding="utf-8",
    )


def _csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _validate(
    tmp_path: Path,
    rows: list[dict[str, str]],
    expected_records: int = 1,
) -> dict[str, Any]:
    contract = tmp_path / "contract.yaml"
    data = tmp_path / "data.csv"
    out = tmp_path / "manifest.json"
    _contract(contract, expected_records)
    _csv(data, rows)
    return validate_contract(contract, data, out)


def test_record_delta_is_measured_not_self_subtracted(tmp_path: Path) -> None:
    payload = _validate(tmp_path, [ROW], expected_records=3)

    assert payload["verification_metrics"]["epistemic_drift_delta"] == 2


def test_high_below_low_fails_closed(tmp_path: Path) -> None:
    row = dict(ROW, high="80")

    with pytest.raises(FinancialContractError, match="core mathematical invariants"):
        _validate(tmp_path, [row])


def test_naive_timestamp_fails_closed(tmp_path: Path) -> None:
    row = dict(ROW, ts_utc="2026-05-26T00:00:00")

    with pytest.raises(FinancialContractError, match="UTC Z suffix"):
        _validate(tmp_path, [row])


def test_non_monotonic_timestamp_fails_closed(tmp_path: Path) -> None:
    row1 = dict(ROW, ts_utc="2026-05-26T00:02:00Z")
    row2 = dict(ROW, ts_utc="2026-05-26T00:01:00Z")

    with pytest.raises(FinancialContractError, match="non-monotonic ts_utc"):
        _validate(tmp_path, [row1, row2], expected_records=2)
