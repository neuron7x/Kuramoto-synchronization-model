from __future__ import annotations

import logging
import sys

def setup_logger(level: str = "INFO") -> None:
    """Configure root logger with stdout handler and uniform format."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(lvl)
