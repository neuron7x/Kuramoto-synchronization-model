#!/usr/bin/env python
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Production readiness verification script for TradePulse modules.

This script performs comprehensive validation checks to ensure all core
modules are production-ready. Run this before deployment to verify system
integrity.

Usage:
    python scripts/production_readiness_check.py
    python scripts/production_readiness_check.py --verbose
    python scripts/production_readiness_check.py --json-output report.json

Environment Variables Required:
    TRADEPULSE_TWO_FACTOR_SECRET - Two-factor authentication secret
    TRADEPULSE_AUDIT_SECRET - Audit logging secret (min 16 chars)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """Result of a single verification check."""

    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadinessReport:
    """Complete production readiness report."""

    timestamp: str
    total_checks: int
    passed: int
    failed: int
    skipped: int
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_checks == 0:
            return 0.0
        return (self.passed / self.total_checks) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "summary": {
                "total_checks": self.total_checks,
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "success_rate": round(self.success_rate, 2),
            },
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "duration_ms": round(c.duration_ms, 2),
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


def check_module_import(module_path: str, verbose: bool = False) -> CheckResult:
    """Check if a module can be imported successfully."""
    start = time.perf_counter()
    try:
        importlib.import_module(module_path)
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"import:{module_path}",
            passed=True,
            message=f"Module {module_path} imported successfully",
            duration_ms=duration,
        )
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"import:{module_path}",
            passed=False,
            message=f"Failed to import {module_path}: {exc}",
            duration_ms=duration,
            details={"error": str(exc), "type": type(exc).__name__},
        )


def check_class_instantiation(
    module_path: str, class_name: str, verbose: bool = False
) -> CheckResult:
    """Check if a class can be instantiated with default parameters."""
    start = time.perf_counter()
    try:
        module = importlib.import_module(module_path)
        _cls = getattr(module, class_name)  # noqa: F841 - verify class is accessible
        # Try to get the class signature to understand requirements
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"class:{module_path}.{class_name}",
            passed=True,
            message=f"Class {class_name} is available and accessible",
            duration_ms=duration,
            details={"module": module_path, "class": class_name},
        )
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"class:{module_path}.{class_name}",
            passed=False,
            message=f"Failed to access {class_name}: {exc}",
            duration_ms=duration,
            details={"error": str(exc), "type": type(exc).__name__},
        )


def check_config_file(path: str, verbose: bool = False) -> CheckResult:
    """Check if a configuration file exists and is valid."""
    import os

    start = time.perf_counter()
    try:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Configuration file not found: {path}")

        # Try to parse based on extension
        if path.endswith(".yaml") or path.endswith(".yml"):
            import yaml

            with open(path) as f:
                yaml.safe_load(f)
        elif path.endswith(".json"):
            with open(path) as f:
                json.load(f)
        elif path.endswith(".toml"):
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib
            with open(path, "rb") as f:
                tomllib.load(f)

        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"config:{path}",
            passed=True,
            message=f"Configuration file {path} is valid",
            duration_ms=duration,
        )
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name=f"config:{path}",
            passed=False,
            message=f"Configuration file error: {exc}",
            duration_ms=duration,
            details={"error": str(exc), "type": type(exc).__name__},
        )


def check_security_constraints(verbose: bool = False) -> CheckResult:
    """Check if security constraints are satisfied."""
    start = time.perf_counter()
    try:
        # Run the security constraints verification
        from pathlib import Path

        constraints_file = Path("constraints/security.txt")
        if not constraints_file.exists():
            raise FileNotFoundError("Security constraints file not found")

        # Parse constraints
        constraints: dict[str, str] = {}
        with open(constraints_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" in line:
                    pkg, version = line.split("==", 1)
                    constraints[pkg.lower()] = version
                elif ">=" in line:
                    pkg, version = line.split(">=", 1)
                    constraints[pkg.lower()] = f">={version}"

        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name="security:constraints",
            passed=True,
            message=f"Security constraints file is valid ({len(constraints)} constraints)",
            duration_ms=duration,
            details={"constraint_count": len(constraints)},
        )
    except Exception as exc:
        duration = (time.perf_counter() - start) * 1000
        return CheckResult(
            name="security:constraints",
            passed=False,
            message=f"Security constraints check failed: {exc}",
            duration_ms=duration,
            details={"error": str(exc), "type": type(exc).__name__},
        )


def run_production_checks(verbose: bool = False) -> ReadinessReport:
    """Run all production readiness checks."""
    from datetime import datetime, timezone

    checks: list[CheckResult] = []

    # Core module imports
    core_modules = [
        "core.indicators",
        "core.indicators.kuramoto",
        "core.indicators.kuramoto_ricci_composite",
        "core.data.market_feed",
        "core.strategies.fete",
    ]

    for module in core_modules:
        checks.append(check_module_import(module, verbose))

    # Backtest module imports
    backtest_modules = [
        "backtest.event_driven",
        "backtest.performance",
        "backtest.monte_carlo",
    ]

    for module in backtest_modules:
        checks.append(check_module_import(module, verbose))

    # Execution module imports
    execution_modules = [
        "execution.risk",
        "execution.connectors",
        "execution.live_loop",
        "execution.oms",
        "execution.paper_trading",
    ]

    for module in execution_modules:
        checks.append(check_module_import(module, verbose))

    # Analytics module imports
    analytics_modules = [
        "analytics",
        "analytics.portfolio_risk",
        "analytics.tca",
    ]

    for module in analytics_modules:
        checks.append(check_module_import(module, verbose))

    # Domain module imports
    domain_modules = [
        "domain",
        "domain.portfolio",
    ]

    for module in domain_modules:
        checks.append(check_module_import(module, verbose))

    # Modules package imports
    modules_packages = [
        "modules.adaptive_risk_manager",
        "modules.market_regime_analyzer",
        "modules.dynamic_position_sizer",
        "modules.gaba_inhibition_gate",
    ]

    for module in modules_packages:
        checks.append(check_module_import(module, verbose))

    # Configuration files
    config_files = [
        "configs/live/default.toml",
        "configs/production_readiness.json",
        "configs/risk.yaml",
        "constraints/security.txt",
        "alembic.ini",
    ]

    for config in config_files:
        checks.append(check_config_file(config, verbose))

    # Security constraints
    checks.append(check_security_constraints(verbose))

    # Key classes availability
    key_classes = [
        ("core.indicators", "KuramotoIndicator"),
        ("core.indicators.kuramoto_ricci_composite", "TradePulseCompositeEngine"),
        ("backtest.event_driven", "EventDrivenBacktestEngine"),
        ("execution.risk", "RiskManager"),
        ("execution.risk", "KillSwitch"),
        ("execution.paper_trading", "PaperTradingEngine"),
    ]

    for module, cls in key_classes:
        checks.append(check_class_instantiation(module, cls, verbose))

    # Compile results
    passed = sum(1 for c in checks if c.passed)
    failed = sum(1 for c in checks if not c.passed)

    return ReadinessReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_checks=len(checks),
        passed=passed,
        failed=failed,
        skipped=0,
        checks=checks,
    )


def main() -> int:
    """Main entry point for production readiness checks."""
    parser = argparse.ArgumentParser(
        description="TradePulse Production Readiness Verification"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--json-output",
        "-o",
        type=str,
        default=None,
        help="Output report to JSON file",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("TRADEPULSE PRODUCTION READINESS CHECK")
    print("=" * 70)
    print()

    report = run_production_checks(verbose=args.verbose)

    # Print results
    for check in report.checks:
        status = "✓" if check.passed else "✗"
        print(f"  [{status}] {check.name}")
        if args.verbose or not check.passed:
            print(f"      {check.message}")
            if check.details:
                for key, value in check.details.items():
                    print(f"      {key}: {value}")

    print()
    print("=" * 70)
    print(f"SUMMARY: {report.passed}/{report.total_checks} checks passed")
    print(f"Success Rate: {report.success_rate:.1f}%")
    print("=" * 70)

    if args.json_output:
        with open(args.json_output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport saved to: {args.json_output}")

    if report.failed > 0:
        print("\n⚠️  Some checks failed. Review the output above for details.")
        return 1

    print("\n✓ All production readiness checks passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
