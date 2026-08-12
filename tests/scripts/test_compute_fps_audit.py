# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``scripts/ci/compute_fps_audit.py``.

The compute_fps_audit script gates the CI on the IERD §5
``FPS_audit = 1.00`` invariant. The tests below pin the schema
parser, the per-claim audit semantics (test/artefact path detection,
existence-of-paths, tier-aware numerator), and the threshold logic
against synthetic CLAIMS.yaml fixtures, independent of the live
registry.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "compute_fps_audit.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("compute_fps_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["compute_fps_audit"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cf() -> Any:
    return _load_module()


# ---------------------------------------------------------------------------
# _audit_claim — the per-claim semantics
# ---------------------------------------------------------------------------


def _make_row(cf: Any, *, cid: str, tier: str, paths: list[str]) -> Any:
    return cf.ClaimRow(
        cid=cid,
        priority="P0",
        tier=tier,
        evidence_paths=tuple(paths),
    )


def test_anchored_with_test_path_counts(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="ANCHORED",
        paths=["docs/CLAIMS.yaml", "tests/scripts/test_check_claims.py"],
    )
    audit = cf._audit_claim(row)
    assert audit.has_test is True
    assert audit.all_paths_exist is True
    assert audit.counts_for_numerator is True


def test_anchored_with_artefact_path_counts(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="ANCHORED",
        paths=["docs/audit/ierd_phase0_findings.md"],
    )
    audit = cf._audit_claim(row)
    assert audit.has_artefact is True
    assert audit.all_paths_exist is True
    assert audit.counts_for_numerator is True


def test_anchored_source_only_does_not_count(cf: Any) -> None:
    """Source-only ANCHORED is not real evidence under IERD §5."""
    row = _make_row(cf, cid="x", tier="ANCHORED", paths=["docs/CLAIMS.yaml"])
    audit = cf._audit_claim(row)
    assert audit.has_test is False
    assert audit.has_artefact is False
    assert audit.counts_for_numerator is False


def test_extrapolated_with_test_counts(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="EXTRAPOLATED",
        paths=["tests/scripts/test_check_claims.py"],
    )
    audit = cf._audit_claim(row)
    assert audit.counts_for_numerator is True


def test_speculative_never_counts(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="SPECULATIVE",
        paths=["tests/scripts/test_check_claims.py"],
    )
    audit = cf._audit_claim(row)
    assert audit.counts_for_numerator is False


def test_unknown_never_counts(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="UNKNOWN",
        paths=["tests/scripts/test_check_claims.py"],
    )
    audit = cf._audit_claim(row)
    assert audit.counts_for_numerator is False


def test_missing_path_disqualifies_anchored(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="ANCHORED",
        paths=["tests/scripts/test_check_claims.py", "tests/does/not/exist.py"],
    )
    audit = cf._audit_claim(row)
    assert audit.all_paths_exist is False
    assert audit.counts_for_numerator is False
    assert "tests/does/not/exist.py" in audit.missing_paths


# ---------------------------------------------------------------------------
# _load_claims — schema gate
# ---------------------------------------------------------------------------


def _write_claims(tmp_path: Path, body: dict[str, Any]) -> Path:
    path = tmp_path / "CLAIMS.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def test_load_claims_v2_requires_tier_value_in_set(
    tmp_path: Path, cf: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {
        "schema_version": 2,
        "claims": [
            {
                "id": "x",
                "priority": "P0",
                "tier": "BOGUS",
                "description": "synthetic",
                "evidence_paths": ["docs/CLAIMS.yaml"],
                "added_utc": "2026-05-03",
            },
        ],
    }
    path = _write_claims(tmp_path, body)
    monkeypatch.setattr(cf, "CLAIMS_PATH", path)
    with pytest.raises(ValueError, match="tier"):
        cf._load_claims()


def test_load_claims_v1_legacy_defaults_to_anchored(
    tmp_path: Path, cf: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {
        "schema_version": 1,
        "claims": [
            {
                "id": "legacy",
                "priority": "P0",
                "description": "synthetic",
                "evidence_paths": ["docs/CLAIMS.yaml"],
                "added_utc": "2026-04-25",
            },
        ],
    }
    path = _write_claims(tmp_path, body)
    monkeypatch.setattr(cf, "CLAIMS_PATH", path)
    rows = cf._load_claims()
    assert len(rows) == 1
    assert rows[0].tier == "ANCHORED"


def test_load_claims_unsupported_schema_rejected(
    tmp_path: Path, cf: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"schema_version": 99, "claims": []}
    path = _write_claims(tmp_path, body)
    monkeypatch.setattr(cf, "CLAIMS_PATH", path)
    with pytest.raises(ValueError, match="schema_version"):
        cf._load_claims()


# ---------------------------------------------------------------------------
# Snapshot + serialization
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_round_trip(cf: Any) -> None:
    row = _make_row(
        cf,
        cid="x",
        tier="ANCHORED",
        paths=["tests/scripts/test_check_claims.py"],
    )
    audit = cf._audit_claim(row)
    snap = cf.FpsSnapshot(
        fps_audit=1.0,
        threshold=1.0,
        threshold_met=True,
        total_anchored_or_extrapolated=1,
        qualifying=1,
        tier_distribution={
            "ANCHORED": 1,
            "EXTRAPOLATED": 0,
            "SPECULATIVE": 0,
            "UNKNOWN": 0,
        },
        audits=[audit],
    )
    payload = json.loads(json.dumps(snap.to_dict()))
    assert payload["fps_audit"] == 1.0
    assert payload["threshold_met"] is True
    assert payload["audits"][0]["id"] == "x"
    assert payload["audits"][0]["counts_for_numerator"] is True


# ---------------------------------------------------------------------------
# Live integration — exercise the actual repo state
# ---------------------------------------------------------------------------


def test_live_fps_audit_is_one(cf: Any) -> None:
    """IERD §5: FPS_audit must be exactly 1.00 on main."""
    snapshot = cf.compute_fps_audit(threshold=1.0)
    assert snapshot.threshold_met, (
        f"FPS_audit dropped below 1.00: {snapshot.fps_audit:.4f}; "
        f"non-qualifying ANCHORED/EXTRAPOLATED claims: "
        f"{[a.claim.cid for a in snapshot.audits if a.claim.tier in cf.ANCHORED_TIERS and not a.counts_for_numerator]}"
    )


def test_live_no_speculative_in_product_docs_per_yaml(cf: Any) -> None:
    """SPECULATIVE tier is forbidden in CLAIMS.yaml product surface
    per IERD §2.3 — research notes are out of CLAIMS scope. The live
    ledger should never carry SPECULATIVE."""
    snapshot = cf.compute_fps_audit(threshold=1.0)
    assert snapshot.tier_distribution["SPECULATIVE"] == 0, (
        f"unexpected SPECULATIVE entries: "
        f"{[a.claim.cid for a in snapshot.audits if a.claim.tier == 'SPECULATIVE']}"
    )
