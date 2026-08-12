#!/usr/bin/env python3
"""Evaluate context efficiency from a synthetic web-agent token trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_context_trace(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("events", [])
    if not isinstance(events, list) or not events:
        raise ValueError("Context trace must contain a non-empty 'events' list.")

    total_needed = 0
    total_used = 0
    total_noise = 0
    compacted = 0

    for event in events:
        needed = int(event.get("tokens_needed", 0))
        used = int(event.get("tokens_used", 0))
        if needed <= 0 or used <= 0:
            raise ValueError(f"Invalid token counts for {event.get('task_id')}")
        total_needed += needed
        total_used += used
        total_noise += int(event.get("noise_tokens_retained", 0))
        compacted += 1 if bool(event.get("compaction_applied")) else 0

    ratio = round(total_used / total_needed, 4)
    return {
        "artifact_id": "WEB_AGENT_CONTEXT_EFFICIENCY_EVAL_001",
        "status": (
            "PASS_SYNTHETIC_CONTEXT_TRACE_NOT_LIVE_RUNTIME"
            if ratio <= 1.25
            else "FAIL_CONTEXT_OVER_BUDGET"
        ),
        "measurement_mode": payload.get("measurement_mode", "unknown"),
        "context_efficiency": ratio,
        "tokens_needed": total_needed,
        "tokens_used": total_used,
        "noise_tokens_retained": total_noise,
        "compaction_rate": round(compacted / len(events), 4),
        "events_total": len(events),
        "target_ratio": 1.2,
        "failure_conditions": [
            "Do not treat synthetic token accounting as provider telemetry.",
            "Do not mark context efficiency production-grade until real runtime traces exist.",
            "If tokens_used_over_needed exceeds 1.2, the context gate remains below target.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate web-agent context efficiency trace.")
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.trace.read_text(encoding="utf-8"))
    result = evaluate_context_trace(payload)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
