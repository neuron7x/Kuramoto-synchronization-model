# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed model for ``docs/CLAIMS.yaml`` (schema v3, IERD-PAI-FPS-UX-001).

The schema declares every claim (engineering invariant the project
makes about itself) along with its tier, evidence paths, priority,
and — for v3 ANCHORED claims — a falsifier block whose ``test_id``
must be a real pytest node.

The Pydantic v2 model below is the single source of truth. Validators
in ``scripts/ci/`` and ``tools/commit_acceptor/`` consume the typed
model rather than re-parsing dicts. The JSON Schema export
(``ClaimLedger.model_json_schema()``) is published for external
auditors and IDE autocompletion.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Constants — mirror scripts/ci/check_claims.py (single source of truth here)
# ---------------------------------------------------------------------------

SCHEMA_VERSION_LATEST = 3
SCHEMA_VERSIONS_SUPPORTED = frozenset({1, 2, 3})

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INV_PATTERN = re.compile(r"^INV-[A-Z0-9][A-Z0-9]*(?:-[A-Za-z0-9]+)*$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PYTEST_NODE_PATTERN = re.compile(r"^[\w./\-]+\.py(::[A-Za-z_][\w]*)+$")


class Tier(str, Enum):
    """IERD claim tier ladder.

    Strict ordering: an ANCHORED claim has a falsifier and CI evidence;
    EXTRAPOLATED has partial evidence with a documented missing-evidence
    list; SPECULATIVE / UNKNOWN are aspirational. The ``check_claims``
    gate enforces ``tier ∈ {ANCHORED, EXTRAPOLATED} ⇒ all evidence
    paths exist``.
    """

    ANCHORED = "ANCHORED"
    EXTRAPOLATED = "EXTRAPOLATED"
    SPECULATIVE = "SPECULATIVE"
    UNKNOWN = "UNKNOWN"


class Priority(str, Enum):
    """Claim priority — gate scope.

    P0 / P1 are gated (CI fails on missing evidence). P2 is warn-only.
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


ClaimId = Annotated[str, StringConstraints(pattern=ID_PATTERN.pattern, min_length=1)]
IsoDate = Annotated[str, StringConstraints(pattern=DATE_PATTERN.pattern)]


class Falsifier(BaseModel):
    """v3 falsifier block — pytest node + invariants + failure signature.

    Required on every v3 ANCHORED claim per ADR 0021. The ``test_id``
    must be a resolvable pytest node id; ``invariants_cited`` must be a
    non-empty list of ``INV-<NAME>`` identifiers; ``failure_signature``
    is a free-form description of the assertion shape that must fire on
    invariant violation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    test_id: Annotated[str, StringConstraints(pattern=PYTEST_NODE_PATTERN.pattern)]
    invariants_cited: tuple[str, ...] = Field(min_length=1)
    failure_signature: str = Field(min_length=1)

    @field_validator("invariants_cited")
    @classmethod
    def _check_invariants(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for inv in value:
            if not INV_PATTERN.match(inv):
                raise ValueError(
                    f"falsifier.invariants_cited entry {inv!r} must match {INV_PATTERN.pattern}"
                )
        return value


class ClaimEntry(BaseModel):
    """Single registry entry under ``claims:`` in the ledger.

    The strict-mode ``extra='forbid'`` policy guards against silent
    schema drift: any unknown field at the entry level is a hard error
    (the historical gate would have ignored unknowns and produced
    false-green runs).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: ClaimId
    priority: Priority
    tier: Tier
    description: str = Field(min_length=1)
    evidence_paths: tuple[str, ...] = Field(default_factory=tuple)
    added_utc: IsoDate
    last_updated_utc: IsoDate | None = None
    falsifier: Falsifier | None = None

    @field_validator("added_utc", "last_updated_utc")
    @classmethod
    def _check_date_round_trip(cls, value: str | None) -> str | None:
        if value is None:
            return value
        # round-trip via datetime.date so 2026-13-01 etc. fail
        date.fromisoformat(value)
        return value

    @property
    def is_gated(self) -> bool:
        """Whether the gate enforces evidence-existence on this claim."""
        return self.priority in (Priority.P0, Priority.P1)

    @property
    def requires_falsifier(self) -> bool:
        """True iff schema v3 ANCHORED — falsifier block is mandatory."""
        return self.tier is Tier.ANCHORED


class ClaimLedger(BaseModel):
    """Top-level shape of ``docs/CLAIMS.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1, le=SCHEMA_VERSION_LATEST)
    claims: tuple[ClaimEntry, ...]

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: int) -> int:
        if value not in SCHEMA_VERSIONS_SUPPORTED:
            raise ValueError(
                f"schema_version={value} is outside the supported "
                f"set {sorted(SCHEMA_VERSIONS_SUPPORTED)}"
            )
        return value

    @field_validator("claims")
    @classmethod
    def _check_unique_ids(cls, value: tuple[ClaimEntry, ...]) -> tuple[ClaimEntry, ...]:
        seen: set[str] = set()
        for claim in value:
            if claim.id in seen:
                raise ValueError(f"duplicate claim id: {claim.id}")
            seen.add(claim.id)
        return value

    def by_id(self, claim_id: str) -> ClaimEntry | None:
        for claim in self.claims:
            if claim.id == claim_id:
                return claim
        return None

    def gated(self) -> tuple[ClaimEntry, ...]:
        """Return claims subject to evidence-existence enforcement."""
        return tuple(c for c in self.claims if c.is_gated)

    def by_tier(self, tier: Tier) -> tuple[ClaimEntry, ...]:
        return tuple(c for c in self.claims if c.tier is tier)

    def tier_distribution(self) -> dict[Tier, int]:
        counts = dict.fromkeys(Tier, 0)
        for claim in self.claims:
            counts[claim.tier] += 1
        return counts


def load_claim_ledger(path: str | Path) -> ClaimLedger:
    """Parse + validate ``docs/CLAIMS.yaml``.

    Raises ``pydantic.ValidationError`` on any schema violation, with a
    structured ``loc`` path pointing to the bad field. This replaces
    the hand-coded error reporting in ``scripts/ci/check_claims.py`` and
    surfaces structural violations alongside content violations in a
    single pass.
    """
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level must be a mapping, got {type(raw).__name__}")
    return ClaimLedger.model_validate(raw)


__all__ = [
    "ClaimEntry",
    "ClaimLedger",
    "Falsifier",
    "Priority",
    "SCHEMA_VERSION_LATEST",
    "SCHEMA_VERSIONS_SUPPORTED",
    "Tier",
    "load_claim_ledger",
]
