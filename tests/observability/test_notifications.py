# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
from typing import Any, Mapping

import pytest

from observability.notifications import (
    EmailSender,
    NotificationDispatcher,
    SlackNotifier,
    TeamsNotifier,
)


@pytest.mark.asyncio()
async def test_email_sender_constructs_message(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _DummySMTP:
        def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.authed: tuple[str, str] | None = None
            self.message: EmailMessage | None = None

        def __enter__(self) -> "_DummySMTP":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - no cleanup
            return None

        def starttls(self, *, context=None) -> None:
            self.started_tls = True

        def login(self, username: str, password: str) -> None:
            self.authed = (username, password)

        def send_message(self, message: EmailMessage) -> None:
            self.message = message

    def _smtp_factory(*args: Any, **kwargs: Any) -> _DummySMTP:
        instance = _DummySMTP(*args, **kwargs)
        captured["instance"] = instance
        return instance

    from email.message import EmailMessage

    from observability import notifications as notifications_module

    monkeypatch.setattr(notifications_module.smtplib, "SMTP", _smtp_factory)

    sender = EmailSender(
        host="smtp.example.com",
        port=587,
        sender="alerts@example.com",
        recipients=("ops@example.com",),
        username="user",
        password="secret",
        use_tls=True,
        use_ssl=False,
    )

    await sender.send("GeoSync Alert", "Order executed", metadata={"order_id": "abc"})

    instance: _DummySMTP = captured["instance"]
    assert instance.started_tls is True
    assert instance.authed == ("user", "secret")
    assert instance.message is not None
    payload = instance.message.get_content()
    assert "Order executed" in payload
    assert "order_id" in payload


@pytest.mark.asyncio()
async def test_slack_notifier_posts_payload() -> None:
    events: list[dict[str, Any]] = []

    class _DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class _DummyClient:
        def __init__(self) -> None:
            self.closed = False

        async def post(self, url: str, *, json: dict[str, Any], timeout: float) -> _DummyResponse:
            events.append({"url": url, "payload": json, "timeout": timeout})
            return _DummyResponse()

        async def aclose(self) -> None:
            self.closed = True

    client = _DummyClient()
    notifier = SlackNotifier(
        "https://hooks.slack.com/services/test",
        channel="#alerts",
        username="GeoSync",
        timeout=3.0,
        client=client,
    )

    await notifier.send("Alert", "Order executed", metadata={"symbol": "BTCUSD"})
    await notifier.aclose()

    assert events, "expected webhook payload to be posted"
    payload = events[0]["payload"]
    assert payload["channel"] == "#alerts"
    assert payload["username"] == "GeoSync"
    assert "BTCUSD" in payload["text"]
    assert client.closed is False


@pytest.mark.asyncio()
async def test_teams_notifier_posts_payload() -> None:
    events: list[dict[str, Any]] = []

    class _DummyResponse:
        def raise_for_status(self) -> None:
            return None

    class _DummyClient:
        def __init__(self) -> None:
            self.closed = False

        async def post(self, url: str, *, json: dict[str, Any], timeout: float) -> _DummyResponse:
            events.append({"url": url, "payload": json, "timeout": timeout})
            return _DummyResponse()

        async def aclose(self) -> None:
            self.closed = True

    client = _DummyClient()
    notifier = TeamsNotifier(
        "https://outlook.office.com/webhook/test",
        theme_color="#2eb886",
        timeout=4.0,
        client=client,
    )

    await notifier.send("Deploy", "Deployment completed", metadata={"environment": "staging"})
    await notifier.aclose()

    assert events, "expected webhook payload to be posted"
    payload = events[0]["payload"]
    assert payload["text"].startswith("Deployment completed")
    assert payload["sections"][0]["facts"][0]["name"] == "environment"
    assert client.closed is False


@pytest.mark.asyncio()
async def test_dispatcher_routes_to_all_channels() -> None:
    email_calls: list[tuple[str, str]] = []
    slack_calls: list[str] = []
    teams_calls: list[str] = []

    class _EmailStub:
        async def send(
            self,
            subject: str,
            message: str,
            *,
            metadata: Mapping[str, Any] | None = None,
        ) -> None:
            email_calls.append((subject, message))

    class _SlackStub:
        async def send(
            self,
            subject: str,
            message: str,
            *,
            metadata: Mapping[str, Any] | None = None,
        ) -> None:
            slack_calls.append(subject)

        async def aclose(self) -> None:
            return None

    class _TeamsStub:
        async def send(
            self,
            subject: str,
            message: str,
            *,
            metadata: Mapping[str, Any] | None = None,
        ) -> None:
            teams_calls.append(message)

        async def aclose(self) -> None:
            return None

    dispatcher = NotificationDispatcher(
        email_sender=_EmailStub(),
        slack_notifier=_SlackStub(),
        teams_notifier=_TeamsStub(),
        logger=logging.getLogger("test.notifications"),
    )

    await dispatcher.dispatch(
        "order.submitted",
        subject="Order Created",
        message="New order submitted",
        metadata={"order_id": "abc"},
    )

    assert email_calls == [("Order Created", "New order submitted")]
    assert slack_calls == ["Order Created"]
    assert teams_calls == ["New order submitted"]
