# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automatic falsifier-candidate forge.

Lie blocked:
    "falsifier exists only because human remembered it"

Reads structured rules from claim ledger, evidence matrix, and
translation matrix; emits candidate mutation plans that, if applied,
would re-introduce a named lie. The forge does NOT apply mutations.
It produces a plan: {target_path, mutation_kind, target_token, lie}.

Falsifier categories generated:
    IGNORE_DEPENDENCY_TRUTH    drop the dependency_truth gate in P4
    INVERT_SELECTION_BIAS      flip the bias-precedence in P2
    REMOVE_DRIFT_BOUND         drop the drift-bound check in P3
    TREAT_CORRELATION_AS_BIND  bypass perturbation in P6
    SKIP_SHUFFLED_NULL         drop the shuffled-null gate in P5/P7
    MARK_STALE_EVIDENCE_VALID  bypass decay class in evidence_decay
    SKIP_PER_WINDOW_CHECK      collapse per-window growth fits in P8
    SKIP_REQUIRED_INTERSECTION bypass required-constraints in P10
    DROP_EQUIVALENCE_TOLERANCE bypass equivalence in P9

The plan is structured + deterministic; deduplication is on
(target_path, mutation_kind). The forge proposes; humans dispose.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSLATION = REPO_ROOT / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
DEFAULT_OUTPUT = Path("/tmp/geosync_falsifier_forge.json")


@dataclass(frozen=True)
class FalsifierCandidate:
    """One proposed mutation plan."""

    candidate_id: str
    pattern_id: str
    mutation_kind: str
    target_path: str
    target_token: str
    lie_re_introduced: str
    expected_failing_tests: tuple[str, ...]


@dataclass
class ForgeReport:
    candidates: list[FalsifierCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": len(self.candidates),
            "candidates": [asdict(c) for c in sorted(self.candidates, key=_sort_key)],
        }


def _sort_key(c: FalsifierCandidate) -> tuple[str, str, str]:
    return (c.pattern_id, c.mutation_kind, c.candidate_id)


# Pattern → (mutation_kind, lie, target_token, expected_test_substring)
# Token strings here are recognisable substrings of the implementation
# that the human falsifier process targets. The forge encodes the rule;
# it does not apply it.
_PATTERN_RULES: Mapping[str, tuple[str, str, str, tuple[str, ...]]] = {
    "P1_POPULATION_EVENT_CATALOG": (
        "INVERT_DUPLICATE_REJECTION",
        "cataloged event = prediction",
        "if event.event_id in self._events:",
        ("test_duplicate_event_is_rejected_and_state_unchanged",),
    ),
    "P2_STRUCTURED_ABSENCE_INFERENCE": (
        "INVERT_SELECTION_BIAS",
        "missing data = true absence",
        "if bias_present:",
        (
            "test_active_selection_bias_returns_selection_bias",
            "test_selection_bias_takes_precedence_over_low_coverage",
        ),
    ),
    "P3_DYNAMIC_NULL_MODEL": (
        "REMOVE_DRIFT_BOUND",
        "baseline fixed forever / drift hides anomaly",
        "if drift_used > bound:",
        ("test_drift_above_bound_returns_null_drift_exceeded",),
    ),
    "P4_GLOBAL_PARITY_WITNESS": (
        "IGNORE_DEPENDENCY_TRUTH",
        "local pass = global pass",
        "_SURFACE_DEPENDENCY_TRUTH in required and not input_.dependency_truth_ok",
        ("test_dependency_truth_failure",),
    ),
    "P5_MOTIONAL_CORRELATION_WITNESS": (
        "SKIP_SHUFFLED_NULL",
        "static correlation = dynamic relation",
        "if not np.isfinite(null_p95) or abs(traj) <= null_p95 + float(input_.margin):",
        ("test_shuffled_trajectory_does_not_classify_as_dynamic",),
    ),
    "P6_COMPOSITE_BINDING_STRUCTURE": (
        "TREAT_CORRELATION_AS_BIND",
        "correlation = binding",
        "if perturb_median < threshold:",
        ("test_transient_correlation_that_dissolves_under_perturbation",),
    ),
    "P7_REGIME_FRONT_ROUGHNESS": (
        "SKIP_SHUFFLED_NULL",
        "transitions are smooth by default",
        "if observed > null_p95 + threshold:",
        ("test_shuffled_null_match_blocks_rough_classification",),
    ),
    "P8_NON_SELFSIMILAR_CLUSTER_GROWTH": (
        "SKIP_PER_WINDOW_CHECK",
        "one growth exponent explains all windows",
        "for i, exp in enumerate(per_window):",
        ("test_non_self_similar_when_one_window_diverges",),
    ),
    "P9_EFFECTIVE_DEPTH_GUARD": (
        "DROP_EQUIVALENCE_TOLERANCE",
        "longer reasoning = deeper truth",
        "if math.isfinite(dist) and dist <= tolerance:",
        ("test_redundant_depth_detected_within_tolerance",),
    ),
    "P10_CLAIM_GAUGE_WITNESS": (
        "SKIP_REQUIRED_INTERSECTION",
        "single local check = global proof",
        "failing: list[str] = [c for c in required if c in sat and not sat[c]]",
        ("test_one_required_violated_refuses",),
    ),
}


# Cross-cutting rule bound to the evidence-decay engine, not the
# pattern matrix.
_EVIDENCE_DECAY_RULE = (
    "MARK_STALE_EVIDENCE_VALID",
    "old evidence remains true forever",
    "tools/governance/evidence_decay.py",
    "elif age >= expired:",
    ("test_security_evidence_eight_days_old_is_stale",),
)


def _load_translation(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"translation matrix not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"translation matrix {path} must be a mapping")
    return data


def forge_candidates(
    translation_matrix_path: Path = DEFAULT_TRANSLATION,
) -> ForgeReport:
    """Build a list of candidate mutation plans from the translation matrix.

    A pattern enters the forge only when its implementation_status is
    IMPLEMENTED — proposing falsifiers for unbuilt modules is a lie.
    """
    report = ForgeReport()
    data = _load_translation(translation_matrix_path)
    patterns = data.get("patterns") or []
    if not isinstance(patterns, list):
        return report

    seen: set[tuple[str, str]] = set()
    for entry in patterns:
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("pattern_id") or "")
        if entry.get("implementation_status") != "IMPLEMENTED":
            continue
        rule = _PATTERN_RULES.get(pid)
        if rule is None:
            continue
        mutation_kind, lie, target_token, tests = rule
        target_path = str(entry.get("proposed_module") or "")
        key = (target_path, mutation_kind)
        if key in seen:
            continue
        seen.add(key)
        report.candidates.append(
            FalsifierCandidate(
                candidate_id=f"{pid}-{mutation_kind}",
                pattern_id=pid,
                mutation_kind=mutation_kind,
                target_path=target_path,
                target_token=target_token,
                lie_re_introduced=lie,
                expected_failing_tests=tests,
            )
        )

    # Cross-cutting evidence-decay rule.
    mk, lie, target_path, target_token, tests = _EVIDENCE_DECAY_RULE
    key = (target_path, mk)
    if key not in seen:
        seen.add(key)
        report.candidates.append(
            FalsifierCandidate(
                candidate_id=f"EVIDENCE_DECAY-{mk}",
                pattern_id="EVIDENCE_DECAY",
                mutation_kind=mk,
                target_path=target_path,
                target_token=target_token,
                lie_re_introduced=lie,
                expected_failing_tests=tests,
            )
        )

    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forge falsifier candidates")
    parser.add_argument("--translation", type=Path, default=DEFAULT_TRANSLATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = forge_candidates(args.translation)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(f"OK: forged {len(report.candidates)} candidate(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
