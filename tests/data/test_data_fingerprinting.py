import json
import os
from pathlib import Path

os.environ.setdefault("TRADEPULSE_LIGHT_DATA_IMPORT", "1")

from core.data import fingerprint
from core.data.dataset_contracts import contract_by_id


def test_compute_dataset_fingerprint_is_deterministic() -> None:
    contract = contract_by_id("sample-timeseries-v1")
    assert contract is not None
    fp1 = fingerprint.compute_dataset_fingerprint(contract)
    fp2 = fingerprint.compute_dataset_fingerprint(contract)
    assert fp1["content_hash"] == fp2["content_hash"]
    assert fp1["schema_hash"] == fp2["schema_hash"]


def test_record_run_fingerprint_writes_artifact(tmp_path: Path) -> None:
    contract = contract_by_id("sample-timeseries-v1")
    assert contract is not None
    dest = fingerprint.record_run_fingerprint(
        contract, run_type="backtest", output_dir=tmp_path
    )
    payload = json.loads(dest.read_text())
    assert payload["dataset_id"] == contract.dataset_id
    assert payload["content_hash"]
    assert payload["schema_hash"]


def test_record_transformation_trace(tmp_path: Path) -> None:
    input_fp = fingerprint.fingerprint_rows(
        [{"value": 1}], columns=["value"], dataset_id="input", schema_version="test"
    )
    output_fp = fingerprint.fingerprint_rows(
        [{"value": 2}], columns=["value"], dataset_id="output", schema_version="test"
    )
    dest = fingerprint.record_transformation_trace(
        transformation_id="unit-test-transformation",
        parameters={"param": "x"},
        input_fingerprint=input_fp,
        output_fingerprint=output_fp,
        output_dir=tmp_path,
    )
    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["input"]["content_hash"] != data["output"]["content_hash"]
