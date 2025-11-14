#!/usr/bin/env python3
"""Validate GitHub Actions workflow YAML files.

This script validates all workflow files in .github/workflows/ for:
1. Valid YAML syntax
2. Correct heredoc syntax (using <<- with tab indentation)
3. Common workflow issues

Usage:
    python scripts/validate_workflows.py
    
Exit codes:
    0 - All workflows valid
    1 - Validation errors found
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

import yaml


def find_workflow_files(workflows_dir: Path) -> List[Path]:
    """Find all YAML workflow files."""
    return sorted(workflows_dir.glob("*.yml"))


def validate_yaml_syntax(workflow_path: Path) -> Tuple[bool, str]:
    """Validate YAML syntax of a workflow file.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with open(workflow_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True, ""
    except yaml.YAMLError as e:
        return False, str(e)


def check_heredoc_syntax(workflow_path: Path) -> List[str]:
    """Check for heredoc syntax issues.
    
    Returns:
        List of warning messages
    """
    warnings = []
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.splitlines()
    
    # Find heredoc start markers with <<'DELIMITER'
    heredoc_pattern = re.compile(r"<<(['\"]?)(\w+)\1")
    
    for i, line in enumerate(lines, 1):
        match = heredoc_pattern.search(line)
        if match:
            delimiter = match.group(2)
            uses_dash = "<<-" in line
            
            # Find the closing delimiter
            found_closing = False
            closing_line_num = None
            for j in range(i, min(i + 200, len(lines) + 1)):  # Look ahead max 200 lines
                if j <= len(lines) and lines[j - 1].strip() == delimiter:
                    found_closing = True
                    closing_line_num = j
                    # Check if closing delimiter is indented with spaces
                    closing_line = lines[j - 1]
                    if closing_line != delimiter and not uses_dash:
                        warnings.append(
                            f"Line {j}: Heredoc closing marker '{delimiter}' is indented but "
                            f"'<<' (not '<<-') was used. Use '<<-' to allow indented markers."
                        )
                    elif uses_dash and closing_line.startswith(' '):
                        warnings.append(
                            f"Line {j}: Heredoc closing marker '{delimiter}' is indented with spaces. "
                            f"When using '<<-', use tabs (not spaces) for indentation."
                        )
                    break
            
            if not found_closing:
                warnings.append(
                    f"Line {i}: Heredoc starting with '{delimiter}' has no closing marker found "
                    f"within 200 lines. This may cause shell syntax errors."
                )
    
    return warnings


def main() -> int:
    """Main validation function."""
    repo_root = Path(__file__).parent.parent
    workflows_dir = repo_root / ".github" / "workflows"
    
    if not workflows_dir.exists():
        print(f"❌ Workflows directory not found: {workflows_dir}", file=sys.stderr)
        return 1
    
    workflow_files = find_workflow_files(workflows_dir)
    
    if not workflow_files:
        print(f"⚠️  No workflow files found in {workflows_dir}", file=sys.stderr)
        return 0
    
    print(f"🔍 Validating {len(workflow_files)} workflow files...\n")
    
    errors_found = False
    warnings_found = False
    
    for workflow_path in workflow_files:
        workflow_name = workflow_path.name
        
        # Validate YAML syntax
        is_valid, error_msg = validate_yaml_syntax(workflow_path)
        if not is_valid:
            print(f"❌ {workflow_name}: YAML syntax error")
            print(f"   {error_msg}\n")
            errors_found = True
            continue
        
        # Check heredoc syntax
        warnings = check_heredoc_syntax(workflow_path)
        if warnings:
            print(f"⚠️  {workflow_name}: Heredoc syntax warnings")
            for warning in warnings:
                print(f"   {warning}")
            print()
            warnings_found = True
        else:
            print(f"✅ {workflow_name}")
    
    print("\n" + "="*60)
    if errors_found:
        print("❌ Validation failed: Errors found in workflow files")
        return 1
    elif warnings_found:
        print("⚠️  Validation passed with warnings")
        print("   Consider reviewing heredoc syntax for better shell compatibility")
        return 0
    else:
        print(f"✅ All {len(workflow_files)} workflow files validated successfully")
        return 0


if __name__ == "__main__":
    sys.exit(main())
