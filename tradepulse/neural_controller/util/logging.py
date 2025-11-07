"""Minimal structured logging helpers for neural decisions."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


def setup_json_logger(level: str = "INFO") -> logging.Logger:
    """Configure a JSON logger for neural controller decisions."""

    log_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("neural_controller")
    logger.propagate = False
    logger.handlers = [handler]
    logger.setLevel(log_level)
    return logger


def log_decision(logger: logging.Logger, **payload: Any) -> None:
    """Emit a structured JSON decision payload."""

    logger.info(json.dumps(payload, ensure_ascii=False))
