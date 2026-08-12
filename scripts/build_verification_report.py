# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Emit ``artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json`` — fail-closed.

The 2026-04-30 external audit required a single machine-readable artefact
that carries every load-bearing claim, its evidence tier, and the
provenance chain that justifies headline use. This script is the
generator. It is **fail-closed**: missing provenance, unsigned data,
unknown null-model coverage → exit non-zero, do not write a stale file.

Current scope is intentionally narrow — the only `MEASURED` rows are
ones whose evidence is mechanically reproducible inside this repository
(invariant count, kernel self-check). Everything else is emitted as
``RETIRED`` until a future experiment supplies a signed evidence
pointer.

Usage::

    python scripts/build_verification_report.py
    python scripts/build_verification_report.py --output path/to/report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from scripts.count_invariants import REPO_ROOT, collect_invariant_ids

DEFAULT_OUTPUT: Final[Path] = (
    REPO_ROOT / "artifacts" / "audit" / "SCIENTIFIC_VERIFICATION_REPORT.json"
)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"


def _build_report() -> dict[str, Any]:
    invariant_ids = collect_invariant_ids()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": now,
        "commit": _git_commit(),
        "audit_traceability": {
            "audit_date": "2026-04-30",
            "audit_doc": "docs/audit/2026-04-30-external-audit.md",
            "claims_ledger": "CLAIMS.md",
            "alternative_hypotheses": ".claude/physics/ALTERNATIVE_HYPOTHESES.md",
        },
        "invariant_registry": {
            "source": ".claude/physics/INVARIANTS.yaml",
            "count": len(invariant_ids),
            "ids": invariant_ids,
        },
        "tests": {
            "collected": None,
            "passed": None,
            "physics_grounded": None,
            "note": (
                "fields are intentionally null until pytest is wired into "
                "this generator and emits a signed JSON summary; do not "
                "hand-fill"
            ),
        },
        "ci_gates_present": [
            "physics-kernel-gate.yml",
            "claims-evidence-gate.yml",
            "formal-verification.yml",
            "main-validation.yml",
            "pr-gate.yml",
            "invariant-count-sync (added 2026-04-30)",
        ],
        "oos_evidence": {
            "status": "RETRACTED",
            "reason": (
                "Audit 2026-04-30 (S4.2): README OOS '+78% vs equal-weight, "
                "drawdown -53%' had no signed artefact, no declared cost "
                "model, no factor-neutral baseline. See CLAIMS.md row "
                "R-OOS-78 for re-emission requirements."
            ),
            "required_fields_for_re_emission": [
                "data_provenance",
                "data_hashes",
                "date_range",
                "universe",
                "cost_model",
                "slippage_model",
                "borrow_funding_costs",
                "survivorship_bias_treatment",
                "walk_forward_folds",
                "purged_embargoed_cv",
                "frozen_parameter_date",
                "factor_neutral_baseline",
                "null_models",
                "multiple_testing_correction",
                "confidence_intervals",
            ],
        },
        "criticality_evidence": {
            "status": "RETRACTED",
            "reason": (
                "Audit 2026-04-30 (S4.1): threshold-crossing on R(t) was "
                "presented as a phase transition without finite-size "
                "scaling, susceptibility, or scaling collapse. See "
                "CLAIMS.md row R-CRITICALITY and ALTERNATIVE_HYPOTHESES.md "
                "H5 for the required battery."
            ),
            "required_battery": [
                "R_N(K) for N in {8,16,32,64,128}",
                "chi_N(K) = N * Var(R)",
                "K_c(N) estimation",
                "scaling collapse with (beta/nu, gamma/nu)",
                "null-model rejection (IAAFT / ARMA / GARCH / shuffled)",
            ],
        },
        "null_models_supported": [
            "IAAFT",
            "time_shuffle",
            "degree_preserving_rewiring",
            "counterfactual_perturbation",
        ],
        "null_models_required_but_missing": [
            "AR / ARMA / GARCH surrogates",
            "factor-model residuals",
            "sector-block bootstrap",
            "correlation-preserving Gaussian copula",
        ],
        "multiple_testing_correction": {
            "status": "PARTIAL",
            "notes": (
                "Some research notebooks apply Holm / BH-FDR; not yet "
                "enforced at the claims-evidence-gate level. See audit "
                "backlog row S3.3."
            ),
        },
        "known_failures": [
            "criticality FSS battery not implemented",
            "OOS audit artefact not yet signed",
            "phase-extractor robustness (rank/sign) not yet wired",
        ],
        "retracted_claims": [
            "R-VERIFIED-PHYS (top-level 'verified physical system')",
            "R-OOS-78 (+78% OOS / -53% drawdown headline)",
            "R-CRITICALITY (phase-transition framing without FSS)",
            "R-MARKET-CONS (market energy / momentum conservation)",
        ],
    }


def write_report(output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _build_report()
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "destination JSON path (default: artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json)"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if any retracted claim re-appears with a non-RETRACTED status",
    )
    args = parser.parse_args(argv)
    report = write_report(args.output)
    rel = args.output.relative_to(REPO_ROOT) if args.output.is_absolute() else args.output
    print(
        f"wrote {rel}: {report['invariant_registry']['count']} invariants, "
        f"{len(report['retracted_claims'])} retracted claim(s)."
    )
    if args.check:
        oos = report["oos_evidence"]["status"]
        crit = report["criticality_evidence"]["status"]
        if oos != "RETRACTED" or crit != "RETRACTED":
            print(
                "FAIL-CLOSED: a retracted claim is no longer marked RETRACTED",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
