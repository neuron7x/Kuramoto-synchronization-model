#!/usr/bin/env python3
"""One-command L2-edge reproduction.

Runs the canonical 9-axis analysis cycle end-to-end on the configured L2
substrate, then renders the three demo figures. Emits a manifest
(results/L2_FULL_CYCLE_MANIFEST.json) with per-artifact SHA-256 replay
hashes so divergence from a reference run is detectable bit-precisely.

Axes (in dependency order):
    1. kill test            → L2_KILLTEST_VERDICT.json
    2. attribution          → L2_IC_ATTRIBUTION.json
    3. purged K-fold        → L2_PURGED_CV.json
    4. spectral             → L2_SPECTRAL.json
    5. Hurst DFA            → L2_HURST.json
    6. regime Markov        → L2_REGIME_MARKOV.json
    7. robustness (R1-R4)   → L2_ROBUSTNESS.json
    8. transfer entropy     → L2_TRANSFER_ENTROPY.json
    9. conditional TE       → L2_CONDITIONAL_TE.json

Plus the pre-existing diurnal + cost-sweep artifacts are required as
inputs for figures; they are NOT regenerated here (bit-frozen gate
fixtures). Exit 0 on full cycle, 2 on data error, 3 on a sub-script
non-zero exit, 4 on missing gate fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from research.microstructure.visualize import render_all

_log = logging.getLogger("l2_full_cycle")


@dataclass(frozen=True)
class Stage:
    name: str
    cli: str
    extra_args: tuple[str, ...]
    artifact: str


STAGES: Final[tuple[Stage, ...]] = (
    Stage("killtest", "scripts/run_l2_killtest.py", (), "results/L2_KILLTEST_VERDICT.json"),
    Stage("attribution", "scripts/run_l2_attribution.py", (), "results/L2_IC_ATTRIBUTION.json"),
    Stage("purged_cv", "scripts/run_l2_purged_cv.py", (), "results/L2_PURGED_CV.json"),
    Stage("spectral", "scripts/run_l2_spectral.py", (), "results/L2_SPECTRAL.json"),
    Stage("hurst", "scripts/run_l2_hurst.py", (), "results/L2_HURST.json"),
    Stage(
        "regime_markov",
        "scripts/run_l2_regime_markov.py",
        ("--diurnal-filter", "results/L2_DIURNAL_PROFILE.json"),
        "results/L2_REGIME_MARKOV.json",
    ),
    Stage("robustness", "scripts/run_l2_robustness.py", (), "results/L2_ROBUSTNESS.json"),
    Stage(
        "transfer_entropy",
        "scripts/run_l2_transfer_entropy.py",
        ("--n-surrogates", "100"),
        "results/L2_TRANSFER_ENTROPY.json",
    ),
    Stage(
        "conditional_te",
        "scripts/run_l2_conditional_te.py",
        ("--n-surrogates", "80", "--conditioner", "BTCUSDT"),
        "results/L2_CONDITIONAL_TE.json",
    ),
)

REQUIRED_INPUTS: Final[tuple[str, ...]] = (
    "results/L2_DIURNAL_PROFILE.json",
    "results/L2_EXEC_COST_SWEEP.json",
    "results/gate_fixtures/breakeven_q75.json",
    "results/gate_fixtures/breakeven_q75_diurnal.json",
    "results/gate_fixtures/ic_test_q75.json",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_stage(stage: Stage, data_dir: Path, repo_root: Path) -> tuple[float, int]:
    cmd = [
        sys.executable,
        stage.cli,
        "--data-dir",
        str(data_dir),
        *stage.extra_args,
    ]
    env = {"PYTHONPATH": str(repo_root)}
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        env={**env, "PATH": ""},
    )
    dt = time.time() - t0
    if proc.returncode != 0:
        _log.error("%s failed (exit %d):\n%s", stage.name, proc.returncode, proc.stderr[-2000:])
    return dt, proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/binance_l2_perp"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--skip-stages", default="", help="comma-separated stage names to skip")
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("results/L2_FULL_CYCLE_MANIFEST.json"),
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    repo_root = Path.cwd()
    data_dir = Path(args.data_dir)
    results_dir = Path(args.results_dir)
    if not data_dir.exists():
        _log.error("data dir does not exist: %s", data_dir)
        return 2

    for req in REQUIRED_INPUTS:
        if not (repo_root / req).exists():
            _log.error("required input missing: %s", req)
            return 4

    skip = {s.strip() for s in str(args.skip_stages).split(",") if s.strip()}
    stages_report: list[dict[str, Any]] = []
    overall_start = time.time()

    for stage in STAGES:
        if stage.name in skip:
            _log.info("[skip] %s", stage.name)
            continue
        _log.info("[run ] %s", stage.name)
        dt, rc = _run_stage(stage, data_dir, repo_root)
        if rc != 0:
            _log.error("stage %s exited %d — aborting", stage.name, rc)
            return 3
        artifact_path = repo_root / stage.artifact
        if not artifact_path.exists():
            _log.error("stage %s did not produce %s", stage.name, stage.artifact)
            return 3
        stages_report.append(
            {
                "name": stage.name,
                "artifact": stage.artifact,
                "sha256": _sha256_file(artifact_path),
                "duration_sec": round(dt, 3),
                "size_bytes": artifact_path.stat().st_size,
            }
        )
        _log.info("[ok  ] %s in %.1fs", stage.name, dt)

    figures: dict[str, str] = {}
    if not args.skip_figures:
        _log.info("[run ] figures")
        fig_paths = render_all(results_dir, results_dir / "figures")
        for label, path in (
            ("cover", fig_paths.cover),
            ("signal_validation", fig_paths.signal_validation),
            ("dynamics", fig_paths.dynamics),
            ("coupling", fig_paths.coupling),
            ("stability", fig_paths.stability),
        ):
            figures[label] = _sha256_file(path)

    inputs_report = {path: _sha256_file(repo_root / path) for path in REQUIRED_INPUTS}
    manifest = {
        "schema_version": 1,
        "cycle_duration_sec": round(time.time() - overall_start, 3),
        "data_dir": str(data_dir),
        "stages": stages_report,
        "required_inputs": inputs_report,
        "figures": figures,
    }
    Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _log.info("manifest → %s", args.manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
