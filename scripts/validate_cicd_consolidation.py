#!/usr/bin/env python3
"""
CI/CD Consolidation Validation Script

This script validates the new consolidated CI/CD pipeline and provides
metrics comparison with the old workflow setup.

Usage:
    python scripts/validate_cicd_consolidation.py [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


class CICDValidator:
    """Validates CI/CD consolidation implementation."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.workflows_dir = repo_root / ".github" / "workflows"
        self.actions_dir = repo_root / ".github" / "actions"
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_yaml_syntax(self) -> bool:
        """Validate YAML syntax of all workflow and action files."""
        print("🔍 Validating YAML syntax...")

        files_to_check = []
        files_to_check.extend(self.workflows_dir.glob("*.yml"))
        files_to_check.extend(self.actions_dir.glob("*/action.yml"))

        valid_count = 0
        for file_path in files_to_check:
            try:
                with open(file_path, "r") as f:
                    yaml.safe_load(f)
                valid_count += 1
            except yaml.YAMLError as e:
                self.errors.append(f"YAML syntax error in {file_path}: {e}")

        print(f"  ✅ {valid_count}/{len(files_to_check)} files have valid YAML syntax")
        return len(self.errors) == 0

    def validate_composite_actions(self) -> bool:
        """Validate composite action structure."""
        print("\n🔍 Validating composite actions...")

        required_actions = [
            "setup-python-env",
            "quality-gate",
            "run-tests",
        ]

        for action_name in required_actions:
            action_path = self.actions_dir / action_name / "action.yml"
            if not action_path.exists():
                self.errors.append(f"Missing action: {action_name}")
                continue

            try:
                with open(action_path, "r") as f:
                    action_data = yaml.safe_load(f)

                # Validate required fields
                required_fields = ["name", "description", "runs"]
                for field in required_fields:
                    if field not in action_data:
                        self.errors.append(
                            f"Action {action_name} missing required field: {field}"
                        )

                # Validate composite action structure
                if action_data.get("runs", {}).get("using") != "composite":
                    self.errors.append(
                        f"Action {action_name} is not a composite action"
                    )

                print(f"  ✅ {action_name}: Valid composite action")

            except Exception as e:
                self.errors.append(f"Error validating {action_name}: {e}")

        return len(self.errors) == 0

    def validate_consolidated_workflow(self) -> bool:
        """Validate the consolidated CI workflow."""
        print("\n🔍 Validating consolidated workflow...")

        workflow_path = self.workflows_dir / "consolidated-ci.yml"
        if not workflow_path.exists():
            self.errors.append("Missing consolidated-ci.yml workflow")
            return False

        try:
            with open(workflow_path, "r") as f:
                workflow_data = yaml.safe_load(f)

            # Validate workflow structure
            if "jobs" not in workflow_data:
                self.errors.append("Workflow missing 'jobs' section")
                return False

            jobs = workflow_data["jobs"]
            expected_jobs = [
                "quality-gate",
                "test-matrix",
                "test-e2e",
                "coverage-gate",
                "mutation-testing",
                "pipeline-status",
            ]

            found_jobs = list(jobs.keys())
            for job in expected_jobs:
                if job in found_jobs:
                    print(f"  ✅ Job '{job}' found")
                else:
                    self.warnings.append(f"Expected job '{job}' not found")

            # Validate composite action usage
            action_uses = 0
            for job_name, job_data in jobs.items():
                steps = job_data.get("steps", [])
                for step in steps:
                    if "uses" in step and step["uses"].startswith("./.github/actions/"):
                        action_uses += 1

            print(f"  ✅ Found {action_uses} composite action usages")

            if action_uses == 0:
                self.warnings.append(
                    "No composite actions used in consolidated workflow"
                )

        except Exception as e:
            self.errors.append(f"Error validating consolidated workflow: {e}")
            return False

        return True

    def analyze_workflow_complexity(self) -> Dict[str, int]:
        """Analyze and compare workflow complexity."""
        print("\n📊 Analyzing workflow complexity...")

        metrics = {
            "total_workflows": 0,
            "total_lines": 0,
            "workflows_with_pytest": 0,
            "composite_actions": 0,
        }

        # Count all workflows
        for workflow_path in self.workflows_dir.glob("*.yml"):
            if workflow_path.name.startswith("."):
                continue

            metrics["total_workflows"] += 1

            with open(workflow_path, "r") as f:
                content = f.read()
                metrics["total_lines"] += len(content.splitlines())

                if "pytest" in content.lower():
                    metrics["workflows_with_pytest"] += 1

        # Count composite actions
        for action_dir in self.actions_dir.iterdir():
            if action_dir.is_dir() and (action_dir / "action.yml").exists():
                metrics["composite_actions"] += 1

        print(f"  • Total workflows: {metrics['total_workflows']}")
        print(f"  • Total lines of YAML: {metrics['total_lines']}")
        print(f"  • Workflows with pytest: {metrics['workflows_with_pytest']}")
        print(f"  • Composite actions: {metrics['composite_actions']}")

        return metrics

    def validate_documentation(self) -> bool:
        """Validate that required documentation exists."""
        print("\n📚 Validating documentation...")

        required_docs = [
            "docs/architecture/cicd-consolidation.md",
            ".github/actions/README.md",
            ".github/workflows/MIGRATION_PLAN.md",
            "CICD_CONSOLIDATION_EXECUTIVE_SUMMARY.md",
        ]

        all_exist = True
        for doc_path in required_docs:
            full_path = self.repo_root / doc_path
            if full_path.exists():
                size = full_path.stat().st_size
                print(f"  ✅ {doc_path} ({size:,} bytes)")
            else:
                self.errors.append(f"Missing documentation: {doc_path}")
                all_exist = False

        return all_exist

    def generate_report(self) -> Dict:
        """Generate validation report."""
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "status": "PASS" if len(self.errors) == 0 else "FAIL",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Validate CI/CD consolidation implementation"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON"
    )
    args = parser.parse_args()

    # Find repository root
    repo_root = Path(__file__).parent.parent
    if not (repo_root / ".github").exists():
        print("❌ Could not find .github directory")
        sys.exit(1)

    print("=" * 70)
    print("CI/CD Consolidation Validation")
    print("=" * 70)

    validator = CICDValidator(repo_root)

    # Run validations
    yaml_valid = validator.validate_yaml_syntax()
    actions_valid = validator.validate_composite_actions()
    workflow_valid = validator.validate_consolidated_workflow()
    docs_valid = validator.validate_documentation()

    # Analyze complexity
    metrics = validator.analyze_workflow_complexity()

    # Generate report
    report = validator.generate_report()

    print("\n" + "=" * 70)
    print("Validation Summary")
    print("=" * 70)

    if report["status"] == "PASS":
        print("✅ All validations PASSED")
    else:
        print("❌ Validation FAILED")

    if report["errors"]:
        print(f"\n❌ Errors ({len(report['errors'])}):")
        for error in report["errors"]:
            print(f"   • {error}")

    if report["warnings"]:
        print(f"\n⚠️  Warnings ({len(report['warnings'])}):")
        for warning in report["warnings"]:
            print(f"   • {warning}")

    print("\n📊 Metrics:")
    print(f"   • Total workflows: {metrics['total_workflows']}")
    print(f"   • Composite actions: {metrics['composite_actions']}")
    print(f"   • Workflows with pytest: {metrics['workflows_with_pytest']}")

    if args.json:
        output = {
            "status": report["status"],
            "errors": report["errors"],
            "warnings": report["warnings"],
            "metrics": metrics,
        }
        print("\n" + json.dumps(output, indent=2))

    print("=" * 70)

    sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
