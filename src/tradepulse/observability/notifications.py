"""Notification helpers for email and Slack integrations."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Mapping

import httpx

__all__ = [
    "EmailSender",
    "SlackNotifier",
    "TeamsNotifier",
    "NotificationDispatcher",
]


class EmailSender:
    """Send notification emails via SMTP with optional TLS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipients: tuple[str, ...],
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: float = 10.0,
    ) -> None:
        if use_tls and use_ssl:
            raise ValueError("use_tls and use_ssl cannot both be enabled")
        if not recipients:
            raise ValueError("At least one recipient must be configured")
        self._host = host
        self._port = int(port)
        self._sender = sender
        self._recipients = recipients
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl
        self._timeout = float(timeout)

    async def send(
        self,
        subject: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = self._sender
        email["To"] = ", ".join(self._recipients)
        body = message
        if metadata:
            details = "\n".join(
                f"- {key}: {value}" for key, value in sorted(metadata.items())
            )
            body = f"{message}\n\nDetails:\n{details}"
        email.set_content(body)
        await asyncio.to_thread(self._deliver, email)

    def _deliver(self, email: EmailMessage) -> None:
        if self._use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self._host,
                self._port,
                timeout=self._timeout,
                context=context,
            ) as client:
                self._authenticate(client)
                client.send_message(email)
            return

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as client:
            if self._use_tls:
                context = ssl.create_default_context()
                client.starttls(context=context)
            self._authenticate(client)
            client.send_message(email)

    def _authenticate(self, client: smtplib.SMTP) -> None:
        if self._username and self._password:
            client.login(self._username, self._password)


class SlackNotifier:
    """Send notifications to Slack via incoming webhooks."""

    def __init__(
        self,
        webhook_url: str,
        *,
        channel: str | None = None,
        username: str | None = None,
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._channel = channel
        self._username = username
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def send(
        self,
        subject: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        text = f"*{subject}*\n{message}" if subject else message
        if metadata:
            details = "\n".join(
                f"• {key}: `{value}`" for key, value in sorted(metadata.items())
            )
            text = f"{text}\n{details}"
        payload: dict[str, Any] = {"text": text}
        if self._channel:
            payload["channel"] = self._channel
        if self._username:
            payload["username"] = self._username
        response = await self._client.post(
            self._webhook_url, json=payload, timeout=self._timeout
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class TeamsNotifier:
    """Send notifications to Microsoft Teams via incoming webhooks."""

    def __init__(
        self,
        webhook_url: str,
        *,
        theme_color: str | None = None,
        timeout: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._theme_color = theme_color.upper() if theme_color else None
        self._timeout = timeout
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def send(
        self,
        subject: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": subject or message,
            "title": subject or message,
            "text": message,
        }
        if self._theme_color:
            payload["themeColor"] = self._theme_color.lstrip("#")
        if metadata:
            payload.setdefault("sections", []).append(
                {
                    "title": "Details",
                    "facts": [
                        {"name": str(key), "value": str(value)}
                        for key, value in sorted(metadata.items())
                    ],
                    "markdown": True,
                }
            )
        response = await self._client.post(
            self._webhook_url, json=payload, timeout=self._timeout
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class NotificationDispatcher:
    """Coordinate notification delivery across configured channels."""

    def __init__(
        self,
        *,
        email_sender: EmailSender | None = None,
        slack_notifier: SlackNotifier | None = None,
        teams_notifier: TeamsNotifier | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._email_sender = email_sender
        self._slack_notifier = slack_notifier
        self._teams_notifier = teams_notifier
        self._logger = logger or logging.getLogger("tradepulse.notifications")

    async def dispatch(
        self,
        event: str,
        *,
        subject: str,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        tasks = []
        if self._email_sender is not None:
            tasks.append(self._email_sender.send(subject, message, metadata=metadata))
        if self._slack_notifier is not None:
            tasks.append(self._slack_notifier.send(subject, message, metadata=metadata))
        if self._teams_notifier is not None:
            tasks.append(self._teams_notifier.send(subject, message, metadata=metadata))

        if not tasks:
            self._logger.debug(
                "No notification channels configured; skipping dispatch.",
                extra={"event": event},
            )
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self._logger.error(
                    "Notification delivery failed",
                    exc_info=result,
                    extra={"event": event},
                )

    async def aclose(self) -> None:
        if self._slack_notifier is not None:
            await self._slack_notifier.aclose()
        if self._teams_notifier is not None:
            await self._teams_notifier.aclose()
