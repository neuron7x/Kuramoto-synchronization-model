# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics v2 — Universal Synchronization Manifold typed contract layer.

This package is the **first implementation slice** of the Physics v2
architecture handoff (``docs/architecture/physics_v2_universal_synchronization_manifold.md``).

Scope discipline (enforced by the architecture contract):

* It contains *only* typed, deterministic data contracts and their fail-closed
  validators. There is **no solver, no numerical Ricci flow, and no L2 ingest**
  in this slice — those land in later PRs once these contracts are covered by
  tests (architecture doc §4: "Do not skip P0. Do not merge P4 before P2/P3").
* No predictive-alpha claim, no production-trading claim, no real-L2 claim. The
  only objects here are schemas and the fail-closed gate that makes a missing
  licensed-L2 dataset an *explicit* ``DATA_UNAVAILABLE`` verdict rather than a
  silent synthetic substitution.

The contracts reuse — rather than duplicate — the repo's existing evidence
machinery. ``EvidenceCapsuleShape`` documents how a Physics v2 run maps onto the
already-shipped ``instrument_validation.capsule.Capsule`` and the 14-rung
``analytics.signals.claim_maturity`` ladder; see ``artifacts/physics_v2/inventory.md``.
"""

from __future__ import annotations

from physics_contracts.manifold.contracts import (
    CausalCutoffStatus,
    ComparisonReport,
    CurvatureSyncFrame,
    EvidenceCapsuleShape,
    LicensedDataStatus,
    LicensedDataUnavailable,
    MarketCausalGraphSnapshot,
    NullControl,
    canonical_digest,
    deterministic_run_id,
    require_licensed_l2,
    resolve_data_status,
)

__all__ = [
    "CausalCutoffStatus",
    "ComparisonReport",
    "CurvatureSyncFrame",
    "EvidenceCapsuleShape",
    "LicensedDataStatus",
    "LicensedDataUnavailable",
    "MarketCausalGraphSnapshot",
    "NullControl",
    "canonical_digest",
    "deterministic_run_id",
    "require_licensed_l2",
    "resolve_data_status",
]
