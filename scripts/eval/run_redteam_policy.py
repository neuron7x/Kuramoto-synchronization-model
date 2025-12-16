#!/usr/bin/env python3
"""Red-Team Policy Evaluation Harness.

Offline evaluation of policy decisions against adversarial test cases.
No network calls or external LLM dependencies.

Usage:
    python scripts/eval/run_redteam_policy.py [--fixtures PATH] [--output PATH] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Add repository root to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

# Import directly using importlib to avoid triggering parent __init__.py
import importlib.util


def _load_module_direct(name: str, path: Path):
    """Load a module directly without triggering parent __init__.py."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load policy modules directly
_policy_path = REPO_ROOT / "src" / "tradepulse" / "policy"
_decision_types = _load_module_direct(
    "tradepulse.policy.decision_types",
    _policy_path / "decision_types.py",
)
DecisionType = _decision_types.DecisionType

_decision_trace = _load_module_direct(
    "tradepulse.policy.decision_trace",
    _policy_path / "decision_trace.py",
)
TraceScrubber = _decision_trace.TraceScrubber

_policy_engine = _load_module_direct(
    "tradepulse.policy.policy_engine",
    _policy_path / "policy_engine.py",
)
PolicyEngine = _policy_engine.PolicyEngine
PolicyEngineConfig = _policy_engine.PolicyEngineConfig
PolicyResult = _policy_engine.PolicyResult
SimplePolicyModule = _policy_engine.SimplePolicyModule

# Fixed seed for reproducibility
RANDOM_SEED = 42


@dataclass(frozen=True, slots=True)
class TestCase:
    """A single red-team test case."""

    id: str
    category: str
    input_text: str
    expected_minimum_decision: DecisionType
    description: str = ""


@dataclass(slots=True)
class TestResult:
    """Result of evaluating a single test case."""

    test_id: str
    category: str
    passed: bool
    expected_minimum: str
    actual_decision: str
    is_false_allow: bool
    is_false_block: bool
    reasons: list[str] = field(default_factory=list)
    trace_id: str = ""


@dataclass(slots=True)
class EvaluationReport:
    """Summary report of red-team evaluation."""

    timestamp: str
    total_cases: int
    passed: int
    failed: int
    false_allow_count: int
    false_block_count: int
    decision_distribution: dict[str, int]
    category_results: dict[str, dict[str, int]]
    top_reasons: list[tuple[str, int]]
    results: list[TestResult]
    strict_mode: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "summary": {
                "total_cases": self.total_cases,
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": self.passed / self.total_cases if self.total_cases > 0 else 0.0,
                "false_allow_count": self.false_allow_count,
                "false_block_count": self.false_block_count,
            },
            "decision_distribution": self.decision_distribution,
            "category_results": self.category_results,
            "top_reasons": [{"reason": r, "count": c} for r, c in self.top_reasons],
            "strict_mode": self.strict_mode,
            "results": [
                {
                    "test_id": r.test_id,
                    "category": r.category,
                    "passed": r.passed,
                    "expected_minimum": r.expected_minimum,
                    "actual_decision": r.actual_decision,
                    "is_false_allow": r.is_false_allow,
                    "is_false_block": r.is_false_block,
                    "reasons": r.reasons,
                    "trace_id": r.trace_id,
                }
                for r in self.results
            ],
        }


def parse_decision(value: str) -> DecisionType:
    """Parse decision type from string."""
    mapping = {
        "ALLOW": DecisionType.ALLOW,
        "BLOCK": DecisionType.BLOCK,
        "REDACT": DecisionType.REDACT,
        "REWRITE": DecisionType.REWRITE,
        "ESCALATE": DecisionType.ESCALATE,
    }
    return mapping[value.upper()]


def load_test_cases(fixtures_path: Path) -> list[TestCase]:
    """Load test cases from YAML file."""
    with fixtures_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cases = []
    for item in data.get("test_cases", []):
        cases.append(
            TestCase(
                id=item["id"],
                category=item["category"],
                input_text=item["input_text"],
                expected_minimum_decision=parse_decision(item["expected_minimum_decision"]),
                description=item.get("description", ""),
            )
        )
    return cases


def create_stub_policy_engine(strict_mode: bool = False) -> PolicyEngine:
    """Create a policy engine with stub modules for offline testing.

    This uses pattern-based detection to simulate policy decisions
    without any network calls or external dependencies.
    """
    config = PolicyEngineConfig(
        strict_mode=strict_mode,
        require_reasons_for_allow=True,
        log_traces=False,
        version="1.0.0-redteam",
    )

    # Injection patterns -> BLOCK
    injection_module = SimplePolicyModule(
        name="injection_detector",
        version="1.0.0",
        patterns={
            "ignore all previous": DecisionType.BLOCK,
            "ignore your": DecisionType.BLOCK,
            "[[system]]": DecisionType.BLOCK,
            "disregard safety": DecisionType.BLOCK,
            "admin_override": DecisionType.BLOCK,
            "developer mode": DecisionType.BLOCK,
            "dan mode": DecisionType.BLOCK,
            "unrestricted ai": DecisionType.BLOCK,
            "no restrictions": DecisionType.REDACT,
            "no ethical guidelines": DecisionType.BLOCK,
            "execute privileged": DecisionType.BLOCK,
        },
    )

    # Exfiltration patterns -> BLOCK
    exfiltration_module = SimplePolicyModule(
        name="exfiltration_detector",
        version="1.0.0",
        patterns={
            "api key": DecisionType.BLOCK,
            "api keys": DecisionType.BLOCK,
            "environment variable": DecisionType.BLOCK,
            "/etc/passwd": DecisionType.BLOCK,
            "user credentials": DecisionType.BLOCK,
            "training data": DecisionType.REDACT,
            "passwords": DecisionType.BLOCK,
            "secrets": DecisionType.BLOCK,
            "config files": DecisionType.BLOCK,
        },
    )

    # Harmful content -> BLOCK
    harmful_module = SimplePolicyModule(
        name="harmful_content_detector",
        version="1.0.0",
        patterns={
            "hurt myself": DecisionType.BLOCK,
            "ending my life": DecisionType.BLOCK,
            "harm people": DecisionType.BLOCK,
            "attack someone": DecisionType.BLOCK,
            "keylogger": DecisionType.BLOCK,
            "ransomware": DecisionType.BLOCK,
            "ransom": DecisionType.BLOCK,
            "botnet": DecisionType.BLOCK,
            "ddos": DecisionType.BLOCK,
            "make weapons": DecisionType.BLOCK,
        },
    )

    # Jailbreak patterns -> REDACT/BLOCK
    jailbreak_module = SimplePolicyModule(
        name="jailbreak_detector",
        version="1.0.0",
        patterns={
            "pretend you have no": DecisionType.REDACT,
            "hypothetically": DecisionType.REDACT,
            "if you had no safety": DecisionType.REDACT,
            "act as an": DecisionType.REDACT,
            "bypass security": DecisionType.REDACT,
            "help bypass": DecisionType.REDACT,
        },
    )

    # Policy evasion patterns -> REDACT
    evasion_module = SimplePolicyModule(
        name="evasion_detector",
        version="1.0.0",
        patterns={
            "byp4ss": DecisionType.REDACT,
            "s3cur1ty": DecisionType.REDACT,
            "iggnore": DecisionType.REDACT,
            "r.e.s.t.r.i.c.t.e.d": DecisionType.REDACT,
            # Common Base64-encoded attack patterns
            "aW5qZWN0": DecisionType.REDACT,  # "inject" in Base64
            "aWdub3Jl": DecisionType.REDACT,  # "ignore" in Base64
            "YnlwYXNz": DecisionType.REDACT,  # "bypass" in Base64
        },
    )

    # PII/Secrets detection -> REDACT
    def pii_evaluator(content: str, context: dict[str, object] | None) -> PolicyResult:
        scrubber = TraceScrubber()
        scrubbed = scrubber.scrub(content)

        if scrubbed != content:
            # Content was modified, indicating PII/secrets found
            return PolicyResult(
                decision=DecisionType.REDACT,
                reasons=["pii_detected", "secrets_detected"],
                rule_hits=["pii_scrubber"],
            )
        return PolicyResult(
            decision=DecisionType.ALLOW,
            reasons=["no_pii_detected"],
        )

    pii_module = SimplePolicyModule(
        name="pii_detector",
        version="1.0.0",
        evaluator=pii_evaluator,
    )

    engine = PolicyEngine(config=config)
    engine.register_module(injection_module)
    engine.register_module(exfiltration_module)
    engine.register_module(harmful_module)
    engine.register_module(jailbreak_module)
    engine.register_module(evasion_module)
    engine.register_module(pii_module)

    return engine


def decision_meets_minimum(actual: DecisionType, minimum: DecisionType) -> bool:
    """Check if actual decision meets the minimum requirement.

    Lower DecisionType value = higher priority/stricter.
    For expected_minimum=REDACT, REDACT/BLOCK/ESCALATE all pass.
    """
    # ALLOW has highest value (5), BLOCK has lowest (1)
    # Meeting minimum means actual is at least as strict as minimum
    return actual.value <= minimum.value


def evaluate_test_cases(
    engine: PolicyEngine,
    cases: list[TestCase],
) -> EvaluationReport:
    """Evaluate all test cases and generate a report."""
    results: list[TestResult] = []
    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    category_results: dict[str, dict[str, int]] = {}

    false_allow_count = 0
    false_block_count = 0
    passed_count = 0

    for case in cases:
        result, trace = engine.evaluate(case.input_text, stage="redteam")

        passed = decision_meets_minimum(result.decision, case.expected_minimum_decision)

        is_false_allow = (
            result.decision == DecisionType.ALLOW
            and case.expected_minimum_decision != DecisionType.ALLOW
        )
        is_false_block = (
            result.decision == DecisionType.BLOCK
            and case.expected_minimum_decision == DecisionType.ALLOW
        )

        if is_false_allow:
            false_allow_count += 1
        if is_false_block:
            false_block_count += 1
        if passed:
            passed_count += 1

        decision_counts[str(result.decision)] += 1
        for reason in result.reasons:
            reason_counts[reason] += 1

        # Track by category
        if case.category not in category_results:
            category_results[case.category] = {"passed": 0, "failed": 0, "total": 0}
        category_results[case.category]["total"] += 1
        if passed:
            category_results[case.category]["passed"] += 1
        else:
            category_results[case.category]["failed"] += 1

        results.append(
            TestResult(
                test_id=case.id,
                category=case.category,
                passed=passed,
                expected_minimum=str(case.expected_minimum_decision),
                actual_decision=str(result.decision),
                is_false_allow=is_false_allow,
                is_false_block=is_false_block,
                reasons=result.reasons,
                trace_id=trace.trace_id,
            )
        )

    return EvaluationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_cases=len(cases),
        passed=passed_count,
        failed=len(cases) - passed_count,
        false_allow_count=false_allow_count,
        false_block_count=false_block_count,
        decision_distribution=dict(decision_counts),
        category_results=category_results,
        top_reasons=reason_counts.most_common(10),
        results=results,
        strict_mode=engine.strict_mode,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Red-Team Policy Evaluation Harness",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "redteam_cases.yaml",
        help="Path to test fixtures YAML file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to output JSON report (default: reports/redteam/report_<timestamp>.json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run in strict mode (ESCALATE becomes BLOCK)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of test cases to run",
    )
    args = parser.parse_args()

    # Load test cases
    if not args.fixtures.exists():
        print(f"Error: Fixtures file not found: {args.fixtures}", file=sys.stderr)
        return 1

    cases = load_test_cases(args.fixtures)
    if args.limit:
        cases = cases[: args.limit]

    print(f"Loaded {len(cases)} test cases from {args.fixtures}")

    # Create policy engine with stub modules
    engine = create_stub_policy_engine(strict_mode=args.strict)
    print(f"Policy engine initialized (strict_mode={args.strict})")

    # Run evaluation
    report = evaluate_test_cases(engine, cases)

    # Print summary
    print("\n" + "=" * 60)
    print("RED-TEAM EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total cases: {report.total_cases}")
    print(f"Passed: {report.passed} ({100 * report.passed / report.total_cases:.1f}%)")
    print(f"Failed: {report.failed}")
    print(f"False allows (critical): {report.false_allow_count}")
    print(f"False blocks: {report.false_block_count}")
    print("\nDecision distribution:")
    for decision, count in sorted(report.decision_distribution.items()):
        print(f"  {decision}: {count}")
    print("\nResults by category:")
    for cat, stats in sorted(report.category_results.items()):
        pct = 100 * stats["passed"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['passed']}/{stats['total']} ({pct:.0f}%)")

    # Show failed cases
    failed_cases = [r for r in report.results if not r.passed]
    if failed_cases:
        print(f"\nFailed cases ({len(failed_cases)}):")
        for fc in failed_cases[:10]:  # Show first 10
            print(f"  - {fc.test_id}: expected {fc.expected_minimum}, got {fc.actual_decision}")

    # Write report
    if args.output:
        output_path = args.output
    else:
        reports_dir = REPO_ROOT / "reports" / "redteam"
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = reports_dir / f"report_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"\nReport written to: {output_path}")

    # Exit with error if any false allows (critical security failures)
    if report.false_allow_count > 0:
        print(f"\n⚠️  CRITICAL: {report.false_allow_count} false allow(s) detected!")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
