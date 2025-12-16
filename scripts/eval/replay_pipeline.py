"""Replay pipeline harness for offline regression testing.

This script runs recorded test cases through the MLSDM pipeline
with deterministic configuration to detect behavioral regressions.

Usage:
    python -m scripts.eval.replay_pipeline [OPTIONS]

    Options:
        --fixtures-dir: Directory containing replay fixtures (default: fixtures/replay)
        --output-dir: Directory for replay reports (default: reports/replay)
        --seed: Random seed for deterministic execution (default: 42)
        --strict: Enable strict mode for error handling
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_module_directly(module_name: str, file_path: str) -> Any:
    """Load a module directly from file path without triggering package __init__.py."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Constants
TRACE_SEED_RANGE = 10000  # Range for trace ID seed variation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ReplayCase:
    """A single replay test case.

    Attributes:
        case_id: Unique identifier for the case.
        input_text: Input text/prompt for the pipeline.
        context: Additional context for the pipeline.
        expected_decision: Expected decision type (ALLOW, BLOCK, REDACT, REWRITE).
        expected_output_hash: Optional hash of expected output.
        expected_rule_hits: Expected policy rules to trigger.
        tags: Tags for categorizing the test case.
    """

    case_id: str
    input_text: str
    context: dict[str, Any] = field(default_factory=dict)
    expected_decision: str = "ALLOW"
    expected_output_hash: str | None = None
    expected_rule_hits: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplayCase:
        """Create ReplayCase from dictionary."""
        return cls(
            case_id=data["case_id"],
            input_text=data["input_text"],
            context=data.get("context", {}),
            expected_decision=data.get("expected_decision", "ALLOW"),
            expected_output_hash=data.get("expected_output_hash"),
            expected_rule_hits=data.get("expected_rule_hits", []),
            tags=data.get("tags", []),
        )


@dataclass
class ReplayResult:
    """Result of running a replay case.

    Attributes:
        case_id: The case identifier.
        passed: Whether the case passed.
        actual_decision: Actual decision from pipeline.
        actual_output_hash: Hash of actual output.
        expected_decision: Expected decision.
        expected_output_hash: Expected output hash.
        cache_key: Cache key computed for this run.
        trace_id: Trace ID for this execution.
        errors: List of errors/failures.
        duration_ms: Execution duration in milliseconds.
    """

    case_id: str
    passed: bool
    actual_decision: str
    actual_output_hash: str
    expected_decision: str
    expected_output_hash: str | None
    cache_key: str
    trace_id: str
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ReplayReport:
    """Report of a replay run.

    Attributes:
        timestamp: When the replay was run.
        seed: Random seed used.
        total_cases: Total number of cases.
        passed_cases: Number of cases that passed.
        failed_cases: Number of cases that failed.
        results: Individual case results.
        summary: Summary statistics.
    """

    timestamp: str
    seed: int
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: list[ReplayResult]
    summary: dict[str, Any] = field(default_factory=dict)


class StubLLM:
    """Stub LLM for offline replay testing.

    This stub provides deterministic outputs based on input hashing
    to enable reproducible replay testing without network calls.
    """

    def __init__(self, seed: int = 42) -> None:
        """Initialize stub LLM with seed.

        Args:
            seed: Random seed for deterministic behavior.
        """
        self.seed = seed
        self._call_count = 0

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate stub response.

        Args:
            prompt: Input prompt.
            **kwargs: Additional parameters (ignored).

        Returns:
            Deterministic stub response.
        """
        self._call_count += 1
        # Create deterministic response based on prompt hash
        combined = f"{self.seed}:{self._call_count}:{prompt}"
        hash_hex = hashlib.sha256(combined.encode()).hexdigest()[:8]
        return f"[STUB_RESPONSE:{hash_hex}] Processed: {prompt[:50]}..."


class ReplayPipeline:
    """Pipeline wrapper for replay execution.

    This class wraps the MLSDM pipeline components to provide
    deterministic execution for replay testing.
    """

    _canonical_module: Any = None
    _pipeline_result_module: Any = None

    def __init__(self, seed: int = 42, strict_mode: bool = False) -> None:
        """Initialize replay pipeline.

        Args:
            seed: Random seed for determinism.
            strict_mode: Enable strict error handling.
        """
        self.seed = seed
        self.strict_mode = strict_mode
        self.llm = StubLLM(seed=seed)
        self._policy_version = "1.0.0"

    def _get_canonical_module(self) -> Any:
        """Get the canonical module, loading it directly to avoid SDK deps."""
        if ReplayPipeline._canonical_module is not None:
            return ReplayPipeline._canonical_module

        # Try standard import first
        try:
            from tradepulse.sdk.mlsdm.core import canonical

            ReplayPipeline._canonical_module = canonical
            return canonical
        except ImportError:
            pass

        # Load directly from file
        script_dir = Path(__file__).parent.parent.parent
        canonical_path = (
            script_dir / "src" / "tradepulse" / "sdk" / "mlsdm" / "core" / "canonical.py"
        )
        if canonical_path.exists():
            ReplayPipeline._canonical_module = _load_module_directly(
                "mlsdm_core_canonical", str(canonical_path)
            )
            return ReplayPipeline._canonical_module

        raise ImportError("Cannot load canonical module")

    def _get_pipeline_result_module(self) -> Any:
        """Get the pipeline_result module, loading it directly to avoid SDK deps."""
        if ReplayPipeline._pipeline_result_module is not None:
            return ReplayPipeline._pipeline_result_module

        # Try standard import first
        try:
            from tradepulse.sdk.mlsdm.core import pipeline_result

            ReplayPipeline._pipeline_result_module = pipeline_result
            return pipeline_result
        except ImportError:
            pass

        # Load directly from file
        script_dir = Path(__file__).parent.parent.parent
        result_path = (
            script_dir
            / "src"
            / "tradepulse"
            / "sdk"
            / "mlsdm"
            / "core"
            / "pipeline_result.py"
        )
        if result_path.exists():
            ReplayPipeline._pipeline_result_module = _load_module_directly(
                "mlsdm_core_pipeline_result", str(result_path)
            )
            return ReplayPipeline._pipeline_result_module

        raise ImportError("Cannot load pipeline_result module")

    def process(self, case: ReplayCase) -> dict[str, Any]:
        """Process a replay case through the pipeline.

        Args:
            case: The replay case to process.

        Returns:
            Dictionary with processing results.
        """
        # Import modules directly from file to avoid SDK dependency chain
        canonical_mod = self._get_canonical_module()
        pipeline_mod = self._get_pipeline_result_module()

        canonical_request = canonical_mod.canonical_request
        Decision = pipeline_mod.Decision
        PipelineResult = pipeline_mod.PipelineResult
        create_trace_id = pipeline_mod.create_trace_id

        # Create canonical request
        config = {
            "strict_mode": self.strict_mode,
            "seed": self.seed,
            **case.context,
        }
        req = canonical_request(
            user_text=case.input_text,
            policy_version=self._policy_version,
            config=config,
            strict_mode=self.strict_mode,
        )

        # Determine trace ID (deterministic for replay using SHA-256)
        case_hash = int(hashlib.sha256(case.case_id.encode()).hexdigest()[:8], 16)
        trace_id = create_trace_id(seed=self.seed + case_hash % TRACE_SEED_RANGE)

        # Apply policy checks
        decision, reasons, rule_hits = self._apply_policy(case.input_text)

        # Generate output through stub LLM
        if decision == Decision.BLOCK:
            output_text = "[BLOCKED]"
        elif decision == Decision.REDACT:
            output_text = self._redact_output(
                self.llm.generate(case.input_text)
            )
        else:
            output_text = self.llm.generate(case.input_text)

        result = PipelineResult(
            output_text=output_text,
            decision=decision,
            reasons=tuple(reasons),
            cache_key=req.cache_key,
            trace_id=trace_id,
            rule_hits=tuple(rule_hits),
        )

        return result.to_dict()

    def _apply_policy(
        self, text: str
    ) -> tuple[Any, list[str], list[str]]:
        """Apply policy checks to input.

        Args:
            text: Input text.

        Returns:
            Tuple of (decision, reasons, rule_hits).
        """
        pipeline_mod = self._get_pipeline_result_module()
        Decision = pipeline_mod.Decision

        reasons: list[str] = []
        rule_hits: list[str] = []

        text_lower = text.lower()

        # Check for injection patterns
        injection_patterns = [
            r"\bignore\s+(all\s+)?(previous\s+)?instructions?\b",
            r"\bsystem\s*prompt\b",
            r"\byou\s+are\s+now\s+a\b",  # More specific to avoid false positives
            r"\bact\s+as\s+if\s+you\b",  # More specific
            r"\bpretend\s+(you\s+are|to\s+be)\b",  # Role-playing injection
            r"\boverride\s+(safety|security|rules)\b",  # Override attempts
        ]
        for pattern in injection_patterns:
            if re.search(pattern, text_lower):
                rule_hits.append("INJECTION_ATTEMPT")
                reasons.append(f"Matched injection pattern: {pattern}")

        # Check for exfiltration patterns
        exfil_patterns = [
            r"\brepeat\s+(all\s+)?(the\s+)?(text|instructions?|input)\b",
            r"\boutput\s+(your|the)\s+prompt\b",
            r"\breveal\s+.*(secret|password|key)\b",
        ]
        for pattern in exfil_patterns:
            if re.search(pattern, text_lower):
                rule_hits.append("EXFIL_ATTEMPT")
                reasons.append(f"Matched exfiltration pattern: {pattern}")

        # Check for PII patterns (for redaction)
        pii_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # Email
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # Phone
        ]
        has_pii = any(re.search(p, text) for p in pii_patterns)
        if has_pii:
            rule_hits.append("PII_DETECTED")
            reasons.append("PII detected in input")

        # Determine decision
        if "INJECTION_ATTEMPT" in rule_hits or "EXFIL_ATTEMPT" in rule_hits:
            return Decision.BLOCK, reasons, rule_hits
        elif "PII_DETECTED" in rule_hits:
            return Decision.REDACT, reasons, rule_hits
        else:
            return Decision.ALLOW, reasons, rule_hits

    def _redact_output(self, text: str) -> str:
        """Redact sensitive content from output.

        Args:
            text: Input text.

        Returns:
            Redacted text.
        """
        # Redact emails
        text = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[EMAIL_REDACTED]",
            text,
        )
        # Redact phone numbers
        text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE_REDACTED]", text)
        return text


def load_fixtures(fixtures_dir: Path) -> list[ReplayCase]:
    """Load replay fixtures from directory.

    Args:
        fixtures_dir: Directory containing fixture files.

    Returns:
        List of ReplayCase objects.
    """
    cases: list[ReplayCase] = []

    if not fixtures_dir.exists():
        logger.warning(f"Fixtures directory not found: {fixtures_dir}")
        return cases

    # Load JSONL files
    for filepath in fixtures_dir.glob("*.jsonl"):
        logger.info(f"Loading fixtures from {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    cases.append(ReplayCase.from_dict(data))

    # Load JSON files
    for filepath in fixtures_dir.glob("*.json"):
        logger.info(f"Loading fixtures from {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    cases.append(ReplayCase.from_dict(item))
            else:
                cases.append(ReplayCase.from_dict(data))

    return cases


def run_replay(
    cases: list[ReplayCase],
    seed: int = 42,
    strict_mode: bool = False,
) -> ReplayReport:
    """Run replay on all cases.

    Args:
        cases: List of cases to replay.
        seed: Random seed for determinism.
        strict_mode: Enable strict error handling.

    Returns:
        ReplayReport with results.
    """
    import time

    pipeline = ReplayPipeline(seed=seed, strict_mode=strict_mode)
    results: list[ReplayResult] = []
    passed = 0
    failed = 0

    for case in cases:
        start_time = time.perf_counter()
        errors: list[str] = []

        try:
            output = pipeline.process(case)
            actual_decision = output["decision"]
            actual_output_hash = hashlib.sha256(
                output["output_text"].encode()
            ).hexdigest()
            cache_key = output["cache_key"]
            trace_id = output["trace_id"]

            # Check decision match
            if actual_decision != case.expected_decision:
                errors.append(
                    f"Decision mismatch: expected {case.expected_decision}, "
                    f"got {actual_decision}"
                )

            # Check output hash if expected
            if case.expected_output_hash:
                if actual_output_hash != case.expected_output_hash:
                    errors.append(
                        f"Output hash mismatch: expected {case.expected_output_hash}, "
                        f"got {actual_output_hash}"
                    )

        except Exception as e:
            actual_decision = "ERROR"
            actual_output_hash = ""
            cache_key = ""
            trace_id = ""
            errors.append(f"Exception: {e}")

        duration_ms = (time.perf_counter() - start_time) * 1000
        case_passed = len(errors) == 0

        if case_passed:
            passed += 1
        else:
            failed += 1

        results.append(
            ReplayResult(
                case_id=case.case_id,
                passed=case_passed,
                actual_decision=actual_decision,
                actual_output_hash=actual_output_hash,
                expected_decision=case.expected_decision,
                expected_output_hash=case.expected_output_hash,
                cache_key=cache_key,
                trace_id=trace_id,
                errors=errors,
                duration_ms=duration_ms,
            )
        )

    return ReplayReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        seed=seed,
        total_cases=len(cases),
        passed_cases=passed,
        failed_cases=failed,
        results=results,
        summary={
            "pass_rate": passed / len(cases) if cases else 0.0,
            "avg_duration_ms": sum(r.duration_ms for r in results) / len(results)
            if results
            else 0.0,
        },
    )


def scrub_report(report: dict[str, Any]) -> dict[str, Any]:
    """Scrub sensitive data from report.

    Removes any PII or secrets that might have leaked into the report.

    Args:
        report: Raw report dictionary.

    Returns:
        Scrubbed report dictionary.
    """
    import copy

    scrubbed = copy.deepcopy(report)

    # Patterns that might indicate secrets
    secret_patterns = [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",  # Email
        r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # Phone
        r"(sk|pk|api)[-_][a-zA-Z0-9_]{8,}",  # API keys with prefix (e.g., sk_live_...)
        r"(key|token|secret|password)[-_]?[a-zA-Z0-9]{12,}",  # Other secrets
        r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",  # Bearer tokens
    ]

    def scrub_value(value: Any) -> Any:
        if isinstance(value, str):
            result = value
            for pattern in secret_patterns:
                result = re.sub(pattern, "[SCRUBBED]", result, flags=re.IGNORECASE)
            return result
        elif isinstance(value, dict):
            return {k: scrub_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [scrub_value(item) for item in value]
        return value

    return scrub_value(scrubbed)


def save_report(report: ReplayReport, output_path: Path) -> None:
    """Save replay report to file.

    Args:
        report: The replay report.
        output_path: Path to save the report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict and scrub
    report_dict = {
        "timestamp": report.timestamp,
        "seed": report.seed,
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "summary": report.summary,
        "results": [asdict(r) for r in report.results],
    }
    scrubbed = scrub_report(report_dict)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scrubbed, f, indent=2)

    logger.info(f"Report saved to {output_path}")


def main() -> int:
    """Main entry point for replay harness.

    Returns:
        Exit code (0 for success, 1 for failures).
    """
    parser = argparse.ArgumentParser(
        description="Run offline replay tests for MLSDM pipeline"
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path("fixtures/replay"),
        help="Directory containing replay fixtures",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/replay"),
        help="Directory for replay reports",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic execution",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode for error handling",
    )

    args = parser.parse_args()

    logger.info(f"Loading fixtures from {args.fixtures_dir}")
    cases = load_fixtures(args.fixtures_dir)

    if not cases:
        logger.error("No replay cases found")
        return 1

    logger.info(f"Running replay on {len(cases)} cases with seed={args.seed}")
    report = run_replay(cases, seed=args.seed, strict_mode=args.strict)

    # Generate output filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"replay_{timestamp}.json"

    save_report(report, output_path)

    # Print summary
    logger.info(f"Replay complete: {report.passed_cases}/{report.total_cases} passed")
    if report.failed_cases > 0:
        logger.error(f"{report.failed_cases} cases failed")
        for result in report.results:
            if not result.passed:
                logger.error(f"  - {result.case_id}: {result.errors}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
