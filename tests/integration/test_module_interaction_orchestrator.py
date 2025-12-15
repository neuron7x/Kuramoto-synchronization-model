"""Integration tests for ModuleInteractionOrchestrator with TradePulse system."""

from __future__ import annotations

from core.orchestrator.interaction_sequencer import (
    ModuleDefinition,
    ModuleInteractionOrchestrator,
    ModulePhase,
)


class TestModuleInteractionOrchestratorIntegration:
    """Integration tests for the module interaction orchestrator."""

    def test_full_pipeline_orchestration(self):
        """Test complete trading pipeline orchestration."""
        orchestrator = ModuleInteractionOrchestrator()
        execution_log = []

        # Define pipeline modules
        def ingest_module(context_data):
            execution_log.append("ingestion")
            return {"raw_data": [100, 101, 102, 103, 104]}

        def validate_module(context_data):
            execution_log.append("validation")
            raw_data = context_data.get("raw_data", [])
            assert len(raw_data) > 0
            return {"validated_data": raw_data}

        def feature_module(context_data):
            execution_log.append("features")
            data = context_data.get("validated_data", [])
            return {
                "features": {
                    "mean": sum(data) / len(data),
                    "max": max(data),
                    "min": min(data),
                }
            }

        def signal_module(context_data):
            execution_log.append("signals")
            features = context_data.get("features", {})
            mean = features.get("mean", 0)
            return {"signal": "BUY" if mean > 100 else "SELL"}

        def neuro_module(context_data):
            execution_log.append("neuromodulation")
            return {"modulation_factor": 1.2}

        def risk_module(context_data):
            execution_log.append("risk")
            signal = context_data.get("signal")
            return {"risk_approved": signal in ["BUY", "SELL"]}

        def execution_module(context_data):
            execution_log.append("execution")
            if not context_data.get("risk_approved"):
                raise ValueError("Risk not approved")
            return {"executed": True, "order_id": "12345"}

        # Register modules in non-sequential order to test dependency resolution
        orchestrator.register_module(
            ModuleDefinition(
                name="risk_check",
                phase=ModulePhase.RISK_ASSESSMENT,
                handler=risk_module,
                dependencies=["signal_gen", "neuromodulation"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="signal_gen",
                phase=ModulePhase.SIGNAL_GENERATION,
                handler=signal_module,
                dependencies=["features"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="ingestion",
                phase=ModulePhase.INGESTION,
                handler=ingest_module,
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="validation",
                phase=ModulePhase.VALIDATION,
                handler=validate_module,
                dependencies=["ingestion"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="features",
                phase=ModulePhase.FEATURE_ENGINEERING,
                handler=feature_module,
                dependencies=["validation"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="neuromodulation",
                phase=ModulePhase.NEUROMODULATION,
                handler=neuro_module,
                dependencies=["signal_gen"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="execution",
                phase=ModulePhase.EXECUTION,
                handler=execution_module,
                dependencies=["risk_check"],
            )
        )

        # Execute pipeline
        context = orchestrator.execute()

        # Verify execution order follows dependencies and phases
        assert execution_log == [
            "ingestion",
            "validation",
            "features",
            "signals",
            "neuromodulation",
            "risk",
            "execution",
        ]

        # Verify results
        assert context.get("executed") is True
        assert context.get("order_id") == "12345"
        assert context.get("signal") in ["BUY", "SELL"]
        assert context.get("risk_approved") is True
        assert not context.has_error()

    def test_parallel_indicator_computation(self):
        """Test parallel computation of multiple indicators."""
        orchestrator = ModuleInteractionOrchestrator()

        def data_ingestion(context_data):
            return {"prices": [100, 102, 101, 103, 105]}

        def sma_indicator(context_data):
            prices = context_data.get("prices", [])
            return {"sma": sum(prices) / len(prices)}

        def ema_indicator(context_data):
            prices = context_data.get("prices", [])
            # Simplified EMA
            return {"ema": sum(prices) / len(prices) * 1.1}

        def rsi_indicator(context_data):
            return {"rsi": 55.0}

        def macd_indicator(context_data):
            return {"macd": 0.5}

        def signal_aggregation(context_data):
            sma = context_data.get("sma", 0)
            ema = context_data.get("ema", 0)
            rsi = context_data.get("rsi", 50)
            macd = context_data.get("macd", 0)

            # Aggregate signals
            bullish_signals = 0
            if ema > sma:
                bullish_signals += 1
            if rsi < 30:
                bullish_signals += 1
            if macd > 0:
                bullish_signals += 1

            return {"signal_strength": bullish_signals / 3}

        # Register data ingestion
        orchestrator.register_module(
            ModuleDefinition(
                name="data",
                phase=ModulePhase.INGESTION,
                handler=data_ingestion,
            )
        )

        # Register indicators that can run in parallel (all depend only on data)
        for name, handler in [
            ("sma", sma_indicator),
            ("ema", ema_indicator),
            ("rsi", rsi_indicator),
            ("macd", macd_indicator),
        ]:
            orchestrator.register_module(
                ModuleDefinition(
                    name=name,
                    phase=ModulePhase.FEATURE_ENGINEERING,
                    handler=handler,
                    dependencies=["data"],
                )
            )

        # Signal aggregation depends on all indicators
        orchestrator.register_module(
            ModuleDefinition(
                name="signal_aggregation",
                phase=ModulePhase.SIGNAL_GENERATION,
                handler=signal_aggregation,
                dependencies=["sma", "ema", "rsi", "macd"],
            )
        )

        # Execute
        context = orchestrator.execute()

        # Verify all indicators computed
        assert "sma" in context.data
        assert "ema" in context.data
        assert "rsi" in context.data
        assert "macd" in context.data
        assert "signal_strength" in context.data

        # Verify execution order
        sequence = orchestrator.get_sequence()
        assert sequence[0] == "data"
        assert "signal_aggregation" == sequence[-1]

    def test_module_enabling_disabling(self):
        """Test dynamic enabling and disabling of modules."""
        orchestrator = ModuleInteractionOrchestrator()

        def basic_signal(context_data):
            return {"signal": "BASIC"}

        def advanced_signal(context_data):
            return {"advanced_signal": "ADVANCED"}

        orchestrator.register_module(
            ModuleDefinition(
                name="basic",
                phase=ModulePhase.SIGNAL_GENERATION,
                handler=basic_signal,
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="advanced",
                phase=ModulePhase.SIGNAL_GENERATION,
                handler=advanced_signal,
            )
        )

        # Execute with both enabled
        context1 = orchestrator.execute()
        assert "signal" in context1.data
        assert "advanced_signal" in context1.data

        # Disable advanced
        orchestrator.disable_module("advanced")
        context2 = orchestrator.execute()
        assert "signal" in context2.data
        assert "advanced_signal" not in context2.data

        # Re-enable advanced
        orchestrator.enable_module("advanced")
        context3 = orchestrator.execute()
        assert "signal" in context3.data
        assert "advanced_signal" in context3.data

    def test_error_propagation_stops_execution(self):
        """Test that errors stop execution and preserve state."""
        orchestrator = ModuleInteractionOrchestrator()

        def step1(context_data):
            return {"step1": "complete"}

        def step2_fails(context_data):
            raise RuntimeError("Step 2 failed")

        def step3(context_data):
            return {"step3": "complete"}

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
                handler=step2_fails,
                dependencies=["step1"],
            )
        )

        orchestrator.register_module(
            ModuleDefinition(
                name="step3",
                phase=ModulePhase.FEATURE_ENGINEERING,
                handler=step3,
                dependencies=["step2"],
            )
        )

        context = orchestrator.execute()

        # Verify step1 completed
        assert context.get("step1") == "complete"

        # Verify step3 did not execute
        assert context.get("step3") is None

        # Verify error was recorded
        assert context.has_error()
        assert any("Step 2 failed" in err for err in context.errors)

        # Verify execution stopped at step1
        executed = context.metadata.get("modules_executed", [])
        assert "step1" in executed
        assert "step2" not in executed
        assert "step3" not in executed

    def test_phase_based_filtering(self):
        """Test filtering modules by phase."""
        orchestrator = ModuleInteractionOrchestrator()

        # Register modules across different phases
        for i in range(3):
            orchestrator.register_module(
                ModuleDefinition(
                    name=f"ingest_{i}",
                    phase=ModulePhase.INGESTION,
                    handler=lambda d: {},
                )
            )

        for i in range(2):
            orchestrator.register_module(
                ModuleDefinition(
                    name=f"feature_{i}",
                    phase=ModulePhase.FEATURE_ENGINEERING,
                    handler=lambda d: {},
                )
            )

        orchestrator.register_module(
            ModuleDefinition(
                name="signal",
                phase=ModulePhase.SIGNAL_GENERATION,
                handler=lambda d: {},
            )
        )

        # Get modules by phase
        ingestion = orchestrator.list_modules_by_phase(ModulePhase.INGESTION)
        features = orchestrator.list_modules_by_phase(ModulePhase.FEATURE_ENGINEERING)
        signals = orchestrator.list_modules_by_phase(ModulePhase.SIGNAL_GENERATION)

        assert len(ingestion) == 3
        assert len(features) == 2
        assert len(signals) == 1

        assert all(name.startswith("ingest_") for name in ingestion)
        assert all(name.startswith("feature_") for name in features)
