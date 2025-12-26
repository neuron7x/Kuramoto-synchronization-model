"""Deprecated mirror. Canonical implementation lives in core.neuro.serotonin.serotonin_controller."""

from core.neuro.serotonin.serotonin_controller import (  # noqa: F401
    ControllerOutput,
    SerotoninConfig,
    SerotoninConfigEnvelope,
    SerotoninController,
    SerotoninLegacyConfig,
    _generate_config_table,
)

__all__ = [
    "ControllerOutput",
    "SerotoninConfig",
    "SerotoninConfigEnvelope",
    "SerotoninController",
    "SerotoninLegacyConfig",
    "_generate_config_table",
]
