"""Dataset fingerprinting utilities for reproducibility and auditability."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .dataset_contracts import DatasetContract

DEFAULT_FINGERPRINT_DIR = Path("artifacts/data-fingerprints")
DEFAULT_TRACE_DIR = Path("artifacts/data-traces")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise_text_lines(text: str) -> bytes:
    lines = [line.rstrip() for line in text.splitlines()]
    return ("\n".join(lines) + "\n").encode("utf-8")


def hash_csv_content(path: Path) -> str:
    """Return a stable SHA256 hash of the CSV content."""

    text = path.read_text(encoding="utf-8")
    return _sha256(_normalise_text_lines(text))


def hash_schema(columns: Sequence[str], dtypes: Sequence[str]) -> str:
    """Return a stable hash for a schema definition."""

    if len(columns) != len(dtypes):
        raise ValueError("columns and dtypes must align")
    payload = [{"name": name, "dtype": dtype} for name, dtype in zip(columns, dtypes)]
    normalised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256(normalised.encode("utf-8"))


def fingerprint_rows(
    rows: Sequence[Sequence[object]] | Sequence[Mapping[str, object]],
    *,
    columns: Sequence[str] | None = None,
    dataset_id: str = "transient",
    schema_version: str = "n/a",
) -> Mapping[str, object]:
    """Fingerprint an in-memory tabular payload without requiring pandas."""

    materialised_rows: list[list[str]] = []
    if rows and isinstance(rows[0], Mapping):  # type: ignore[index]
        mapping_rows = rows  # type: ignore[assignment]
        if columns is None:
            key_union: set[str] = set()
            for row in mapping_rows:  # type: ignore[assignment]
                key_union.update(row.keys())  # type: ignore[arg-type]
            columns = sorted(key_union)
        for row in mapping_rows:  # type: ignore[assignment]
            materialised_rows.append([str(row.get(col, "")) for col in columns])
    else:
        if columns is None:
            columns = []
        for row in rows:
            materialised_rows.append([str(value) for value in row])

    header = ",".join(columns)
    lines = [header] + [",".join(r) for r in materialised_rows]
    content_hash = _sha256(_normalise_text_lines("\n".join(lines)))
    schema_hash = hash_schema(columns, ["str"] * len(columns)) if columns else _sha256(b"")
    return {
        "dataset_id": dataset_id,
        "schema_version": schema_version,
        "content_hash": content_hash,
        "schema_hash": schema_hash,
        "rows": len(materialised_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_dataset_fingerprint(contract: DatasetContract) -> Mapping[str, object]:
    """Compute both content and schema hashes for a registered dataset."""

    if not contract.path.exists():
        raise FileNotFoundError(f"Dataset not found: {contract.path}")
    row_count = sum(1 for _ in contract.path.read_text(encoding="utf-8").splitlines()) - 1
    content_hash = hash_csv_content(contract.path)
    schema_hash = hash_schema(contract.columns, contract.dtypes)
    return {
        "dataset_id": contract.dataset_id,
        "path": str(contract.path),
        "schema_version": contract.schema_version,
        "content_hash": content_hash,
        "schema_hash": schema_hash,
        "rows": max(row_count, 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_fingerprint_artifact(
    fingerprint: Mapping[str, object], *, output_dir: Path = DEFAULT_FINGERPRINT_DIR
) -> Path:
    """Persist a fingerprint JSON artifact."""

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{fingerprint['dataset_id']}.json"
    destination.write_text(
        json.dumps(fingerprint, indent=2, sort_keys=True), encoding="utf-8"
    )
    return destination


def record_run_fingerprint(
    contract: DatasetContract,
    *,
    run_type: str,
    output_dir: Path = DEFAULT_FINGERPRINT_DIR,
) -> Path:
    """Compute and persist a dataset fingerprint for a specific run type."""

    fingerprint = compute_dataset_fingerprint(contract)
    fingerprint = {
        **fingerprint,
        "run_type": run_type,
    }
    return write_fingerprint_artifact(fingerprint, output_dir=output_dir)


def record_transformation_trace(
    *,
    transformation_id: str,
    parameters: Mapping[str, object],
    input_fingerprint: Mapping[str, object],
    output_fingerprint: Mapping[str, object],
    output_dir: Path = DEFAULT_TRACE_DIR,
) -> Path:
    """Write a trace artifact linking inputs, outputs, and parameters."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "transformation_id": transformation_id,
        "parameters": dict(parameters),
        "input": dict(input_fingerprint),
        "output": dict(output_fingerprint),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = output_dir / f"{transformation_id}.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return destination


__all__ = [
    "compute_dataset_fingerprint",
    "fingerprint_rows",
    "hash_csv_content",
    "hash_schema",
    "record_run_fingerprint",
    "record_transformation_trace",
    "write_fingerprint_artifact",
]
