#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Validation script for DOC PR COPILOT v2 agent configuration.

This script verifies that the agent configuration files are properly structured
and contain all required sections.
"""

import json
import sys
from pathlib import Path


def validate_agent_prompt(prompt_file: Path) -> tuple[bool, list[str]]:
    """Validate that agent prompt file contains required sections."""
    errors = []

    if not prompt_file.exists():
        return False, [f"File not found: {prompt_file}"]

    content = prompt_file.read_text(encoding="utf-8")

    # Check for required sections
    required_sections = [
        "## 0. РОЛЬ",
        "## 1. СКОП",
        "## 2. СТАНДАРТ МОВИ (4C + CNL)",
        "## 3. ВХІДНІ ДАНІ",
        "## 4. РОБОЧИЙ ЦИКЛ (PLAN → ACT → REFLECT)",
        "## 5. ОБМЕЖЕННЯ ТА НЕВИЗНАЧЕНІСТЬ",
        "## 6. ФОРМАТ ВІДПОВІДІ (ДЛЯ PR-БОТА)",
        "## 7. ВНУТРІШНІ ПРИНЦИПИ",
    ]

    for section in required_sections:
        if section not in content:
            errors.append(f"Missing required section: {section}")

    # Check for key subsections in output format
    output_subsections = [
        "### 6.1. DOC_SUMMARY",
        "### 6.2. DOC_PATCHES",
        "### 6.3. REVIEW_NOTES",
    ]

    for subsection in output_subsections:
        if subsection not in content:
            errors.append(f"Missing required subsection: {subsection}")

    # Check for workflow phases
    workflow_phases = ["PLAN", "ACT", "REFLECT"]
    for phase in workflow_phases:
        if f"### {phase}" not in content:
            errors.append(f"Missing workflow phase: {phase}")

    return len(errors) == 0, errors


def validate_schema(schema_file: Path) -> tuple[bool, list[str]]:
    """Validate that JSON schema is valid JSON."""
    errors = []

    if not schema_file.exists():
        return False, [f"File not found: {schema_file}"]

    try:
        with open(schema_file, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # Basic schema structure checks
        if "$schema" not in schema:
            errors.append("Missing $schema property")

        if "title" not in schema:
            errors.append("Missing title property")

    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    return len(errors) == 0, errors


def validate_documentation(doc_file: Path, required_sections: list[str]) -> tuple[bool, list[str]]:
    """Validate that documentation contains required sections."""
    errors = []

    if not doc_file.exists():
        return False, [f"File not found: {doc_file}"]

    content = doc_file.read_text(encoding="utf-8")

    for section in required_sections:
        if section not in content:
            errors.append(f"Missing section: {section}")

    return len(errors) == 0, errors


def main():
    """Run all validation checks."""
    agents_dir = Path(__file__).parent

    print("🔍 Validating DOC PR COPILOT v2 Agent Configuration...")
    print()

    all_valid = True

    # Validate main agent prompt
    print("1. Validating agent prompt (doc-pr-copilot-v2.md)...")
    valid, errors = validate_agent_prompt(agents_dir / "doc-pr-copilot-v2.md")
    if valid:
        print("   ✅ Agent prompt is valid")
    else:
        print("   ❌ Agent prompt validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate schema
    print("2. Validating schema (schema.json)...")
    valid, errors = validate_schema(agents_dir / "schema.json")
    if valid:
        print("   ✅ Schema is valid")
    else:
        print("   ❌ Schema validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate README
    print("3. Validating README (README.md)...")
    valid, errors = validate_documentation(
        agents_dir / "README.md", ["## Available Agents", "### DOC PR COPILOT v2"]
    )
    if valid:
        print("   ✅ README is valid")
    else:
        print("   ❌ README validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate Integration Guide
    print("4. Validating Integration Guide (INTEGRATION.md)...")
    valid, errors = validate_documentation(
        agents_dir / "INTEGRATION.md",
        ["## DOC PR COPILOT v2 Integration", "### GitHub Actions Workflow Example"],
    )
    if valid:
        print("   ✅ Integration guide is valid")
    else:
        print("   ❌ Integration guide validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate 4C Principles
    print("5. Validating 4C Principles (4C-PRINCIPLES.md)...")
    valid, errors = validate_documentation(
        agents_dir / "4C-PRINCIPLES.md",
        [
            "## The 4C Framework",
            "### 1. Clarity",
            "### 2. Conciseness",
            "### 3. Correctness",
            "### 4. Consistency",
        ],
    )
    if valid:
        print("   ✅ 4C Principles documentation is valid")
    else:
        print("   ❌ 4C Principles validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Final result
    print("=" * 60)
    if all_valid:
        print("✅ All validation checks passed!")
        return 0
    else:
        print("❌ Some validation checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
