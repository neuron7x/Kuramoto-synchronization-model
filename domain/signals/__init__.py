"""Signal bounded context within the domain layer."""

from .entity import Signal
from .value_objects import SignalAction

__all__ = ["Signal", "SignalAction"]
