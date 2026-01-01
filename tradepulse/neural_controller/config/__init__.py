"""Configuration helpers for the neural controller package."""

from __future__ import annotations

import io
import logging
import pkgutil
from typing import Any, Mapping

import yaml

_CONFIG_PACKAGE = __name__
_DEFAULT_CONFIG_NAME = "neural_params.yaml"
_LOGGER = logging.getLogger(__name__)


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


def _safe_merge(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
    *,
    path: tuple[str, ...] = (),
    allow_new_keys: bool = False,
    warn_unknown: bool = True,
) -> Mapping[str, Any]:
    merged: dict[str, Any] = {}
    for key, base_value in base.items():
        if key in override:
            override_value = override[key]
            if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
                merged[key] = _safe_merge(
                    base_value, override_value, path=(*path, str(key))
                )
            else:
                merged[key] = override_value
        else:
            merged[key] = base_value
    for key in override:
        if key not in base:
            dotted = ".".join((*path, str(key)))
            if warn_unknown:
                _LOGGER.warning("Ignoring unknown config key %s", dotted)
            if allow_new_keys:
                merged[key] = override[key]
    return merged


def merge_config(
    base: Mapping[str, Any],
    override: Mapping[str, Any] | None,
    *,
    safe_merge: bool = True,
) -> Mapping[str, Any]:
    if override is None:
        return dict(base)
    if not isinstance(override, Mapping):
        raise TypeError("override config must be a mapping")
    if safe_merge:
        return _safe_merge(base, override)
    merged = dict(base)
    merged.update(override)
    return merged


def load_default_config(*, safe_merge: bool = True) -> Mapping[str, Any]:
    """Return the packaged YAML configuration for the neural controller."""

    cfg = dict(_load_packaged_yaml(_DEFAULT_CONFIG_NAME))
    include_name = cfg.get("include") or cfg.get("ref")
    if include_name:
        try:
            include_cfg = _load_packaged_yaml(str(include_name))
        except FileNotFoundError:
            return cfg
        if safe_merge:
            return _safe_merge(
                cfg,
                include_cfg,
                allow_new_keys=True,
                warn_unknown=False,
            )
        return merge_config(cfg, include_cfg, safe_merge=False)
    return cfg


__all__ = ["load_default_config", "merge_config"]
