"""Code generation orchestration for TradePulse."""

from . import plugins as _plugins  # noqa: F401 - ensure built-ins register
from .engine import CodegenEngine, GenerationSummary
from .config import CodegenConfig, load_config
from .registry import generator_registry

__all__ = [
    "CodegenConfig",
    "CodegenEngine",
    "GenerationSummary",
    "generator_registry",
    "load_config",
]
