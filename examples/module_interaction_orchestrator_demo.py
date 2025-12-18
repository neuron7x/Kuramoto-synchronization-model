#!/usr/bin/env python
"""Demo script for the Module Interaction Orchestrator.

This script demonstrates how to use the ModuleInteractionOrchestrator to
manage the sequence of module interactions in a trading pipeline.
"""

from __future__ import annotations

from core.orchestrator.interaction_sequencer import (
    ModuleDefinition,
    ModuleInteractionOrchestrator,
    ModulePhase,
)


def demo_basic_orchestration():
    """Demonstrate basic orchestration with sequential modules."""
    print("=" * 80)
    print("DEMO 1: Basic Sequential Orchestration")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    # Define module handlers
    def ingest_data(context_data):
        """Simulate data ingestion."""
        print("  → Ingesting market data...")
        return {"raw_data": [100, 101, 102, 103, 104]}

    def validate_data(context_data):
        """Simulate data validation."""
        print("  → Validating data quality...")
        raw_data = context_data.get("raw_data", [])
        if not raw_data:
            raise ValueError("No data to validate")
        return {"validated_data": raw_data, "is_valid": True}

    def engineer_features(context_data):
        """Simulate feature engineering."""
        print("  → Engineering features...")
        data = context_data.get("validated_data", [])
        features = {"mean": sum(data) / len(data), "count": len(data)}
        return {"features": features}

    # Register modules
    orchestrator.register_module(
        ModuleDefinition(
            name="data_ingestor",
            phase=ModulePhase.INGESTION,
            handler=ingest_data,
            priority=1,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="data_validator",
            phase=ModulePhase.VALIDATION,
            handler=validate_data,
            dependencies=["data_ingestor"],
            priority=1,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="feature_engineer",
            phase=ModulePhase.FEATURE_ENGINEERING,
            handler=engineer_features,
            dependencies=["data_validator"],
            priority=1,
        )
    )

    print("\nExecution Order:", orchestrator.get_sequence())
    print("\nExecuting pipeline...")

    context = orchestrator.execute()

    print("\n✓ Execution completed")
    print(f"Features: {context.get('features')}")
    print(f"Errors: {context.errors if context.has_error() else 'None'}")


def demo_parallel_modules():
    """Demonstrate parallel module execution within same phase."""
    print("\n" + "=" * 80)
    print("DEMO 2: Parallel Module Execution")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    def ingest_data(context_data):
        print("  → Ingesting data...")
        return {"price_data": [100, 102, 101, 103]}

    def calculate_sma(context_data):
        """Calculate simple moving average."""
        print("  → Calculating SMA indicator...")
        prices = context_data.get("price_data", [])
        sma = sum(prices) / len(prices) if prices else 0
        return {"sma": sma}

    def calculate_rsi(context_data):
        """Calculate relative strength index."""
        print("  → Calculating RSI indicator...")
        # Simplified RSI calculation
        return {"rsi": 50.0}

    def calculate_volume(context_data):
        """Calculate volume metrics."""
        print("  → Calculating volume metrics...")
        return {"volume_avg": 1000}

    def generate_signal(context_data):
        """Generate trading signal from indicators."""
        print("  → Generating trading signal...")
        context_data.get("sma", 0)
        rsi = context_data.get("rsi", 50)
        signal = "BUY" if rsi < 30 else "SELL" if rsi > 70 else "HOLD"
        return {"signal": signal, "confidence": 0.75}

    # Register modules
    orchestrator.register_module(
        ModuleDefinition(
            name="ingestor",
            phase=ModulePhase.INGESTION,
            handler=ingest_data,
        )
    )

    # These three indicators can run in parallel (no dependencies between them)
    orchestrator.register_module(
        ModuleDefinition(
            name="sma_calculator",
            phase=ModulePhase.FEATURE_ENGINEERING,
            handler=calculate_sma,
            dependencies=["ingestor"],
            priority=1,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="rsi_calculator",
            phase=ModulePhase.FEATURE_ENGINEERING,
            handler=calculate_rsi,
            dependencies=["ingestor"],
            priority=1,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="volume_calculator",
            phase=ModulePhase.FEATURE_ENGINEERING,
            handler=calculate_volume,
            dependencies=["ingestor"],
            priority=1,
        )
    )

    # Signal generation depends on all indicators
    orchestrator.register_module(
        ModuleDefinition(
            name="signal_generator",
            phase=ModulePhase.SIGNAL_GENERATION,
            handler=generate_signal,
            dependencies=["sma_calculator", "rsi_calculator", "volume_calculator"],
        )
    )

    print("\nExecution Order:", orchestrator.get_sequence())
    print("\nExecuting pipeline...")

    context = orchestrator.execute()

    print("\n✓ Execution completed")
    print(f"Signal: {context.get('signal')}")
    print(f"Confidence: {context.get('confidence')}")


def demo_conditional_execution():
    """Demonstrate conditional module execution."""
    print("\n" + "=" * 80)
    print("DEMO 3: Conditional Module Execution")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    def generate_signal(context_data):
        print("  → Generating signal...")
        return {"signal": "BUY", "risk_score": 0.3}

    def risk_check(context_data):
        print("  → Performing risk assessment...")
        risk_score = context_data.get("risk_score", 0)
        if risk_score > 0.7:
            raise ValueError("Risk too high!")
        return {"risk_approved": True}

    def execute_trade(context_data):
        print("  → Executing trade...")
        if not context_data.get("risk_approved"):
            raise ValueError("Risk not approved")
        return {"trade_id": "12345", "status": "executed"}

    # Register modules
    orchestrator.register_module(
        ModuleDefinition(
            name="signal_gen",
            phase=ModulePhase.SIGNAL_GENERATION,
            handler=generate_signal,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="risk_check",
            phase=ModulePhase.RISK_ASSESSMENT,
            handler=risk_check,
            dependencies=["signal_gen"],
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="trade_executor",
            phase=ModulePhase.EXECUTION,
            handler=execute_trade,
            dependencies=["risk_check"],
        )
    )

    print("\nExecution Order:", orchestrator.get_sequence())
    print("\nExecuting pipeline...")

    context = orchestrator.execute()

    print("\n✓ Execution completed")
    print(f"Trade Status: {context.get('status')}")
    print(f"Trade ID: {context.get('trade_id')}")


def demo_module_disabling():
    """Demonstrate dynamic module enabling/disabling."""
    print("\n" + "=" * 80)
    print("DEMO 4: Dynamic Module Control")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    def basic_signal(context_data):
        print("  → Generating basic signal...")
        return {"signal": "HOLD"}

    def advanced_signal(context_data):
        print("  → Generating advanced signal...")
        return {"signal": "BUY", "advanced": True}

    def neuromodulation(context_data):
        print("  → Applying neuromodulation...")
        return {"modulated": True}

    # Register modules
    orchestrator.register_module(
        ModuleDefinition(
            name="basic_signal",
            phase=ModulePhase.SIGNAL_GENERATION,
            handler=basic_signal,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="advanced_signal",
            phase=ModulePhase.SIGNAL_GENERATION,
            handler=advanced_signal,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="neuromodulation",
            phase=ModulePhase.NEUROMODULATION,
            handler=neuromodulation,
        )
    )

    print("\n--- Running with all modules enabled ---")
    print("Execution Order:", orchestrator.get_sequence())
    context1 = orchestrator.execute()
    print(f"Result: {context1.data}")

    print("\n--- Disabling advanced signal ---")
    orchestrator.disable_module("advanced_signal")
    print("Execution Order:", orchestrator.get_sequence())
    context2 = orchestrator.execute()
    print(f"Result: {context2.data}")

    print("\n--- Disabling neuromodulation ---")
    orchestrator.disable_module("neuromodulation")
    print("Execution Order:", orchestrator.get_sequence())
    context3 = orchestrator.execute()
    print(f"Result: {context3.data}")


def demo_phase_listing():
    """Demonstrate phase-based module listing."""
    print("\n" + "=" * 80)
    print("DEMO 5: Phase-Based Module Management")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    # Register modules in various phases
    phases_modules = [
        ("ingestor", ModulePhase.INGESTION),
        ("validator", ModulePhase.VALIDATION),
        ("feature_1", ModulePhase.FEATURE_ENGINEERING),
        ("feature_2", ModulePhase.FEATURE_ENGINEERING),
        ("signal_gen", ModulePhase.SIGNAL_GENERATION),
        ("dopamine", ModulePhase.NEUROMODULATION),
        ("serotonin", ModulePhase.NEUROMODULATION),
        ("risk_check", ModulePhase.RISK_ASSESSMENT),
        ("executor", ModulePhase.EXECUTION),
    ]

    for name, phase in phases_modules:
        orchestrator.register_module(
            ModuleDefinition(
                name=name,
                phase=phase,
                handler=lambda d: {},
            )
        )

    print("\nModules by Phase:")
    print("-" * 80)
    for phase in ModulePhase:
        modules = orchestrator.list_modules_by_phase(phase)
        if modules:
            print(f"{phase.value:25} : {', '.join(modules)}")


def demo_error_handling():
    """Demonstrate error handling in orchestration."""
    print("\n" + "=" * 80)
    print("DEMO 6: Error Handling")
    print("=" * 80)

    orchestrator = ModuleInteractionOrchestrator()

    def step1(context_data):
        print("  → Step 1: Success")
        return {"step1": "done"}

    def step2_failing(context_data):
        print("  → Step 2: Failing...")
        raise RuntimeError("Simulated failure in step 2")

    def step3(context_data):
        print("  → Step 3: Should not execute")
        return {"step3": "done"}

    orchestrator.register_module(
        ModuleDefinition(
            name="step1",
            phase=ModulePhase.INGESTION,
            handler=step1,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="step2",
            phase=ModulePhase.VALIDATION,
            handler=step2_failing,
        )
    )

    orchestrator.register_module(
        ModuleDefinition(
            name="step3",
            phase=ModulePhase.FEATURE_ENGINEERING,
            handler=step3,
        )
    )

    print("\nExecuting pipeline with expected failure...")

    context = orchestrator.execute()

    print("\n✓ Execution stopped on error")
    print(f"Errors: {context.errors}")
    print(f"Modules executed: {context.metadata.get('modules_executed', [])}")
    print(f"Data collected: {list(context.data.keys())}")


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  Module Interaction Orchestrator for TradePulse".center(78) + "║")
    print("║" + "  Unified Sequence Management Demo".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    demo_basic_orchestration()
    demo_parallel_modules()
    demo_conditional_execution()
    demo_module_disabling()
    demo_phase_listing()
    demo_error_handling()

    print("\n" + "=" * 80)
    print("All demos completed successfully!")
    print("=" * 80)
    print("\nKey Takeaways:")
    print("  1. Orchestrator manages module execution sequence automatically")
    print("  2. Dependencies ensure correct ordering of module execution")
    print("  3. Phase-based organization provides logical grouping")
    print("  4. Modules can be dynamically enabled/disabled")
    print("  5. Context accumulates results across all modules")
    print("  6. Error handling stops execution and preserves partial results")
    print("  7. Priority controls execution order within phases")
    print()


if __name__ == "__main__":
    main()
