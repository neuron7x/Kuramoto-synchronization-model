# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Real-data ingest validator — ``validate_real_data_contract``.

Closes audit task T6 of the 9.9 upgrade. Pure-function, fail-closed
validator for the ``interbank.panel.v1`` real-data shape documented
in :doc:`REAL_DATA_INGEST_CONTRACT.md`.

Three terminal statuses (mirroring Protocol X-9R):

    PASS      contract satisfied; downstream may proceed
    FAIL      contract violated; downstream must abort
    BLOCKED   licence/legal/technical block; downstream must STOP

The validator never raises on contract violations — it returns a
``DataContractReport`` with ``status`` and ``reason``. It only
raises ``ValueError`` on contract-on-the-validator-itself bugs
(e.g. negative integer arg). Pure stdlib + pandas + numpy.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

import numpy as np
import pandas as pd

__all__ = [
    "DataContractReport",
    "REQUIRED_INPUT_FILES",
    "REQUIRED_MANIFEST_KEYS",
    "BLOCKED_LICENSE_TOKENS",
    "validate_real_data_contract",
]


REQUIRED_INPUT_FILES: tuple[str, ...] = (
    "manifest.json",
    "exposure_panel.parquet",
    "node_mapping.parquet",
    "crisis_ledger.json",
    "license.txt",
)


REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "source_id",
    "schema_version",
    "capture_timestamp_utc",
    "payload_sha256",
    "seed",
    "config_hash",
    "n_banks",
    "n_days",
    "crisis_lock_timestamp_utc",
    "first_evaluation_timestamp_utc",
)


BLOCKED_LICENSE_TOKENS: tuple[str, ...] = (
    "BLOCKED",
    "RESTRICTED",
    "EXPIRED",
    "DENIED",
    "EMBARGOED",
)


_CONTRACT_SCHEMA_VERSION: str = "interbank.panel.v1"


ContractStatus = Literal["PASS", "FAIL", "BLOCKED"]


class DataContractReport(NamedTuple):
    """Frozen verdict of :func:`validate_real_data_contract`.

    Mirrors the three-status alphabet of Protocol X-9R so a caller
    can dispatch identically: ``status == "BLOCKED"`` → STOP;
    ``status == "FAIL"`` → abort; ``status == "PASS"`` → proceed.
    """

    status: ContractStatus
    reason: str | None
    schema_version: str | None
    n_banks: int | None
    n_days: int | None
    n_events: int | None
    payload_sha256: str | None


def _sha256_of_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(reason: str) -> DataContractReport:
    return DataContractReport(
        status="FAIL",
        reason=reason,
        schema_version=None,
        n_banks=None,
        n_days=None,
        n_events=None,
        payload_sha256=None,
    )


def _blocked(reason: str) -> DataContractReport:
    return DataContractReport(
        status="BLOCKED",
        reason=reason,
        schema_version=None,
        n_banks=None,
        n_days=None,
        n_events=None,
        payload_sha256=None,
    )


def validate_real_data_contract(dataset_dir: str | Path) -> DataContractReport:
    """Validate a real-data dataset directory against the v1 contract.

    Returns a :class:`DataContractReport` with one of three statuses.
    Never raises on contract violations.
    """
    root = Path(dataset_dir)
    if not root.exists() or not root.is_dir():
        return _fail(f"dataset_dir does not exist or is not a directory: {root}")

    # 1. file presence
    missing = [name for name in REQUIRED_INPUT_FILES if not (root / name).is_file()]
    if missing:
        return _fail(f"missing required files: {missing}")

    # 2. license — read first; BLOCKED tokens trigger BLOCKED status.
    license_text = (root / "license.txt").read_text(encoding="utf-8").strip()
    if not license_text:
        return _blocked("license.txt is empty (cannot establish ingestion right)")
    # Word-boundary regex match — substring match falsely flags
    # "unrestricted" as containing "RESTRICTED".
    import re as _re

    upper = license_text.upper()
    _pattern = _re.compile(
        r"\b(" + "|".join(_re.escape(t) for t in BLOCKED_LICENSE_TOKENS) + r")\b"
    )
    _match = _pattern.search(upper)
    blocked_token = _match.group(1) if _match else None
    if blocked_token is not None:
        return _blocked(f"license.txt contains restriction token: {blocked_token!r}")

    # 3. manifest schema
    try:
        manifest_payload: Any = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _fail(f"manifest.json malformed: {exc}")
    if not isinstance(manifest_payload, dict):
        return _fail(f"manifest.json is not a JSON object, got {type(manifest_payload).__name__}")
    manifest: dict[str, Any] = manifest_payload
    missing_keys = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        return _fail(f"manifest missing required keys: {missing_keys}")
    if manifest["schema_version"] != _CONTRACT_SCHEMA_VERSION:
        return _fail(
            f"schema_version {manifest['schema_version']!r} != {_CONTRACT_SCHEMA_VERSION!r}"
        )

    # 4. timestamp tz check
    for key in (
        "capture_timestamp_utc",
        "crisis_lock_timestamp_utc",
        "first_evaluation_timestamp_utc",
    ):
        try:
            ts = datetime.fromisoformat(manifest[key])
        except (TypeError, ValueError):
            return _fail(f"manifest.{key} unparseable: {manifest[key]!r}")
        if ts.tzinfo is None:
            return _fail(f"manifest.{key} lacks timezone offset (naive timestamp)")

    lock = datetime.fromisoformat(manifest["crisis_lock_timestamp_utc"])
    first_eval = datetime.fromisoformat(manifest["first_evaluation_timestamp_utc"])
    if lock >= first_eval:
        return _fail(
            f"crisis_lock {lock.isoformat()} >= first_evaluation {first_eval.isoformat()} "
            f"(crisis-date tuning forbidden)"
        )

    # 5. shape constraints
    n_banks = int(manifest["n_banks"])
    n_days = int(manifest["n_days"])
    if n_banks < 3:
        return _fail(f"n_banks {n_banks} < 3")
    if n_days < 90:
        return _fail(f"n_days {n_days} < 90 (need ≥ 3× bootstrap min-lead-window)")

    # 6. payload sha256 — declared vs actual
    declared = manifest["payload_sha256"]
    actual = _sha256_of_path(root / "exposure_panel.parquet")
    if declared != actual:
        return _fail(f"payload_sha256 mismatch: declared={declared} actual={actual}")

    # 7. exposure_panel.parquet schema + invariants
    try:
        panel_df = pd.read_parquet(root / "exposure_panel.parquet")
    except Exception as exc:  # pragma: no cover — defensive
        return _fail(f"exposure_panel.parquet unreadable: {exc}")
    required_panel_cols = {"date", "source", "target", "exposure"}
    if not required_panel_cols.issubset(panel_df.columns):
        return _fail(
            f"exposure_panel.parquet missing required columns; got {sorted(panel_df.columns)}"
        )
    exp = panel_df["exposure"].to_numpy(dtype=np.float64, copy=False)
    if not np.all(np.isfinite(exp)):
        return _fail("exposure_panel contains non-finite values (NaN/Inf)")
    if np.any(exp < 0):
        return _fail("exposure_panel contains negative entries (forbidden)")
    if np.any(panel_df["source"].to_numpy() == panel_df["target"].to_numpy()):
        return _fail("exposure_panel contains self-loops (source == target)")

    # 8. node_mapping.parquet
    try:
        node_df = pd.read_parquet(root / "node_mapping.parquet")
    except Exception as exc:  # pragma: no cover — defensive
        return _fail(f"node_mapping.parquet unreadable: {exc}")
    if set(node_df.columns) != {"node_id", "bank_label"}:
        return _fail(f"node_mapping columns {sorted(node_df.columns)} != {{node_id, bank_label}}")
    ids = sorted(int(x) for x in node_df["node_id"].tolist())
    if ids != list(range(n_banks)):
        return _fail(f"node_mapping.node_id not surjective onto [0, {n_banks}); got {ids[:5]}...")
    if node_df["bank_label"].duplicated().any():
        return _fail("node_mapping.bank_label contains duplicates (survivorship risk)")

    # 9. crisis_ledger.json
    try:
        crisis = json.loads((root / "crisis_ledger.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _fail(f"crisis_ledger.json malformed: {exc}")
    if (
        not isinstance(crisis, dict)
        or "events" not in crisis
        or not isinstance(crisis["events"], list)
    ):
        return _fail("crisis_ledger must be {'events': [...]}")
    events = crisis["events"]
    if not events:
        return _fail("crisis_ledger has zero events")
    seen_ids: set[str] = set()
    panel_dates = pd.to_datetime(panel_df["date"]).dt.date.unique()
    panel_date_set = {pd.Timestamp(d).date() for d in panel_dates}
    for ev in events:
        if not isinstance(ev, dict):
            return _fail(f"crisis event is not a mapping: {ev!r}")
        eid = ev.get("id")
        if not isinstance(eid, str) or not eid:
            return _fail(f"crisis event missing/empty id: {ev!r}")
        if eid in seen_ids:
            return _fail(f"duplicate crisis id: {eid}")
        seen_ids.add(eid)
        try:
            ev_date = datetime.fromisoformat(ev["date"]).date()
        except (KeyError, TypeError, ValueError):
            return _fail(f"crisis event {eid} has unparseable date: {ev.get('date')!r}")
        if ev_date in panel_date_set:
            return _fail(
                f"crisis event {eid} date {ev_date.isoformat()} is inside the panel "
                f"(post-event contamination)"
            )

    # 10. all clear
    return DataContractReport(
        status="PASS",
        reason=None,
        schema_version=_CONTRACT_SCHEMA_VERSION,
        n_banks=n_banks,
        n_days=n_days,
        n_events=len(events),
        payload_sha256=actual,
    )
