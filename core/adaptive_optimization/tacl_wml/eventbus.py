"""Event bus for WML state changes."""

from typing import Dict, Any, Callable, List, Tuple


class EventBus:
    """Base event bus interface."""

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        """Emit an event.

        Args:
            event: Event name
            data: Event data
        """
        raise NotImplementedError

    def subscribe(self, event: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to an event.

        Args:
            event: Event name
            handler: Callback function
        """
        raise NotImplementedError


class RecordingEventBus(EventBus):
    """Event bus that records events for testing/debugging."""

    def __init__(self) -> None:
        """Initialize recording event bus."""
        self._events: List[Tuple[str, Dict[str, Any]]] = []
        self._handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def emit(self, event: str, data: Dict[str, Any]) -> None:
        """Emit and record an event."""
        self._events.append((event, data))
        for handler in self._handlers.get(event, []):
            handler(data)

    def subscribe(self, event: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to an event."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def get_events(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Get all recorded events.

        Returns:
            List of (event_name, event_data) tuples
        """
        return self._events.copy()

    def clear(self) -> None:
        """Clear recorded events."""
        self._events.clear()
