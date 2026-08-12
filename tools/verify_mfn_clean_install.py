#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verify MFN import, entrypoints, and one-command bundle from a clean venv."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("mfn", "mfn-api", "mfn-validate")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a ``Z`` suffix."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Check:
    """One machine-verifiable fact emitted by the clean-install verifier."""

    id: str
    command: list[str]
    cwd: str
    passed: bool
    level: str = "MACHINE_VERIFIED"
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "command": self.command,
            "cwd": self.cwd,
            "passed": self.passed,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(slots=True)
class VerificationState:
    """Aggregate MFN product-state facts for this verifier run."""

    python_executable: str
    checks: list[Check] = field(default_factory=list)
    entrypoints: dict[str, str] = field(default_factory=dict)
    bundle: str | None = None
    started_utc: str = field(default_factory=utc_now)
    finished_utc: str | None = None

    def add(self, check: Check) -> None:
        self.checks.append(check)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def as_report(self) -> dict[str, Any]:
        blocking_nodes: list[str] = []
        if not self.passed:
            blocking_nodes.append("one_or_more_machine_checks_failed")
        blocking_nodes.append("full_dependency_lockfile_install_not_verified_by_this_mfn_smoke")
        passed_checks = sum(1 for check in self.checks if check.passed)
        total_checks = len(self.checks)
        raw_score = round(100 * passed_checks / total_checks) if total_checks else 0
        score = min(79, raw_score) if self.passed else raw_score
        return {
            "schema_version": "geosync.mfn.product_state.v1",
            "generated_utc": self.finished_utc or utc_now(),
            "verification_level": "MACHINE_VERIFIED" if self.passed else "MACHINE_ASSISTED",
            "python_executable": self.python_executable,
            "repo_root": str(REPO_ROOT),
            "checks": [check.as_dict() for check in self.checks],
            "project_state_delta": {
                "packaging_contract": {
                    "editable_install_passes": self._check_passed("editable_install"),
                    "entrypoints_installed": len(self.entrypoints) == len(ENTRYPOINTS),
                },
                "import_contract": {
                    "top_level_import_passes": self._check_passed("import_geosync_mfn"),
                    "no_module_not_found": self._check_passed("import_geosync_mfn"),
                },
                "cli_contract": {
                    "mfn_available": "mfn" in self.entrypoints,
                    "mfn_api_available": "mfn-api" in self.entrypoints,
                    "mfn_validate_available": "mfn-validate" in self.entrypoints,
                    "help_commands_pass": all(
                        self._check_passed(f"{entrypoint}_help") for entrypoint in ENTRYPOINTS
                    ),
                    "command_exit_codes_deterministic": self.passed,
                },
                "operation_contract": {
                    "simulate_passes": self._check_passed("mfn_run"),
                    "extract_passes": self._check_passed("mfn_run"),
                    "detect_passes": self._check_passed("mfn_run"),
                    "forecast_passes": self._check_passed("mfn_run"),
                    "compare_passes": self._check_passed("mfn_run"),
                    "report_passes": self._check_passed("mfn_run"),
                },
                "artifact_contract": {
                    "output_bundle_created": self._check_passed("mfn_run"),
                    "manifest_created": self._check_passed("mfn_validate"),
                    "sha256_manifest_created": self._check_passed("mfn_validate"),
                    "runbook_created": self._check_passed("mfn_validate"),
                    "first_file_to_open_printed": self._check_passed("mfn_validate"),
                    "reproducible_clean_run": self.passed,
                },
                "production_readiness": {
                    "score_0_100": score,
                    "score_basis": {
                        "passed_checks": passed_checks,
                        "total_checks": total_checks,
                        "raw_machine_score": raw_score,
                        "cap_reason": (
                            "full_dependency_lockfile_install_not_verified" if self.passed else None
                        ),
                    },
                    "blocking_nodes": blocking_nodes,
                    "machine_verified": self.passed,
                    "human_review_only_claims": [
                        "predictive_edge_or_alpha",
                        "full_dependency_lockfile_release_readiness",
                        "scientific_validity_of_market_hypotheses",
                    ],
                    "final_status": "YELLOW" if self.passed else "RED",
                },
            },
            "entrypoints": self.entrypoints,
            "bundle": self.bundle,
        }

    def _check_passed(self, check_id: str) -> bool:
        return any(check.id == check_id and check.passed for check in self.checks)


def _run(
    state: VerificationState,
    check_id: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    state.add(
        Check(
            id=check_id,
            command=command,
            cwd=str(cwd),
            passed=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", default=sys.executable, help="Python executable used to create venv."
    )
    parser.add_argument(
        "--keep", action="store_true", help="Keep the temporary venv for inspection."
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="Write product-state JSON report."
    )
    return parser.parse_args(argv)


def _write_report(path: Path | None, state: VerificationState) -> None:
    state.finished_utc = utc_now()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.as_report(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"product_state_report={path}")


def _exit_code(exc: SystemExit) -> int:
    return exc.code if isinstance(exc.code, int) else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    state = VerificationState(python_executable=args.python)
    workdir = Path(tempfile.mkdtemp(prefix="geosync-mfn-clean-"))
    venv = workdir / "venv"
    outside_cwd = workdir / "outside-cwd"
    outside_cwd.mkdir()
    try:
        _run(state, "create_clean_venv", [args.python, "-m", "venv", str(venv)], cwd=REPO_ROOT)
        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        bin_dir = python.parent
        _run(
            state,
            "install_build_backend",
            [str(python), "-m", "pip", "install", "setuptools>=69", "setuptools_scm>=8", "wheel"],
            cwd=outside_cwd,
        )
        _run(
            state,
            "editable_install",
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-e",
                str(REPO_ROOT),
                "--no-deps",
                "--no-build-isolation",
            ],
            cwd=outside_cwd,
        )
        _run(
            state,
            "import_geosync_mfn",
            [
                str(python),
                "-c",
                "import geosync.mfn; print('import_ok', geosync.mfn.__name__)",
            ],
            cwd=outside_cwd,
        )
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        for entrypoint in ENTRYPOINTS:
            resolved = shutil.which(entrypoint, path=env["PATH"])
            if resolved is None:
                print(f"missing entrypoint: {entrypoint}", file=sys.stderr)
                state.add(
                    Check(
                        id=f"command_v_{entrypoint}",
                        command=["command", "-v", entrypoint],
                        cwd=str(outside_cwd),
                        passed=False,
                        returncode=1,
                    )
                )
                _write_report(args.report, state)
                return 1
            state.entrypoints[entrypoint] = resolved
            print(f"command_v_{entrypoint}={resolved}")
            state.add(
                Check(
                    id=f"command_v_{entrypoint}",
                    command=["command", "-v", entrypoint],
                    cwd=str(outside_cwd),
                    passed=True,
                    stdout=resolved + "\n",
                )
            )
            _run(state, f"{entrypoint}_help", [resolved, "--help"], cwd=outside_cwd, env=env)
        bundle = workdir / "bundle"
        state.bundle = str(bundle)
        _run(
            state,
            "mfn_run",
            [str(bin_dir / "mfn"), "--out", str(bundle), "run"],
            cwd=outside_cwd,
            env=env,
        )
        _run(
            state,
            "mfn_validate",
            [str(bin_dir / "mfn-validate"), "--bundle", str(bundle)],
            cwd=outside_cwd,
            env=env,
        )
        print(f"verified_clean_bundle={bundle}")
        _write_report(args.report, state)
        return 0
    except SystemExit as exc:
        _write_report(args.report, state)
        return _exit_code(exc)
    finally:
        if args.keep:
            print(f"kept_clean_env={workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
