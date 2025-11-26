"""Incident management helpers for automated workflows."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

__all__ = ["IncidentRecord", "IncidentManager"]


@dataclass(slots=True, frozen=True)
class IncidentRecord:
    """Reference to a persisted incident."""

    identifier: str
    directory: Path
    summary_path: Path


class IncidentManager:
    """Create incident records under ``reports/incidents``."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root or "reports/incidents").resolve()

    def create(
        self,
        *,
        title: str,
        description: str,
        metadata: Mapping[str, object] | None = None,
        severity: str = "major",
    ) -> IncidentRecord:
        """Persist an incident summary and return its reference."""

        timestamp = datetime.now(timezone.utc)
        year_directory = self._root / f"{timestamp.year:04d}"
        year_directory.mkdir(parents=True, exist_ok=True)

        date_prefix = timestamp.strftime("%Y%m%d")
        existing = sorted(
            path
            for path in year_directory.glob(f"INC-{date_prefix}-*")
            if path.is_dir()
        )
        identifier = f"INC-{date_prefix}-{len(existing) + 1:03d}"
        incident_dir = year_directory / identifier
        incident_dir.mkdir(parents=True, exist_ok=True)

        summary_path = incident_dir / "summary.json"
        payload = {
            "id": identifier,
            "title": title,
            "description": description,
            "severity": severity,
            "created_at": timestamp.isoformat(),
            "metadata": dict(metadata or {}),
        }
        summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return IncidentRecord(
            identifier=identifier, directory=incident_dir, summary_path=summary_path
        )
