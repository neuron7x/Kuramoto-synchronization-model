# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for landauer_nonzero_erasure_cost and irreversible_cost_dominance."""

from __future__ import annotations

import pytest

from core.physics.landauer import (
    assert_irreversible_dominance,
    bit_erasure_cost,
    irreversible_cost,
    reversible_baseline,
)
from core.physics.reversible_gate import irreversibility_score


def test_bit_erasure_cost_is_positive() -> None:
    """Positive witness: erasing >0 bits at >0 K costs strictly more than zero."""
    for bits in (1.0, 8.0, 1024.0):
        for temperature in (4.2, 300.0, 1000.0):
            cost = bit_erasure_cost(bits, temperature)
            assert cost > 0.0, (
                f"LANDAUER VIOLATED: bit_erasure_cost({bits}, {temperature}) = {cost} "
                f"is not > 0. Floor is k_B*T*ln2*bits; there is no free erasure."
            )


def test_zero_cost_erasure_claim_is_rejected() -> None:
    """Negative control: an undefined thermal context (T<=0) fails closed."""
    with pytest.raises(ValueError, match="temperature must be finite and > 0"):
        bit_erasure_cost(8.0, 0.0)
    with pytest.raises(ValueError, match="bits must be finite and >= 0"):
        bit_erasure_cost(-1.0, 300.0)


def test_irreversible_dominates_reversible() -> None:
    """Positive witness: irreversible cost >= reversible baseline over an action sweep."""
    actions = [
        {"base_cost": 1.0, "action_kind": "read", "payload_size": 0, "side_effects": 0},
        {"base_cost": 2.0, "action_kind": "write", "payload_size": 4096, "side_effects": 3},
        {"base_cost": 0.5, "action_kind": "delete", "payload_size": 64, "side_effects": 1},
    ]
    for action in actions:
        c_irr = irreversible_cost(action)
        c_rev = reversible_baseline(action)
        score = irreversibility_score(
            str(action["action_kind"]),
            int(action["payload_size"]),
            int(action["side_effects"]),
        )
        # Must not raise — the dominance law holds for honest costs.
        assert_irreversible_dominance(c_irr, c_rev, score)
        assert c_irr >= c_rev


def test_fake_free_rollback_is_rejected() -> None:
    """Negative control: a reversible baseline above the irreversible cost is rejected."""
    with pytest.raises(ValueError, match="IRREVERSIBLE-COST VIOLATED"):
        assert_irreversible_dominance(irr_cost=1.0, rev_cost=2.0, irreversibility_score_value=0.5)
    # Equal costs while score > 0 is also a violation (no free irreversibility).
    with pytest.raises(ValueError, match="IRREVERSIBLE-COST VIOLATED"):
        assert_irreversible_dominance(irr_cost=1.0, rev_cost=1.0, irreversibility_score_value=0.4)
