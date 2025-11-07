"""Configuration resources for the NaK controller package."""
from __future__ import annotations

from importlib import resources
from typing import Final

PACKAGE_NAME: Final = "nak_controller"
DEFAULT_CONFIG_PATH = resources.files(PACKAGE_NAME).joinpath("conf", "nak.yaml")

__all__ = ["DEFAULT_CONFIG_PATH", "PACKAGE_NAME"]
