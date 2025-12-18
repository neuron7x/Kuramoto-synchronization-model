"""Incident response utilities."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Any, Callable

logger = logging.getLogger(__name__)


class IncidentResponse:
    """Record and react to security incidents."""

    SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def __init__(self, kill_switch_hook: Callable[[], None] | None = None) -> None:
        self.incidents: list[dict[str, Any]] = []
        self._next_id: int = 0
        self._kill_switch_hook = kill_switch_hook

    def report(self, severity: str, event: str, details: dict[str, Any]) -> None:
        if severity not in self.SEVERITY:
            raise ValueError(f"Unknown severity '{severity}'")
        incident = {
            "id": self._next_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": severity,
            "event": event,
            "details": details,
            "status": "OPEN",
        }

        self.incidents.append(incident)
        self._next_id += 1

        if self.SEVERITY[severity] >= self.SEVERITY["HIGH"]:
            self._alert(incident)

        if severity == "CRITICAL":
            self._kill_switch()

    def _alert(self, incident: dict[str, Any]) -> None:
        try:
            msg = MIMEText(f"SECURITY INCIDENT: {incident}")
            msg["Subject"] = f"[{incident['severity']}] {incident['event']}"
            msg["From"] = "security@tradepulse.com"
            msg["To"] = "security-team@tradepulse.com"
            # SMTP configuration supports TLS/auth; integrate with other notifiers as needed.
            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "25"))
            use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
            smtp_user = os.getenv("SMTP_USERNAME")
            smtp_password = os.getenv("SMTP_PASSWORD")
            if not smtp_user or not smtp_password:
                logger.warning(
                    "Missing SMTP credentials; incident alerts will be sent without authentication"
                )
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
                if use_tls:
                    smtp.starttls()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
        except Exception as exc:
            logger.warning("Failed to send security incident alert", exc_info=exc)

    def _kill_switch(self) -> None:
        """Emergency halt all trading (best-effort)."""

        if self._kill_switch_hook is not None:
            try:
                self._kill_switch_hook()
            except Exception as exc:
                logger.warning("Kill switch hook execution failed", exc_info=exc)
            return

        try:
            from tradepulse.runtime import kill_switch
        except ImportError:
            return
        activate = getattr(kill_switch, "activate", None)
        if callable(activate):
            try:
                activate()
            except Exception as exc:
                logger.warning("Kill switch activation failed", exc_info=exc)


ir = IncidentResponse()
