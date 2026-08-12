# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over the FLAGSHIP-RQ-001 selection-bias report (RES-007).

The flagship claim is only credible if the multiplicity / researcher-degrees-of-
freedom of its baseline programme are controlled: the FINAL inference must use the
PRE-SPECIFIED primary comparison, the number of tried variants must be recorded,
and a "best-of-N" pick must never be paraded as the primary without a stated
multiple-testing correction. This gate refuses to let ``selection_bias_report.json``
drift into any of those failure modes. It verifies:

1. PRIMARY == PREREG PRIMARY -- the report's declared primary comparison is
   ``FLAGSHIP`` (the flagship tier in ``hierarchy.yaml``) contrasted against the
   preregistered null baseline (the tier whose ``rq_role`` marks it the *primary
   null*, i.e. ``EXISTING_SUITE``). A mismatch means a post-hoc comparison is being
   passed off as the preregistered one -> RED.
2. SELECTION COUNT RECORDED -- ``selection_count`` is present, a non-negative int,
   and equals the number of listed comparisons. An unrecorded count hides how many
   comparisons were made -> RED.
3. CORRECTION APPLIED / NO UNCORRECTED BEST-OF-N -- a recognised family-wise / FDR
   correction (Bonferroni / Holm / Benjamini-Hochberg) with adjusted thresholds is
   present, and the primary is flagged ``pre_specified`` (not a post-hoc ``argmax``
   / ``best-of-N`` pick). A best-of-N primary WITHOUT a correction -> RED.
4. NO MANUFACTURED SIGNIFICANCE -- the report's ``final_verdict`` matches the
   RES-008 comparison report's verdict, so a corrected conclusion cannot be
   inflated past ``INSUFFICIENT_EVIDENCE``.

Exit codes::

    0  -- primary is the prereg primary, selection_count recorded, correction
          applied, no manufactured significance
    1  -- a selection-bias violation (wrong primary / unrecorded count /
          uncorrected best-of-N / inflated verdict)
    2  -- a required file is absent or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "artifacts" / "research" / "selection_bias_report.json"
HIERARCHY_YAML = ROOT / "benchmarks" / "flagship_baselines" / "hierarchy.yaml"
COMPARISON_REPORT = ROOT / "benchmarks" / "flagship_baselines" / "comparison_report.json"

VALID_CORRECTIONS = frozenset(
    {
        "bonferroni",
        "holm",
        "holm-bonferroni",
        "holm_bonferroni",
        "benjamini-hochberg",
        "benjamini_hochberg",
        "bh",
        "bh-fdr",
        "fdr-bh",
    }
)

# Tokens that betray a post-hoc "best-of-N" selection dressed up as the primary.
_BEST_OF_N_TOKENS = ("best", "argmax", "post_hoc", "post-hoc", "max_over", "cherry", "top_")


class GateError(Exception):
    """Malformed / missing input -- maps to exit code 2 (fail-closed)."""


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"malformed JSON in {path}: {exc}") from exc


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise GateError(f"malformed YAML in {path}: {exc}") from exc


def _prereg_primary_from_hierarchy(hierarchy: dict[str, Any]) -> tuple[str, str]:
    """Derive (intervention_tier, primary_null_tier) from the baseline hierarchy.

    intervention = the flagship tier. primary_null = the baseline tier whose
    ``rq_role`` marks it the *primary null* reference. Both are read from the
    committed contract, so the expected primary is NOT hard-coded in this gate.
    """
    flagship = hierarchy.get("flagship")
    if not isinstance(flagship, dict) or not flagship.get("tier"):
        raise GateError("hierarchy.yaml: missing flagship.tier")
    intervention = str(flagship["tier"])

    primary_null: str | None = None
    for entry in hierarchy.get("baselines", []):
        if not isinstance(entry, dict):
            continue
        if "primary null" in str(entry.get("rq_role", "")).lower():
            primary_null = str(entry.get("tier"))
            break
    if primary_null is None:
        raise GateError("hierarchy.yaml: no baseline tier flagged as the primary null")
    return intervention, primary_null


def evaluate() -> dict[str, Any]:
    """Return a machine-readable verdict for the selection-bias report.

    Raises GateError (exit 2) on missing/malformed files.
    """
    report = _load_json(REPORT_PATH)
    if not isinstance(report, dict):
        raise GateError("selection_bias_report.json must parse to a mapping")
    hierarchy = _load_yaml(HIERARCHY_YAML)
    if not isinstance(hierarchy, dict):
        raise GateError("hierarchy.yaml must parse to a mapping")
    comparison = _load_json(COMPARISON_REPORT)
    if not isinstance(comparison, dict):
        raise GateError("comparison_report.json must parse to a mapping")

    exp_intervention, exp_primary_null = _prereg_primary_from_hierarchy(hierarchy)
    problems: list[str] = []

    # --- (1) declared primary == preregistered primary ----------------------- #
    primary = report.get("primary")
    if not isinstance(primary, dict):
        problems.append("primary: missing or not a mapping")
        primary = {}
    got_intervention = str(primary.get("intervention", ""))
    got_null = str(primary.get("null_baseline", ""))
    if got_intervention != exp_intervention or got_null != exp_primary_null:
        problems.append(
            f"primary comparison '{got_intervention} vs {got_null}' does NOT match the "
            f"preregistered primary '{exp_intervention} vs {exp_primary_null}' "
            "(derived from hierarchy.yaml flagship + primary-null tiers)"
        )

    # --- (2) selection_count recorded and consistent ------------------------- #
    comparisons = report.get("comparisons")
    n_listed = len(comparisons) if isinstance(comparisons, list) else None
    sel = report.get("selection_count")
    if not isinstance(sel, int) or isinstance(sel, bool) or sel < 0:
        problems.append("selection_count is unrecorded / not a non-negative integer")
    elif n_listed is not None and sel != n_listed:
        problems.append(
            f"selection_count ({sel}) != number of listed comparisons ({n_listed})"
        )

    # --- (3) correction applied; no uncorrected best-of-N primary ------------ #
    correction = report.get("correction")
    method = str(correction.get("method", "")).strip().lower() if isinstance(correction, dict) else ""
    has_valid_correction = (
        isinstance(correction, dict)
        and method in VALID_CORRECTIONS
        and correction.get("family_wise_alpha") is not None
        and bool(correction.get("rejected_after_correction") is not None)
    )
    if not has_valid_correction:
        problems.append(
            "correction: missing or invalid multiple-testing correction "
            f"(method '{method or '<none>'}' not in {sorted(VALID_CORRECTIONS)}, "
            "or adjusted thresholds / rejections absent)"
        )

    basis = str(primary.get("selection_basis", "")).lower()
    pre_specified = bool(primary.get("pre_specified"))
    looks_best_of_n = (not pre_specified) or any(tok in basis for tok in _BEST_OF_N_TOKENS)
    if looks_best_of_n and not has_valid_correction:
        problems.append(
            "a best-of-N / post-hoc primary is presented WITHOUT a valid "
            f"multiple-testing correction (pre_specified={pre_specified}, "
            f"selection_basis='{basis}')"
        )
    if not pre_specified:
        problems.append(
            "primary.pre_specified is not true -- the final inference must use the "
            "PRE-SPECIFIED primary, never a post-hoc pick"
        )

    # --- (4) no manufactured significance ------------------------------------ #
    report_verdict = report.get("final_verdict")
    res008_verdict = comparison.get("verdict")
    if report_verdict != res008_verdict:
        problems.append(
            f"final_verdict '{report_verdict}' does NOT match the RES-008 comparison "
            f"verdict '{res008_verdict}' -- corrected conclusion must not inflate the verdict"
        )

    return {
        "expected_primary": f"{exp_intervention} vs {exp_primary_null}",
        "declared_primary": f"{got_intervention} vs {got_null}",
        "selection_count": sel,
        "listed_comparisons": n_listed,
        "correction_method": method or None,
        "final_verdict": report_verdict,
        "res008_verdict": res008_verdict,
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable verdict")
    args = parser.parse_args(argv)

    try:
        verdict = evaluate()
    except GateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"SELECTION-BIAS GATE: MALFORMED -- {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["ok"]:
        print(
            "SELECTION-BIAS GATE: PASS -- primary "
            f"'{verdict['declared_primary']}' is the preregistered primary, "
            f"selection_count={verdict['selection_count']} recorded, "
            f"correction '{verdict['correction_method']}' applied, "
            f"verdict '{verdict['final_verdict']}' not inflated."
        )
    else:
        print("SELECTION-BIAS GATE: FAIL", file=sys.stderr)
        for problem in verdict["problems"]:
            print(f"  - {problem}", file=sys.stderr)

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
