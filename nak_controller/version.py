"""Version utilities for the TradePulse NaK controller package.

This module exposes :data:`__version__` by reading the installed package
metadata. When the package is not installed (for example during local
development) it falls back to the canonical packaging version declared in the
``pyproject.toml``.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from importlib import metadata

_FALLBACK_VERSION = "2.0.0"


def _detect_version() -> str:
    """Return the installed package version.

    The package metadata is the single source of truth. When it is not
    available (editable installs or source checkouts) we use the fallback value
    that mirrors the version in ``pyproject.toml`` to keep the code paths
    stable during development.
    """

    try:
        return metadata.version("tradepulse-nak")
    except metadata.PackageNotFoundError:
        return _FALLBACK_VERSION


__version__ = _detect_version()

__all__ = ["__version__"]
