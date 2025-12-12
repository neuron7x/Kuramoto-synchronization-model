"""Interactive production readiness checklist CLI."""

from __future__ import annotations

import argparse

from tools.production_gates import GateStatus, ProductionGateValidator

MANUAL_ITEMS = [
    "Secrets rotated within 90 days",
    "Incident runbooks tested",
    "Disaster recovery plan validated",
    "Stakeholder sign-off obtained",
    "Production environment provisioned",
    "Monitoring dashboards reviewed",
    "SLA targets documented",
]


def _prompt_manual_items() -> list[bool]:
    """Prompt the operator to confirm manual checklist items."""
    results: list[bool] = []
    for item in MANUAL_ITEMS:
        answer = input(f"✓ {item} [y/N]: ").strip().lower()
        results.append(answer.startswith("y"))
    return results


def cmd_validate() -> None:
    """Run automated gate validation."""
    validator = ProductionGateValidator()
    statuses = validator.as_report_payload()
    print("\n=== Production Gate Results ===\n")
    for name, payload in statuses.items():
        symbol = payload["symbol"]
        severity = payload["severity"]
        desc = payload["description"]
        print(f"{symbol} {name} ({severity}): {desc}")

    passed = sum(1 for p in statuses.values() if p["status"] == GateStatus.PASS.name)
    total = len(statuses)
    if passed == total:
        print("\n✅ All automated gates passed! Ready for production.\n")
    else:
        print(f"\n❌ {total - passed} gates failed or pending.\n")


def cmd_manual() -> None:
    """Run interactive manual checklist."""
    print("\n=== Manual Production Checklist ===\n")
    completed = _prompt_manual_items()
    if all(completed):
        print("\n✅ Manual checklist complete!\n")
        return

    pending = (item for item, done in zip(MANUAL_ITEMS, completed) if not done)
    print("\n⚠️  Pending items:")
    for item in pending:
        print(f"  - {item}")
    print()


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Production readiness checklist CLI")
    parser.add_argument(
        "command",
        choices=["validate", "manual"],
        help="Run automated validation or interactive manual checklist",
    )
    args = parser.parse_args()

    if args.command == "validate":
        cmd_validate()
    else:
        cmd_manual()


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    main()
