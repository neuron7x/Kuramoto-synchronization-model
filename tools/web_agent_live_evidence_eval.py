#!/usr/bin/env python3
"""Evaluate live evidence and adapter verification boundaries for the web agent.

This evaluator is deliberately conservative: blocked unverified adapters can
mitigate critical risk, but they do not count as full live adapter verification.
Numbers are cute. Runtime evidence is cuter.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

UNVERIFIED_STATUSES = {"NOT_VERIFIED", "NOT_VERIFIED_IN_THIS_CONNECTOR_PASS"}
DISABLED_STATUS = "DISABLED_UNTIL_VERIFIED"


def evaluate_live_evidence(
    trace_payload: dict[str, Any], adapter_payload: dict[str, Any]
) -> dict[str, Any]:
    events = trace_payload.get("events", [])
    adapters = adapter_payload.get("adapters", [])
    if not isinstance(events, list) or not events:
        raise ValueError("Live trace must contain a non-empty events list.")
    if not isinstance(adapters, list) or not adapters:
        raise ValueError("Adapter matrix must contain a non-empty adapters list.")

    event_ids = {event.get("event_id") for event in events}
    bad_events = [
        event.get("event_id")
        for event in events
        if not event.get("contract_match")
        or event.get("result") not in {"success", "success_pending_this_patch"}
        or (event.get("confirmation_required") and not event.get("confirmation_present"))
    ]

    unverified_enabled = []
    enabled_without_trace = []
    verified_count = 0
    disabled_count = 0

    for adapter in adapters:
        tool_id = adapter.get("tool_id")
        live_status = str(adapter.get("live_status", ""))
        runtime_status = str(adapter.get("runtime_status", ""))
        trace_ids = set(adapter.get("trace_ids", []))

        is_unverified = live_status in UNVERIFIED_STATUSES or live_status.startswith("NOT_VERIFIED")
        is_disabled = runtime_status == DISABLED_STATUS

        if is_unverified and not is_disabled:
            unverified_enabled.append(tool_id)
        if not is_unverified and "ENABLED" in runtime_status:
            verified_count += 1
            if not trace_ids or not trace_ids.issubset(event_ids):
                enabled_without_trace.append(tool_id)
        if is_disabled:
            disabled_count += 1

    critical_unmitigated = len(unverified_enabled) + len(enabled_without_trace) + len(bad_events)
    full_live_adapter_verification = (
        critical_unmitigated == 0 and disabled_count == 0 and verified_count == len(adapters)
    )

    return {
        "artifact_id": "WEB_AGENT_LIVE_EVIDENCE_EVAL_001",
        "status": (
            "PASS_CRITICAL_RISK_MITIGATED_NOT_FULL_PRODUCTION_READY"
            if critical_unmitigated == 0
            else "FAIL_UNMITIGATED_LIVE_EVIDENCE_RISK"
        ),
        "measurement_mode": "live_github_connector_trace_plus_adapter_disable_policy",
        "live_runtime_trace": critical_unmitigated == 0 and len(events) > 0,
        "live_tool_adapter_verification": full_live_adapter_verification,
        "unverified_adapters_disabled": len(unverified_enabled) == 0,
        "github_adapter_subset_verified": verified_count >= 3,
        "critical_unmitigated_adapters": critical_unmitigated,
        "unverified_enabled_adapters": len(unverified_enabled),
        "events_checked": len(events),
        "adapters_checked": len(adapters),
        "bad_events": bad_events,
        "enabled_without_trace": enabled_without_trace,
        "unverified_enabled": unverified_enabled,
        "production_interpretation": (
            "Live runtime trace exists for the GitHub connector subset. Full tool "
            "adapter verification remains false when any adapter is disabled until verified."
        ),
        "failure_conditions": [
            "Do not mark live_tool_adapter_verification true from this artifact unless every adapter is live verified.",
            "Do not enable disabled adapters without live trace evidence.",
            "Do not treat branch-scoped GitHub writes as deployment approval.",
            "Do not merge as production release without CI evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate live evidence boundary for the web-agent protocol."
    )
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--adapter-matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    trace_payload = json.loads(args.trace.read_text(encoding="utf-8"))
    adapter_payload = json.loads(args.adapter_matrix.read_text(encoding="utf-8"))
    result = evaluate_live_evidence(trace_payload, adapter_payload)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
