# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared fixtures for D-002G P1 adversarial test suite.

Provides
--------
* ``locked_governance_paths`` — the seven files the implementation PR
  must NOT mutate.
* ``ricci_substrate`` — convenience wrapper around the only
  seed-sensitive stock substrate (``ricci_flow``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.systemic_risk.d002c_substrates import SUBSTRATE_BY_ID

REPO_ROOT = Path(__file__).resolve().parents[2]

LOCKED_GOVERNANCE_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "governance" / "D002G_PREREGISTRATION.yaml",
    REPO_ROOT / "docs" / "governance" / "D002G_NONDEGENERATE_NULL_DESIGN.md",
    REPO_ROOT / "docs" / "governance" / "D002G_ACCEPTANCE_RULES.md",
    REPO_ROOT / ".claude" / "commit_acceptors" / "x10r-d002g-nondegenerate-null-redesign.yaml",
    REPO_ROOT / "docs" / "governance" / "D002C_PREREGISTRATION.yaml",
    REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml",
    REPO_ROOT / "docs" / "governance" / "D002C_CANONICAL_RUN_REPORT.md",
    REPO_ROOT / "docs" / "governance" / "D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md",
)


@pytest.fixture(scope="session")
def locked_governance_paths() -> tuple[Path, ...]:
    """Tuple of locked governance file paths (resolved against repo root)."""
    return LOCKED_GOVERNANCE_PATHS


@pytest.fixture()
def ricci_substrate() -> object:
    """The only stock substrate that is seed-sensitive at lambda=0."""
    return SUBSTRATE_BY_ID["ricci_flow"]
