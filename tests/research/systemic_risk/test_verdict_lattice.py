# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verdict-lattice algebra tests.

Property-tests verify that ``(TierLattice, join, NONE)`` is a
commutative idempotent monoid (= a join-semilattice) and that
``(TierLattice, meet, KILL)`` is its dual. These are the four lattice
axioms whose code-level enforcement was previously implicit in a
hand-written precedence dict + scan loop.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from research.systemic_risk.verdict_lattice import (
    TierLattice,
    aggregate_actions,
    is_more_destructive_than,
    join,
    meet,
)

# ----- Strategy -----
_lattice = st.sampled_from(list(TierLattice))


class TestLatticeAxioms:
    @given(a=_lattice)
    def test_idempotence_join(self, a: TierLattice) -> None:
        assert join(a, a) == a

    @given(a=_lattice)
    def test_idempotence_meet(self, a: TierLattice) -> None:
        assert meet(a, a) == a

    @given(a=_lattice, b=_lattice)
    def test_commutativity_join(self, a: TierLattice, b: TierLattice) -> None:
        assert join(a, b) == join(b, a)

    @given(a=_lattice, b=_lattice)
    def test_commutativity_meet(self, a: TierLattice, b: TierLattice) -> None:
        assert meet(a, b) == meet(b, a)

    @given(a=_lattice, b=_lattice, c=_lattice)
    def test_associativity_join(self, a: TierLattice, b: TierLattice, c: TierLattice) -> None:
        assert join(join(a, b), c) == join(a, join(b, c))

    @given(a=_lattice, b=_lattice, c=_lattice)
    def test_associativity_meet(self, a: TierLattice, b: TierLattice, c: TierLattice) -> None:
        assert meet(meet(a, b), c) == meet(a, meet(b, c))

    @given(a=_lattice)
    def test_identity_join_is_none(self, a: TierLattice) -> None:
        assert join(a, TierLattice.NONE) == a

    @given(a=_lattice)
    def test_identity_meet_is_kill(self, a: TierLattice) -> None:
        assert meet(a, TierLattice.KILL) == a

    @given(a=_lattice, b=_lattice, c=_lattice)
    def test_distributivity_join_over_meet(
        self, a: TierLattice, b: TierLattice, c: TierLattice
    ) -> None:
        # Birkhoff 1948: every total order is a distributive lattice.
        assert join(a, meet(b, c)) == meet(join(a, b), join(a, c))

    @given(a=_lattice, b=_lattice, c=_lattice)
    def test_distributivity_meet_over_join(
        self, a: TierLattice, b: TierLattice, c: TierLattice
    ) -> None:
        assert meet(a, join(b, c)) == join(meet(a, b), meet(a, c))

    @given(a=_lattice, b=_lattice)
    def test_absorption(self, a: TierLattice, b: TierLattice) -> None:
        # join(a, meet(a, b)) == a; meet(a, join(a, b)) == a.
        assert join(a, meet(a, b)) == a
        assert meet(a, join(a, b)) == a


class TestAggregate:
    def test_empty_returns_none_identity(self) -> None:
        assert aggregate_actions([]) == TierLattice.NONE

    def test_single_returns_self(self) -> None:
        assert aggregate_actions([TierLattice.DEMOTE]) == TierLattice.DEMOTE

    def test_kill_dominates(self) -> None:
        actions = [
            TierLattice.DEMOTE,
            TierLattice.STOP,
            TierLattice.KILL,
            TierLattice.QUARANTINE,
        ]
        assert aggregate_actions(actions) == TierLattice.KILL

    def test_invalidate_dominates_quarantine(self) -> None:
        assert (
            aggregate_actions([TierLattice.INVALIDATE, TierLattice.QUARANTINE])
            == TierLattice.INVALIDATE
        )

    @given(actions=st.lists(_lattice, min_size=0, max_size=12))
    def test_aggregate_equals_max(self, actions: list[TierLattice]) -> None:
        # The lattice join is exactly max for a totally ordered set.
        if not actions:
            assert aggregate_actions(actions) == TierLattice.NONE
        else:
            assert aggregate_actions(actions) == max(actions)


class TestStringRoundTrip:
    @pytest.mark.parametrize(
        "name",
        ["NONE", "STOP", "DEMOTE", "QUARANTINE", "INVALIDATE", "KILL"],
    )
    def test_from_action_name_roundtrip(self, name: str) -> None:
        assert TierLattice.from_action_name(name).name == name

    def test_from_action_name_unknown_rejects(self) -> None:
        with pytest.raises(ValueError, match="unknown tier action"):
            TierLattice.from_action_name("BOGUS")


class TestStrictOrder:
    def test_kill_is_strictly_more_destructive_than_demote(self) -> None:
        assert is_more_destructive_than(TierLattice.KILL, TierLattice.DEMOTE)

    def test_self_is_not_more_destructive(self) -> None:
        for a in TierLattice:
            assert not is_more_destructive_than(a, a)
