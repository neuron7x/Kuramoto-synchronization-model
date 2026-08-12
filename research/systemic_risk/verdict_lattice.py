# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verdict lattice — algebraic foundation of tier-action composition.

The set of canonical tier actions

    {NONE, STOP, DEMOTE, QUARANTINE, INVALIDATE, KILL}

forms a **totally ordered set** under "destructiveness". Every total
order is a *complete lattice* with the binary operations

    meet (⊓)  ≡  min  ≡  least disruptive
    join (⊔)  ≡  max  ≡  most disruptive

The aggregation rule of the death engine — "destroy beats preserve" —
is exactly the *join* over the multiset of fired triggers' actions.
This module ships that algebra explicitly so the precedence rule is

    expressed once, in algebra, and reused by composition

rather than re-implemented imperatively in every callsite. Lattice
axioms (idempotence, commutativity, associativity, identity) are
property-tested in :mod:`tests.research.systemic_risk
.test_verdict_lattice` via Hypothesis.

Mathematical content
====================

Let ``L = (TierLattice, ≤)`` with the order

    NONE < STOP < DEMOTE < QUARANTINE < INVALIDATE < KILL

Define ``a ⊔ b := max(a, b)`` and ``a ⊓ b := min(a, b)``.

* ``(L, ⊔)`` is a commutative idempotent monoid with identity
  :data:`TierLattice.NONE`.
* ``(L, ⊓)`` is a commutative idempotent monoid with identity
  :data:`TierLattice.KILL`.
* Distributivity holds because every total order is a distributive
  lattice (Birkhoff 1948, Theorem II.1.1).

Pure-function API. No I/O. No mutable state.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum
from functools import reduce

__all__ = [
    "TierLattice",
    "join",
    "meet",
    "aggregate_actions",
    "is_more_destructive_than",
]


class TierLattice(IntEnum):
    """Canonical tier actions, totally ordered by destructiveness.

    The integer value is the position in the lattice; ``NONE`` is the
    bottom element (identity of ``⊔``) and ``KILL`` is the top element
    (identity of ``⊓``).

    The corresponding string aliases match the
    :data:`research.systemic_risk.death_conditions.TierAction` Literal
    so the two namespaces interoperate by name.
    """

    NONE = 0
    STOP = 1
    DEMOTE = 2
    QUARANTINE = 3
    INVALIDATE = 4
    KILL = 5

    @classmethod
    def from_action_name(cls, action: str) -> "TierLattice":
        """Map a :data:`death_conditions.TierAction` string to a lattice element.

        Raises
        ------
        ValueError
            If ``action`` is not one of the six canonical names.
        """
        try:
            return cls[action]
        except KeyError as exc:
            raise ValueError(
                f"unknown tier action {action!r}; expected one of {[m.name for m in cls]}"
            ) from exc


def join(a: TierLattice, b: TierLattice) -> TierLattice:
    """Lattice join (⊔) — the *more destructive* of ``a`` and ``b``.

    Properties (verified by Hypothesis property tests):

    * Commutativity: ``join(a, b) == join(b, a)``.
    * Associativity: ``join(join(a, b), c) == join(a, join(b, c))``.
    * Idempotence:   ``join(a, a) == a``.
    * Identity:      ``join(a, NONE) == a``.

    These four axioms make ``(TierLattice, join, NONE)`` a commutative
    idempotent monoid — equivalent to a join-semilattice.
    """
    return a if a >= b else b


def meet(a: TierLattice, b: TierLattice) -> TierLattice:
    """Lattice meet (⊓) — the *less destructive* of ``a`` and ``b``.

    Dual of :func:`join`. Identity is :data:`TierLattice.KILL`.
    """
    return a if a <= b else b


def aggregate_actions(actions: Iterable[TierLattice]) -> TierLattice:
    """Aggregate a finite sequence of actions under the join.

    Equivalent to ``reduce(join, actions, TierLattice.NONE)``. Returns
    :data:`TierLattice.NONE` for the empty sequence (identity of ``⊔``).

    This is the algebraic statement of the death-engine's precedence
    rule:

        KILL > INVALIDATE > QUARANTINE > DEMOTE > STOP > NONE

    "destroying a claim wins over preserving it".
    """
    return reduce(join, actions, TierLattice.NONE)


def is_more_destructive_than(a: TierLattice, b: TierLattice) -> bool:
    """Strict order on the lattice: ``a > b``.

    Returns ``True`` iff ``a`` is strictly more destructive than ``b``.
    Equivalent to ``join(a, b) == a and a != b``.
    """
    return a > b
