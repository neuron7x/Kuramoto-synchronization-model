#!/usr/bin/env python3
"""NeuroPhysioGuard demonstration script.

This script demonstrates the usage of the NeuroPhysioGuard AI agent for
neurophysiology research projects. It showcases the iterative pipeline:
Ideate -> Model -> Simulate -> Validate -> Iterate

Run with:
    python examples/neuro_physio_guard_demo.py

Requirements:
    - Install TradePulse: pip install -e .
"""

from __future__ import annotations

from tradepulse.core.neuro import (
    NeuroPhysioGuard,
    NeurophysiologyDomain,
    PhysioScenario,
    create_neurophysiology_pipeline,
)


def demo_basic_usage() -> None:
    """Demonstrate basic usage with the convenience function."""
    print("=" * 60)
    print("NeuroPhysioGuard - Basic Usage Demo")
    print("=" * 60)

    # Create a pipeline for synaptic plasticity modeling
    output = create_neurophysiology_pipeline(
        domain="synaptic_plasticity",
        task_type="model",
        organism="mouse",
        brain_region="hippocampus_CA1",
    )

    print("\n📊 Project Milestone:")
    print(f"  {output.project_milestone}")

    print("\n🔬 Pipeline Steps:")
    for step in output.pipeline_steps:
        print(f"  [{step.priority}] {step.step_name}: {step.operation}")
        print(f"      Rationale: {step.rationale[:80]}...")
        print(f"      Tools: {', '.join(step.tools)}")

    print("\n📝 Key Outputs:")
    print("  Code snippet preview:")
    print("  " + output.key_outputs["code_snippet"][:200].replace("\n", "\n  ") + "...")

    print("\n⚠️ Safety Log:")
    print(f"  Confidence Score: {output.safety_log.confidence_score}")
    print(f"  Validation Required: {output.safety_log.validation_required}")
    print(f"  Is Hypothesis: {output.safety_log.is_hypothesis}")
    print("  Risks Mitigated:")
    for risk in output.safety_log.risks_mitigated:
        print(f"    - {risk}")
    print("  Biases Flagged:")
    for bias in output.safety_log.biases_flagged:
        print(f"    - {bias}")

    print("\n➡️ Next Action:")
    print(f"  {output.next_action}")

    print()


def demo_hodgkin_huxley() -> None:
    """Demonstrate ion channel modeling with Hodgkin-Huxley parameters."""
    print("=" * 60)
    print("NeuroPhysioGuard - Hodgkin-Huxley Model Demo")
    print("=" * 60)

    # Create a scenario for ion channel modeling
    guard = NeuroPhysioGuard(
        confidence_threshold=0.85,
        enable_safety_validation=True,
    )

    scenario = PhysioScenario(
        domain=NeurophysiologyDomain.ION_CHANNELS,
        task_type="simulate",
        organism="squid",  # Original HH model organism
        brain_region="giant_axon",
    )

    output = guard.process(scenario)

    print("\n📊 Project Milestone:")
    print(f"  {output.project_milestone}")

    print("\n📐 Hodgkin-Huxley Parameters:")
    print(f"  g_Na: {output.parameters.get('g_na_mS_cm2')} mS/cm²")
    print(f"  g_K: {output.parameters.get('g_k_mS_cm2')} mS/cm²")
    print(f"  g_L: {output.parameters.get('g_l_mS_cm2')} mS/cm²")
    print(f"  E_Na: {output.parameters.get('e_na_mV')} mV")
    print(f"  E_K: {output.parameters.get('e_k_mV')} mV")

    print("\n📝 Equations:")
    for name, eq in output.key_outputs["equations"].items():
        print(f"  {name}: {eq}")

    print("\n✅ Safety Validation:")
    print(f"  Confidence: {output.safety_log.confidence_score}")
    print(f"  Validation Method: {output.safety_log.validation_method}")

    print()


def demo_all_domains() -> None:
    """Demonstrate pipeline for all supported domains."""
    print("=" * 60)
    print("NeuroPhysioGuard - All Domains Demo")
    print("=" * 60)

    for domain in NeurophysiologyDomain:
        print(f"\n🧠 Domain: {domain.value}")
        output = create_neurophysiology_pipeline(
            domain=domain.value,
            task_type="model",
        )
        print(f"   Milestone: {output.project_milestone[:80]}...")
        print(f"   Confidence: {output.safety_log.confidence_score}")
        print(f"   Steps: {len(output.pipeline_steps)}")

    print()


def demo_json_output() -> None:
    """Demonstrate JSON output format."""
    print("=" * 60)
    print("NeuroPhysioGuard - JSON Output Demo")
    print("=" * 60)

    output = create_neurophysiology_pipeline(
        domain="network_oscillations",
        task_type="validate",
    )

    print("\n📄 JSON Output (first 1500 chars):")
    json_output = output.to_json()
    print(json_output[:1500] + "...")

    print()


def main() -> None:
    """Run all demos."""
    print("\n" + "=" * 60)
    print("NeuroPhysioGuard - AI Agent for Neurophysiology Research")
    print("=" * 60)
    print("""
Core Principles (Non-Negotiable Safety Guardrails):
1. Alignment Check - Outputs align with neurophysiological facts
2. Robustness - Chain-of-thought reasoning with verifiable steps
3. Interpretability - Transparent decision explanations
4. Ethical Rails - No medical advice, flag biases
5. Project Velocity - Ideate -> Model -> Simulate -> Validate -> Iterate
    """)

    demo_basic_usage()
    demo_hodgkin_huxley()
    demo_all_domains()
    demo_json_output()

    print("=" * 60)
    print("Demo Complete! Ready for iteration?")
    print("=" * 60)


if __name__ == "__main__":
    main()
