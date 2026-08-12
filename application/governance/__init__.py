# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed governance schemas for IERD-PAI-FPS-UX-001.

Single source of truth for the two YAML schemas that drive the
GeoSync governance layer:

* ``docs/CLAIMS.yaml``                       → ClaimLedger / ClaimEntry / Falsifier
* ``.claude/commit_acceptors/*.yaml``        → CommitAcceptor

Replaces hand-rolled dict access in ``scripts/ci/check_claims.py`` and
``tools/commit_acceptor/validate_commit_acceptor.py``. Pydantic v2
performs validation at model construction time; the JSON Schema
export under :func:`json_schemas` is consumable by IDEs and external
auditors without re-parsing the YAML.
"""

from __future__ import annotations

from application.governance.claim_ledger import (
    ClaimEntry,
    ClaimLedger,
    Falsifier,
    Priority,
    Tier,
    load_claim_ledger,
)
from application.governance.commit_acceptor import (
    AcceptorFalsifier,
    CommitAcceptor,
    DiffScope,
    load_all_commit_acceptors,
    load_commit_acceptor,
)

__all__ = [
    "AcceptorFalsifier",
    "ClaimEntry",
    "ClaimLedger",
    "CommitAcceptor",
    "DiffScope",
    "Falsifier",
    "Priority",
    "Tier",
    "load_all_commit_acceptors",
    "load_claim_ledger",
    "load_commit_acceptor",
]
