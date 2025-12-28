"""Shim for canonical serotonin controller located under ``tradepulse.core``."""

from tradepulse.core.neuro.serotonin.serotonin_controller import (  # noqa: F401
    _generate_config_table,
)
from tradepulse.core.neuro.serotonin.serotonin_controller import *  # noqa: F401,F403

__CANONICAL__ = False
