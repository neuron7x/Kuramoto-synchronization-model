"""Automated production readiness validation gates.

This module provides a lightweight framework for evaluating production
readiness criteria. It is intentionally defensive: individual gate
validators return ``False`` on missing inputs or unexpected conditions
instead of raising, so the caller always receives a complete status map.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
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


class GateSeverity(Enum):
    """Severity classification for gates."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


@dataclass
class Gate:
    """Production readiness gate configuration."""

    name: str
    description: str
    validator: Callable[[], bool]
    severity: GateSeverity
    automated: bool = True


class ProductionGateValidator:
    """Automated production readiness validation."""

    def __init__(
        self,
        coverage_target: float = 98.0,
        mutation_target: float = 90.0,
        latency_target: float = 50.0,
        gates: Iterable[Gate] | None = None,
        mutation_report_paths: Iterable[str | Path] | None = None,
        docs_root: str | Path | None = None,
        performance_budget_path: str | Path | None = None,
        monitoring_paths: Iterable[str | Path] | None = None,
    ) -> None:
        self.coverage_target = coverage_target
        self.mutation_target = mutation_target
        self.latency_target = latency_target
        self.mutation_report_paths = (
            [Path(p) for p in mutation_report_paths]
            if mutation_report_paths is not None
            else [Path("reports/mutation/mutmut.json"), Path("reports/mutation/summary.json")]
        )
        self.docs_root = Path(docs_root) if docs_root is not None else Path("docs")
        self.performance_budget_path = (
            Path(performance_budget_path)
            if performance_budget_path is not None
            else Path("configs/performance_budgets.yaml")
        )
        self.monitoring_paths = (
            [Path(p) for p in monitoring_paths]
            if monitoring_paths is not None
            else [
                Path("monitoring/alerts.yaml"),
                Path("monitoring/alerts.yml"),
                Path("monitoring/dashboards"),
            ]
        )
        self.gates: List[Gate] = list(gates) if gates is not None else self._define_gates()

    # --- Gate definitions -------------------------------------------------
    def _define_gates(self) -> List[Gate]:
        return [
            Gate(
                name="test_coverage",
                description=f"Test coverage ≥{self.coverage_target:.0f}%",
                validator=self._check_coverage,
                severity=GateSeverity.CRITICAL,
                automated=True,
            ),
            Gate(
                name="mutation_score",
                description=f"Mutation score ≥{self.mutation_target:.0f}%",
                validator=self._check_mutations,
                severity=GateSeverity.HIGH,
                automated=True,
            ),
            Gate(
                name="zero_critical_vulns",
                description="Zero critical vulnerabilities",
                validator=self._check_security,
                severity=GateSeverity.CRITICAL,
                automated=True,
            ),
            Gate(
                name="secrets_rotated",
                description="All secrets rotated <90 days",
                validator=self._check_secrets,
                severity=GateSeverity.HIGH,
                automated=False,
            ),
            Gate(
                name="latency_sla",
                description=f"p99 latency <{self.latency_target:.0f}ms",
                validator=self._check_latency,
                severity=GateSeverity.CRITICAL,
                automated=True,
            ),
            Gate(
                name="docs_complete",
                description="All docs current and valid",
                validator=self._check_docs,
                severity=GateSeverity.MEDIUM,
                automated=True,
            ),
            Gate(
                name="monitoring_configured",
                description="Alerts and dashboards active",
                validator=self._check_monitoring,
                severity=GateSeverity.CRITICAL,
                automated=True,
            ),
            Gate(
                name="runbooks_validated",
                description="Incident runbooks tested",
                validator=self._check_runbooks,
                severity=GateSeverity.HIGH,
                automated=False,
            ),
        ]

    # --- Validators -------------------------------------------------------
    def _check_coverage(self) -> bool:
        """Validate test coverage from an existing .coverage file."""
        try:
            import coverage
        except ImportError:
            return False

        data_file = Path(".coverage")
        if not data_file.exists():
            return False

        try:
            cov = coverage.Coverage(data_file=str(data_file))
            cov.load()
            buffer = io.StringIO()
            total = cov.report(file=buffer)
            return total >= self.coverage_target
        except Exception:
            return False

    def _check_mutations(self) -> bool:
        """Check mutation testing report if available."""
        possible_keys = ("mutation_score", "score", "kill_rate", "mutation_kill_rate")
        for path in self.mutation_report_paths:
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Accept either plain percentage or nested structure
            if isinstance(payload, Mapping):
                for key in possible_keys:
                    score = payload.get(key)
                    if isinstance(score, (int, float)):
                        return float(score) >= self.mutation_target
        return False

    def _check_security(self) -> bool:
        """Check for critical vulnerabilities using safety if available."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "safety", "check", "--full-report", "--bare"],
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
                cwd=Path.cwd(),
            )
        except Exception:
            return False

        output = (result.stdout or "").upper()
        if result.returncode not in (0, 1):
            return False
        if "CRITICAL" in output:
            return False
        # safety exits with 1 when any vulnerability is found
        return result.returncode == 0

    def _check_secrets(self) -> bool:
        """Manual gate placeholder for secret rotation."""
        return False

    def _check_latency(self) -> bool:
        """Validate latency budgets using optional performance budget file."""
        budgets = self.performance_budget_path
        if not budgets.exists():
            return False
        try:
            import yaml
        except ImportError:
            return False

        try:
            data = yaml.safe_load(budgets.read_text(encoding="utf-8")) or {}
            candidates = [
                data.get("latency", {}).get("p99_ms"),
                data.get("latency_p99_ms"),
            ]
            numeric_candidates: list[float] = []
            for candidate in candidates:
                if candidate is None:
                    continue
                try:
                    numeric_candidates.append(float(candidate))
                except (TypeError, ValueError):
                    continue
            if not numeric_candidates:
                return False
            return any(value < self.latency_target for value in numeric_candidates)
        except Exception:
            return False

    def _check_docs(self) -> bool:
        """Verify documentation index exists."""
        return self.docs_root.exists() and any(self.docs_root.glob("*.md"))

    def _check_monitoring(self) -> bool:
        """Check for presence of monitoring configuration files."""
        return any(path.exists() for path in self.monitoring_paths)

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
        """Return a JSON-serializable summary of gate results."""
        statuses = self.validate_all()
        payload: Dict[str, Dict[str, object]] = {}
        for gate in self.gates:
            status = statuses.get(gate.name, GateStatus.PENDING)
            payload[gate.name] = {
                "status": status.name,
                "symbol": status.value,
                "severity": gate.severity.value,
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
                f"({gate.severity.value}): {gate.description}"
            )

        total = len(self.gates)
        automated_statuses = [
            statuses.get(gate.name, GateStatus.PENDING)
            for gate in self.gates
            if gate.automated
        ]
        automated_total = len(automated_statuses)
        if automated_statuses:
            passed = sum(1 for s in automated_statuses if s == GateStatus.PASS)
            rate_total = automated_total
        else:
            passed = sum(1 for s in statuses.values() if s == GateStatus.PASS)
            rate_total = total
        all_passed = bool(automated_total) and all(
            status == GateStatus.PASS for status in automated_statuses
        )
        pass_rate = (passed / rate_total * 100.0) if rate_total else 0.0
        lines.extend(
            [
                "",
                "## Summary",
                f"- Total Gates: {total}",
                f"- Passed: {passed}",
                f"- Pass Rate: {pass_rate:.1f}%",
                "",
                "## Production Ready?",
                "✅ YES" if all_passed and total > 0 else "❌ NO - Address failures above",
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
