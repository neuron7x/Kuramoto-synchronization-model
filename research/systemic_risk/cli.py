# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Command-line entry point for the canonical-seven evaluation pipeline.

Closes audit task 19. Provides

    python -m research.systemic_risk.cli evaluate \\
        --claim-id CLAIM_XYZ \\
        --data synthetic \\
        --seed 42

which runs the full canonical-seven pipeline on a synthetic panel
(or, when a real-data ingest path is wired, on real data) and
prints a structured JSON report to stdout. The CLI is the
operational entry point for batch evaluation and CI integration;
the pure-function APIs remain the canonical research interface.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .data_firewall import run_data_firewall
from .minimal import (
    Claim,
    initial_claim,
    state_name,
)
from .minimal import (
    evaluate as minimal_evaluate,
)
from .synthetic import SyntheticPanelConfig, generate_panel

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.systemic_risk.cli",
        description="Canonical-Seven evaluation pipeline CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    evl = sub.add_parser("evaluate", help="Run one canonical-seven round.")
    evl.add_argument("--claim-id", required=True, help="Identifier of the claim under evaluation.")
    evl.add_argument(
        "--data",
        choices=["synthetic"],
        default="synthetic",
        help=(
            "Data source. 'synthetic' generates a panel via "
            "synthetic.generate_panel; real-data ingest is not yet "
            "wired (see LIMITATIONS.md §4)."
        ),
    )
    evl.add_argument("--seed", type=int, default=42, help="RNG seed for synthetic generator.")
    evl.add_argument("--n-banks", type=int, default=20, help="Number of banks (synthetic only).")
    evl.add_argument("--n-days", type=int, default=30, help="Number of daily snapshots.")
    evl.add_argument(
        "--prior-log-odds",
        type=float,
        default=-1.0,
        help="Prior log-odds for the claim (default −1.0).",
    )
    return parser


def _run_evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """Execute one canonical-seven round; return a structured dict."""
    if args.data == "synthetic":
        cfg = SyntheticPanelConfig(
            n_banks=args.n_banks,
            n_days=args.n_days,
            seed=args.seed,
        )
        panels, labels = generate_panel(cfg)
        firewall_report = run_data_firewall(panels, node_labels=labels, provenances={})
        firewall_passed = bool(firewall_report.passed_all)
    else:  # pragma: no cover — guarded by argparse choices
        raise ValueError(f"unsupported data source {args.data!r}")

    # Minimal canonical-seven round: only the firewall outcome is
    # populated since real leakage / ladder / replication evidence
    # requires data we do not yet have. The other channels remain
    # `None` per the contract.
    claim: Claim = initial_claim(args.claim_id, prior_log_odds=args.prior_log_odds)
    claim = minimal_evaluate(claim, firewall_passed_all=firewall_passed)

    return {
        "claim_id": claim.claim_id,
        "tier": claim.tier,
        "tier_name": state_name(claim.tier),
        "posterior_log_odds": claim.posterior_log_odds,
        "evidence_count": claim.evidence_count,
        "last_action": claim.last_action.name,
        "firewall_passed_all": firewall_passed,
        "firewall_gate_log": [
            {"gate": o.name, "passed": o.passed, "reason": o.reason}
            for o in firewall_report.gate_outcomes
        ],
        "data_source": args.data,
        "seed": args.seed,
        "n_banks": args.n_banks,
        "n_days": args.n_days,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the exit code: 0 on success, 1 on failure."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        report = _run_evaluate(args)
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
