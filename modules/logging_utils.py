"""Shared logging helpers for TradePulse modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional


@dataclass
class ModuleLoggingConfig:
    """Configuration for module-level structured logging."""

    enabled: bool = True
    level: int | str = logging.INFO
    base_fields: Dict[str, Any] = field(default_factory=dict)


def _resolve_level(level: int | str | None) -> int:
    if level is None:
        return logging.INFO
    if isinstance(level, int):
        return level
    level_name = str(level).upper()
    return logging._nameToLevel.get(level_name, logging.INFO)


def configure_module_logger(
    name: str, config: Optional[ModuleLoggingConfig | Dict[str, Any]] = None
) -> logging.Logger:
    """Return a logger configured according to the provided settings."""
    if config is None:
        resolved_config = ModuleLoggingConfig()
    elif isinstance(config, ModuleLoggingConfig):
        resolved_config = config
    else:
        resolved_config = ModuleLoggingConfig(**config)

    logger = logging.getLogger(name)
    logger.setLevel(_resolve_level(resolved_config.level))
    logger.disabled = not resolved_config.enabled
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    component: str,
    fields: Optional[Dict[str, Any]] = None,
    base_fields: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a structured log event using the unified JSON format."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level),
        "event": event,
        "component": component,
    }
    if base_fields:
        payload.update(base_fields)
    if fields:
        payload.update(fields)

    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
