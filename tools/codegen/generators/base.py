from __future__ import annotations

"""Base primitives for code generators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GenerationRequest:
    name: str
    sources: dict[str, Any]
    template: Path | None
    output_path: Path
    metadata: dict[str, Any]
    project_root: Path


@dataclass(slots=True)
class GenerationResult:
    content: str
    diagnostics: dict[str, Any]


class CodeGenerator(ABC):
    """Interface implemented by all generators."""

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
