"""Schema and semantic validation for repository datasets."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List

os.environ.setdefault("TRADEPULSE_LIGHT_DATA_IMPORT", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data.dataset_contracts import DatasetContract, iter_contracts


def _infer_dtype(value: str) -> str:
    if value == "":
        return "str"
    try:
        int(value)
        return "int"
    except ValueError:
        try:
            float(value)
            return "float"
        except ValueError:
            return "str"


def _merge_type(current: str, new: str) -> str:
    if current == new:
        return current
    if {"int", "float"} == {current, new}:
        return "float"
    return "str"


def _parse_timestamp(value: str) -> float:
    value = str(value).strip()
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _validate_row_semantics(
    row: list[str], header: list[str], contract: DatasetContract, errors: list[str], row_number: int
) -> None:
    rules = contract.semantic_rules
    name_to_value = dict(zip(header, row))

    if rules.get("no_nulls"):
        for key, val in name_to_value.items():
            if val == "":
                errors.append(f"{contract.path}: row {row_number} has empty value for {key}")

    for field in rules.get("non_negative", []):
        if field in name_to_value:
            try:
                if float(name_to_value[field]) < 0:
                    errors.append(
                        f"{contract.path}: row {row_number} has negative value for {field}"
                    )
            except ValueError:
                errors.append(
                    f"{contract.path}: row {row_number} non-numeric value for {field}"
                )

    for field in rules.get("positive_fields", []):
        if field in name_to_value:
            try:
                if float(name_to_value[field]) <= 0:
                    errors.append(
                        f"{contract.path}: row {row_number} expected positive value for {field}"
                    )
            except ValueError:
                errors.append(
                    f"{contract.path}: row {row_number} non-numeric value for {field}"
                )

    ohlc = rules.get("ohlc_fields")
    if ohlc:
        try:
            open_v = float(name_to_value[ohlc["open"]])
            high_v = float(name_to_value[ohlc["high"]])
            low_v = float(name_to_value[ohlc["low"]])
            close_v = float(name_to_value[ohlc["close"]])
            if low_v > high_v:
                errors.append(f"{contract.path}: row {row_number} low exceeds high")
            if not (low_v <= open_v <= high_v):
                errors.append(f"{contract.path}: row {row_number} open outside [low, high]")
            if not (low_v <= close_v <= high_v):
                errors.append(f"{contract.path}: row {row_number} close outside [low, high]")
        except Exception:
            errors.append(f"{contract.path}: row {row_number} invalid OHLC fields")


def validate_contract(contract: DatasetContract) -> list[str]:
    errors: List[str] = []
    if not contract.path.exists():
        return [f"Missing dataset: {contract.path}"]

    with contract.path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return [f"{contract.path} is empty"]

        if header != list(contract.columns):
            errors.append(
                f"{contract.path} schema mismatch. Expected columns {contract.columns}, found {header}"
            )

        inferred = [None] * len(header)
        rules = contract.semantic_rules
        timestamp_column = rules.get("timestamp_column")
        partition_keys = rules.get("partition_by") or []
        previous_ts: dict[tuple[str, ...], float] = {}

        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                errors.append(
                    f"{contract.path}: row {row_number} has {len(row)} columns, expected {len(header)}"
                )
                continue

            for idx, value in enumerate(row):
                dtype = _infer_dtype(value)
                inferred[idx] = dtype if inferred[idx] is None else _merge_type(inferred[idx], dtype)

            name_to_value = dict(zip(header, row))

            if rules.get("monotonic") and timestamp_column in header:
                ts_value = row[header.index(timestamp_column)]
                try:
                    current_ts = _parse_timestamp(ts_value)
                    key = tuple(name_to_value[k] for k in partition_keys) if partition_keys else ("_all",)
                    last_ts = previous_ts.get(key)
                    if last_ts is not None and current_ts < last_ts:
                        errors.append(
                            f"{contract.path}: row {row_number} timestamp not monotonic (decrease detected)"
                        )
                    previous_ts[key] = current_ts
                except Exception as exc:
                    errors.append(
                        f"{contract.path}: row {row_number} invalid timestamp value '{ts_value}' ({exc})"
                    )

            _validate_row_semantics(row, header, contract, errors, row_number)

    if None in inferred:
        errors.append(f"{contract.path}: could not infer dtypes from data")
    else:
        expected = list(contract.dtypes)
        if inferred != expected:
            errors.append(
                f"{contract.path} dtype mismatch. Expected {expected}, inferred {inferred}"
            )

    return errors


def validate_all() -> list[str]:
    errors: list[str] = []
    for contract in iter_contracts():
        errors.extend(validate_contract(contract))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dataset schemas and semantics.")
    parser.parse_args(argv)
    errors = validate_all()
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 1
    print("All dataset schemas validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
