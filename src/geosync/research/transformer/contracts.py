# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed research envelopes for the GeoSync inference transformer control plane.

This module defines inert data contracts. It does not execute orders, route capital,
or promote research hypotheses. Every object is designed to preserve provenance,
uncertainty, and explicit claim boundaries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ClaimTier(str, Enum):
    """Allowed evidence tiers for research-line claims."""

    HYPOTHESIS = "HYPOTHESIS"
    INSTRUMENTED = "INSTRUMENTED"
    MEASURED_SINGLE = "MEASURED_SINGLE"
    MEASURED_MULTI = "MEASURED_MULTI"
    LIMITED_EMPIRICAL = "LIMITED_EMPIRICAL"
    REJECTED = "REJECTED"
    BLOCKED_COST_MODEL = "BLOCKED_COST_MODEL"


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Return stable JSON for hashing and reproducible evidence artifacts."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(payload: Mapping[str, Any]) -> str:
    """Return a deterministic sha256 digest for a JSON-like mapping."""

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _as_tier(value: ClaimTier | str) -> ClaimTier:
    try:
        return value if isinstance(value, ClaimTier) else ClaimTier(str(value))
    except ValueError as exc:
        allowed = ", ".join(t.value for t in ClaimTier)
        raise ValueError(f"invalid claim_tier={value!r}; allowed={allowed}") from exc


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_mapping(name: str, value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")


def validate_no_forbidden_promotions(text: str, forbidden_terms: list[str]) -> None:
    """Reject claim-promotion language outside an explicit evidence authority.

    The check is intentionally lexical and conservative. It is a guardrail for
    research documents, not a semantic proof system.
    """

    lowered = text.lower()
    hits = sorted({term for term in forbidden_terms if term.lower() in lowered})
    if hits:
        raise ValueError("forbidden promotion terms detected: " + ", ".join(hits))


@dataclass(frozen=True)
class GeometryState:
    """Multi-view geometric state with explicit domain and uncertainty."""

    method_version: str
    domain: str
    ricci_summary: Mapping[str, Any] = field(default_factory=dict)
    kuramoto_summary: Mapping[str, Any] = field(default_factory=dict)
    topology_summary: Mapping[str, Any] = field(default_factory=dict)
    uncertainty: Mapping[str, Any] = field(default_factory=dict)
    downgrade_reason: str = "not_measured"

    def __post_init__(self) -> None:
        _require_text("method_version", self.method_version)
        _require_text("domain", self.domain)
        _require_text("downgrade_reason", self.downgrade_reason)
        _require_mapping("ricci_summary", self.ricci_summary)
        _require_mapping("kuramoto_summary", self.kuramoto_summary)
        _require_mapping("topology_summary", self.topology_summary)
        _require_mapping("uncertainty", self.uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_version": self.method_version,
            "domain": self.domain,
            "ricci_summary": dict(self.ricci_summary),
            "kuramoto_summary": dict(self.kuramoto_summary),
            "topology_summary": dict(self.topology_summary),
            "uncertainty": dict(self.uncertainty),
            "downgrade_reason": self.downgrade_reason,
        }


@dataclass(frozen=True)
class RegimeCertificate:
    """Runtime passport for one research inference result."""

    run_id: str
    research_line: str
    regime_label: str
    claim_tier: ClaimTier | str
    confidence: float
    domain: str
    geometry_state: GeometryState
    downgrade_reason: str
    assumptions: tuple[str, ...] = ()
    status: str = "ABSTAIN"

    def __post_init__(self) -> None:
        _require_text("run_id", self.run_id)
        _require_text("research_line", self.research_line)
        _require_text("regime_label", self.regime_label)
        _require_text("domain", self.domain)
        _require_text("downgrade_reason", self.downgrade_reason)
        if not isinstance(self.geometry_state, GeometryState):
            raise ValueError("geometry_state must be a GeometryState")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be within [0.0, 1.0]")
        object.__setattr__(self, "claim_tier", _as_tier(self.claim_tier))
        if self.claim_tier is ClaimTier.HYPOTHESIS and self.status != "ABSTAIN":
            raise ValueError("HYPOTHESIS certificates must keep status=ABSTAIN")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "research_line": self.research_line,
            "regime_label": self.regime_label,
            "claim_tier": self.claim_tier.value,
            "confidence": float(self.confidence),
            "domain": self.domain,
            "geometry_state": self.geometry_state.to_dict(),
            "downgrade_reason": self.downgrade_reason,
            "assumptions": list(self.assumptions),
            "status": self.status,
        }


@dataclass(frozen=True)
class ResearchInferenceArtifact:
    """Canonical envelope for an evidence-bound research inference artifact."""

    run_id: str
    git_sha: str
    data_sha256: str
    config_sha256: str
    replay_command: str
    certificate: RegimeCertificate

    def __post_init__(self) -> None:
        _require_text("run_id", self.run_id)
        _require_text("git_sha", self.git_sha)
        _require_text("data_sha256", self.data_sha256)
        _require_text("config_sha256", self.config_sha256)
        _require_text("replay_command", self.replay_command)
        if not isinstance(self.certificate, RegimeCertificate):
            raise ValueError("certificate must be a RegimeCertificate")
        if self.certificate.run_id != self.run_id:
            raise ValueError("artifact run_id must match certificate run_id")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "git_sha": self.git_sha,
            "data_sha256": self.data_sha256,
            "config_sha256": self.config_sha256,
            "replay_command": self.replay_command,
            "certificate": self.certificate.to_dict(),
        }
        payload["output_sha256"] = sha256_json(payload)
        return payload
