# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cognitive-bridge invariants (CB-INV-1..7).

Each invariant is a fail-closed contract enforced by ``CognitiveSidecar``.
Violations raise ``BridgeInvariantError`` and the bridge collapses the
exchange into ``AdvisoryStatus.UNAVAILABLE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class InvariantId(str, Enum):
    CB_INV_1_SCHEMA = "CB-INV-1"
    CB_INV_2_TIMEOUT = "CB-INV-2"
    CB_INV_3_ADVISORY_ONLY = "CB-INV-3"
    CB_INV_4_CORRELATION = "CB-INV-4"
    CB_INV_5_KILL_SWITCH = "CB-INV-5"
    CB_INV_6_STRESSED = "CB-INV-6"
    CB_INV_7_VERSION = "CB-INV-7"


@dataclass(frozen=True)
class Invariant:
    """A single fail-closed contract entry.

    ``severity`` follows the GeoSync convention: ``P0`` halts the host,
    ``P1`` collapses the exchange but lets the host continue with the
    deterministic baseline.
    """

    invariant_id: InvariantId
    description: str
    severity: str


CB_INVARIANTS: Mapping[InvariantId, Invariant] = {
    InvariantId.CB_INV_1_SCHEMA: Invariant(
        invariant_id=InvariantId.CB_INV_1_SCHEMA,
        description=(
            "AdvisoryRequest and AdvisoryResponse must validate against the "
            "frozen Pydantic schema; malformed payloads produce no advice."
        ),
        severity="P1",
    ),
    InvariantId.CB_INV_2_TIMEOUT: Invariant(
        invariant_id=InvariantId.CB_INV_2_TIMEOUT,
        description=(
            "Sidecar exchange must complete within SidecarConfig.timeout_s; "
            "a timeout collapses to AdvisoryStatus.UNAVAILABLE."
        ),
        severity="P1",
    ),
    InvariantId.CB_INV_3_ADVISORY_ONLY: Invariant(
        invariant_id=InvariantId.CB_INV_3_ADVISORY_ONLY,
        description=(
            "AdvisoryResponse is a frozen Pydantic model with extra='forbid' "
            "and exposes no mutator API. The bridge therefore CANNOT carry "
            "an executable side-effect back to the host: the only payload "
            "available is descriptive text plus a tier label that defaults "
            "to SPECULATIVE. Falsified by: (a) the model becoming mutable, "
            "(b) any new field that admits a callable / executable, or "
            "(c) the tier defaulting to a non-speculative value. The host "
            "contract is documentary; structural enforcement lives in the "
            "schema."
        ),
        severity="P0",
    ),
    InvariantId.CB_INV_4_CORRELATION: Invariant(
        invariant_id=InvariantId.CB_INV_4_CORRELATION,
        description=(
            "AdvisoryResponse.correlation_id must equal "
            "AdvisoryRequest.correlation_id(); mismatched ids indicate "
            "out-of-order delivery or replay and are rejected."
        ),
        severity="P0",
    ),
    InvariantId.CB_INV_5_KILL_SWITCH: Invariant(
        invariant_id=InvariantId.CB_INV_5_KILL_SWITCH,
        description=(
            "When kill_switch_active is set the bridge short-circuits to "
            "AdvisoryStatus.DISABLED before any transport call."
        ),
        severity="P0",
    ),
    InvariantId.CB_INV_6_STRESSED: Invariant(
        invariant_id=InvariantId.CB_INV_6_STRESSED,
        description=(
            "When stressed_state is set the bridge short-circuits to "
            "AdvisoryStatus.DISABLED; safety preempts exploration."
        ),
        severity="P0",
    ),
    InvariantId.CB_INV_7_VERSION: Invariant(
        invariant_id=InvariantId.CB_INV_7_VERSION,
        description=(
            "protocol_version on both request and response must match "
            "PROTOCOL_VERSION; cross-version exchanges are rejected."
        ),
        severity="P1",
    ),
}


__all__ = ["CB_INVARIANTS", "Invariant", "InvariantId"]
