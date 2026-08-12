# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Protocol X-9R/1.0-RUN — full failure-mode coverage tests.

Every test scenario from the protocol spec is covered: schema /
license / provenance / mapping / survivorship / leakage / null /
metrics / capsule / rerun / governance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from research.systemic_risk.protocol_x9r import (
    GateName,
    GateStatus,
    MaxClaimTier,
    ProtocolVerdict,
    rerun_capsule,
    run_protocol_x9r,
)

# ============================================================================
# Helpers — build a clean dataset_dir; tests then break ONE thing.
# ============================================================================


def _sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_clean_dataset(
    root: Path,
    *,
    n_banks: int = 6,
    n_days: int = 120,
    seed: int = 42,
    crisis_offset_days: int = 10,
    high_signal: bool = True,
) -> Path:
    """Build a fully valid dataset_dir at ``root / 'dataset_dir'``.

    The exposure panel optionally injects a high-signal pre-crisis
    spike so the candidate score beats the nulls in the baseline run.

    The crisis date sits ``crisis_offset_days`` days *after* the panel
    end, so the lead window ``[crisis - 90, crisis)`` overlaps the
    last ``90 - crisis_offset_days`` panel days. Default 10 → window
    covers panel days [n_days - 80, n_days], catching the spike that
    is injected at days [n_days - 30, n_days - 1].
    """
    dataset_dir = root / "dataset_dir"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    # 1. node_mapping.parquet — surjective onto 0..N-1, unique labels.
    node_df = pd.DataFrame(
        {
            "node_id": list(range(n_banks)),
            "bank_label": [f"BANK_{i:02d}" for i in range(n_banks)],
        }
    )
    node_df.to_parquet(dataset_dir / "node_mapping.parquet", index=False)

    # 2. exposure_panel.parquet — long format (date, source, target, exposure).
    base = date(2026, 1, 1)
    rows: list[dict[str, Any]] = []
    for d_offset in range(n_days):
        d = base + timedelta(days=d_offset)
        for s in range(n_banks):
            for t in range(n_banks):
                if s == t:
                    continue
                # Baseline exposure: 1.0 + small structured drift.
                ex = 1.0 + 0.01 * (s + t)
                if high_signal and d_offset >= n_days - 30:
                    # Pre-crisis spike — boost exposures so the
                    # candidate trailing-mean score beats both the
                    # shuffled-time and permuted-crisis nulls. Spike
                    # is in the LAST 30 days of the panel, just
                    # before the (off-panel) crisis date.
                    ex *= 5.0 + 0.5 * (d_offset - (n_days - 30))
                rows.append({"date": d, "source": s, "target": t, "exposure": ex})
    panel_df = pd.DataFrame(rows)
    panel_df.to_parquet(dataset_dir / "exposure_panel.parquet", index=False)

    # 3. crisis_ledger.json — at least 2 events so AUC has ≥ 2
    # positive samples. Both sit at offsets *after* the panel end so
    # each lead window overlaps the panel's spike region.
    event_date = base + timedelta(days=n_days - 1 + crisis_offset_days)
    event_date_2 = base + timedelta(days=n_days - 1 + max(1, crisis_offset_days // 2))
    crisis = {
        "events": [
            {"id": "E_PRIMARY", "date": event_date.isoformat(), "country": "TEST"},
            {"id": "E_SECONDARY", "date": event_date_2.isoformat(), "country": "TEST"},
        ]
    }
    (dataset_dir / "crisis_ledger.json").write_text(
        json.dumps(crisis, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 4. manifest.json — payload_sha256 must match the panel parquet.
    panel_sha = _sha256_path(dataset_dir / "exposure_panel.parquet")
    capture_ts = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc).isoformat()
    crisis_lock = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc).isoformat()
    first_eval = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = {
        "source_id": "synthetic-x9r-v1",
        "schema_version": "interbank.panel.v1",
        "capture_timestamp_utc": capture_ts,
        "payload_sha256": panel_sha,
        "seed": seed,
        "config_hash": "deadbeef" * 8,
        "n_banks": n_banks,
        "n_days": n_days,
        "crisis_lock_timestamp_utc": crisis_lock,
        "first_evaluation_timestamp_utc": first_eval,
        "config": {"window": 30, "align": "trailing"},
    }
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # 5. license.txt — clean.
    (dataset_dir / "license.txt").write_text(
        "Test dataset under MIT for protocol X-9R unit testing.", encoding="utf-8"
    )
    return dataset_dir


def _refresh_panel_sha(dataset_dir: Path) -> None:
    """Recompute payload_sha256 in manifest after panel mutation."""
    manifest = json.loads((dataset_dir / "manifest.json").read_text())
    manifest["payload_sha256"] = _sha256_path(dataset_dir / "exposure_panel.parquet")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


# ============================================================================
# Happy path — full protocol PASS
# ============================================================================


class TestHappyPath:
    def test_clean_dataset_passes_all_gates(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = tmp_path / "capsule"
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        # The full machine should run all 9 gates.
        gate_names = [g.gate for g in capsule.gate_results]
        assert gate_names == [g.value for g in GateName]
        # All gates pass — verdict PASS.
        assert capsule.verdict == ProtocolVerdict.PASS.value
        assert capsule.failed_gate is None
        assert capsule.max_claim_tier == MaxClaimTier.OBSERVED_IN_DATASET.value
        # Capsule on disk has every required artefact.
        for required in (
            "capsule.json",
            "gate_results.json",
            "metrics.json",
            "null_audit.json",
            "leakage_report.json",
            "evidence_ledger.jsonl",
            "death_conditions.json",
            "rerun.sh",
        ):
            assert (out / required).is_file()
        for required_dir in ("logs", "figures", "figure_sources"):
            assert (out / required_dir).is_dir()
        # Rerun.sh executable bit set.
        assert (out / "rerun.sh").stat().st_mode & 0o111


# ============================================================================
# Gate 1 — INPUT_SCHEMA failures
# ============================================================================


class TestInputSchemaGate:
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
    def test_missing_required_file_fails(self, tmp_path: Path, victim: str) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        (dataset_dir / victim).unlink()
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.INPUT_SCHEMA.value
        assert capsule.max_claim_tier == MaxClaimTier.HYPOTHESIS.value

    def test_missing_dataset_dir(self, tmp_path: Path) -> None:
        capsule = run_protocol_x9r(
            dataset_dir=tmp_path / "nonexistent",
            output_dir=tmp_path / "capsule",
        )
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.INPUT_SCHEMA.value


# ============================================================================
# Gate 2 — DATA_FIREWALL failures (license / provenance / mapping / survivorship)
# ============================================================================


class TestDataFirewallGate:
    def test_blocked_license_token_yields_BLOCKED(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        (dataset_dir / "license.txt").write_text(
            "Status: RESTRICTED — covered by ECB MMSR Regulation 2014/1333",
            encoding="utf-8",
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.BLOCKED_BY_DATA_ACCESS.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_empty_license_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        (dataset_dir / "license.txt").write_text("", encoding="utf-8")
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_provenance_hash_mismatch_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        # Tamper with manifest's payload_sha256 — declared ≠ actual.
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        manifest["payload_sha256"] = "0" * 64
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_manifest_missing_required_keys_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        del manifest["seed"]
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_mapping_columns_wrong_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        bad = pd.DataFrame({"id": [0, 1, 2], "name": ["a", "b", "c"]})
        bad.to_parquet(dataset_dir / "node_mapping.parquet", index=False)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_mapping_not_surjective_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        df = pd.DataFrame({"node_id": [0, 1, 99], "bank_label": ["A", "B", "C"]})
        df.to_parquet(dataset_dir / "node_mapping.parquet", index=False)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_mapping_duplicate_labels_survivorship_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path, n_banks=3)
        df = pd.DataFrame({"node_id": [0, 1, 2], "bank_label": ["A", "A", "C"]})
        df.to_parquet(dataset_dir / "node_mapping.parquet", index=False)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value

    def test_panel_columns_wrong_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        bad = pd.DataFrame({"day": [date(2026, 1, 1)], "from": [0], "to": [1], "amount": [1.0]})
        bad.to_parquet(dataset_dir / "exposure_panel.parquet", index=False)
        _refresh_panel_sha(dataset_dir)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.DATA_FIREWALL.value


# ============================================================================
# Gate 3 — LEAKAGE_SENTINEL failures
# ============================================================================


class TestLeakageSentinelGate:
    def test_label_leakage_column_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        panel = pd.read_parquet(dataset_dir / "exposure_panel.parquet")
        panel["crisis_label"] = 0
        panel.to_parquet(dataset_dir / "exposure_panel.parquet", index=False)
        _refresh_panel_sha(dataset_dir)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value

    def test_centered_window_in_config_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        manifest["config"]["center"] = True
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value

    def test_align_center_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        manifest["config"]["align"] = "center"
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value

    def test_full_sample_normalization_op_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        manifest["config"]["ops"] = ["full_sample_zscore", "rolling_std"]
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value

    def test_crisis_date_tuning_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        manifest = json.loads((dataset_dir / "manifest.json").read_text())
        # Lock AFTER first evaluation — crisis-date tuning.
        manifest["crisis_lock_timestamp_utc"] = "2026-06-01T12:00:00+00:00"
        manifest["first_evaluation_timestamp_utc"] = "2026-05-08T12:00:00+00:00"
        (dataset_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value

    def test_post_event_contamination_fails(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        # Inject a crisis event whose date is INSIDE the panel
        # (post-event contamination — score window must end before crisis).
        panel = pd.read_parquet(dataset_dir / "exposure_panel.parquet")
        first_panel_date = pd.to_datetime(panel["date"]).dt.date.min()
        crisis = {
            "events": [
                {
                    "id": "E_INSIDE",
                    "date": (first_panel_date + timedelta(days=30)).isoformat(),
                    "country": "TEST",
                }
            ]
        }
        (dataset_dir / "crisis_ledger.json").write_text(
            json.dumps(crisis, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.LEAKAGE_SENTINEL.value


# ============================================================================
# Gate 4 — END_TO_END_RUN: placeholder-score impossibility
# ============================================================================


class TestEndToEndRunGate:
    def test_zero_panel_yields_fail(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        # Crisis date so far in the future that no pre-event window
        # of the panel applies → all per-event scores NaN → FAIL.
        crisis = {
            "events": [
                {
                    "id": "E_FAR_FUTURE",
                    "date": "2099-01-01T00:00:00+00:00",
                    "country": "TEST",
                }
            ]
        }
        (dataset_dir / "crisis_ledger.json").write_text(
            json.dumps(crisis, indent=2, sort_keys=True), encoding="utf-8"
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        # Score window finds no panel dates — produces NaN scores —
        # gate fails on placeholder-score guard.
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.END_TO_END_RUN.value


# ============================================================================
# Gate 5 — NULL_AUDIT failures
# ============================================================================


class TestNullAuditGate:
    def test_low_signal_panel_loses_to_null(self, tmp_path: Path) -> None:
        # high_signal=False → uniform exposures → candidate cannot
        # beat shuffled-time / permuted-crisis nulls by the required
        # margin → NULL_AUDIT FAIL.
        dataset_dir = _build_clean_dataset(tmp_path, high_signal=False)
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=tmp_path / "capsule")
        assert capsule.verdict == ProtocolVerdict.FAIL.value
        assert capsule.failed_gate == GateName.NULL_AUDIT.value


# ============================================================================
# Gate 6 — METRICS_VALIDITY: AUC + CI + Bonferroni p, no AUC-only
# ============================================================================


class TestMetricsValidityGate:
    def test_metrics_payload_has_full_triple(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = tmp_path / "capsule"
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        if capsule.verdict != ProtocolVerdict.PASS.value:
            pytest.skip(f"happy-path prerequisite failed at {capsule.failed_gate}")
        metrics = json.loads((out / "metrics.json").read_text())
        # AUC-only forbidden — must have AUC + CI + Bonferroni p.
        for required in ("auc", "ci_low_95", "ci_high_95", "p_bonferroni"):
            assert required in metrics


# ============================================================================
# Gate 7 — CAPSULE_WRITE: missing capsule
# ============================================================================


class TestCapsuleWrite:
    def test_capsule_artefacts_complete(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = tmp_path / "capsule"
        run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        assert (out / "capsule.json").is_file()
        capsule_payload = json.loads((out / "capsule.json").read_text())
        # Capsule.json carries metrics_sha, score_sha, input_shas, etc.
        for required in (
            "verdict",
            "max_claim_tier",
            "input_shas",
            "metrics_sha",
            "rerun_command",
            "written_at_utc",
        ):
            assert required in capsule_payload


# ============================================================================
# Gate 8 — RERUN_CHECK: rerun mismatch detection
# ============================================================================


class TestRerunCheck:
    def test_rerun_on_unchanged_dataset_passes(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = dataset_dir.parent / "capsule"
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        if capsule.verdict != ProtocolVerdict.PASS.value:
            pytest.skip("baseline did not PASS; cannot test rerun")
        # rerun_capsule expects ../dataset_dir relative to the capsule.
        rerun = rerun_capsule(capsule_dir=out)
        assert rerun.verdict == ProtocolVerdict.PASS.value

    def test_rerun_on_mutated_dataset_fails_on_mismatch(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = dataset_dir.parent / "capsule"
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        if capsule.verdict != ProtocolVerdict.PASS.value:
            pytest.skip("baseline did not PASS; cannot test rerun mismatch")
        # Tamper with the capsule's stored metrics_sha. The rerun
        # will recompute the actual metrics_sha (deterministic on
        # the unchanged dataset) and compare against the tampered
        # value — RERUN_CHECK gate must detect the mismatch. This
        # is the canonical "someone edited the capsule" attack.
        cap_payload = json.loads((out / "capsule.json").read_text())
        cap_payload["metrics_sha"] = "0" * 64  # known-different SHA
        (out / "capsule.json").write_text(
            json.dumps(cap_payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        rerun = rerun_capsule(capsule_dir=out)
        assert rerun.verdict == ProtocolVerdict.FAIL.value
        assert rerun.failed_gate == GateName.RERUN_CHECK.value
        # Per the canonical-7 contract, RERUN_CHECK fail → REJECTED
        # (terminal — no resurrection).
        assert rerun.max_claim_tier == MaxClaimTier.REJECTED.value

    def test_rerun_without_capsule_json_raises(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty_capsule"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="capsule.json"):
            rerun_capsule(capsule_dir=empty_dir)


# ============================================================================
# Gate 9 — CLAIM_GOVERNANCE: overclaim grep
# ============================================================================


class TestClaimGovernance:
    def test_overclaim_in_capsule_dir_fails(self, tmp_path: Path) -> None:
        # Pre-seed the output_dir with an overclaim-laden file BEFORE
        # the protocol runs. CAPSULE_WRITE adds its files alongside;
        # CLAIM_GOVERNANCE then greps the entire dir.
        dataset_dir = _build_clean_dataset(tmp_path)
        out = tmp_path / "capsule"
        out.mkdir()
        (out / "overclaim_note.md").write_text(
            "# Result\n\nThe model is VALIDATED and predicts crisis events in production.",
            encoding="utf-8",
        )
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        # Either the CLAIM_GOVERNANCE gate trips, or earlier gates
        # PASS and CLAIM_GOVERNANCE catches the planted overclaim.
        if capsule.verdict == ProtocolVerdict.PASS.value:
            pytest.fail("overclaim should have been caught by CLAIM_GOVERNANCE")
        assert capsule.failed_gate == GateName.CLAIM_GOVERNANCE.value


# ============================================================================
# Gate-result contract — every gate emits the canonical record shape
# ============================================================================


class TestGateContract:
    def test_every_gate_emits_canonical_record_shape(self, tmp_path: Path) -> None:
        dataset_dir = _build_clean_dataset(tmp_path)
        out = tmp_path / "capsule"
        capsule = run_protocol_x9r(dataset_dir=dataset_dir, output_dir=out)
        for g in capsule.gate_results:
            assert g.gate in {gn.value for gn in GateName}
            assert g.status in {st.value for st in GateStatus}
            assert isinstance(g.inputs_sha256, tuple)
            assert isinstance(g.outputs_sha256, tuple)
            assert isinstance(g.evidence, dict)
            # Timestamps round-trip ISO-8601.
            datetime.fromisoformat(g.started_at_utc)
            datetime.fromisoformat(g.ended_at_utc)
