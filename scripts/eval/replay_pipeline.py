#!/usr/bin/env python3
"""Offline Pipeline Replay Harness.

Runs replay tests against the LLM pipeline using stub providers.
Produces reports with NO raw prompts (only hashes).

Usage:
    python scripts/eval/replay_pipeline.py [--fixtures PATH] [--output PATH] [--strict]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add repository root to path for imports
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_module_direct(name: str, path: Path):
    """Load a module directly without triggering parent __init__.py."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load modules directly to avoid parent package dependencies
_mlsdm_path = REPO_ROOT / "src" / "tradepulse" / "sdk" / "mlsdm"

_replay_fingerprint = _load_module_direct(
    "tradepulse.sdk.mlsdm.utils.replay_fingerprint",
    _mlsdm_path / "utils" / "replay_fingerprint.py",
)
sha256_hex = _replay_fingerprint.sha256_hex

_stub_llm = _load_module_direct(
    "tradepulse.sdk.mlsdm.core.stub_llm",
    _mlsdm_path / "core" / "stub_llm.py",
)
StubLLMProvider = _stub_llm.StubLLMProvider

_llm_pipeline = _load_module_direct(
    "tradepulse.sdk.mlsdm.core.llm_pipeline",
    _mlsdm_path / "core" / "llm_pipeline.py",
)
LLMPipeline = _llm_pipeline.LLMPipeline
PipelineConfig = _llm_pipeline.PipelineConfig

__all__ = [
    "ReplayCase",
    "ReplayResult",
    "ReplayReport",
    "load_cases",
    "run_replay",
    "main",
]

# Decision priority ordering (lower = stricter)
DECISION_PRIORITY: dict[str, int] = {
    "BLOCK": 1,
    "REDACT": 2,
    "REWRITE": 3,
    "ALLOW": 4,
}


@dataclass(frozen=True, slots=True)
class ReplayCase:
    """A single replay test case.

    Attributes:
        case_id: Unique identifier for the case.
        input_text: The input text to test.
        expected_min_decision: Minimum expected decision level.
    """

    case_id: str
    input_text: str
    expected_min_decision: str


@dataclass(slots=True)
class ReplayResult:
    """Result of replaying a single test case.

    Note: input_text is NOT stored, only its hash.
    """

    case_id: str
    cache_key: str
    decision: str
    reasons: list[str]
    output_hash: str
    passed: bool
    expected_min_decision: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "case_id": self.case_id,
            "cache_key": self.cache_key,
            "decision": self.decision,
            "reasons": self.reasons,
            "output_hash": self.output_hash,
            "passed": self.passed,
            "expected_min_decision": self.expected_min_decision,
        }


@dataclass(slots=True)
class ReplayReport:
    """Report from replay execution.

    Contains NO raw prompts - only hashes and metadata.
    """

    timestamp: str
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    strict_mode: bool
    pipeline_version: str
    results: list[ReplayResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "summary": {
                "total_cases": self.total_cases,
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": self.pass_rate,
            },
            "strict_mode": self.strict_mode,
            "pipeline_version": self.pipeline_version,
            "results": [r.to_dict() for r in self.results],
        }


def decision_meets_minimum(actual: str, minimum: str) -> bool:
    """Check if actual decision meets minimum requirement.

    A stricter decision always meets a less strict requirement.
    BLOCK > REDACT > REWRITE > ALLOW

    Args:
        actual: The actual decision from pipeline.
        minimum: The minimum expected decision.

    Returns:
        True if actual is at least as strict as minimum.
    """
    actual_priority = DECISION_PRIORITY.get(actual.upper(), 5)
    minimum_priority = DECISION_PRIORITY.get(minimum.upper(), 5)
    # Lower priority number = stricter, so actual <= minimum means meets requirement
    return actual_priority <= minimum_priority


def load_cases(path: Path) -> list[ReplayCase]:
    """Load test cases from JSONL file.

    Args:
        path: Path to the cases.jsonl file.

    Returns:
        List of ReplayCase objects.

    Raises:
        FileNotFoundError: If path doesn't exist.
        json.JSONDecodeError: If JSON is malformed.
    """
    cases: list[ReplayCase] = []

    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                cases.append(
                    ReplayCase(
                        case_id=data["case_id"],
                        input_text=data["input_text"],
                        expected_min_decision=data["expected_min_decision"],
                    )
                )
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"Invalid case at line {line_num}: {e}") from e

    return cases


def run_replay(
    cases: list[ReplayCase],
    pipeline: LLMPipeline,
) -> ReplayReport:
    """Run replay on all test cases.

    Args:
        cases: List of test cases to replay.
        pipeline: The LLM pipeline to use.

    Returns:
        ReplayReport with results (no raw prompts).
    """
    results: list[ReplayResult] = []
    passed_count = 0

    for case in cases:
        # Run pipeline
        result = pipeline.run_with_trace(case.input_text)

        # Check if decision meets minimum
        passed = decision_meets_minimum(result.decision, case.expected_min_decision)
        if passed:
            passed_count += 1

        # Store result WITHOUT raw prompt
        results.append(
            ReplayResult(
                case_id=case.case_id,
                cache_key=result.cache_key,
                decision=result.decision,
                reasons=result.reasons,
                output_hash=result.output_hash,
                passed=passed,
                expected_min_decision=case.expected_min_decision,
            )
        )

    # Build report
    total = len(cases)
    return ReplayReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_cases=total,
        passed=passed_count,
        failed=total - passed_count,
        pass_rate=passed_count / total if total > 0 else 0.0,
        strict_mode=pipeline.strict_mode,
        pipeline_version=pipeline.config.version,
        results=results,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Offline Pipeline Replay Harness",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "replay" / "cases.jsonl",
        help="Path to test fixtures JSONL file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to output JSON report (default: reports/replay/report.json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run in strict mode",
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

    cases = load_cases(args.fixtures)
    if args.limit:
        cases = cases[: args.limit]

    print(f"Loaded {len(cases)} test cases from {args.fixtures}")

    # Create pipeline with stub provider
    config = PipelineConfig(strict_mode=args.strict)
    provider = StubLLMProvider()
    pipeline = LLMPipeline(config=config, provider=provider)

    print(f"Pipeline initialized (strict_mode={args.strict})")

    # Run replay
    report = run_replay(cases, pipeline)

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE REPLAY SUMMARY")
    print("=" * 60)
    print(f"Total cases: {report.total_cases}")
    print(f"Passed: {report.passed} ({100 * report.pass_rate:.1f}%)")
    print(f"Failed: {report.failed}")

    # Show failed cases
    failed_cases = [r for r in report.results if not r.passed]
    if failed_cases:
        print(f"\nFailed cases ({len(failed_cases)}):")
        for fc in failed_cases[:10]:  # Show first 10
            print(f"  - {fc.case_id}: expected {fc.expected_min_decision}, got {fc.decision}")

    # Write report
    if args.output:
        output_path = args.output
    else:
        reports_dir = REPO_ROOT / "reports" / "replay"
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / "report.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    print(f"\nReport written to: {output_path}")

    # Verify report contains no raw prompts
    report_text = output_path.read_text()
    for case in cases:
        if case.input_text in report_text:
            print(
                f"ERROR: Raw prompt found in report for case {case.case_id}",
                file=sys.stderr,
            )
            return 1

    print("✓ Report verified: no raw prompts found")

    # Exit with error if any failures
    if report.failed > 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
