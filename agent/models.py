"""Data structures for the GeoSync Resurrection Agent (§7 of SYSTEM_ARTIFACT_v9.0)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# -------------------------------------------------------------------- #
# §5 State Machine
# -------------------------------------------------------------------- #


class AgentState(str, Enum):
    BOOT = "BOOT"
    DISCOVER_SOURCES = "DISCOVER_SOURCES"
    CHECK_CONNECTIVITY = "CHECK_CONNECTIVITY"
    CHECK_LIVENESS = "CHECK_LIVENESS"
    AUDIT_SCHEMA = "AUDIT_SCHEMA"
    BACKFILL = "BACKFILL"
    CANONICALIZE = "CANONICALIZE"
    ENRICH = "ENRICH"
    BUILD_FEATURES = "BUILD_FEATURES"
    VALIDATE = "VALIDATE"
    REVIEW = "REVIEW"
    REPORT = "REPORT"
    DEGRADED = "DEGRADED"
    DORMANT = "DORMANT"
    ABORT = "ABORT"


class SubstrateStatus(str, Enum):
    LIVE = "LIVE"
    DEGRADED = "DEGRADED"
    DEAD = "DEAD"


class ActionKind(str, Enum):
    DISCOVER_SOURCES = "DISCOVER_SOURCES"
    CHECK_CONNECTIVITY = "CHECK_CONNECTIVITY"
    BACKFILL = "BACKFILL"
    CANONICALIZE = "CANONICALIZE"
    ENRICH = "ENRICH"
    BUILD_FEATURES = "BUILD_FEATURES"
    VALIDATE = "VALIDATE"
    REPORT = "REPORT"
    QUARANTINE = "QUARANTINE"
    DORMANT = "DORMANT"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class SubstrateLabel(str, Enum):
    LIVE = "LIVE"
    LATE_GEOMETRY_ONLY = "LATE_GEOMETRY_ONLY"
    DEGRADED = "DEGRADED"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    INSUFFICIENT_SUBSTRATE = "INSUFFICIENT_SUBSTRATE"


# -------------------------------------------------------------------- #
# §7 Data structures
# -------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: str
    provider: str
    type: str  # "rest" | "websocket" | "file" | "internal_api"
    assets: tuple[str, ...]
    auth_ok: bool
    latency_ms: float
    live: bool
    reachable: bool
    supports_bid_ask: bool
    supports_depth: bool
    supports_trades: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["assets"] = list(self.assets)
        return d


@dataclass(frozen=True, slots=True)
class AssetSchemaReport:
    asset: str
    fields: tuple[str, ...]
    has_bid: bool
    has_ask: bool
    has_trades: bool
    has_bid_depth: bool
    has_ask_depth: bool
    has_spread: bool
    has_ofi: bool
    can_derive_spread: bool
    can_derive_ofi: bool
    precursor_capable: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fields"] = list(self.fields)
        return d


@dataclass(frozen=True, slots=True)
class SubstrateHealth:
    ts: datetime
    status: SubstrateStatus
    feed_live: bool
    heartbeat_ok: bool
    freshness_minutes: float
    asset_coverage: int
    gap_count: int
    nan_rate: float
    duplicate_rate: float
    schema_complete: bool
    precursor_capable_assets: int
    quality_score: float
    substrate_label: SubstrateLabel

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        d["status"] = self.status.value
        d["substrate_label"] = self.substrate_label.value
        return d


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    kind: str  # "RICCI" | "BETTI1" | "OFI" | "QUEUE_PRESSURE" | "STRESS"
    panel_id: str
    target_asset: str
    horizon_bars: int
    window: int
    threshold: float
    permutations: int
    seed: int


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    IC: float
    p_value: float
    corr_momentum: float | None
    corr_vol: float | None
    corr_vix: float | None
    corr_hyg: float | None
    lead_capture: float | None
    substrate_label: SubstrateLabel
    status: ValidationStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["substrate_label"] = self.substrate_label.value
        d["status"] = self.status.value
        return d


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """Full §13 output schema — every field mandatory, JSON-serialisable."""

    state: AgentState
    substrate_status: SubstrateStatus
    action: ActionKind
    priority: Priority
    target: str
    why: tuple[str, ...]
    blocking_conditions: tuple[str, ...]
    next_required_artifact: str
    admissible: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "substrate_status": self.substrate_status.value,
            "action": self.action.value,
            "priority": self.priority.value,
            "target": self.target,
            "why": list(self.why),
            "blocking_conditions": list(self.blocking_conditions),
            "next_required_artifact": self.next_required_artifact,
            "admissible": self.admissible,
            "diagnostics": self.diagnostics,
        }


__all__ = [
    "AgentState",
    "SubstrateStatus",
    "ActionKind",
    "Priority",
    "SubstrateLabel",
    "ValidationStatus",
    "SourceDescriptor",
    "AssetSchemaReport",
    "SubstrateHealth",
    "ExperimentSpec",
    "ValidationVerdict",
    "ActionIntent",
]
