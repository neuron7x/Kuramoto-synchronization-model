
"""Configuration helpers for the neural controller package."""

from __future__ import annotations

from importlib import resources
from typing import Any, Mapping

import yaml

_CONFIG_PACKAGE = __name__
_DEFAULT_CONFIG_NAME = "neural_params.yaml"


def load_default_config() -> Mapping[str, Any]:
    """Return the packaged YAML configuration for the neural controller."""

    with resources.files(_CONFIG_PACKAGE).joinpath(_DEFAULT_CONFIG_NAME).open(
        "r", encoding="utf-8"
    ) as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, Mapping):  # pragma: no cover - defensive
        raise TypeError("neural controller config must be a mapping")
    return data


__all__ = ["load_default_config"]
