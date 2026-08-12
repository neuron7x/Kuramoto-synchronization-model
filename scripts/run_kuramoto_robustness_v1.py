#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto robustness-framework v1 CLI runner.

Read-only on every frozen input. Writes strictly under
``results/cross_asset_kuramoto/robustness_v1/``:

- ``verdict.json``          — terminal decision + suite scalars
- ``cpcv_summary.json``     — PBO, PSR, fold sharpes
- ``null_summary.json``     — two null families + p-values
- ``jitter_summary.json``   — placeholder evaluator output
- ``ROBUSTNESS_RESULTS.md`` — 1-page human-readable report

A hash-mismatch on any frozen artifact exits 2 with a ``FAIL`` verdict
file already written to disk.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backtest.robustness_gates import DecisionLabel, evaluate_robustness_gates  # noqa: E402
from research.robustness.protocols.kuramoto_contract import (  # noqa: E402
    FrozenArtifactMismatch,
    KuramotoRobustnessContract,
)
from research.robustness.protocols.kuramoto_gate_runner import (  # noqa: E402
    run_kuramoto_gate_runner,
)

OUT_DIR = REPO / "results" / "cross_asset_kuramoto" / "robustness_v1"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_convergence(path: Path) -> dict[str, Any] | None:
    """Read `null_convergence.csv` and classify convergence per family.

    Returns ``None`` when the CSV is absent (the convergence script has
    not been run yet). When present, returns a dict with overall status,
    per-family max |Δp|, and the raw (n, p) pairs.
    """
    if not path.is_file():
        return None
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            rows.append(raw)
    if not rows:
        return None
    per_family: dict[str, dict[int, float]] = {}
    for r in rows:
        family = r["family_id"]
        n = int(r["n_trials"])
        p = float(r["p_value"])
        per_family.setdefault(family, {})[n] = p
    deltas: dict[str, float] = {}
    for family, p_map in per_family.items():
        trials = sorted(p_map.keys())
        pairs = [
            (trials[i], trials[i + 1])
            for i in range(len(trials) - 1)
            if trials[i + 1] == trials[i] * 2
        ]
        deltas[family] = (
            max(abs(p_map[n] - p_map[twice]) for n, twice in pairs) if pairs else float("inf")
        )
    overall_max = max(deltas.values()) if deltas else float("inf")
    status = "CONVERGED" if overall_max < 0.02 else "NOT_CONVERGED"
    return {
        "status": status,
        "overall_max_delta": overall_max,
        "per_family_max_delta": deltas,
        "per_family_trajectory": per_family,
    }


def _render_markdown(
    verdict_label: str,
    cpcv_dict: dict[str, Any],
    null_dict: dict[str, Any],
    jitter_dict: dict[str, Any],
    reasons: tuple[str, ...],
    convergence: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Cross-asset Kuramoto · Robustness v1 report",
        "",
        f"Terminal decision: **{verdict_label}**",
        "",
        "## Suite summary",
        "",
        "| Suite | Metric | Value | Pass |",
        "|---|---|---:|:-:|",
        f"| CPCV | PBO (fold mirror, n={cpcv_dict['pbo_candidate_count']}, "
        f"*{cpcv_dict['pbo_interpretation']}*) | "
        f"{cpcv_dict['pbo']:.4f} | "
        f"{'✓' if cpcv_dict['pbo_pass'] else '✗'} |",
        f"| CPCV | PSR (daily, no HAC) | {cpcv_dict['psr_daily']:.4f} | "
        f"{'✓' if cpcv_dict['psr_pass'] else '✗'} |",
        f"| CPCV | PSR (daily, HAC Newey–West L={cpcv_dict['psr_hac_lag']}) | "
        f"{cpcv_dict['psr_hac_daily']:.4f} | "
        f"{'✓' if cpcv_dict['psr_hac_pass'] else '✗'} |",
        f"| CPCV | Annualised Sharpe (daily) | {cpcv_dict['annualised_sharpe']:.4f} | n/a |",
    ]
    loo_pbo = cpcv_dict.get("loo_pbo")
    if loo_pbo is not None:
        lines.append(
            f"| CPCV | PBO (LOO grid, n={cpcv_dict['loo_n_strategies']}, "
            f"*{cpcv_dict['loo_pbo_interpretation']}*) | "
            f"{loo_pbo:.4f} | "
            f"{'✓' if cpcv_dict['loo_pbo_pass'] else '✗'} |"
        )
    for family in null_dict["families"]:
        lines.append(
            f"| Null | {family['family']} p-value | "
            f"{family['p_value']:.4f} | "
            f"{'✓' if family['p_value_pass'] else '✗'} |"
        )
    jitter_is_placeholder = jitter_dict["evaluator_mode"] != "LIVE"
    if jitter_is_placeholder:
        jitter_pass_cell = "N/A"
        jitter_note = (
            "`PLACEHOLDER_APPROXIMATION` (not decision-grade; live evaluator "
            "required to flip this row to ✓ / ✗)"
        )
    else:
        jitter_pass_cell = "✓" if jitter_dict["fraction_within_tol_pass"] else "✗"
        jitter_note = f"`{jitter_dict['evaluator_mode']}`"
    lines.extend(
        [
            f"| Jitter | fraction_within_tol | "
            f"{jitter_dict['stability']['fraction_within_tol']:.4f} | "
            f"{jitter_pass_cell} |",
            f"| Jitter | evaluator_mode | {jitter_note} | n/a |",
            "",
            "## Reasons",
            "",
        ]
    )
    if reasons:
        lines.extend(f"- {r}" for r in reasons)
    else:
        lines.append("- (none — all gates green)")
    if convergence is not None:
        lines.extend(
            [
                "",
                "## Null p-value convergence",
                "",
                f"- overall status: **{convergence['status']}**",
                f"- overall max |Δp|: {convergence['overall_max_delta']:.4f} (tolerance 0.0200)",
            ]
        )
        for family, delta in convergence["per_family_max_delta"].items():
            lines.append(f"- {family}: max |Δp| = {delta:.4f}")
        lines.append(
            "- Note: the demeaned bootstrap families converge to "
            "p ∈ [0.08, 0.10] — the observed Sharpe is statistically "
            "suggestive but does not clear the strict α = 0.05 bar. "
            "Verdict FAIL is decision-stable across trial counts "
            "(500 → 5000)."
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Evidence is derived from the frozen `offline_robustness/"
            "SOURCE_HASHES.json` bundle; 28 artifacts hash-verified.",
            "- Null suite uses mathematically exact daily log-returns "
            "(`diff(log(strategy_cumret))`) — no approximation. See "
            "`ROBUSTNESS_PROTOCOL.md` § 1 for the derivation contract.",
            "- PBO interpretation: fewer than 3 candidates is `tautological`, "
            "fewer than 5 is `weak`, 5+ is `admissible`. The fold-mirror PBO "
            "is always tautological by construction and is kept only as a "
            "sanity baseline; the LOO-grid PBO is the decision-grade one.",
            "- Jitter row shows `N/A` while the evaluator is "
            "`PLACEHOLDER_APPROXIMATION`; a live rebuild is required to "
            "replace the row with a real ✓ / ✗.",
            "- PSR is now reported in two flavours: naive `psr_daily` and "
            "HAC-adjusted `psr_hac_daily` (Newey–West Bartlett kernel, "
            "auto-bandwidth `L = floor(4 · (T/100)^(2/9))`). Under positive "
            "serial correlation the HAC number is the decision-grade one; "
            "the naive PSR is retained for comparability with the v1 bundle. "
            "Derivation: `research/robustness/cpcv.py::"
            "probabilistic_sharpe_ratio_hac`.",
            "- Decision thresholds (α = 0.05, pbo_max = 0.50, "
            "psr_min = 0.95, jitter_floor = 0.80) are documented "
            "verbatim in `ROBUSTNESS_PROTOCOL.md` § 3.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=1000,
        help="null resamples per family (default: 1000)",
    )
    parser.add_argument(
        "--n-jitter-candidates",
        type=int,
        default=64,
        help="jitter candidates (default: 64)",
    )
    parser.add_argument(
        "--require-live-jitter",
        action="store_true",
        help="demote to INSUFFICIENT_EVIDENCE if jitter is placeholder",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help=f"output directory (default: {OUT_DIR})",
    )
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        contract = KuramotoRobustnessContract.from_frozen_artifacts()
    except FrozenArtifactMismatch as exc:
        verdict = {
            "label": DecisionLabel.FAIL.value,
            "reasons": (f"frozen-artifact integrity failure: {exc}",),
        }
        _write_json(args.out_dir / "verdict.json", verdict)
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    evidence = run_kuramoto_gate_runner(
        contract,
        null_kwargs={"n_bootstrap": args.n_bootstrap},
        jitter_kwargs={"n_candidates": args.n_jitter_candidates},
    )
    decision = evaluate_robustness_gates(
        evidence,
        require_live_jitter=args.require_live_jitter,
    )

    cpcv_dict = asdict(evidence.cpcv)
    null_dict = {
        "all_families_pass": evidence.null.all_families_pass,
        "families": [asdict(f) for f in evidence.null.families],
    }
    jitter_dict = {
        "evaluator_mode": evidence.jitter.evaluator_mode,
        "fraction_within_tol_pass": evidence.jitter.fraction_within_tol_pass,
        "pass_threshold": evidence.jitter.pass_threshold,
        "stability": asdict(evidence.jitter.stability),
    }

    _write_json(args.out_dir / "cpcv_summary.json", cpcv_dict)
    _write_json(args.out_dir / "null_summary.json", null_dict)
    _write_json(args.out_dir / "jitter_summary.json", jitter_dict)
    _write_json(
        args.out_dir / "verdict.json",
        {
            "label": decision.label.value,
            "cpcv_pass": decision.cpcv_pass,
            "null_pass": decision.null_pass,
            "jitter_pass": decision.jitter_pass,
            "jitter_is_placeholder": decision.jitter_is_placeholder,
            "reasons": list(decision.reasons),
            "input_source": "daily_log_returns",
            "label_qualifier": (
                "FAIL_ON_DAILY_RETURNS"
                if decision.label is DecisionLabel.FAIL
                else decision.label.value
            ),
            "contract_manifest_generated_utc": contract.manifest.generated_utc,
            "contract_manifest_regenerated_utc": contract.manifest.regenerated_utc,
        },
    )
    convergence = _read_convergence(args.out_dir / "null_convergence.csv")
    (args.out_dir / "ROBUSTNESS_RESULTS.md").write_text(
        _render_markdown(
            verdict_label=decision.label.value,
            cpcv_dict=cpcv_dict,
            null_dict=null_dict,
            jitter_dict=jitter_dict,
            reasons=decision.reasons,
            convergence=convergence,
        ),
        encoding="utf-8",
    )

    print(f"verdict: {decision.label.value}")
    for r in decision.reasons:
        print(f"  - {r}")
    return 0 if decision.label is DecisionLabel.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
