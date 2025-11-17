"""Robust benchmark comparison script for CI performance regression detection.

This script compares benchmark results between PR and base branches,
handling missing data gracefully and providing detailed regression analysis.
"""

import json
import os
import sys


def load_json(path):
    """Load benchmark JSON file with error handling.

    Args:
        path: Path to JSON file

    Returns:
        Benchmark data dict if valid, None if file missing or invalid
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
            # Validate structure
            return data if data.get("benchmarks") else None
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return None


def main():
    """Main comparison logic."""
    pr_data = load_json("pr-benchmark.json")
    base_data = load_json("base-benchmark.json")

    # Handle missing data gracefully
    if pr_data is None and base_data is None:
        print("No benchmark data for PR and base. Exiting without regression.")
        # Write empty comparison to avoid CI parse errors
        with open("comparison.json", "w") as f:
            json.dump({"regressions": [], "improvements": []}, f, indent=2)
        sys.exit(0)

    if pr_data is None or base_data is None:
        missing = "PR" if pr_data is None else "base"
        print(
            f"Partial benchmark data ({missing} missing). Skipping regression detection."
        )
        # Write empty comparison to avoid CI parse errors
        with open("comparison.json", "w") as f:
            json.dump({"regressions": [], "improvements": []}, f, indent=2)
        sys.exit(0)

    # Both datasets available - perform comparison
    pr_benchmarks = {b["name"]: b for b in pr_data.get("benchmarks", [])}
    base_benchmarks = {b["name"]: b for b in base_data.get("benchmarks", [])}

    if not pr_benchmarks or not base_benchmarks:
        print("No benchmark results found in one or both files.")
        with open("comparison.json", "w") as f:
            json.dump({"regressions": [], "improvements": []}, f, indent=2)
        sys.exit(0)

    regressions = []
    improvements = []
    threshold = 1.10  # 10% threshold
    critical_threshold = 25.0  # 25% critical threshold

    for name, pr_bench in pr_benchmarks.items():
        if name in base_benchmarks:
            base_bench = base_benchmarks[name]

            pr_mean = pr_bench["stats"]["mean"]
            base_mean = base_bench["stats"]["mean"]

            if base_mean <= 0:
                continue

            ratio = pr_mean / base_mean
            change_pct = (ratio - 1) * 100

            if ratio > threshold:
                regressions.append(
                    {
                        "name": name,
                        "base": base_mean,
                        "pr": pr_mean,
                        "ratio": ratio,
                        "change": change_pct,
                    }
                )
            elif ratio < (1 / threshold):
                improvements.append(
                    {
                        "name": name,
                        "base": base_mean,
                        "pr": pr_mean,
                        "ratio": ratio,
                        "change": (1 - ratio) * 100,
                    }
                )

    print(f"REGRESSIONS={len(regressions)}")
    print(f"IMPROVEMENTS={len(improvements)}")

    if regressions:
        print("\n⚠️  Performance Regressions Detected:")
        for r in sorted(regressions, key=lambda x: x["change"], reverse=True)[:5]:
            print(f"  - {r['name']}: +{r['change']:.1f}% slower")

    if improvements:
        print("\n✅ Performance Improvements:")
        for i in sorted(improvements, key=lambda x: x["change"], reverse=True)[:5]:
            print(f"  - {i['name']}: +{i['change']:.1f}% faster")

    # Write results
    with open("comparison.json", "w") as f:
        json.dump(
            {"regressions": regressions, "improvements": improvements}, f, indent=2
        )

    # Exit with error if significant regressions
    if len(regressions) > 0:
        max_regression = max(r["change"] for r in regressions)
        if max_regression > critical_threshold:
            print(f"\n❌ Critical regression detected: {max_regression:.1f}%")
            sys.exit(1)

    print("\n✅ Performance check passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
