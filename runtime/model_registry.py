# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Central registry for model metadata across the runtime stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping


@dataclass(frozen=True)
class ModelMetadata:
    """Metadata for a deployed or trainable model."""

    model_id: str
    training_data_window: Mapping[str, str]
    eval_metrics: Mapping[str, Any]
    model_type: str
    module: str
    owners: Iterable[str] = field(default_factory=tuple)
    notes: str = ""


class ModelRegistry:
    """In-memory registry for model metadata."""

    def __init__(self) -> None:
        self._models: Dict[str, ModelMetadata] = {}

    def register(self, metadata: ModelMetadata) -> ModelMetadata:
        existing = self._models.get(metadata.model_id)
        if existing is not None:
            if existing == metadata:
                return existing
            raise ValueError(
                f"Model '{metadata.model_id}' already registered with different metadata."
            )
        self._models[metadata.model_id] = metadata
        return metadata

    def get(self, model_id: str) -> ModelMetadata:
        return self._models[model_id]

    def list(self) -> List[ModelMetadata]:
        return list(self._models.values())

    def export(self) -> Dict[str, Dict[str, Any]]:
        return {
            model_id: {
                "model_id": metadata.model_id,
                "training_data_window": dict(metadata.training_data_window),
                "eval_metrics": dict(metadata.eval_metrics),
                "model_type": metadata.model_type,
                "module": metadata.module,
                "owners": list(metadata.owners),
                "notes": metadata.notes,
            }
            for model_id, metadata in self._models.items()
        }


MODEL_REGISTRY = ModelRegistry()


def register_model(metadata: ModelMetadata) -> ModelMetadata:
    """Register model metadata in the global registry."""

    return MODEL_REGISTRY.register(metadata)


def list_models() -> List[ModelMetadata]:
    """List all registered models."""

    return MODEL_REGISTRY.list()
