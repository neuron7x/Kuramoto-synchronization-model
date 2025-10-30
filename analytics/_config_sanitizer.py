# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Utilities for sanitizing experiment configurations before logging."""
from __future__ import annotations

import re
from typing import Any

from omegaconf import DictConfig, OmegaConf

_REDACTED_PLACEHOLDER = "***REDACTED***"
_SENSITIVE_TOKENS = (
    "password",
    "secret",
    "token",
    "apikey",
    "api_key",
    "credential",
    "auth",
    "key",
)

_CAMELCASE_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def _iter_key_tokens(key: str) -> list[str]:
    """Return normalized tokens extracted from a configuration key."""

    normalized = _CAMELCASE_BOUNDARY.sub(r"\1_\2", key)
    normalized = normalized.lower()
    return [token for token in re.split(r"[^0-9a-z]+", normalized) if token]


def _is_sensitive_key(key: str) -> bool:
    """Return ``True`` when the provided configuration key is sensitive."""

    return any(token in _SENSITIVE_TOKENS for token in _iter_key_tokens(key))


def _redact_sensitive_data(data: Any) -> Any:
    """Return a copy of ``data`` with sensitive keys masked."""

    if isinstance(data, dict):
        return {
            key: (
                _REDACTED_PLACEHOLDER
                if _is_sensitive_key(str(key))
                else _redact_sensitive_data(value)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_sensitive_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(_redact_sensitive_data(item) for item in data)
    return data


def redacted_config_yaml(cfg: DictConfig) -> str:
    """Serialize ``cfg`` to YAML with sensitive values redacted."""

    container = OmegaConf.to_container(
        cfg,
        resolve=False,
        throw_on_missing=False,
    )
    redacted_container = _redact_sensitive_data(container)
    redacted_conf = OmegaConf.create(redacted_container)
    return OmegaConf.to_yaml(redacted_conf, resolve=False)


__all__ = ["redacted_config_yaml"]
