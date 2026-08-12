#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Validation script for Fractal Tech Debt Engine v2.0 agent configuration.

This script verifies that the agent configuration files are properly structured
and contain all required sections as specified in the system prompt.
"""

import sys
from pathlib import Path


def validate_agent_prompt(prompt_file: Path) -> tuple[bool, list[str]]:
    """Validate that agent prompt file contains required sections."""
    errors = []

    if not prompt_file.exists():
        return False, [f"File not found: {prompt_file}"]

    content = prompt_file.read_text(encoding="utf-8")

    # Check for required sections (0-16)
    required_sections = [
        "## 0. ІДЕНТИЧНІСТЬ",
        "## 1. МІСІЯ ТА РЕЗУЛЬТАТ",
        "## 2. РЕЖИМИ РОБОТИ (AGGRESSIVENESS MODES)",
        "## 3. НАУКОВО-ІНЖЕНЕРНА ОСНОВА",
        "## 4. ФРАКТАЛЬНІ РІВНІ АНАЛІЗУ",
        "## 5. ФРАКТАЛЬНИЙ ПРОТОКОЛ ОЦІНКИ (ОСНОВНИЙ ЦИКЛ)",
        "## 6. ТАКСОНОМІЯ ТЕХНІЧНОГО БОРГУ",
        "## 7. ПРІОРИТЕТИ ТА РИЗИК",
        "## 8. ПРАВИЛА БЕЗПЕКИ ЗМІН",
        "## 9. ІНСТРУМЕНТИ ТА ФАКТИЧНА БАЗА (TOOL-USE)",
        "## 10. АНТИ-ГАЛЮЦИНАЦІЙНІ ПРАВИЛА",
        "## 11. КОНТРОЛЬ ОБСЯГУ ЗМІН (PATCH BUDGET)",
        "## 12. СТЕК ТА ІДІОМАТИЧНА ПОВЕДІНКА",
        "## 13. ТЕСТИ ТА СПОСТЕРЕЖУВАНІСТЬ ПЕРШИМИ",
        "## 14. РОБОТА З НЕПОВНИМ КОНТЕКСТОМ",
        "## 15. ФОРМАТИ ВИХОДУ",
        "## 16. СТИЛЬ ВІДПОВІДЕЙ",
    ]

    for section in required_sections:
        if section not in content:
            errors.append(f"Missing required section: {section}")

    # Check for operational modes
    operational_modes = ["CONSERVATIVE", "STANDARD", "AGGRESSIVE"]
    for mode in operational_modes:
        if f"**Mode: {mode}**" not in content:
            errors.append(f"Missing operational mode: {mode}")

    # Check for fractal levels (L0-L4)
    fractal_levels = ["L0:", "L1:", "L2:", "L3:", "L4:"]
    for level in fractal_levels:
        if level not in content:
            errors.append(f"Missing fractal analysis level: {level}")

    # Check for 5-step fractal protocol
    protocol_steps = [
        "INTENT",
        "MISMATCH",
        "REFACTOR PLAN",
        "SAFE PATCH",
        "VERIFY LOOP",
    ]
    protocol_line = " → ".join(protocol_steps)
    if protocol_line not in content:
        errors.append(f"Missing or incomplete fractal protocol: {protocol_line}")

    # Check for technical debt taxonomy (9 types)
    debt_types = [
        "DESIGN_DEBT",
        "CODE_STYLE_DEBT",
        "COMPLEXITY_DEBT",
        "TESTING_DEBT",
        "OBSERVABILITY_DEBT",
        "SECURITY_DEBT",
        "PERFORMANCE_DEBT",
        "DATA_QUALITY_DEBT",
        "EXPERIMENT_REPRO_DEBT",
    ]
    for debt_type in debt_types:
        if f"**{debt_type}**" not in content:
            errors.append(f"Missing technical debt type: {debt_type}")

    # Check for priority levels
    priority_levels = ["HIGH/CRITICAL", "MEDIUM", "LOW"]
    for priority in priority_levels:
        if f"**{priority}**" not in content:
            errors.append(f"Missing priority level: {priority}")

    # Check for output formats
    output_formats = ["TECH_DEBT_REPORT", "GITHUB_REVIEW_COMMENTS", "PATCH_ONLY"]
    for output_format in output_formats:
        if f"**{output_format}" not in content:
            errors.append(f"Missing output format: {output_format}")

    # Check for subsections in fractal protocol
    protocol_subsections = [
        "**5.1. INTENT",
        "**5.2. MISMATCH",
        "**5.3. REFACTOR PLAN",
        "**5.4. SAFE PATCH",
        "**5.5. VERIFY LOOP",
    ]
    for subsection in protocol_subsections:
        if subsection not in content:
            errors.append(f"Missing protocol subsection: {subsection}")

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

    print("🔍 Validating Fractal Tech Debt Engine v2.0 Agent Configuration...")
    print()

    all_valid = True

    # Validate main agent prompt
    print("1. Validating agent prompt (fractal-tech-debt-engine-v2.md)...")
    valid, errors = validate_agent_prompt(agents_dir / "fractal-tech-debt-engine-v2.md")
    if valid:
        print("   ✅ Agent prompt is valid")
    else:
        print("   ❌ Agent prompt validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate README contains Fractal Tech Debt Engine entry
    print("2. Validating README (README.md)...")
    valid, errors = validate_documentation(
        agents_dir / "README.md",
        ["## Available Agents", "### FRACTAL TECH DEBT ENGINE v2.0"],
    )
    if valid:
        print("   ✅ README is valid")
    else:
        print("   ❌ README validation failed:")
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
