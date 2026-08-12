#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operator-facing facade for the coverage quality system.

The facade hides the internal authority, calibration, and matrix modules behind one
stable entrypoint. Operators configure stage, limit, and evidence reuse; internal
artifact paths remain implementation details.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from tools.coverage import coverage_control_plane as ccp

QualityStage = Literal["short_term", "mid_term", "final"]


@dataclass(frozen=True)
class QualitySystemConfig:
    root: Path = Path(".")
    stage: QualityStage = "mid_term"
    limit: int = 8
    run_intelligence: bool = True
    coverage: Path = Path("reports/coverage/coverage.xml")
    junit: Path = Path("reports/coverage/junit.xml")
    targets: Path = Path("configs/quality/coverage_targets.toml")
    critical: Path = Path("configs/quality/critical_surface.toml")
    claims: Path = Path("docs/CLAIMS.yaml")
    intelligence_out: Path = Path("reports/coverage/intelligence")
    calibration_out: Path = Path("reports/coverage/calibration")
    matrix_out: Path = Path("reports/coverage/matrix")
    manifest: Path = Path("reports/coverage/control_plane.json")


class CoverageQualitySystem:
    """Encapsulated quality-system runner."""

    def __init__(self, config: QualitySystemConfig | None = None) -> None:
        self._config = config or QualitySystemConfig()

    @property
    def config(self) -> QualitySystemConfig:
        return self._config

    def run(self) -> ccp.ControlPlaneManifest:
        cfg = self._config
        root = cfg.root.resolve()
        manifest = ccp.run_control_plane(
            root=root,
            coverage=cfg.coverage,
            junit=cfg.junit,
            targets=cfg.targets,
            critical=cfg.critical,
            claims=cfg.claims,
            out_dir=cfg.intelligence_out,
            calibration_dir=cfg.calibration_out,
            matrix_dir=cfg.matrix_out,
            stage=cfg.stage,
            limit=cfg.limit,
            run_intelligence=cfg.run_intelligence,
        )
        ccp.write_manifest(manifest, root / cfg.manifest)
        return manifest


def run_quality_system(
    config: QualitySystemConfig | None = None,
) -> ccp.ControlPlaneManifest:
    return CoverageQualitySystem(config).run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--stage",
        choices=("short_term", "mid_term", "final"),
        default="mid_term",
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-intelligence", action="store_true")
    parser.add_argument("--manifest", default="reports/coverage/control_plane.json")
    args = parser.parse_args(argv)

    manifest = run_quality_system(
        QualitySystemConfig(
            root=Path(args.root),
            stage=cast(QualityStage, args.stage),
            limit=args.limit,
            run_intelligence=not args.skip_intelligence,
            manifest=Path(args.manifest),
        )
    )
    print(f"coverage quality system: {manifest.verdict}")
    return 0 if manifest.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
