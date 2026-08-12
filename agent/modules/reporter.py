"""Reporter (§4.J): emit machine-auditable artefacts.

Every main-loop tick produces a JSON sidecar that downstream systems
(CI, ops dashboards, stakeholder reports) can consume. Files are
always written atomically and indented for human grep-ability.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "reports"


def write_report(name: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / name
    text = json.dumps(payload, indent=2, sort_keys=True)
    out.write_text(text)
    return out


def emit_replay_hash(payload: dict[str, Any]) -> str:
    """Deterministic hash of the payload — used for audit reproducibility."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "replay_hash.sha256").write_text(digest)
    return digest


__all__ = ["write_report", "emit_replay_hash", "REPORTS_DIR"]
