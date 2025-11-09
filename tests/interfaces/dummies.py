"""Test helpers for LiveTradingRunner secrets integration."""

from __future__ import annotations

from typing import Mapping

from tradepulse.execution.connectors import ExecutionConnector


class DummyConnector(ExecutionConnector):
    """Minimal connector used to exercise credential plumbing in tests."""

    def __init__(self, *, sandbox: bool = True) -> None:
        super().__init__(sandbox=sandbox)
        self.connected: bool = False
        self.last_credentials: Mapping[str, str] | None = None

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:  # type: ignore[override]
        self.connected = True
        self.last_credentials = credentials

    def disconnect(self) -> None:  # type: ignore[override]
        self.connected = False
        self.last_credentials = None


__all__ = ["DummyConnector"]
