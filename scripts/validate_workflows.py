#!/usr/bin/env python3
"""
Validate GitHub Actions workflows for common issues.

2025 Best Practice: Catch workflow problems before pushing to CI.

Usage:
    python scripts/validate_workflows.py

Exit codes:
    0 - All checks passed
    1 - Critical issues found
    2 - Warnings found (non-blocking)
"""

import sys
import yaml
from pathlib import Path
from typing import List, Dict, Tuple


class WorkflowValidator:
    """Validates GitHub Actions workflow files."""
    
    def __init__(self, workflows_dir: Path):
        self.workflows_dir = workflows_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> Tuple[int, int]:
        """Validate all workflow files. Returns (errors, warnings) count."""
        workflow_files = list(self.workflows_dir.glob("*.yml"))
        workflow_files += list(self.workflows_dir.glob("*.yaml"))
        
        if not workflow_files:
            self.errors.append(f"No workflow files found in {self.workflows_dir}")
            return len(self.errors), len(self.warnings)
        
        print(f"🔍 Validating {len(workflow_files)} workflow files...\n")
        
        for workflow_file in sorted(workflow_files):
            self._validate_workflow(workflow_file)
        
        return len(self.errors), len(self.warnings)
    
    def _validate_workflow(self, workflow_file: Path) -> None:
        """Validate a single workflow file."""
        print(f"Checking {workflow_file.name}...")
        
        try:
            with open(workflow_file) as f:
                workflow = yaml.safe_load(f)
        except yaml.YAMLError as e:
            self.errors.append(f"{workflow_file.name}: Invalid YAML - {e}")
            return
        
        if not isinstance(workflow, dict):
            self.errors.append(f"{workflow_file.name}: Root element must be a dictionary")
            return
        
        # Check required top-level keys
        if 'name' not in workflow:
            self.warnings.append(f"{workflow_file.name}: Missing 'name' field")
        
        if 'on' not in workflow:
            self.errors.append(f"{workflow_file.name}: Missing 'on' trigger configuration")
        
        if 'jobs' not in workflow:
            self.errors.append(f"{workflow_file.name}: Missing 'jobs' section")
            return
        
        # Validate permissions
        self._check_permissions(workflow_file.name, workflow)
        
        # Validate jobs
        jobs = workflow.get('jobs', {})
        for job_name, job_config in jobs.items():
            self._validate_job(workflow_file.name, job_name, job_config)
        
        # Check for deprecated actions
        self._check_deprecated_actions(workflow_file.name, workflow)
        
        print(f"  ✓ {workflow_file.name} validated\n")
    
    def _check_permissions(self, filename: str, workflow: Dict) -> None:
        """Check if permissions are properly scoped."""
        permissions = workflow.get('permissions')
        
        if permissions is None:
            self.warnings.append(
                f"{filename}: No 'permissions' specified. "
                "Best practice: explicitly declare required permissions"
            )
        elif isinstance(permissions, str) and permissions == 'write-all':
            self.warnings.append(
                f"{filename}: Using 'write-all' permissions. "
                "Best practice: use least privilege principle"
            )
    
    def _validate_job(self, filename: str, job_name: str, job_config: Dict) -> None:
        """Validate individual job configuration."""
        if not isinstance(job_config, dict):
            self.errors.append(f"{filename}: Job '{job_name}' is not a dictionary")
            return
        
        # Check for timeout
        if 'timeout-minutes' not in job_config:
            self.warnings.append(
                f"{filename}: Job '{job_name}' missing 'timeout-minutes'. "
                "2025 best practice: always set explicit timeouts"
            )
        
        # Check runs-on
        if 'runs-on' not in job_config and 'uses' not in job_config:
            self.errors.append(
                f"{filename}: Job '{job_name}' missing 'runs-on' or 'uses'"
            )
        
        # Validate steps
        steps = job_config.get('steps', [])
        if steps and not isinstance(steps, list):
            self.errors.append(f"{filename}: Job '{job_name}' steps must be a list")
            return
        
        for i, step in enumerate(steps):
            self._validate_step(filename, job_name, i, step)
    
    def _validate_step(self, filename: str, job_name: str, 
                       step_index: int, step: Dict) -> None:
        """Validate individual step configuration."""
        if not isinstance(step, dict):
            self.errors.append(
                f"{filename}: Job '{job_name}' step {step_index} is not a dictionary"
            )
            return
        
        # Check for name (best practice)
        if 'name' not in step:
            self.warnings.append(
                f"{filename}: Job '{job_name}' step {step_index} missing 'name'. "
                "Best practice: name all steps for better readability"
            )
        
        # Check for action or run
        if 'uses' not in step and 'run' not in step:
            self.errors.append(
                f"{filename}: Job '{job_name}' step {step_index} "
                "must have either 'uses' or 'run'"
            )
        
        # Check for long-running steps without timeout
        if 'run' in step:
            run_command = step['run']
            if any(cmd in run_command for cmd in ['pytest', 'npm test', 'go test']):
                if 'timeout-minutes' not in step:
                    self.warnings.append(
                        f"{filename}: Job '{job_name}' step {step_index} "
                        "runs tests without timeout. Consider adding 'timeout-minutes'"
                    )
    
    def _check_deprecated_actions(self, filename: str, workflow: Dict) -> None:
        """Check for usage of deprecated actions."""
        deprecated_actions = {
            'actions/checkout@v2': 'Update to actions/checkout@v5',
            'actions/setup-python@v2': 'Update to actions/setup-python@v6',
            'actions/upload-artifact@v2': 'Update to actions/upload-artifact@v4',
            'actions/cache@v2': 'Update to actions/cache@v4',
        }
        
        workflow_str = yaml.dump(workflow)
        for old_action, message in deprecated_actions.items():
            if old_action in workflow_str:
                self.warnings.append(f"{filename}: {message}")
    
    def print_results(self) -> None:
        """Print validation results."""
        print("\n" + "=" * 70)
        print("VALIDATION RESULTS")
        print("=" * 70 + "\n")
        
        if self.errors:
            print("❌ ERRORS:")
            for error in self.errors:
                print(f"  - {error}")
            print()
        
        if self.warnings:
            print("⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
            print()
        
        if not self.errors and not self.warnings:
            print("✅ All workflows passed validation!")
        else:
            print(f"Found {len(self.errors)} error(s) and {len(self.warnings)} warning(s)")


def main() -> int:
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    workflows_dir = repo_root / ".github" / "workflows"
    
    if not workflows_dir.exists():
        print(f"❌ Workflows directory not found: {workflows_dir}")
        return 1
    
    validator = WorkflowValidator(workflows_dir)
    errors, warnings = validator.validate_all()
    validator.print_results()
    
    if errors > 0:
        print("\n❌ Validation failed with critical errors")
        return 1
    elif warnings > 0:
        print("\n⚠️  Validation passed with warnings")
        return 2
    else:
        print("\n✅ All validations passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
