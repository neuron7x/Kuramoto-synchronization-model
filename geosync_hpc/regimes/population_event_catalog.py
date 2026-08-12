# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Population event catalog — engineering analog of GWTC-4.0 admission discipline.

pattern_id:        P1_POPULATION_EVENT_CATALOG
source_id:         S1_GWTC4
claim_tier:        ENGINEERING_ANALOG
implementation:    PR-2 (this module)

Engineering analog
==================

GWTC-4.0 (LIGO/Virgo/KAGRA) records compact-binary candidates as a
population catalog under explicit admission rules: each candidate carries
provenance, a survival flag from event validation, and an evidence tier
(p_astro >= 0.5). Population analyses build on the catalog as a
provenance-bearing record, not on un-vetted candidate streams.

This module imports the *admission discipline*, not the physics. A
GeoSync market / regime event is recorded only when:

    1. its identifier is present and unique
    2. its timestamp is timezone-aware
    3. its asset universe is non-empty
    4. its features are finite numeric values
    5. its evidence tier is from the closed enum
    6. its source window is well-formed and ordered
    7. its provenance is recorded
    8. its falsifier_status is recorded

Admission emits a structured witness. The witness names the outcome and
the reason. There is no prediction field. The catalog does NOT return
trading signals or scores; promotion of catalog entries to actionable
signals is a downstream concern that lives outside this module.

Explicit non-claims
===================

This module does NOT claim:
  - that a market event is a gravitational wave
  - that catalog admission constitutes a trading signal
  - that admission predicts future returns
  - any physical equivalence between GeoSync and physics

The module imports the admission discipline only. Its outputs are
provenance-bearing evidence records.

Determinism contract
====================

  - admit(event) is pure: no I/O, no clock, no random, no global state.
  - events() returns the catalogued admitted events sorted by
    (timestamp, event_id), giving byte-identical iteration on identical
    inputs.
  - to_dict() / from_dict() are inverses for the catalog plus its
    admission witnesses; round-trip is byte-stable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "EvidenceTier",
    "SourceWindow",
    "EventInput",
    "AdmissionWitness",
    "PopulationEventCatalog",
]


class EvidenceTier(str, Enum):
    """Closed enum of admission evidence tiers.

    Tiers are ordinal and small by design. Each tier names the strength
    of the upstream provenance, not a probability or score.
    """

    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    DERIVED = "DERIVED"


@dataclass(frozen=True)
class SourceWindow:
    """The time window of the upstream observation that produced the event.

    `start` and `end` must be timezone-aware datetimes with `start < end`.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.start, datetime) or not isinstance(self.end, datetime):
            raise TypeError("SourceWindow.start and SourceWindow.end must be datetimes")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("SourceWindow.start and SourceWindow.end must be timezone-aware")
        if not self.start < self.end:
            raise ValueError(
                f"SourceWindow.start must be strictly before end: "
                f"{self.start.isoformat()} >= {self.end.isoformat()}"
            )

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, str]) -> SourceWindow:
        return cls(
            start=datetime.fromisoformat(payload["start"]),
            end=datetime.fromisoformat(payload["end"]),
        )


@dataclass(frozen=True)
class EventInput:
    """One candidate event to be considered for catalogue admission.

    Field-level validation is enforced in `__post_init__`; the rest of
    the admission contract (duplicate detection, deterministic ordering)
    is enforced by `PopulationEventCatalog.admit`.
    """

    event_id: str
    timestamp: datetime
    asset_universe: tuple[str, ...]
    regime_label: str
    event_features: Mapping[str, float]
    evidence_tier: EvidenceTier
    source_window: SourceWindow
    provenance: str
    falsifier_status: str

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if not isinstance(self.asset_universe, tuple) or not self.asset_universe:
            raise ValueError("asset_universe must be a non-empty tuple of strings")
        if any(not isinstance(a, str) or not a for a in self.asset_universe):
            raise ValueError("asset_universe entries must be non-empty strings")
        if not isinstance(self.regime_label, str) or not self.regime_label.strip():
            raise ValueError("regime_label must be a non-empty string")
        if not isinstance(self.event_features, Mapping):
            raise TypeError("event_features must be a mapping")
        for key, value in self.event_features.items():
            if not isinstance(key, str) or not key:
                raise ValueError("event_features keys must be non-empty strings")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"event_features[{key!r}] must be a finite numeric value")
            if not math.isfinite(float(value)):
                raise ValueError(f"event_features[{key!r}] must be finite (got {value!r})")
        if not isinstance(self.evidence_tier, EvidenceTier):
            raise TypeError(
                "evidence_tier must be a EvidenceTier enum member; "
                "string inputs must be normalised by the caller before construction"
            )
        if not isinstance(self.source_window, SourceWindow):
            raise TypeError("source_window must be a SourceWindow")
        if not (self.source_window.start <= self.timestamp <= self.source_window.end):
            raise ValueError(
                "timestamp must lie within source_window "
                f"[{self.source_window.start.isoformat()}, "
                f"{self.source_window.end.isoformat()}]"
            )
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("provenance must be a non-empty string")
        if not isinstance(self.falsifier_status, str) or not self.falsifier_status:
            raise ValueError("falsifier_status must be a non-empty string")

        # Freeze the features mapping so admission carries an immutable view.
        # We replace `event_features` on the frozen instance via object.__setattr__
        # since dataclass(frozen=True) blocks normal assignment.
        object.__setattr__(
            self,
            "event_features",
            MappingProxyType(dict(self.event_features)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_universe": list(self.asset_universe),
            "regime_label": self.regime_label,
            "event_features": dict(self.event_features),
            "evidence_tier": self.evidence_tier.value,
            "source_window": self.source_window.to_dict(),
            "provenance": self.provenance,
            "falsifier_status": self.falsifier_status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EventInput:
        return cls(
            event_id=str(payload["event_id"]),
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            asset_universe=tuple(str(a) for a in payload["asset_universe"]),
            regime_label=str(payload["regime_label"]),
            event_features={str(k): float(v) for k, v in dict(payload["event_features"]).items()},
            evidence_tier=EvidenceTier(str(payload["evidence_tier"])),
            source_window=SourceWindow.from_dict(payload["source_window"]),
            provenance=str(payload["provenance"]),
            falsifier_status=str(payload["falsifier_status"]),
        )


@dataclass(frozen=True)
class AdmissionWitness:
    """Outcome of an admission attempt.

    `accepted` is the binary verdict; `reason` is a structured tag that
    is stable across runs (never a free-form message that could leak
    state). The witness intentionally does NOT carry any prediction,
    forecast, score, signal, direction, or recommendation field. The
    catalog records evidence; downstream layers read it to decide what
    to do, and that decision lives elsewhere.
    """

    accepted: bool
    event_id: str
    reason: str
    evidence_tier: EvidenceTier | None
    falsifier_status: str | None
    catalog_size_after: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "event_id": self.event_id,
            "reason": self.reason,
            "evidence_tier": (self.evidence_tier.value if self.evidence_tier is not None else None),
            "falsifier_status": self.falsifier_status,
            "catalog_size_after": self.catalog_size_after,
        }


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass
class PopulationEventCatalog:
    """A deterministic record of admitted events.

    The catalog rejects duplicates, normalises iteration order to
    (timestamp, event_id), and exposes serialization for audit. It does
    NOT promote events into trading signals; that is the explicit
    non-claim of the engineering analog.
    """

    _events: dict[str, EventInput] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Admission
    # ------------------------------------------------------------------
    def admit(self, event: EventInput) -> AdmissionWitness:
        """Admit an event into the catalogue.

        Returns an `AdmissionWitness` either way. The function is pure:
        if `accepted` is False the catalog state is unchanged.
        """
        if event.event_id in self._events:
            return AdmissionWitness(
                accepted=False,
                event_id=event.event_id,
                reason="DUPLICATE_EVENT_ID",
                evidence_tier=None,
                falsifier_status=None,
                catalog_size_after=len(self._events),
            )

        # All field-level validation happens at EventInput construction
        # time; if a caller hands us an EventInput, it is already well-
        # formed. The catalog's job is the population-level rule
        # (uniqueness + ordering + provenance preservation).
        self._events[event.event_id] = event
        return AdmissionWitness(
            accepted=True,
            event_id=event.event_id,
            reason="OK",
            evidence_tier=event.evidence_tier,
            falsifier_status=event.falsifier_status,
            catalog_size_after=len(self._events),
        )

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._events)

    def __contains__(self, event_id: object) -> bool:
        return isinstance(event_id, str) and event_id in self._events

    def events(self) -> tuple[EventInput, ...]:
        """Return events in deterministic order: (timestamp, event_id)."""
        return tuple(
            sorted(
                self._events.values(),
                key=lambda e: (e.timestamp, e.event_id),
            )
        )

    def get(self, event_id: str) -> EventInput | None:
        return self._events.get(event_id)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "events": [e.to_dict() for e in self.events()],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PopulationEventCatalog:
        if payload.get("schema_version") != 1:
            raise ValueError(f"unsupported schema_version: {payload.get('schema_version')!r}")
        catalog = cls()
        for raw in payload.get("events") or []:
            event = EventInput.from_dict(raw)
            verdict = catalog.admit(event)
            if not verdict.accepted:
                raise ValueError(
                    f"replay produced a rejected admission for {event.event_id!r}: {verdict.reason}"
                )
        return catalog

    # ------------------------------------------------------------------
    # Convenience for tests / functional code
    # ------------------------------------------------------------------
    def replace(self, **overrides: Any) -> PopulationEventCatalog:
        """Return a copy of this catalog with the given fields replaced.

        Provided for symmetry with the dataclass.replace pattern used
        elsewhere in the project; the catalog itself has no overridable
        fields beyond `_events`, but this method exists so callers can
        rely on a uniform shape.
        """
        return replace(self, **overrides)
