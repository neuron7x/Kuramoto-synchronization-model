from __future__ import annotations

"""Registry for code generation plugins."""

from collections.abc import Callable
from typing import Dict, Type

from .generators.base import CodeGenerator


class CodeGeneratorRegistry:
    """Runtime registry used to discover generator implementations."""

    def __init__(self) -> None:
        self._generators: Dict[str, Callable[[], CodeGenerator]] = {}

    def register(self, name: str, factory: Callable[[], CodeGenerator]) -> None:
        if name in self._generators:
            raise ValueError(f"Generator '{name}' already registered")
        self._generators[name] = factory

    def create(self, name: str) -> CodeGenerator:
        try:
            factory = self._generators[name]
        except KeyError as exc:
            raise KeyError(f"Unknown generator '{name}'. Registered: {list(self._generators)}") from exc
        return factory()

    def names(self) -> list[str]:
        return sorted(self._generators)


generator_registry = CodeGeneratorRegistry()
