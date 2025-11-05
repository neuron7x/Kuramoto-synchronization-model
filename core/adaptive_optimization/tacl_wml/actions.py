"""Action abstractions and execution guards."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Any, Generator


@dataclass
class ActionPlan:
    """Plan for system adjustments."""

    timing: Dict[str, Any]
    conduct: Dict[str, Any]
    metabolic: Dict[str, Any]

    def __eq__(self, other: object) -> bool:
        """Check equality of action plans."""
        if not isinstance(other, ActionPlan):
            return False
        return (
            self.timing == other.timing
            and self.conduct == other.conduct
            and self.metabolic == other.metabolic
        )


class Action:
    """Base class for system actions."""

    def apply(self, path: str, plan: ActionPlan) -> None:
        """Apply the action plan to the system."""
        raise NotImplementedError

    def rollback(self, path: str, plan: ActionPlan) -> None:
        """Rollback the action plan."""
        raise NotImplementedError


class NoOpActions(Action):
    """No-op action implementation for testing."""

    def apply(self, path: str, plan: ActionPlan) -> None:
        """No-op apply."""
        pass

    def rollback(self, path: str, plan: ActionPlan) -> None:
        """No-op rollback."""
        pass


@contextmanager
def guarded_apply(
    actions: Action, path: str, plan: ActionPlan
) -> Generator[None, None, None]:
    """Apply actions with automatic rollback on exception.

    Args:
        actions: Action implementation
        path: Hot path identifier
        plan: Action plan to apply

    Yields:
        None

    Raises:
        Exception: Re-raises any exception after rollback
    """
    actions.apply(path, plan)
    try:
        yield
    except Exception:
        actions.rollback(path, plan)
        raise
