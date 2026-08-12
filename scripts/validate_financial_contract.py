#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from uuid import UUID

import yaml  # type: ignore[import-untyped]

DEFAULT_CONTRACT_FILE = Path("docs/architecture/methodology/financial/FINANCIAL_DATA_CONTRACT.yaml")
DEFAULT_DATA_FILE = Path("docs/architecture/methodology/financial/sample_financial_data.csv")
DEFAULT_OUT_FILE = Path("artifacts/financial_verification_manifest.json")
BENFORD_ENFORCEMENT_MIN_ROWS = 30
BENFORD_CHI2_CRITICAL_001_DF8 = 20.09


class FinancialContractError(ValueError):
    pass


def _first_digit(x: float) -> int:
    v = abs(x)
    while v >= 10:
        v /= 10
    while 0 < v < 1:
        v *= 10
    return int(v)


def _benford_chi_square(amounts: list[float]) -> float:
    digits = [_first_digit(a) for a in amounts if a > 0]
    n = len(digits)
    if n == 0:
        return float("inf")
    obs = Counter(digits)
    chi2 = 0.0
    for d in range(1, 10):
        p = math.log10(1 + 1 / d)
        e = n * p
        o = obs.get(d, 0)
        chi2 += ((o - e) ** 2) / e
    return chi2


def _z_scores_log(amounts: list[float]) -> list[float]:
    ln = [math.log(x) for x in amounts if x > 0]
    if not ln:
        raise FinancialContractError(
            "no positive amount values available for log z-score validation"
        )
    mu = mean(ln)
    sigma = pstdev(ln) or 1e-12
    return [(v - mu) / sigma for v in ln]


def _is_uuid4(s: str) -> bool:
    try:
        u = UUID(s)
        return u.version == 4
    except Exception:
        return False


def _parse_utc_timestamp(raw: str, row_idx: int) -> datetime:
    if not raw.endswith("Z"):
        raise FinancialContractError(f"ts_utc must use explicit UTC Z suffix at row {row_idx}")
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinancialContractError(f"invalid ts_utc at row {row_idx}: {exc}") from exc
    if ts.tzinfo is None or ts.utcoffset() != timezone.utc.utcoffset(ts):
        raise FinancialContractError(f"ts_utc is not UTC at row {row_idx}")
    return ts


def _load_rows(data_file: Path) -> list[dict[str, str]]:
    with data_file.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise FinancialContractError("empty dataset")
    return rows


def validate_contract(
    contract_file: Path = DEFAULT_CONTRACT_FILE,
    data_file: Path = DEFAULT_DATA_FILE,
    out_file: Path = DEFAULT_OUT_FILE,
) -> dict[str, object]:
    if not contract_file.exists() or not data_file.exists():
        raise FinancialContractError("missing required financial validation assets")

    contract = yaml.safe_load(contract_file.read_text(encoding="utf-8")) or {}
    required_fields = [f["name"] for f in contract.get("required_fields", [])]
    if not required_fields:
        raise FinancialContractError("contract has no required_fields")

    rows = _load_rows(data_file)
    amounts: list[float] = []
    timestamps_by_symbol: dict[str, list[datetime]] = defaultdict(list)

    for idx, row in enumerate(rows, start=1):
        for field in required_fields:
            if field not in row or row[field] == "":
                raise FinancialContractError(f"missing field '{field}' at row {idx}")

        if (
            "transaction_id" in row
            and row["transaction_id"]
            and not _is_uuid4(row["transaction_id"])
        ):
            raise FinancialContractError(f"invalid transaction_id at row {idx}")
        if "source_hash" in row and row["source_hash"]:
            source_hash = row["source_hash"]
            if len(source_hash) != 64 or any(
                c not in "0123456789abcdefABCDEF" for c in source_hash
            ):
                raise FinancialContractError(f"invalid source_hash at row {idx}")

        try:
            high = float(row["high"])
            low = float(row["low"])
            open_val = float(row["open"])
            close_val = float(row["close"])
            volume = float(row["volume"])
            spread = float(row["spread_bps"])
            fee = float(row["fee_bps"])
            amount = float(row.get("amount") or close_val)
        except ValueError as exc:
            raise FinancialContractError(f"non-numeric value at row {idx}: {exc}") from exc

        values = [high, low, open_val, close_val, volume, spread, fee, amount]
        if not all(math.isfinite(v) for v in values):
            raise FinancialContractError(f"non-finite numeric value at row {idx}")
        if not (
            high >= low
            and open_val > 0
            and close_val > 0
            and volume >= 0
            and spread >= 0
            and fee >= 0
            and amount > 0
        ):
            raise FinancialContractError(f"core mathematical invariants breached at row {idx}")

        ts = _parse_utc_timestamp(row["ts_utc"], idx)
        timestamps_by_symbol[row["symbol"]].append(ts)
        amounts.append(amount)

    for symbol, timestamps in timestamps_by_symbol.items():
        if timestamps != sorted(timestamps):
            raise FinancialContractError(f"non-monotonic ts_utc detected for symbol {symbol}")

    benford_chi2 = _benford_chi_square(amounts)
    benford_enforced = len(amounts) >= BENFORD_ENFORCEMENT_MIN_ROWS
    if benford_enforced and benford_chi2 > BENFORD_CHI2_CRITICAL_001_DF8:
        raise FinancialContractError(f"benford chi-square too high ({benford_chi2:.4f})")

    z_scores = _z_scores_log(amounts)
    max_abs_z = max(abs(z) for z in z_scores)
    expected_records = int(contract.get("expected_records", len(rows)))
    record_delta = abs(len(rows) - expected_records)

    manifest = {
        "protocol_version": "DFV-EP v1.0",
        "timestamp_utc": "1970-01-01T00:00:00Z",
        "verification_metrics": {
            "records_processed": len(rows),
            "expected_records": expected_records,
            "benford_chi_square": round(benford_chi2, 6),
            "benford_enforced": benford_enforced,
            "max_detected_z_score": round(max_abs_z, 6),
            "epistemic_drift_delta": record_delta,
        },
        "integrity": {
            "data_ledger_sha256": hashlib.sha256(data_file.read_bytes()).hexdigest(),
            "verification_provenance_marker": "local-dev-marker",
        },
        "verdict": "EP_PARITY_PASSED",
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    try:
        validate_contract()
    except FinancialContractError as exc:
        print(f"CONTRACT VIOLATION: {exc}")
        return 1
    print("OK: Financial data contract runtime validations passed cleanly.")
    return 0


def validate_financial_data() -> list[str]:
    try:
        validate_contract()
    except FinancialContractError as exc:
        return [str(exc)]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
