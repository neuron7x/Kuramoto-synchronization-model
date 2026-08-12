# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the real-data ingest contract validator."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from research.systemic_risk.real_data_contract import (
    BLOCKED_LICENSE_TOKENS,
    DataContractReport,
    validate_real_data_contract,
)


def _sha256_of_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_clean(root: Path, *, n_banks: int = 6, n_days: int = 100) -> Path:
    """Build a contract-valid dataset_dir under ``root / "ds"``."""
    ds = root / "ds"
    ds.mkdir(parents=True, exist_ok=True)

    # node_mapping
    nodes = pd.DataFrame(
        {
            "node_id": list(range(n_banks)),
            "bank_label": [f"BANK_{i:02d}" for i in range(n_banks)],
        }
    )
    nodes.to_parquet(ds / "node_mapping.parquet", index=False)

    # exposure_panel
    base = date(2026, 1, 1)
    rows: list[dict[str, Any]] = []
    for d_offset in range(n_days):
        d = base + timedelta(days=d_offset)
        for s in range(n_banks):
            for t in range(n_banks):
                if s == t:
                    continue
                rows.append({"date": d, "source": s, "target": t, "exposure": 1.0 + 0.01 * (s + t)})
    pd.DataFrame(rows).to_parquet(ds / "exposure_panel.parquet", index=False)

    # crisis_ledger — event past panel end
    ev_date = base + timedelta(days=n_days + 30)
    crisis = {"events": [{"id": "E1", "date": ev_date.isoformat(), "country": "TEST"}]}
    (ds / "crisis_ledger.json").write_text(
        json.dumps(crisis, indent=2, sort_keys=True), encoding="utf-8"
    )

    # license
    (ds / "license.txt").write_text(
        "Test data under MIT for v1 ingest contract validation.", encoding="utf-8"
    )

    # manifest
    panel_sha = _sha256_of_path(ds / "exposure_panel.parquet")
    manifest = {
        "source_id": "synthetic-contract-test",
        "schema_version": "interbank.panel.v1",
        "capture_timestamp_utc": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        "payload_sha256": panel_sha,
        "seed": 42,
        "config_hash": "deadbeef" * 8,
        "n_banks": n_banks,
        "n_days": n_days,
        "crisis_lock_timestamp_utc": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        "first_evaluation_timestamp_utc": datetime(
            2026, 5, 8, 12, 0, tzinfo=timezone.utc
        ).isoformat(),
    }
    (ds / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return ds


class TestPass:
    def test_clean_dataset_passes(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        rep = validate_real_data_contract(ds)
        assert isinstance(rep, DataContractReport)
        assert rep.status == "PASS"
        assert rep.reason is None
        assert rep.schema_version == "interbank.panel.v1"
        assert rep.n_banks == 6
        assert rep.n_days == 100
        assert rep.n_events == 1


class TestBlocked:
    @pytest.mark.parametrize("token", BLOCKED_LICENSE_TOKENS)
    def test_blocked_license_token(self, tmp_path: Path, token: str) -> None:
        ds = _build_clean(tmp_path)
        (ds / "license.txt").write_text(
            f"Status: {token} — please consult counsel.", encoding="utf-8"
        )
        rep = validate_real_data_contract(ds)
        assert rep.status == "BLOCKED"
        assert token in (rep.reason or "")

    def test_empty_license_blocks(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        (ds / "license.txt").write_text("", encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "BLOCKED"


class TestFail:
    def test_missing_dataset_dir(self, tmp_path: Path) -> None:
        rep = validate_real_data_contract(tmp_path / "nonexistent")
        assert rep.status == "FAIL"

    @pytest.mark.parametrize(
        "victim",
        [
            "manifest.json",
            "exposure_panel.parquet",
            "node_mapping.parquet",
            "crisis_ledger.json",
            "license.txt",
        ],
    )
    def test_missing_required_file(self, tmp_path: Path, victim: str) -> None:
        ds = _build_clean(tmp_path)
        (ds / victim).unlink()
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"

    def test_schema_version_mismatch(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        m = json.loads((ds / "manifest.json").read_text())
        m["schema_version"] = "interbank.panel.v2"
        (ds / "manifest.json").write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "schema_version" in (rep.reason or "")

    def test_payload_sha_mismatch(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        m = json.loads((ds / "manifest.json").read_text())
        m["payload_sha256"] = "0" * 64
        (ds / "manifest.json").write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "payload_sha256" in (rep.reason or "")

    def test_naive_timestamp_rejected(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        m = json.loads((ds / "manifest.json").read_text())
        m["capture_timestamp_utc"] = "2026-05-01T12:00:00"  # no tz
        (ds / "manifest.json").write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"

    def test_crisis_lock_after_evaluation_rejected(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        m = json.loads((ds / "manifest.json").read_text())
        m["crisis_lock_timestamp_utc"] = "2026-06-01T12:00:00+00:00"
        m["first_evaluation_timestamp_utc"] = "2026-05-08T12:00:00+00:00"
        (ds / "manifest.json").write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "crisis_lock" in (rep.reason or "")

    def test_n_days_too_small(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path, n_days=30)  # < 90 minimum
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "n_days" in (rep.reason or "")

    def test_negative_exposure_rejected(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        df = pd.read_parquet(ds / "exposure_panel.parquet")
        df.loc[df.index[0], "exposure"] = -1.0
        df.to_parquet(ds / "exposure_panel.parquet", index=False)
        m = json.loads((ds / "manifest.json").read_text())
        m["payload_sha256"] = _sha256_of_path(ds / "exposure_panel.parquet")
        (ds / "manifest.json").write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "negative" in (rep.reason or "")

    def test_duplicate_bank_label_rejected(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        df = pd.read_parquet(ds / "node_mapping.parquet")
        df.loc[df.index[0], "bank_label"] = df.loc[df.index[1], "bank_label"]
        df.to_parquet(ds / "node_mapping.parquet", index=False)
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "duplicate" in (rep.reason or "").lower()

    def test_crisis_inside_panel_rejected(self, tmp_path: Path) -> None:
        ds = _build_clean(tmp_path)
        # Move event date INSIDE panel.
        crisis = json.loads((ds / "crisis_ledger.json").read_text())
        first_date = pd.to_datetime(
            pd.read_parquet(ds / "exposure_panel.parquet")["date"]
        ).dt.date.min()
        crisis["events"][0]["date"] = (first_date + timedelta(days=30)).isoformat()
        (ds / "crisis_ledger.json").write_text(json.dumps(crisis, sort_keys=True), encoding="utf-8")
        rep = validate_real_data_contract(ds)
        assert rep.status == "FAIL"
        assert "post-event" in (rep.reason or "").lower() or "inside" in (rep.reason or "").lower()
