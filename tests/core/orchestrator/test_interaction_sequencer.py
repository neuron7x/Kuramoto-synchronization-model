"""Tests for the module interaction sequencer."""

from __future__ import annotations

import pytest

from core.orchestrator.interaction_sequencer import (
    ExecutionContext,
    ModuleDefinition,
    ModuleInteractionOrchestrator,
    ModulePhase,
)


class TestExecutionContext:
    """Tests for ExecutionContext."""

    def test_context_initialization(self):
        """Context should initialize with empty collections."""
        ctx = ExecutionContext()
        assert ctx.data == {}
        assert ctx.metadata == {}
        assert ctx.errors == []

    def test_context_set_get(self):
        """Context should store and retrieve values."""
        ctx = ExecutionContext()
        ctx.set("key1", "value1")
        ctx.set("key2", 42)

        assert ctx.get("key1") == "value1"
        assert ctx.get("key2") == 42
        assert ctx.get("nonexistent") is None
        assert ctx.get("nonexistent", "default") == "default"

    def test_context_error_tracking(self):
        """Context should track errors."""
        ctx = ExecutionContext()
        assert not ctx.has_error()

        ctx.add_error("Error 1")
        assert ctx.has_error()
        assert len(ctx.errors) == 1

        ctx.add_error("Error 2")
        assert len(ctx.errors) == 2
        assert "Error 1" in ctx.errors
        assert "Error 2" in ctx.errors


class TestModuleDefinition:
    """Tests for ModuleDefinition."""

    def test_module_definition_creation(self):
        """ModuleDefinition should be created with valid parameters."""
        module = ModuleDefinition(
            name="test_module",
            phase=ModulePhase.INGESTION,
            dependencies=["dep1", "dep2"],
            priority=1,
        )

        assert module.name == "test_module"
        assert module.phase == ModulePhase.INGESTION
        assert module.dependencies == ["dep1", "dep2"]
        assert module.priority == 1
        assert module.enabled is True

    def test_module_definition_empty_name_raises(self):
        """ModuleDefinition should reject empty names."""
        with pytest.raises(ValueError, match="name must be non-empty"):
            ModuleDefinition(
                name="",
                phase=ModulePhase.INGESTION,
            )

        with pytest.raises(ValueError, match="name must be non-empty"):
            ModuleDefinition(
                name="   ",
                phase=ModulePhase.INGESTION,
            )

    def test_module_definition_defaults(self):
        """ModuleDefinition should use sensible defaults."""
        module = ModuleDefinition(
            name="test",
            phase=ModulePhase.SIGNAL_GENERATION,
        )

        assert module.dependencies == []
        assert module.handler is None
        assert module.enabled is True
        assert module.priority == 0


class TestModuleInteractionOrchestrator:
    """Tests for ModuleInteractionOrchestrator."""

    def test_orchestrator_initialization(self):
        """Orchestrator should initialize with empty state."""
        orch = ModuleInteractionOrchestrator()
        assert orch.list_modules() == []

    def test_register_module(self):
        """Should register modules successfully."""
        orch = ModuleInteractionOrchestrator()
        module = ModuleDefinition(
            name="module1",
            phase=ModulePhase.INGESTION,
        )

        orch.register_module(module)
        assert "module1" in orch.list_modules()

    def test_register_duplicate_module_raises(self):
        """Registering duplicate module should raise error."""
        orch = ModuleInteractionOrchestrator()
        module = ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)

        orch.register_module(module)
        with pytest.raises(ValueError, match="already registered"):
            orch.register_module(module)

    def test_remove_module(self):
        """Should remove modules successfully."""
        orch = ModuleInteractionOrchestrator()
        module = ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)

        orch.register_module(module)
        assert "module1" in orch.list_modules()

        orch.remove_module("module1")
        assert "module1" not in orch.list_modules()

    def test_disable_enable_module(self):
        """Should disable and enable modules."""
        orch = ModuleInteractionOrchestrator()
        module = ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)

        orch.register_module(module)
        info = orch.get_module_info("module1")
        assert info.enabled is True

        orch.disable_module("module1")
        info = orch.get_module_info("module1")
        assert info.enabled is False

        orch.enable_module("module1")
        info = orch.get_module_info("module1")
        assert info.enabled is True

    def test_disable_nonexistent_module_raises(self):
        """Disabling nonexistent module should raise error."""
        orch = ModuleInteractionOrchestrator()
        with pytest.raises(KeyError, match="not found"):
            orch.disable_module("nonexistent")

    def test_build_execution_sequence_single_phase(self):
        """Should build correct sequence for single phase."""
        orch = ModuleInteractionOrchestrator()

        # Register modules in non-priority order
        orch.register_module(
            ModuleDefinition(name="module2", phase=ModulePhase.INGESTION, priority=2)
        )
        orch.register_module(
            ModuleDefinition(name="module1", phase=ModulePhase.INGESTION, priority=1)
        )
        orch.register_module(
            ModuleDefinition(name="module3", phase=ModulePhase.INGESTION, priority=3)
        )

        sequence = orch.build_execution_sequence()
        # Should be ordered by priority
        assert sequence == ["module1", "module2", "module3"]

    def test_build_execution_sequence_multiple_phases(self):
        """Should build correct sequence across multiple phases."""
        orch = ModuleInteractionOrchestrator()

        # Register modules in different phases
        orch.register_module(
            ModuleDefinition(name="exec", phase=ModulePhase.EXECUTION)
        )
        orch.register_module(
            ModuleDefinition(name="signal", phase=ModulePhase.SIGNAL_GENERATION)
        )
        orch.register_module(
            ModuleDefinition(name="ingest", phase=ModulePhase.INGESTION)
        )

        sequence = orch.build_execution_sequence()
        # Should follow phase order
        assert sequence.index("ingest") < sequence.index("signal")
        assert sequence.index("signal") < sequence.index("exec")

    def test_build_execution_sequence_with_dependencies(self):
        """Should respect dependencies when building sequence."""
        orch = ModuleInteractionOrchestrator()

        # module2 depends on module1
        orch.register_module(
            ModuleDefinition(
                name="module2",
                phase=ModulePhase.INGESTION,
                dependencies=["module1"],
            )
        )
        orch.register_module(
            ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)
        )

        sequence = orch.build_execution_sequence()
        assert sequence.index("module1") < sequence.index("module2")

    def test_build_execution_sequence_skips_disabled(self):
        """Should skip disabled modules in sequence."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)
        )
        orch.register_module(
            ModuleDefinition(name="module2", phase=ModulePhase.INGESTION)
        )

        orch.disable_module("module2")
        sequence = orch.build_execution_sequence()

        assert "module1" in sequence
        assert "module2" not in sequence

    def test_circular_dependency_detection(self):
        """Should detect circular dependencies."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(
                name="module1",
                phase=ModulePhase.INGESTION,
                dependencies=["module2"],
            )
        )
        orch.register_module(
            ModuleDefinition(
                name="module2",
                phase=ModulePhase.INGESTION,
                dependencies=["module1"],
            )
        )

        with pytest.raises(ValueError, match="Circular dependency"):
            orch.build_execution_sequence()

    def test_execute_with_handlers(self):
        """Should execute modules with handlers in sequence."""
        orch = ModuleInteractionOrchestrator()
        execution_log = []

        def handler1(data):
            execution_log.append("handler1")
            return {"step1": "done"}

        def handler2(data):
            execution_log.append("handler2")
            assert data.get("step1") == "done"
            return {"step2": "done"}

        orch.register_module(
            ModuleDefinition(
                name="module1",
                phase=ModulePhase.INGESTION,
                handler=handler1,
            )
        )
        orch.register_module(
            ModuleDefinition(
                name="module2",
                phase=ModulePhase.VALIDATION,
                handler=handler2,
                dependencies=["module1"],
            )
        )

        context = orch.execute()

        assert execution_log == ["handler1", "handler2"]
        assert context.get("step1") == "done"
        assert context.get("step2") == "done"
        assert not context.has_error()

    def test_execute_without_handler(self):
        """Should handle modules without handlers."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)
        )

        context = orch.execute()
        assert context.has_error()
        assert any("no handler" in err.lower() for err in context.errors)

    def test_execute_with_handler_exception(self):
        """Should handle exceptions in module handlers."""
        orch = ModuleInteractionOrchestrator()

        def failing_handler(data):
            raise RuntimeError("Test error")

        orch.register_module(
            ModuleDefinition(
                name="module1",
                phase=ModulePhase.INGESTION,
                handler=failing_handler,
            )
        )

        context = orch.execute()
        assert context.has_error()
        assert any("Test error" in err for err in context.errors)

    def test_execute_with_initial_context(self):
        """Should use initial context when provided."""
        orch = ModuleInteractionOrchestrator()

        def handler(data):
            return {"result": data.get("initial_value", 0) + 1}

        orch.register_module(
            ModuleDefinition(
                name="module1",
                phase=ModulePhase.INGESTION,
                handler=handler,
            )
        )

        initial_ctx = ExecutionContext()
        initial_ctx.set("initial_value", 10)

        context = orch.execute(initial_ctx)
        assert context.get("result") == 11

    def test_list_modules_by_phase(self):
        """Should list modules filtered by phase."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(name="ingest1", phase=ModulePhase.INGESTION)
        )
        orch.register_module(
            ModuleDefinition(name="ingest2", phase=ModulePhase.INGESTION)
        )
        orch.register_module(
            ModuleDefinition(name="signal1", phase=ModulePhase.SIGNAL_GENERATION)
        )

        ingestion_modules = orch.list_modules_by_phase(ModulePhase.INGESTION)
        assert set(ingestion_modules) == {"ingest1", "ingest2"}

        signal_modules = orch.list_modules_by_phase(ModulePhase.SIGNAL_GENERATION)
        assert signal_modules == ["signal1"]

    def test_reset(self):
        """Should reset orchestrator state."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(name="module1", phase=ModulePhase.INGESTION)
        )
        assert len(orch.list_modules()) == 1

        orch.reset()
        assert len(orch.list_modules()) == 0

    def test_execution_metadata(self):
        """Should track execution metadata."""
        orch = ModuleInteractionOrchestrator()

        orch.register_module(
            ModuleDefinition(
                name="module1",
                phase=ModulePhase.INGESTION,
                handler=lambda data: {"key": "value"},
            )
        )

        context = orch.execute()

        assert "execution_order" in context.metadata
        assert "modules_executed" in context.metadata
        assert "module1" in context.metadata["modules_executed"]

    def test_complex_dependency_graph(self):
        """Should handle complex dependency graphs correctly."""
        orch = ModuleInteractionOrchestrator()

        # Create a complex dependency graph:
        # A -> B -> D
        # A -> C -> D
        orch.register_module(
            ModuleDefinition(name="A", phase=ModulePhase.INGESTION)
        )
        orch.register_module(
            ModuleDefinition(
                name="B",
                phase=ModulePhase.INGESTION,
                dependencies=["A"],
            )
        )
        orch.register_module(
            ModuleDefinition(
                name="C",
                phase=ModulePhase.INGESTION,
                dependencies=["A"],
            )
        )
        orch.register_module(
            ModuleDefinition(
                name="D",
                phase=ModulePhase.VALIDATION,
                dependencies=["B", "C"],
            )
        )

        sequence = orch.build_execution_sequence()

        # A must come first
        assert sequence[0] == "A"
        # D must come last
        assert sequence[-1] == "D"
        # B and C can be in any order, but both after A
        assert sequence.index("B") > sequence.index("A")
        assert sequence.index("C") > sequence.index("A")
