# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Module interaction sequencer for orchestrating execution flow.

This module provides a unified orchestration mechanism that manages the
sequence of interactions between GeoSync modules, ensuring proper
dependency ordering and execution flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ModulePhase(str, Enum):
    """Execution phases for module orchestration."""

    INGESTION = "ingestion"
    VALIDATION = "validation"
    FEATURE_ENGINEERING = "feature_engineering"
    SIGNAL_GENERATION = "signal_generation"
    NEUROMODULATION = "neuromodulation"
    RISK_ASSESSMENT = "risk_assessment"
    EXECUTION = "execution"
    POST_EXECUTION = "post_execution"


@dataclass
class ModuleDefinition:
    """Definition of a module in the orchestration sequence.

    Attributes:
        name: Unique identifier for the module
        phase: Execution phase this module belongs to
        dependencies: List of module names that must execute before this one
        handler: Callable that executes the module logic
        enabled: Whether this module is active in the sequence
        priority: Execution priority within the same phase (lower = earlier)
    """

    name: str
    phase: ModulePhase
    dependencies: List[str] = field(default_factory=list)
    handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    enabled: bool = True
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Module name must be non-empty")
        if not isinstance(self.dependencies, list):
            raise TypeError("dependencies must be a list")


@dataclass
class ExecutionContext:
    """Context passed between modules during orchestration.

    The context accumulates outputs from each module and makes them
    available to downstream modules.
    """

    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        """Store a value in the execution context."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the execution context."""
        return self.data.get(key, default)

    def has_error(self) -> bool:
        """Check if any errors occurred during execution."""
        return len(self.errors) > 0

    def add_error(self, error: str) -> None:
        """Record an error in the execution context."""
        self.errors.append(error)


class ModuleInteractionOrchestrator:
    """Orchestrator for managing module interaction sequences.

    This orchestrator ensures modules execute in the correct order based on
    their dependencies and phases, providing a unified coordination mechanism
    for the GeoSync pipeline.

    Example:
        >>> orchestrator = ModuleInteractionOrchestrator()
        >>> orchestrator.register_module(
        ...     ModuleDefinition(
        ...         name="data_ingestor",
        ...         phase=ModulePhase.INGESTION,
        ...         handler=ingest_data
        ...     )
        ... )
        >>> context = orchestrator.execute()
    """

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleDefinition] = {}
        self._execution_order: List[str] = []
        self._sequence_built = False

    def register_module(self, module: ModuleDefinition) -> None:
        """Register a module in the orchestration sequence.

        Args:
            module: Module definition to register

        Raises:
            ValueError: If a module with the same name is already registered
        """
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' is already registered")

        self._modules[module.name] = module
        self._sequence_built = False

    def remove_module(self, name: str) -> None:
        """Remove a module from the orchestration sequence.

        Args:
            name: Name of the module to remove
        """
        if name in self._modules:
            del self._modules[name]
            self._sequence_built = False

    def disable_module(self, name: str) -> None:
        """Disable a module without removing it.

        Args:
            name: Name of the module to disable

        Raises:
            KeyError: If module does not exist
        """
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not found")
        self._modules[name].enabled = False
        self._sequence_built = False

    def enable_module(self, name: str) -> None:
        """Enable a previously disabled module.

        Args:
            name: Name of the module to enable

        Raises:
            KeyError: If module does not exist
        """
        if name not in self._modules:
            raise KeyError(f"Module '{name}' not found")
        self._modules[name].enabled = True
        self._sequence_built = False

    def build_execution_sequence(self) -> List[str]:
        """Build the execution order based on dependencies and phases.

        Returns:
            List of module names in execution order

        Raises:
            ValueError: If circular dependencies are detected
        """
        if self._sequence_built:
            return self._execution_order

        # Get enabled modules
        enabled_modules = {name: mod for name, mod in self._modules.items() if mod.enabled}

        if not enabled_modules:
            self._execution_order = []
            self._sequence_built = True
            return self._execution_order

        # Group by phase
        phase_groups: Dict[ModulePhase, List[ModuleDefinition]] = {}
        for module in enabled_modules.values():
            if module.phase not in phase_groups:
                phase_groups[module.phase] = []
            phase_groups[module.phase].append(module)

        # Build execution order
        execution_order: List[str] = []
        phase_order = list(ModulePhase)

        for phase in phase_order:
            if phase not in phase_groups:
                continue

            # Sort modules within phase by priority and dependencies
            phase_modules = phase_groups[phase]
            phase_order_local = self._topological_sort(phase_modules, enabled_modules)
            execution_order.extend(phase_order_local)

        self._execution_order = execution_order
        self._sequence_built = True
        return self._execution_order

    def _topological_sort(
        self,
        modules: List[ModuleDefinition],
        all_enabled: Dict[str, ModuleDefinition],
    ) -> List[str]:
        """Perform topological sort on modules considering dependencies.

        Args:
            modules: Modules to sort
            all_enabled: All enabled modules for dependency lookup

        Returns:
            List of module names in dependency order

        Raises:
            ValueError: If circular dependencies detected
        """
        # Build adjacency list for this subset
        in_degree: Dict[str, int] = {mod.name: 0 for mod in modules}
        adjacency: Dict[str, List[str]] = {mod.name: [] for mod in modules}
        module_map = {mod.name: mod for mod in modules}

        for module in modules:
            for dep in module.dependencies:
                # Only count dependencies within enabled modules
                if dep in all_enabled and dep in module_map:
                    adjacency[dep].append(module.name)
                    in_degree[module.name] += 1

        # Kahn's algorithm with priority consideration
        queue: List[tuple[int, str]] = []
        for module in modules:
            if in_degree[module.name] == 0:
                queue.append((module.priority, module.name))

        queue.sort()  # Sort by priority
        result: List[str] = []
        visited: Set[str] = set()

        while queue:
            _, current = queue.pop(0)
            if current in visited:
                continue

            visited.add(current)
            result.append(current)

            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    neighbor_module = module_map[neighbor]
                    queue.append((neighbor_module.priority, neighbor))
                    queue.sort()

        # Check for cycles
        if len(result) != len(modules):
            raise ValueError("Circular dependency detected in module orchestration")

        return result

    def execute(self, initial_context: Optional[ExecutionContext] = None) -> ExecutionContext:
        """Execute all registered modules in the correct sequence.

        Args:
            initial_context: Optional initial execution context

        Returns:
            Final execution context with accumulated results

        Raises:
            RuntimeError: If execution fails
        """
        context = initial_context or ExecutionContext()
        execution_order = self.build_execution_sequence()

        context.metadata["execution_order"] = execution_order
        context.metadata["modules_executed"] = []

        for module_name in execution_order:
            module = self._modules[module_name]

            if not module.handler:
                context.add_error(f"Module '{module_name}' has no handler defined")
                continue

            try:
                result = module.handler(context.data)
                if result is not None:
                    context.data.update(result)
                context.metadata["modules_executed"].append(module_name)
            except Exception as exc:
                error_msg = f"Module '{module_name}' failed: {exc}"
                context.add_error(error_msg)
                # Stop execution on error
                break

        return context

    def get_sequence(self) -> List[str]:
        """Get the current execution sequence.

        Returns:
            List of module names in execution order
        """
        return self.build_execution_sequence()

    def get_module_info(self, name: str) -> Optional[ModuleDefinition]:
        """Get information about a registered module.

        Args:
            name: Name of the module

        Returns:
            Module definition or None if not found
        """
        return self._modules.get(name)

    def list_modules(self) -> List[str]:
        """Get list of all registered module names.

        Returns:
            List of module names
        """
        return list(self._modules.keys())

    def list_modules_by_phase(self, phase: ModulePhase) -> List[str]:
        """Get list of modules in a specific phase.

        Args:
            phase: Phase to filter by

        Returns:
            List of module names in the specified phase
        """
        return [name for name, mod in self._modules.items() if mod.phase == phase and mod.enabled]

    def reset(self) -> None:
        """Clear all registered modules and reset state."""
        self._modules.clear()
        self._execution_order.clear()
        self._sequence_built = False


__all__ = [
    "ModulePhase",
    "ModuleDefinition",
    "ExecutionContext",
    "ModuleInteractionOrchestrator",
]
