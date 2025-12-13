"""Incident response utilities."""

from __future__ import annotations

import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime
from typing import Any


class IncidentResponse:
    """Record and react to security incidents."""

    SEVERITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def __init__(self) -> None:
        self.incidents: list[dict[str, Any]] = []

    def report(self, severity: str, event: str, details: dict[str, Any]) -> None:
        if severity not in self.SEVERITY:
            raise ValueError(f"Unknown severity '{severity}'")
        incident = {
            "id": len(self.incidents),
            "timestamp": datetime.utcnow().isoformat(),
            "severity": severity,
            "event": event,
            "details": details,
            "status": "OPEN",
        }

        self.incidents.append(incident)

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
            # Integrate with SMTP or notification system in production.
            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp = smtplib.SMTP(smtp_host)
            smtp.send_message(msg)
            smtp.quit()
        except Exception:
            # Notification failures should not crash the reporter.
            pass

    def _kill_switch(self) -> None:
        """Emergency halt all trading (best-effort)."""

        try:
            from tradepulse.runtime import kill_switch
        except Exception:
            return
        activate = getattr(kill_switch, "activate", None)
        if callable(activate):
            try:
                activate()
            except Exception:
                pass


ir = IncidentResponse()
