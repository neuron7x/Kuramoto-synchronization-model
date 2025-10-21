from __future__ import annotations

"""Built-in generator registrations."""

from .generators.api_client import ApiClientGenerator
from .generators.dto import DtoGenerator
from .generators.migration import MigrationGenerator
from .generators.sdk import SdkGenerator
from .generators.validator import ValidatorGenerator
from .registry import generator_registry


def register_builtin_generators() -> None:
    if generator_registry.names():
        return
    generator_registry.register("api-client", lambda: ApiClientGenerator())
    generator_registry.register("dto", lambda: DtoGenerator())
    generator_registry.register("validator", lambda: ValidatorGenerator())
    generator_registry.register("sdk", lambda: SdkGenerator())
    generator_registry.register("migration", lambda: MigrationGenerator())


register_builtin_generators()
