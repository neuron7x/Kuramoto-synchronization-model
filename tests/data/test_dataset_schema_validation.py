import os
from pathlib import Path

import pytest

os.environ.setdefault("TRADEPULSE_LIGHT_DATA_IMPORT", "1")

import scripts.validate_dataset_schema as validate_dataset_schema
from core.data.dataset_contracts import DatasetContract


def test_repository_datasets_pass_schema_validation() -> None:
    errors = validate_dataset_schema.validate_all()
    assert errors == []


def test_schema_violation_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_path = tmp_path / "bad.csv"
    bad_path.write_text(
        "ts,open,high,low,close,volume\n1,10,9,11,10,100\n", encoding="utf-8"
    )
    contract = DatasetContract(
        dataset_id="bad-ohlc",
        path=bad_path,
        schema_version="1.0.0",
        columns=["ts", "open", "high", "low", "close", "volume"],
        dtypes=["int", "float", "float", "float", "float", "int"],
        origin="synthetic",
        description="temp contract for test",
        creation_method="generated in test",
        temporal_coverage="1 row",
        intended_use="test",
        forbidden_use="test only",
        semantic_rules={
            "timestamp_column": "ts",
            "monotonic": True,
            "non_negative": ["volume"],
            "ohlc_fields": {"open": "open", "high": "high", "low": "low", "close": "close"},
            "no_nulls": True,
        },
    )

    monkeypatch.setattr(validate_dataset_schema, "iter_contracts", lambda: (contract,))

    errors = validate_dataset_schema.validate_all()
    assert any("open outside" in err or "low exceeds high" in err for err in errors)
