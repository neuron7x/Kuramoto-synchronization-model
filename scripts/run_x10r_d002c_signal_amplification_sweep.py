#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Signal Amplification Sweep launch driver.

This script is the operator-facing entry point for the full
D-002C sweep. It does NOT itself run on CI (the sweep is ~16h
of compute); it is invoked manually by the operator after
the C2.1–C2.4D chain has merged and the four preflight
capsules have been generated.

Pipeline:

  1. Load + lock the pre-registration YAML.
  2. Build the sweep_config from the locked preregistration.
  3. Build :class:`PreflightCapsulePaths` from the
     ``--preflight-dir`` argument.
  4. Call :func:`run_sweep` with ``require_preflight=True``.
     This refuses to launch if any preflight capsule is
     missing / corrupt / FAIL.
  5. Derive the verdict via :func:`derive_verdict`.
  6. Write the verdict capsule (atomic JSON) alongside the
     checkpoint.
  7. Print a short human-readable summary; return 0 on tier
     PASS, 1 on tier FAIL, 2 on infrastructure refusal.

CLI usage::

    python -m scripts.run_x10r_d002c_signal_amplification_sweep \\
        --preregistration docs/governance/D002C_PREREGISTRATION.yaml \\
        --preflight-dir tmp/d002c_preflight \\
        --checkpoint tmp/d002c_sweep_checkpoint.json \\
        --output-dir tmp/d002c_sweep_output

The script is deliberately verbose in error reporting: every
refusal carries the full list of reasons so a single re-launch
fixes all disagreements.

Strict scope
============
Launch infrastructure ONLY. NO claim promotion. NO threshold
tuning. NO retry-on-failure (every failure is recorded and
returned for operator review).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from research.systemic_risk.d002c_preflight import (
    PreflightCapsulePaths,
    PreflightLaunchRefused,
)
from research.systemic_risk.d002c_preregistration import (
    PreregistrationCorrupt,
    PreregistrationMismatch,
    load_and_lock,
)
from research.systemic_risk.d002c_sweep_runner import (
    SweepResult,
    run_sweep,
)
from research.systemic_risk.d002c_verdict import (
    TIER_FAIL,
    TIER_PASS,
    VerdictResult,
    derive_verdict,
)

logger = logging.getLogger("d002c.launch")

EXIT_PASS: int = 0
EXIT_FAIL: int = 1
EXIT_REFUSED: int = 2


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace — mirrors D-002D's atomicity contract."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _build_sweep_config(preregistration: Any) -> dict[str, Any]:
    """Mirror :class:`D002CPreregistration` into a sweep_config dict."""
    return {
        "ci_method": preregistration.ci_method.value,
        "ci_alpha": preregistration.ci_alpha,
        "signal_ci_ratio_threshold": preregistration.signal_ci_ratio_threshold,
        "direction_consistency_min_seeds": (preregistration.direction_consistency_min_seeds),
        "direction_stability_min_fraction": (preregistration.direction_stability_min_fraction),
        "multiple_testing_correction": (preregistration.multiple_testing_correction.value),
        "n_seeds": preregistration.n_seeds,
        "n_bootstrap": preregistration.n_bootstrap,
        "N_grid": list(preregistration.N_grid),
        "lambda_grid": list(preregistration.lambda_grid),
        "substrate_ids": list(preregistration.substrate_ids),
        "metric_ids": list(preregistration.metric_ids),
        "variance_reduction": list(preregistration.variance_reduction),
        "substrate_seed": preregistration.substrate_seed,
        "preregistration_sha": preregistration.preregistration_sha,
    }


def _resolve_preflight_paths(preflight_dir: Path) -> PreflightCapsulePaths:
    """Resolve the four canonical capsule filenames inside the dir.

    By convention:
      <preflight-dir>/pos_control.json
      <preflight-dir>/neg_control.json
      <preflight-dir>/null_audit.json
      <preflight-dir>/smoke_test.json
    """
    return PreflightCapsulePaths(
        pos_control=preflight_dir / "pos_control.json",
        neg_control=preflight_dir / "neg_control.json",
        null_audit=preflight_dir / "null_audit.json",
        smoke_test=preflight_dir / "smoke_test.json",
    )


def _verdict_to_dict(v: VerdictResult) -> dict[str, Any]:
    return {
        "tier": v.tier,
        "selected_cell_key": v.selected_cell_key,
        "marginal_pass": v.marginal_pass,
        "single_path_pass": v.single_path_pass,
        "n_cells_evaluated": v.n_cells_evaluated,
        "n_passing_cells": v.n_passing_cells,
        "preregistration_sha": v.preregistration_sha,
        "sweep_sha": v.sweep_sha,
        "sha256": v.sha256,
        "generated_at": v.generated_at,
        "notes": list(v.notes),
        "rule_evaluations": [
            {
                "rule_id": e.rule_id,
                "cell_key": e.cell_key,
                "measured_value": e.measured_value,
                "threshold": e.threshold,
                "passed": e.passed,
                "marginal": e.marginal,
            }
            for e in v.rule_evaluations
        ],
    }


def _print_summary(verdict: VerdictResult, sweep: SweepResult, wall: float) -> None:
    """Compact stdout summary for the operator."""
    print("=" * 72)
    print(f"D-002C verdict: {verdict.tier}")
    print("=" * 72)
    print(f"  cells evaluated   : {verdict.n_cells_evaluated}")
    print(f"  cells passing     : {verdict.n_passing_cells}")
    print(f"  selected cell     : {verdict.selected_cell_key or '—'}")
    print(f"  marginal_pass     : {verdict.marginal_pass}")
    print(f"  single_path_pass  : {verdict.single_path_pass}")
    print(f"  preregistration   : {verdict.preregistration_sha[:16]}…")
    print(f"  sweep sha         : {verdict.sweep_sha[:16]}…")
    print(f"  verdict sha       : {verdict.sha256[:16]}…")
    print(f"  wallclock total   : {wall:.1f}s")
    print(f"  sweep wallclock   : {sweep.wallclock_seconds:.1f}s")
    if verdict.notes:
        print("  notes:")
        for n in verdict.notes:
            print(f"    - {n}")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the D-002C Signal Amplification Sweep.")
    parser.add_argument(
        "--preregistration",
        type=Path,
        required=True,
        help="Path to the pre-registration YAML.",
    )
    parser.add_argument(
        "--preflight-dir",
        type=Path,
        required=True,
        help="Directory containing pos_control.json + neg_control.json + "
        "null_audit.json + smoke_test.json (output of "
        "scripts/d002c_emit_preflight_capsules.py).",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to the sweep checkpoint JSON (created on first run, consumed on resume).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the verdict + run report are written.",
    )
    parser.add_argument(
        "--null-audit-failed",
        action="store_true",
        help="External flag — set if the null audit reported FAIL on any "
        "audited cell. Forces tier=FAIL regardless of R1/R2/R3.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable summary on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    t0 = time.monotonic()

    try:
        prereg = load_and_lock(args.preregistration)
    except PreregistrationCorrupt as exc:
        logger.error("pre-registration corrupt: %s", exc)
        return EXIT_REFUSED

    sweep_config = _build_sweep_config(prereg)
    capsules = _resolve_preflight_paths(args.preflight_dir)

    try:
        sweep = run_sweep(
            preregistration=prereg,
            sweep_config=sweep_config,
            checkpoint_path=args.checkpoint,
            preflight_capsules=capsules,
            require_preflight=True,
            progress_callback=(
                None
                if args.quiet
                else lambda done, total: logger.info("progress: %d/%d cells", done, total)
            ),
        )
    except (PreflightLaunchRefused, PreregistrationMismatch) as exc:
        logger.error("launch refused: %s", exc)
        return EXIT_REFUSED

    verdict = derive_verdict(sweep, prereg, null_audit_failed=args.null_audit_failed)
    wall = time.monotonic() - t0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(args.output_dir / "d002c_verdict.json", _verdict_to_dict(verdict))

    if not args.quiet:
        _print_summary(verdict, sweep, wall)

    if verdict.tier == TIER_PASS:
        return EXIT_PASS
    if verdict.tier == TIER_FAIL:
        return EXIT_FAIL
    return EXIT_REFUSED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
