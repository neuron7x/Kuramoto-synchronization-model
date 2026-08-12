# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract loader tests — hash verification is fail-closed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from research.robustness.protocols.kuramoto_contract import (
    FrozenArtifactManifest,
    FrozenArtifactMismatch,
    KuramotoRobustnessContract,
)

REPO = Path(__file__).resolve().parents[3]


class TestFrozenArtifactManifest:
    def test_loads_real_manifest(self) -> None:
        manifest = FrozenArtifactManifest.load()
        assert manifest.generated_utc
        assert len(manifest.hashes) == 28

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FrozenArtifactMismatch):
            FrozenArtifactManifest.load(tmp_path / "nope.json")

    def test_hash_mismatch_raises_fail_closed(self, tmp_path: Path) -> None:
        # Snapshot one real artifact into tmp_path, bump its hash in the
        # manifest copy, point the manifest's repo_root at tmp_path and
        # verify_all() must raise.
        src_file = REPO / "results" / "cross_asset_kuramoto" / "demo" / "DEMO_BRIEF.md"
        rel = "results/cross_asset_kuramoto/demo/DEMO_BRIEF.md"
        dst_file = tmp_path / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src_file, dst_file)

        manifest = FrozenArtifactManifest(
            generated_utc="2026-01-01T00:00:00Z",
            regenerated_utc=None,
            hashes={rel: "0" * 64},
            repo_root=tmp_path,
        )
        with pytest.raises(FrozenArtifactMismatch) as exc:
            manifest.verify_all()
        assert "sha256 mismatch" in str(exc.value)

    def test_missing_file_reports_missing(self, tmp_path: Path) -> None:
        manifest = FrozenArtifactManifest(
            generated_utc="2026-01-01T00:00:00Z",
            regenerated_utc=None,
            hashes={"does/not/exist.txt": "0" * 64},
            repo_root=tmp_path,
        )
        with pytest.raises(FrozenArtifactMismatch) as exc:
            manifest.verify_all()
        assert "missing" in str(exc.value)


class TestKuramotoRobustnessContract:
    def test_from_frozen_artifacts_loads_real_bundle(self) -> None:
        c = KuramotoRobustnessContract.from_frozen_artifacts()
        assert len(c.equity_curve) > 1000
        assert len(c.fold_metrics) >= 2
        assert {"sharpe", "ann_vol"} <= set(c.risk_metrics.columns)
        assert c.parameter_lock["seed"] == 42

    def test_daily_returns_have_expected_length(self) -> None:
        c = KuramotoRobustnessContract.from_frozen_artifacts()
        r = c.daily_strategy_returns()
        assert len(r) == len(c.equity_curve) - 1

    def test_fold_metrics_contract_violation_is_caught(self, tmp_path: Path) -> None:
        # Build a manifest whose frozen fold_metrics.csv is missing the
        # 'sharpe' column — assert_frozen_consistency must refuse it.
        rel_equity = "results/cross_asset_kuramoto/demo/equity_curve.csv"
        rel_folds = "results/cross_asset_kuramoto/demo/fold_metrics.csv"
        rel_risk = "results/cross_asset_kuramoto/demo/risk_metrics.csv"
        rel_lock = "results/cross_asset_kuramoto/PARAMETER_LOCK.json"

        (tmp_path / "results" / "cross_asset_kuramoto" / "demo").mkdir(parents=True, exist_ok=True)
        (tmp_path / rel_equity).write_text(
            "date,strategy_cumret,benchmark_cumret,drawdown\n"
            "2020-01-01,1.0,1.0,-0.0\n2020-01-02,1.01,1.0,-0.0\n"
            "2020-01-03,1.02,1.0,-0.0\n"
        )
        (tmp_path / rel_folds).write_text(
            "fold_id,is_start,os_start,os_end,NOT_SHARPE,max_dd,pass_fail\n"
            "1,2020-01-01,2020-02-01,2020-03-01,1.0,-0.1,PASS\n"
            "2,2020-01-01,2020-03-01,2020-04-01,0.5,-0.1,PASS\n"
        )
        (tmp_path / rel_risk).write_text("sharpe,ann_return,ann_vol,max_dd\n1.0,0.1,0.1,-0.1\n")
        (tmp_path / rel_lock).write_text(json.dumps({"seed": 42}))
        manifest_path = tmp_path / "manifest.json"
        import hashlib

        hashes = {
            rel: hashlib.sha256((tmp_path / rel).read_bytes()).hexdigest()
            for rel in (rel_equity, rel_folds, rel_risk, rel_lock)
        }
        manifest_path.write_text(
            json.dumps(
                {"generated_utc": "x", "hashes": hashes},
                indent=2,
            )
        )
        with pytest.raises(FrozenArtifactMismatch) as exc:
            KuramotoRobustnessContract.from_frozen_artifacts(
                manifest_path=manifest_path,
                repo_root=tmp_path,
            )
        assert "fold_metrics" in str(exc.value)
