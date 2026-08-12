"""Fail-closed L2 manifest ingestion (source recorded honestly, never relabelled)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .determinism import git_sha, sha256_path, timestamp_utc

try:  # pragma: no cover - exercised in project env when pandera is installed
    import pandera.pandas as pa
except Exception:  # pandera optional: manual checks below still fail closed
    pa = None


class DataFrameSchemaError(ValueError):
    """L2 frame contract violation (fail-closed).

    A dedicated class constructible from a single message — NOT aliased to
    pandera's ``SchemaError`` (whose ``__init__`` needs positional schema/data),
    so ``_raise_schema(message)`` works and callers can catch one stable type.
    """


REQUIRED_MANIFEST_VERSION = "l2_manifest.v1"
# Known real L2 sources. Recorded honestly — the source is carried through to
# the data_manifest verbatim, never relabelled. LOBSTER's free equity samples
# moved behind a keyed/licensed API (LOBSTER_LICENSED_L2), so the committed
# substrate is BINANCE_FUTURES_DEPTH (public REST depth, no key). Binance data
# must NEVER be rewritten into a LOBSTER label.
ALLOWED_SOURCES = {"LOBSTER_LICENSED_L2", "BINANCE_FUTURES_DEPTH"}
# NC-06 substrate-class binding (single source of truth, fail-closed). A Binance
# public-depth session is BINANCE_PUBLIC_DEPTH / PUBLIC_NO_LICENSE and can never
# be relabelled as a licensed LOBSTER substrate.
SOURCE_CLASS_BINDING = {
    "BINANCE_FUTURES_DEPTH": ("BINANCE_PUBLIC_DEPTH", "PUBLIC_NO_LICENSE"),
    "LOBSTER_LICENSED_L2": ("LOBSTER_LICENSED", "LICENSED"),
}


def _raise_schema(message: str) -> None:
    raise DataFrameSchemaError(message)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest JSON: {exc}") from exc
    required = {"source", "symbol", "date", "depth", "data_path", "schema_version"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"manifest missing required fields: {missing}")
    if payload["source"] not in ALLOWED_SOURCES:
        raise ValueError(f"manifest source must be one of {sorted(ALLOWED_SOURCES)}")
    if payload["schema_version"] != REQUIRED_MANIFEST_VERSION:
        raise ValueError(f"manifest schema_version must be {REQUIRED_MANIFEST_VERSION}")
    if int(payload["depth"]) < 1:
        raise ValueError("manifest depth must be >= 1")
    # NC-06: if the manifest self-declares a substrate class / license, it MUST
    # match the binding for its source. This rejects, fail-closed, a Binance
    # session mislabelled as a licensed LOBSTER substrate.
    expected_class, expected_license = SOURCE_CLASS_BINDING[payload["source"]]
    declared_class = payload.get("source_class")
    if declared_class is not None and declared_class != expected_class:
        raise ValueError(
            f"source_class {declared_class!r} does not match source "
            f"{payload['source']!r} (expected {expected_class!r}) — relabel rejected"
        )
    declared_license = payload.get("license_status")
    if declared_license is not None and declared_license != expected_license:
        raise ValueError(
            f"license_status {declared_license!r} does not match source "
            f"{payload['source']!r} (expected {expected_license!r}) — relabel rejected"
        )
    return payload


def _read_l2_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported L2 data file type: {path.suffix}")


def required_columns(depth: int) -> list[str]:
    columns = ["timestamp", "price"]
    for idx in range(1, depth + 1):
        columns.extend([f"bid_px_{idx}", f"ask_px_{idx}", f"bid_sz_{idx}", f"ask_sz_{idx}"])
    return columns


def validate_l2_frame(frame: pd.DataFrame, *, depth: int) -> pd.DataFrame:
    columns = required_columns(depth)
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        _raise_schema(f"missing column(s): {missing}")
    validated = frame.loc[:, columns].copy()
    validated["timestamp"] = pd.to_datetime(validated["timestamp"], utc=True, errors="raise")
    if not validated["timestamp"].is_monotonic_increasing:
        _raise_schema("non-monotonic timestamp")
    for column in columns:
        if column == "timestamp":
            continue
        validated[column] = pd.to_numeric(validated[column], errors="raise")
        if validated[column].isna().any():
            _raise_schema(f"NaN value in {column}")
    for idx in range(1, depth + 1):
        for column in (f"bid_sz_{idx}", f"ask_sz_{idx}"):
            if (validated[column] < 0).any():
                _raise_schema(f"negative size in {column}")
    if pa is not None:
        schema_columns: dict[str, Any] = {
            "timestamp": pa.Column(pa.DateTime, nullable=False),
            "price": pa.Column(float, nullable=False),
        }
        for idx in range(1, depth + 1):
            schema_columns[f"bid_px_{idx}"] = pa.Column(float, nullable=False)
            schema_columns[f"ask_px_{idx}"] = pa.Column(float, nullable=False)
            schema_columns[f"bid_sz_{idx}"] = pa.Column(float, pa.Check.ge(0), nullable=False)
            schema_columns[f"ask_sz_{idx}"] = pa.Column(float, pa.Check.ge(0), nullable=False)
        try:
            pa.DataFrameSchema(schema_columns, strict=True, coerce=True).validate(validated)
        except Exception as exc:  # normalise pandera SchemaError to our stable type
            _raise_schema(f"pandera validation failed: {exc}")
    return validated


def ingest_manifest(manifest_path: Path, *, out_dir: Path | None = None) -> dict[str, Path]:
    manifest = load_manifest(manifest_path)
    depth = int(manifest["depth"])
    data_path = Path(str(manifest["data_path"]))
    if not data_path.is_absolute():
        data_path = manifest_path.parent / data_path
    if not data_path.is_file():
        raise FileNotFoundError(f"missing L2 data file: {data_path}")
    destination = out_dir or manifest_path.parent
    destination.mkdir(parents=True, exist_ok=True)

    raw_frame = _read_l2_frame(data_path)
    validated = validate_l2_frame(raw_frame, depth=depth)
    parquet_path = destination / "validated_l2_frame.parquet"
    validated.to_parquet(parquet_path, index=False)

    ts = pd.to_datetime(validated["timestamp"], utc=True)
    collector = Path(__file__).with_name("collect_binance_l2.py")
    source_class, license_status = SOURCE_CLASS_BINDING[str(manifest["source"])]
    manifest_out = {
        "source": str(manifest["source"]),  # honest passthrough — never relabelled
        "source_class": source_class,  # NC-06: substrate class bound to source
        "license_status": license_status,
        "source_uri_policy": str(manifest.get("source_uri_policy", "unknown")),
        "venue": str(manifest.get("venue", manifest["source"])),
        "symbol": str(manifest["symbol"]),
        "date": str(manifest["date"]),
        "depth": depth,
        "snapshot_count": int(len(validated)),
        "session_window_utc": [ts.min().isoformat(), ts.max().isoformat()],
        "data_sha256": sha256_path(data_path),
        "collector_version": str(manifest.get("collector_version", "unknown")),
        "collector_sha256": sha256_path(collector) if collector.is_file() else "",
        "git_sha": git_sha(),
        "timestamp_utc": timestamp_utc(),
        "schema_version": REQUIRED_MANIFEST_VERSION,
    }
    data_manifest_path = destination / "data_manifest.json"
    data_manifest_path.write_text(
        json.dumps(manifest_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    ingest_log_path = destination / "ingest_log.json"
    ingest_log_path.write_text(
        json.dumps(
            {
                "rows": int(len(validated)),
                "columns": required_columns(depth),
                "validated_l2_frame": parquet_path.as_posix(),
                "data_manifest": data_manifest_path.as_posix(),
                "status": "VALIDATED",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "data_manifest": data_manifest_path,
        "validated_l2_frame": parquet_path,
        "ingest_log": ingest_log_path,
    }
