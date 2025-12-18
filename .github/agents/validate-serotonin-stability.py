#!/usr/bin/env python3
"""Validation script for Serotonin Stability Controller agent configuration.

This script validates the agent configuration file to ensure:
1. All required sections are present
2. Response format is correctly specified
3. Example scenarios are complete
4. Constraints and boundaries are properly defined
"""

import re
import sys
from pathlib import Path


def read_agent_config(config_path: Path) -> str:
    """Read the agent configuration file."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path} "
            f"(expected: serotonin-stability-controller.md)"
        )
    return config_path.read_text()


def validate_structure(content: str) -> tuple[bool, list[str]]:
    """Validate that all required sections are present."""
    required_sections = [
        "# SEROTONIN STABILITY CONTROLLER",
        "## SYSTEM ROLE",
        "## 1. META-GOAL",
        "## 2. INPUT SIGNALS",
        "## 3. OUTPUT FORMAT",
        "## 4. BEHAVIORAL RULES",
        "## 5. RESPONSE TEMPLATE",
        "## 6. CONSTRAINTS AND BOUNDARIES",
        "## 7. USAGE GUIDELINES",
        "## 8. EXAMPLE SCENARIOS",
    ]

    issues = []
    for section in required_sections:
        if section not in content:
            issues.append(f"Missing required section: {section}")

    return len(issues) == 0, issues


def validate_output_format(content: str) -> tuple[bool, list[str]]:
    """Validate that output format is properly specified."""
    issues = []

    # Check for structured output components
    required_outputs = [
        "serotonin_score",
        "risk_modulation",
        "tempo_adjustment",
        "priority_shift",
        "SEROTONIN REPORT",
        "INTERVENTIONS",
    ]

    for output in required_outputs:
        if output not in content:
            issues.append(f"Missing output component: {output}")

    # Check for valid serotonin_score range specification
    if "[0.0, 1.0]" not in content:
        issues.append("Serotonin score range [0.0, 1.0] not specified")

    return len(issues) == 0, issues


def validate_response_template(content: str) -> tuple[bool, list[str]]:
    """Validate that response template is complete."""
    issues = []

    required_template_sections = [
        "Serotonin Snapshot",
        "Stabilizing Moves",
        "Medium-Horizon Guardrails",
        "Language Reframe",
    ]

    for section in required_template_sections:
        if section not in content:
            issues.append(f"Missing response template section: {section}")

    return len(issues) == 0, issues


def validate_behavioral_rules(content: str) -> tuple[bool, list[str]]:
    """Validate that behavioral rules are properly defined."""
    issues = []

    required_rules = [
        "Stability First",
        "Small Steps, Not Grand Plans",
        "De-Manic the Narrative",
        "Long-Term Horizon",
        "No Hidden Therapy",
    ]

    for rule in required_rules:
        if rule not in content:
            issues.append(f"Missing behavioral rule: {rule}")

    return len(issues) == 0, issues


def validate_constraints(content: str) -> tuple[bool, list[str]]:
    """Validate that constraints and boundaries are clear."""
    issues = []

    # Check for explicit "do not" statements
    if "do not" not in content.lower():
        issues.append("No explicit constraints found")

    # Check for medical disclaimer with specific patterns
    # Remove markdown formatting for pattern matching
    content_clean = content.replace("**", "").replace("*", "")
    medical_patterns = [
        "not a doctor",
        "not provide medical",
        "not give medical",
        "do not give medical",
        "do not provide medical",
    ]
    if not any(pattern in content_clean.lower() for pattern in medical_patterns):
        issues.append("Medical disclaimer may be missing or unclear")

    # Check for therapy disclaimer
    therapy_patterns = ["not analyze trauma", "not diagnose", "no hidden therapy"]
    if not any(pattern in content_clean.lower() for pattern in therapy_patterns):
        issues.append("Therapy disclaimer may be missing")

    return len(issues) == 0, issues


def validate_example_scenarios(content: str) -> tuple[bool, list[str]]:
    """Validate that example scenarios are present and complete."""
    issues = []

    # Extract scenarios
    scenario_pattern = r"### Scenario [A-Z]:"
    scenarios = re.findall(scenario_pattern, content)

    if len(scenarios) < 3:
        issues.append(f"Expected at least 3 example scenarios, found {len(scenarios)}")

    # Check that each scenario has required components
    for i, scenario in enumerate(scenarios):
        try:
            start_idx = content.index(scenario)

            # Find next scenario or next top-level section
            if i < len(scenarios) - 1:
                # Look for next scenario
                next_scenario = scenarios[i + 1]
                try:
                    end_idx = content.index(next_scenario)
                except ValueError:
                    # Fallback if next scenario not found as exact string
                    end_idx = len(content)
            else:
                # Last scenario - look for next top-level section (## but not ###)
                remaining = content[start_idx + len(scenario):]
                next_section_match = re.search(r'\n## [^#]', remaining)
                if next_section_match:
                    end_idx = start_idx + len(scenario) + next_section_match.start()
                else:
                    end_idx = len(content)

            scenario_section = content[start_idx:end_idx]

            required_components = [
                "**Input:**",
                "**Output:**",
                "#### Serotonin Snapshot",
                "#### Stabilizing Moves",
                "#### Medium-Horizon Guardrails",
                "#### Language Reframe",
            ]

            for component in required_components:
                if component not in scenario_section:
                    issues.append(f"{scenario} missing component: {component}")
        except ValueError as e:
            issues.append(f"Error processing {scenario}: {e}")

    return len(issues) == 0, issues


def validate_usage_guidelines(content: str) -> tuple[bool, list[str]]:
    """Validate that usage guidelines are clear."""
    issues = []

    required_guidelines = [
        "When to Invoke",
        "How to Use Output",
        "Integration with Other Agents",
    ]

    for guideline in required_guidelines:
        if guideline not in content:
            issues.append(f"Missing usage guideline: {guideline}")

    return len(issues) == 0, issues


def validate_versioning(content: str) -> tuple[bool, list[str]]:
    """Validate that versioning information is present."""
    issues = []

    if "Current Version:" not in content:
        issues.append("Version number not specified")

    if "Last Updated:" not in content:
        issues.append("Last updated date not specified")

    if "Changelog" not in content:
        issues.append("Changelog not present")

    return len(issues) == 0, issues


def main():
    """Run all validations and report results."""
    script_dir = Path(__file__).parent
    config_path = script_dir / "serotonin-stability-controller.md"

    print("=" * 80)
    print("Serotonin Stability Controller Agent Validation")
    print("=" * 80)
    print()

    try:
        content = read_agent_config(config_path)
        print(f"✓ Configuration file loaded: {config_path}")
        print(f"  Size: {len(content)} characters")
        print()
    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        return 1

    # Run all validations
    validations = [
        ("Structure", validate_structure),
        ("Output Format", validate_output_format),
        ("Response Template", validate_response_template),
        ("Behavioral Rules", validate_behavioral_rules),
        ("Constraints", validate_constraints),
        ("Example Scenarios", validate_example_scenarios),
        ("Usage Guidelines", validate_usage_guidelines),
        ("Versioning", validate_versioning),
    ]

    all_passed = True
    results = []

    for name, validator in validations:
        passed, issues = validator(content)
        results.append((name, passed, issues))
        all_passed &= passed

    # Report results
    print("Validation Results:")
    print("-" * 80)

    for name, passed, issues in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} {name}")
        if issues:
            for issue in issues:
                print(f"         - {issue}")

    print("-" * 80)
    print()

    # Summary
    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)
    success_rate = (passed_count / total_count) * 100

    print(f"Summary: {passed_count}/{total_count} checks passed ({success_rate:.1f}%)")
    print()

    if all_passed:
        print("✓ Configuration is valid and ready for use")
        return 0
    else:
        print("✗ Configuration has issues that need to be addressed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
