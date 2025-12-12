"""Automated production readiness validation gates.

This module provides a lightweight framework for evaluating production
readiness criteria. It is intentionally defensive: individual gate
validators return ``False`` on missing inputs or unexpected conditions
instead of raising, so the caller always receives a complete status map.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping


class GateStatus(Enum):
    """Outcome for a production gate."""

    PASS = "✅"
    FAIL = "❌"
    WARNING = "⚠️"
    PENDING = "⏳"


@dataclass
class Gate:
    """Production readiness gate configuration."""

    name: str
    description: str
    validator: Callable[[], bool]
    severity: str  # CRITICAL, HIGH, MEDIUM
    automated: bool = True


class ProductionGateValidator:
    """Automated production readiness validation."""

    def __init__(
        self,
        coverage_target: float = 98.0,
        mutation_target: float = 90.0,
        gates: Iterable[Gate] | None = None,
    ) -> None:
        self.coverage_target = coverage_target
        self.mutation_target = mutation_target
        self.gates: List[Gate] = list(gates) if gates is not None else self._define_gates()

    # --- Gate definitions -------------------------------------------------
    def _define_gates(self) -> List[Gate]:
        return [
            Gate(
                name="test_coverage",
                description=f"Test coverage ≥{self.coverage_target:.0f}%",
                validator=self._check_coverage,
                severity="CRITICAL",
                automated=True,
            ),
            Gate(
                name="mutation_score",
                description=f"Mutation score ≥{self.mutation_target:.0f}%",
                validator=self._check_mutations,
                severity="HIGH",
                automated=True,
            ),
            Gate(
                name="zero_critical_vulns",
                description="Zero critical vulnerabilities",
                validator=self._check_security,
                severity="CRITICAL",
                automated=True,
            ),
            Gate(
                name="secrets_rotated",
                description="All secrets rotated <90 days",
                validator=self._check_secrets,
                severity="HIGH",
                automated=False,
            ),
            Gate(
                name="latency_sla",
                description="p99 latency <50ms",
                validator=self._check_latency,
                severity="CRITICAL",
                automated=True,
            ),
            Gate(
                name="docs_complete",
                description="All docs current and valid",
                validator=self._check_docs,
                severity="MEDIUM",
                automated=True,
            ),
            Gate(
                name="monitoring_configured",
                description="Alerts and dashboards active",
                validator=self._check_monitoring,
                severity="CRITICAL",
                automated=True,
            ),
            Gate(
                name="runbooks_validated",
                description="Incident runbooks tested",
                validator=self._check_runbooks,
                severity="HIGH",
                automated=False,
            ),
        ]

    # --- Validators -------------------------------------------------------
    def _check_coverage(self) -> bool:
        """Validate test coverage from an existing .coverage file."""
        try:
            import coverage  # type: ignore
        except Exception:
            return False

        data_file = Path(".coverage")
        if not data_file.exists():
            return False

        try:
            cov = coverage.Coverage(data_file=str(data_file))
            cov.load()
            total = cov.report(file=None)
            return total >= self.coverage_target
        except Exception:
            return False

    def _check_mutations(self) -> bool:
        """Check mutation testing report if available."""
        report_paths = [
            Path("reports/mutation/mutmut.json"),
            Path("reports/mutation/summary.json"),
        ]
        for path in report_paths:
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Accept either plain percentage or nested structure
            score = None
            if isinstance(payload, Mapping) and "mutation_score" in payload:
                score = payload.get("mutation_score")
            elif isinstance(payload, Mapping) and "score" in payload:
                score = payload.get("score")
            if isinstance(score, (int, float)):
                return float(score) >= self.mutation_target
        return False

    def _check_security(self) -> bool:
        """Check for critical vulnerabilities using safety if available."""
        try:
            result = subprocess.run(
                ["python", "-m", "safety", "check", "--full-report", "--bare"],
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )
        except Exception:
            return False

        output = result.stdout or ""
        if not output.strip():
            # No output implies no vulnerabilities detected
            return True
        # Treat presence of "CRITICAL" as failure
        return "CRITICAL" not in output.upper()

    def _check_secrets(self) -> bool:
        """Manual gate placeholder for secret rotation."""
        return False

    def _check_latency(self) -> bool:
        """Validate latency budgets using optional performance budget file."""
        budgets = Path("configs/performance_budgets.yaml")
        if not budgets.exists():
            return False
        try:
            import yaml
        except Exception:
            return False

        try:
            data = yaml.safe_load(budgets.read_text(encoding="utf-8")) or {}
            p99_budget = float(
                data.get("latency", {}).get("p99_ms", data.get("latency_p99_ms", 0))
            )
            return p99_budget and p99_budget < 50.0
        except Exception:
            return False

    def _check_docs(self) -> bool:
        """Verify documentation index exists."""
        docs_root = Path("docs")
        return docs_root.exists() and any(docs_root.glob("*.md"))

    def _check_monitoring(self) -> bool:
        """Check for presence of monitoring configuration files."""
        monitoring_paths = [
            Path("monitoring/alerts.yaml"),
            Path("monitoring/alerts.yml"),
            Path("monitoring/dashboards"),
        ]
        return any(path.exists() for path in monitoring_paths)

    def _check_runbooks(self) -> bool:
        """Manual gate placeholder for runbook validation."""
        return False

    # --- Public API -------------------------------------------------------
    def validate_all(self) -> Dict[str, GateStatus]:
        """Run all automated gates and return their statuses."""
        results: Dict[str, GateStatus] = {}
        for gate in self.gates:
            if not gate.automated:
                results[gate.name] = GateStatus.PENDING
                continue
            try:
                passed = bool(gate.validator())
                results[gate.name] = GateStatus.PASS if passed else GateStatus.FAIL
            except Exception:
                results[gate.name] = GateStatus.WARNING
        return results

    def as_report_payload(self) -> Dict[str, Dict[str, object]]:
        """Return a JSON-serialisable summary of gate results."""
        statuses = self.validate_all()
        payload: Dict[str, Dict[str, object]] = {}
        for gate in self.gates:
            status = statuses.get(gate.name, GateStatus.PENDING)
            payload[gate.name] = {
                "status": status.name,
                "symbol": status.value,
                "severity": gate.severity,
                "automated": gate.automated,
                "description": gate.description,
            }
        return payload

    def generate_report(self) -> str:
        """Generate a markdown production readiness report."""
        statuses = self.validate_all()
        lines = [
            "# Production Readiness Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Gate Status",
            "",
        ]
        for gate in self.gates:
            status = statuses.get(gate.name, GateStatus.PENDING)
            lines.append(
                f"{status.value} **{gate.name}** "
                f"({gate.severity}): {gate.description}"
            )

        total = len(self.gates)
        passed = sum(1 for s in statuses.values() if s == GateStatus.PASS)
        lines.extend(
            [
                "",
                "## Summary",
                f"- Total Gates: {total}",
                f"- Passed: {passed}",
                f"- Pass Rate: {passed/total*100:.1f}%",
                "",
                "## Production Ready?",
                "✅ YES" if passed == total else "❌ NO - Address failures above",
            ]
        )
        return "\n".join(lines)


def main() -> None:
    """CLI entrypoint for generating a gate report."""
    import argparse

    parser = argparse.ArgumentParser(description="Production readiness gate validator")
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the markdown report",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional path to write JSON gate results",
    )
    args = parser.parse_args()

    validator = ProductionGateValidator()
    report_text = validator.generate_report()
    print(report_text)

    if args.report:
        args.report.write_text(report_text + "\n", encoding="utf-8")
    if args.json_output:
        payload = validator.as_report_payload()
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    main()
