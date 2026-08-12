# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Structured audit logging for thermodynamic decisions."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_AUDIT_PATH = Path(os.getenv("GEOSYNC_AUDIT_PATH", "/var/log/geosync/thermo_audit.jsonl"))


@dataclass(slots=True)
class AuditRecord:
    timestamp: float
    module: str
    action_class: str
    description: str
    F_now: float
    F_next: float
    delta_F: float
    decision: str
    reason: str
    system_state: str
    dual_approved: bool


def log_action(
    module: str,
    action_class: str,
    description: str,
    *,
    F_now: float,
    F_next: float,
    decision: str,
    reason: str,
    system_state: str,
    dual_approved: bool,
    audit_path: Path | None = None,
) -> None:
    path = audit_path or DEFAULT_AUDIT_PATH
    record = AuditRecord(
        timestamp=time.time(),
        module=module,
        action_class=action_class,
        description=description,
        F_now=F_now,
        F_next=F_next,
        delta_F=F_next - F_now,
        decision=decision,
        reason=reason,
        system_state=system_state,
        dual_approved=dual_approved,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(record), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


__all__ = ["AuditRecord", "log_action", "DEFAULT_AUDIT_PATH"]
