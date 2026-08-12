from __future__ import annotations

import csv
from pathlib import Path

import yaml

CONTRACT_PATH = Path("docs/architecture/methodology/financial/FINANCIAL_DATA_CONTRACT.yaml")
DATA_PATH = Path("docs/architecture/methodology/financial/sample_financial_data.csv")


def test_sample_financial_data_matches_contract() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    required = [f["name"] for f in contract["required_fields"]]

    with DATA_PATH.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert rows
    assert set(required).issubset(rows[0].keys())

    for row in rows:
        assert float(row["high"]) >= float(row["low"])
        assert float(row["open"]) > 0
        assert float(row["close"]) > 0
        assert float(row["volume"]) >= 0
        assert float(row["spread_bps"]) >= 0
        assert float(row["fee_bps"]) >= 0
