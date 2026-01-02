"""Performance budget validation tool.

Validates that component performance metrics stay within defined budgets.
Used in CI gates to prevent performance regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML configuration file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON results file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_budgets(
    config_path: Path, results_path: Path, fail_on_breach: bool = False
) -> int:
    """Validate performance budgets against actual results.

    Args:
        config_path: Path to perf_budgets.yaml configuration
        results_path: Path to test-performance.json results
        fail_on_breach: Whether to exit with error on budget breach

    Returns:
        Exit code: 0 if all budgets met, 1 if any breach detected
    """
    try:
        config = load_yaml(config_path)
    except FileNotFoundError:
        print(f"❌ Config file not found: {config_path}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Error loading config: {e}", file=sys.stderr)
        return 1

    try:
        results = load_json(results_path)
    except FileNotFoundError:
        print(f"⚠️ Results file not found: {results_path}", file=sys.stderr)
        print("Skipping performance budget validation")
        return 0
    except Exception as e:
        print(f"❌ Error loading results: {e}", file=sys.stderr)
        return 1

    if "components" not in config:
        print("⚠️ No components defined in config, skipping validation")
        return 0

    components = config["components"]
    breaches = []
    passes = []

    # Validate each component
    for component_name, budget in components.items():
        budget_ms = budget.get("budget_ms")
        if budget_ms is None:
            print(f"⚠️ No budget_ms defined for {component_name}, skipping")
            continue

        # Look for component in results
        observed_ms = None
        if "components" in results and component_name in results["components"]:
            observed_ms = results["components"][component_name].get("duration_ms")
        elif component_name in results:
            observed_ms = results[component_name].get("duration_ms")

        if observed_ms is None:
            print(f"⚠️ No results found for {component_name}, skipping")
            continue

        # Check budget
        if observed_ms > budget_ms:
            breaches.append(
                {
                    "component": component_name,
                    "observed_ms": observed_ms,
                    "budget_ms": budget_ms,
                    "overage_ms": observed_ms - budget_ms,
                    "overage_pct": ((observed_ms - budget_ms) / budget_ms) * 100,
                }
            )
        else:
            passes.append(
                {
                    "component": component_name,
                    "observed_ms": observed_ms,
                    "budget_ms": budget_ms,
                }
            )

    # Report results
    print("\n### Performance Budget Validation\n")
    print(f"Validated {len(passes) + len(breaches)} components\n")

    if passes:
        print("✅ **Passing Components:**")
        for item in passes:
            print(
                f"  - {item['component']}: {item['observed_ms']:.1f}ms "
                f"/ {item['budget_ms']:.1f}ms"
            )
        print()

    if breaches:
        print("❌ **Budget Breaches:**")
        for breach in breaches:
            print(
                f"  - {breach['component']}: {breach['observed_ms']:.1f}ms "
                f"/ {breach['budget_ms']:.1f}ms "
                f"(+{breach['overage_ms']:.1f}ms, +{breach['overage_pct']:.1f}%)"
            )
        print()

        if fail_on_breach:
            print(f"❌ {len(breaches)} component(s) exceeded performance budget")
            return 1
        else:
            print(
                f"⚠️ {len(breaches)} component(s) exceeded performance budget "
                "(not failing due to --fail-on-breach not set)"
            )
            return 0

    print("✅ All components within performance budget")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate performance budgets against test results"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to perf_budgets.yaml configuration",
    )
    parser.add_argument(
        "--results",
        type=Path,
        required=True,
        help="Path to test-performance.json results",
    )
    parser.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit with error code if any budget is breached",
    )

    args = parser.parse_args()

    return validate_budgets(args.config, args.results, args.fail_on_breach)


if __name__ == "__main__":
    sys.exit(main())
