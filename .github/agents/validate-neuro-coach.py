#!/usr/bin/env python3
"""
Validation script for NEURO-AI DISTINGUISHED ENGINEERING COACH v1.0 agent configuration.

This script verifies that the agent configuration file is properly structured
and contains all required sections.
"""

import sys
from pathlib import Path


def validate_neuro_coach_agent(prompt_file: Path) -> tuple[bool, list[str]]:
    """Validate that agent prompt file contains required sections."""
    errors = []

    if not prompt_file.exists():
        return False, [f"File not found: {prompt_file}"]

    content = prompt_file.read_text(encoding="utf-8")

    # Check for required sections
    required_sections = [
        "## 0. СИСТЕМНА РОЛЬ",
        "## 1. ВХІДНІ ДАНІ (INPUT)",
        "## 2. ГЛОБАЛЬНІ МЕТРИКИ УСПІХУ",
        "## 3. ЖОРСТКІ ПРАВИЛА (NON-NEGOTIABLE)",
        "## 4. РОБОЧИЙ ЦИКЛ ОДНІЄЇ СЕСІЇ",
        "## 5. ДОВГОСТРОКОВИЙ ПРОТОКОЛ (PHASES)",
        "## 6. СТИЛЬ ВІДПОВІДІ",
        "## 7. ФОРМАТ ВІДПОВІДІ",
        "## 8. ОБМЕЖЕННЯ ТА ПРИНЦИПИ",
        "## 9. СПЕЦІАЛІЗАЦІЯ: NEUROSCIENCE-GROUNDED LLM SYSTEMS",
    ]

    for section in required_sections:
        if section not in content:
            errors.append(f"Missing required section: {section}")

    # Check for key subsections in global metrics
    metric_subsections = [
        "### A. ENGINEERING / CODE",
        "### B. IMPACT / РИНОК",
        "### C. РЕПУТАЦІЯ / ПІДТВЕРДЖЕННЯ",
        "### D. INTERNAL SKILL SCORE (0–100)",
    ]

    for subsection in metric_subsections:
        if subsection not in content:
            errors.append(f"Missing required subsection: {subsection}")

    # Check for workflow steps
    workflow_steps = [
        "### STEP 0 — СКАН КОНТЕКСТУ",
        "### STEP 1 — ПЛАН СЕСІЇ (3–7 задач)",
        "### STEP 2 — ПРІОРИТЕТИ",
        "### STEP 3 — КОНТРОЛЬ ЯКОСТІ",
        "### STEP 4 — ПІДСУМОК СЕСІЇ",
    ]

    for step in workflow_steps:
        if step not in content:
            errors.append(f"Missing workflow step: {step}")

    # Check for phases
    phases = [
        "### PHASE 1 — INVENTORY & CLEANUP",
        "### PHASE 2 — ОДИН ФЛАГМАНСЬКИЙ ПРОДУКТ",
        "### PHASE 3 — ВАЛІДАЦІЯ РИНКОМ",
        "### PHASE 4 — ПУБЛІЧНИЙ МАНІФЕСТ / ДОКЛАД",
        "### PHASE 5 — СТАБІЛЬНИЙ РИТМ",
    ]

    for phase in phases:
        if phase not in content:
            errors.append(f"Missing phase: {phase}")

    # Check for output format sections
    output_sections = [
        "### 7.1. CONTEXT_SCAN",
        "### 7.2. SESSION_PLAN",
        "### 7.3. QUALITY_CONTROLS",
        "### 7.5. SESSION_IMPACT",
        "### 7.6. SKILL_ASSESSMENT",
    ]

    for section in output_sections:
        if section not in content:
            errors.append(f"Missing output format section: {section}")

    return len(errors) == 0, errors


def validate_readme_updated(readme_file: Path) -> tuple[bool, list[str]]:
    """Validate that README contains the new agent documentation."""
    errors = []

    if not readme_file.exists():
        return False, [f"File not found: {readme_file}"]

    content = readme_file.read_text(encoding="utf-8")

    # Check for agent entry in README
    if "### NEURO-AI DISTINGUISHED ENGINEERING COACH v1.0" not in content:
        errors.append("Agent not documented in README")

    if "neuro-ai-engineering-coach.md" not in content:
        errors.append("Agent file not referenced in README")

    # Check for key documentation elements
    key_elements = [
        "Personal engineering coach",
        "Phase-based progression system",
        "Global success metrics",
        "skill tracking",  # case-insensitive substring check
    ]

    for element in key_elements:
        if element.lower() not in content.lower():
            errors.append(f"Missing documentation element: {element}")

    return len(errors) == 0, errors


def main():
    """Run all validation checks."""
    agents_dir = Path(__file__).parent

    print("🔍 Validating NEURO-AI DISTINGUISHED ENGINEERING COACH v1.0 Configuration...")
    print()

    all_valid = True

    # Validate main agent prompt
    print("1. Validating agent prompt (neuro-ai-engineering-coach.md)...")
    valid, errors = validate_neuro_coach_agent(
        agents_dir / "neuro-ai-engineering-coach.md"
    )
    if valid:
        print("   ✅ Agent prompt is valid")
        print(
            f"   📄 File size: {(agents_dir / 'neuro-ai-engineering-coach.md').stat().st_size:,} bytes"
        )
    else:
        print("   ❌ Agent prompt validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # Validate README update
    print("2. Validating README documentation (README.md)...")
    valid, errors = validate_readme_updated(agents_dir / "README.md")
    if valid:
        print("   ✅ README is properly updated")
    else:
        print("   ❌ README validation failed:")
        for error in errors:
            print(f"      - {error}")
        all_valid = False
    print()

    # File integrity checks
    print("3. Performing file integrity checks...")
    agent_file = agents_dir / "neuro-ai-engineering-coach.md"
    if agent_file.exists():
        content = agent_file.read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        char_count = len(content)

        print(f"   📊 Lines: {line_count:,}")
        print(f"   📊 Characters: {char_count:,}")

        # Check for UTF-8 encoding
        try:
            agent_file.read_text(encoding="utf-8")
            print("   ✅ UTF-8 encoding verified")
        except UnicodeDecodeError:
            print("   ❌ File has encoding issues")
            all_valid = False
    else:
        print("   ❌ Agent file not found")
        all_valid = False
    print()

    # Final result
    print("=" * 60)
    if all_valid:
        print("✅ All validation checks passed!")
        print()
        print("The NEURO-AI DISTINGUISHED ENGINEERING COACH agent is ready to use.")
        return 0
    else:
        print("❌ Some validation checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
