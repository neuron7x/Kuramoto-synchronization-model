# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Static contract checks for the AAR-PRO-V1 TLA+ model."""

from __future__ import annotations

from pathlib import Path

SPEC = Path("formal/AAR_PRO_V1.tla")
CFG = Path("formal/AAR_PRO_V1.cfg")


def test_tla_spec_declares_required_invariants() -> None:
    source = SPEC.read_text(encoding="utf-8")

    assert "---- MODULE AAR_PRO_V1 ----" in source
    assert "ChronologyInvariant ==" in source
    assert "FailClosedInvariant ==" in source
    assert "NoMemoryWithoutDecision ==" in source
    assert "modelSeq < actionSeq /\\ actionSeq < observedSeq" in source
    assert "witness \\in { INVALID_INPUT, ROLLBACK_REQUIRED }" in source


def test_tla_cfg_binds_all_invariants() -> None:
    cfg = CFG.read_text(encoding="utf-8")

    assert "SPECIFICATION Spec" in cfg
    assert "INVARIANT ChronologyInvariant" in cfg
    assert "INVARIANT FailClosedInvariant" in cfg
    assert "INVARIANT NoMemoryWithoutDecision" in cfg
