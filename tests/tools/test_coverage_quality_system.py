# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from tools.coverage import coverage_control_plane as ccp
from tools.coverage import coverage_quality_system as cqs


def _manifest(verdict: str) -> ccp.ControlPlaneManifest:
    return ccp.ControlPlaneManifest(
        schema_version="1.0",
        verdict=verdict,
        stages=[],
        artifacts=[],
    )


def test_quality_system_facade_hides_internal_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_control_plane(**kwargs: object) -> ccp.ControlPlaneManifest:
        captured.update(kwargs)
        return _manifest("PASS")

    written: dict[str, Path] = {}

    def fake_write_manifest(manifest: ccp.ControlPlaneManifest, path: Path) -> None:
        assert manifest.verdict == "PASS"
        written["path"] = path

    monkeypatch.setattr(cqs.ccp, "run_control_plane", fake_run_control_plane)
    monkeypatch.setattr(cqs.ccp, "write_manifest", fake_write_manifest)

    manifest = cqs.CoverageQualitySystem(
        cqs.QualitySystemConfig(root=tmp_path, stage="final", limit=3)
    ).run()

    assert manifest.verdict == "PASS"
    assert captured["root"] == tmp_path.resolve()
    assert captured["stage"] == "final"
    assert captured["limit"] == 3
    assert captured["coverage"] == Path("reports/coverage/coverage.xml")
    assert captured["out_dir"] == Path("reports/coverage/intelligence")
    assert captured["calibration_dir"] == Path("reports/coverage/calibration")
    assert captured["matrix_dir"] == Path("reports/coverage/matrix")
    assert written["path"] == tmp_path.resolve() / "reports/coverage/control_plane.json"


def test_quality_system_cli_keeps_operator_surface_small(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, cqs.QualitySystemConfig] = {}

    def fake_run_quality_system(
        config: cqs.QualitySystemConfig | None = None,
    ) -> ccp.ControlPlaneManifest:
        assert config is not None
        captured["config"] = config
        return _manifest("PASS")

    monkeypatch.setattr(cqs, "run_quality_system", fake_run_quality_system)

    exit_code = cqs.main(
        [
            "--root",
            str(tmp_path),
            "--stage",
            "short_term",
            "--limit",
            "2",
            "--skip-intelligence",
            "--manifest",
            "reports/coverage/custom_manifest.json",
        ]
    )

    config = captured["config"]
    assert exit_code == 0
    assert config.root == tmp_path
    assert config.stage == "short_term"
    assert config.limit == 2
    assert config.run_intelligence is False
    assert config.manifest == Path("reports/coverage/custom_manifest.json")
    assert config.intelligence_out == Path("reports/coverage/intelligence")


def test_quality_system_cli_returns_nonzero_on_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cqs,
        "run_quality_system",
        lambda config=None: _manifest("FAIL"),
    )

    assert cqs.main([]) == 1
