"""Configuration helpers for the neural controller package."""

from __future__ import annotations

import io
import pkgutil
from typing import Any, Mapping

import yaml

_CONFIG_PACKAGE = __name__
_DEFAULT_CONFIG_NAME = "neural_params.yaml"


def _load_packaged_yaml(name: str) -> Mapping[str, Any]:
    """Load a YAML document packaged with the module.

    The implementation deliberately avoids :mod:`importlib.resources` so the
    controller remains compatible with Python releases that only provide the
    older :mod:`pkgutil` resource API.  This keeps the Semgrep compatibility
    checks green without introducing an additional runtime dependency on the
    ``importlib_resources`` backport.
    """

    data = pkgutil.get_data(_CONFIG_PACKAGE, name)
    if data is None:  # pragma: no cover - defensive
        raise FileNotFoundError(f"unable to locate packaged config: {name}")
    stream = io.StringIO(data.decode("utf-8"))
    parsed = yaml.safe_load(stream)
    if not isinstance(parsed, Mapping):  # pragma: no cover - defensive
        raise TypeError("neural controller config must be a mapping")
    return parsed


def load_default_config() -> Mapping[str, Any]:
    """Return the packaged YAML configuration for the neural controller."""

    cfg = dict(_load_packaged_yaml(_DEFAULT_CONFIG_NAME))
    include_name = cfg.get("include") or cfg.get("ref")
    if include_name:
        try:
            include_cfg = _load_packaged_yaml(str(include_name))
        except FileNotFoundError:
            return cfg
        merged = dict(cfg)
        merged.update(include_cfg)
        return merged
    return cfg


__all__ = ["load_default_config"]
