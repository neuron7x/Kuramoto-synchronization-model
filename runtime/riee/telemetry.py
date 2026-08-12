from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def emit_riee_event(
    status: Any,
    gamma_fact: float,
    gamma_claim: float,
    out_path: Path = Path("artifacts/quarantine/riee_events.jsonl"),
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    status_payload = asdict(status) if is_dataclass(status) else {"repr": repr(status)}
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gamma_fact": gamma_fact,
        "gamma_claim": gamma_claim,
        "status": status_payload,
    }
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
