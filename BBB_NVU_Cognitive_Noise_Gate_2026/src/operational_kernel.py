"""Canonical operational envelope for BBB-NVU deterministic inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from BBB_NVU_Cognitive_Noise_Gate_2026.src.audit import (
    AuditEvent,
    build_replay_bundle,
    verify_replay_bundle,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import canonical, sha256_text
from BBB_NVU_Cognitive_Noise_Gate_2026.src.observability import (
    build_incident_register,
    build_metrics_snapshot,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.src.runtime_boundary import RuntimeBoundary, RuntimeRequest

OPERATIONAL_ENVELOPE_VERSION = "BBB-NVU-CNG-operational-envelope.1"
RequestMapping = dict[str, Any]


class OperationalEnvelope(BaseModel):
    """Complete deterministic packet for integration consumers."""

    model_config = ConfigDict(extra="forbid")

    envelope_version: StrictStr
    created_at: StrictStr
    request_count: StrictInt = Field(ge=0)
    outputs: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    replay_bundles: list[dict[str, Any]]
    metrics_snapshot: dict[str, Any]
    incidents: list[dict[str, Any]]
    manifest: dict[str, Any]
    envelope_hash: StrictStr

    def to_json(self) -> str:
        """Serialize the envelope deterministically."""
        return canonical(self.model_dump())


class OperationalKernel:
    """End-to-end deterministic execution boundary for product integration."""

    def __init__(self, rules: Mapping[str, Any], engine_hash: str | None = None):
        self.rules = dict(rules)
        self.boundary = RuntimeBoundary(self.rules, engine_hash=engine_hash)

    def execute(
        self,
        requests: Sequence[RuntimeRequest | RequestMapping],
        *,
        created_at: str,
    ) -> OperationalEnvelope:
        """Run inference and return outputs, audit, replay, metrics, incidents, and manifest."""
        normalized_requests: list[RuntimeRequest] = []
        for request in requests:
            if isinstance(request, RuntimeRequest):
                normalized_requests.append(request)
            else:
                normalized_requests.append(RuntimeRequest.model_validate(request))

        outputs = [
            self.boundary.engine.build_output(
                request.input_doc,
                source_id=request.source_id,
                created_at=created_at,
            )
            for request in normalized_requests
        ]
        audit_events = [AuditEvent.from_output(output) for output in outputs]
        replay_bundles = [
            build_replay_bundle(output, request.input_doc, self.rules)
            for output, request in zip(outputs, normalized_requests, strict=True)
        ]
        metrics_snapshot = build_metrics_snapshot(outputs, created_at=created_at)
        incidents = build_incident_register(outputs)
        manifest_body: dict[str, Any] = {
            "output_hashes": [sha256_text(canonical(output)) for output in outputs],
            "audit_event_hashes": [
                sha256_text(event.to_jsonl().rstrip("\n")) for event in audit_events
            ],
            "replay_bundle_hashes": [bundle["bundle_hash"] for bundle in replay_bundles],
            "metrics_snapshot_id": metrics_snapshot.snapshot_id,
            "incident_ids": [incident.incident_id for incident in incidents],
            "replay_verified": [verify_replay_bundle(bundle) for bundle in replay_bundles],
        }
        manifest: dict[str, Any] = {
            "manifest_version": "BBB-NVU-CNG-manifest.1",
            "created_at": created_at,
            "rules_version": self.rules.get("rules_version", "unknown"),
            "engine_version": outputs[0]["engine_version"] if outputs else "unknown",
            "request_count": len(normalized_requests),
            **manifest_body,
        }
        envelope_body: dict[str, Any] = {
            "envelope_version": OPERATIONAL_ENVELOPE_VERSION,
            "created_at": created_at,
            "request_count": len(normalized_requests),
            "outputs": outputs,
            "audit_events": [event.model_dump() for event in audit_events],
            "replay_bundles": replay_bundles,
            "metrics_snapshot": metrics_snapshot.model_dump(),
            "incidents": [incident.model_dump() for incident in incidents],
            "manifest": manifest,
        }
        return OperationalEnvelope(
            envelope_hash=sha256_text(canonical(envelope_body)),
            **envelope_body,
        )


def _replay_bundle_hash_is_valid(bundle: Mapping[str, Any]) -> bool:
    body = dict(bundle)
    expected = str(body.pop("bundle_hash", ""))
    return bool(expected) and sha256_text(canonical(body)) == expected


def verify_operational_envelope(envelope: OperationalEnvelope | Mapping[str, Any]) -> bool:
    """Verify envelope hash, manifest hashes, replay checks, and cardinalities."""
    try:
        data = (
            envelope.model_dump() if isinstance(envelope, OperationalEnvelope) else dict(envelope)
        )
        expected_hash = str(data.get("envelope_hash", ""))
        body = dict(data)
        body.pop("envelope_hash", None)
        if not expected_hash or sha256_text(canonical(body)) != expected_hash:
            return False

        outputs = cast(list[dict[str, Any]], list(data.get("outputs", [])))
        audit_events = cast(list[dict[str, Any]], list(data.get("audit_events", [])))
        replay_bundles = cast(list[dict[str, Any]], list(data.get("replay_bundles", [])))
        incidents = cast(list[dict[str, Any]], list(data.get("incidents", [])))
        metrics_snapshot = cast(dict[str, Any], dict(data.get("metrics_snapshot", {})))
        manifest = cast(dict[str, Any], dict(data.get("manifest", {})))

        if data.get("request_count") != len(outputs):
            return False
        if len(audit_events) != len(outputs) or len(replay_bundles) != len(outputs):
            return False
        if manifest.get("request_count") != len(outputs):
            return False

        output_hashes = [sha256_text(canonical(output)) for output in outputs]
        audit_event_hashes = [sha256_text(canonical(event)) for event in audit_events]
        replay_bundle_hashes = [bundle.get("bundle_hash") for bundle in replay_bundles]
        replay_verified = [verify_replay_bundle(bundle) for bundle in replay_bundles]
        metric_snapshot_id = metrics_snapshot.get("snapshot_id")
        incident_ids = [incident.get("incident_id") for incident in incidents]

        return (
            manifest.get("output_hashes") == output_hashes
            and manifest.get("audit_event_hashes") == audit_event_hashes
            and manifest.get("replay_bundle_hashes") == replay_bundle_hashes
            and all(_replay_bundle_hash_is_valid(bundle) for bundle in replay_bundles)
            and manifest.get("replay_verified") == replay_verified
            and manifest.get("metrics_snapshot_id") == metric_snapshot_id
            and manifest.get("incident_ids") == incident_ids
        )
    except (KeyError, TypeError, ValueError):
        return False
