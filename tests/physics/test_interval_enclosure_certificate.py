# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Interval-arithmetic enclosure certificate — verified computing for the algebraic laws.

A tolerance check ("|repo - expected| < eps") can pass by luck. Verified computing
is stronger: it brackets the TRUE mathematical value in a machine-checked interval
[lo, hi] obtained with OUTWARD-rounded (directed) arithmetic, so the true value is
GUARANTEED to lie inside, and then proves the repo's float result also lies inside
a tight enclosure. The enclosure width (a few ULP) is itself the certificate of
correctness — no hidden tolerance.

A minimal directed-rounding ``Interval`` is implemented with ``math.nextafter``
(stdlib, no deps): every operation rounds its bounds outward so the result
provably contains the exact value of the operation on any points in the operands.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import scipy.constants as scipy_constants

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.physics.landauer import K_BOLTZMANN, bit_erasure_cost

_NEG_INF = float("-inf")
_POS_INF = float("inf")


@dataclass(frozen=True)
class Interval:
    """A closed real interval [lo, hi] with outward-rounded arithmetic (guaranteed enclosure)."""

    lo: float
    hi: float

    def __post_init__(self) -> None:
        if not (self.lo <= self.hi):
            raise ValueError(f"degenerate interval [{self.lo}, {self.hi}]")

    @staticmethod
    def exact(x: float) -> "Interval":
        return Interval(x, x)

    def __mul__(self, other: "Interval") -> "Interval":
        products = (self.lo * other.lo, self.lo * other.hi, self.hi * other.lo, self.hi * other.hi)
        return Interval(math.nextafter(min(products), _NEG_INF), math.nextafter(max(products), _POS_INF))

    def __truediv__(self, other: "Interval") -> "Interval":
        if other.lo <= 0.0 <= other.hi:
            raise ValueError("interval division straddling zero is not enclosable")
        quotients = (self.lo / other.lo, self.lo / other.hi, self.hi / other.lo, self.hi / other.hi)
        return Interval(math.nextafter(min(quotients), _NEG_INF), math.nextafter(max(quotients), _POS_INF))

    def contains(self, x: float) -> bool:
        return self.lo <= x <= self.hi

    @property
    def width(self) -> float:
        return self.hi - self.lo


def test_kelly_value_is_certified_by_interval_enclosure() -> None:
    """Verified computing: the true mu/sigma^2 is bracketed and the repo f* lies inside.

    The enclosure is built with outward rounding, so it provably contains the
    exact mu/sigma^2; the repo Kelly result must lie inside it, and the enclosure
    must be tight (a few ULP). That certifies the repo computes the true value to
    machine precision — not merely within an arbitrary tolerance.
    """
    for mu, sigma_sq in ((0.002, 2.5e-3), (0.001, 9e-4), (0.005, 1e-2)):
        enclosure = Interval.exact(mu) / Interval.exact(sigma_sq)
        repo_f = kelly_from_edge_variance(mu, sigma_sq, fractional_kelly=1.0, max_fraction=1e9)
        assert enclosure.contains(repo_f), (
            f"INTERVAL-ENCLOSURE VIOLATED: repo Kelly f*={repo_f!r} is OUTSIDE the certified "
            f"enclosure [{enclosure.lo!r}, {enclosure.hi!r}] of mu/sigma^2 (mu={mu}, sigma^2={sigma_sq}). "
            f"The float result is not provably the true value."
        )
        rel_width = enclosure.width / abs(repo_f)
        assert rel_width < 1e-12, (
            f"INTERVAL-ENCLOSURE too loose: relative width {rel_width:.2e} >= 1e-12 for Kelly "
            f"(mu={mu}, sigma^2={sigma_sq}); the certificate must be tight (few ULP)."
        )


def test_landauer_floor_is_certified_by_interval_enclosure() -> None:
    """Verified computing: the true k_B*T*ln2 is bracketed and the repo cost lies inside."""
    ln2 = Interval(math.nextafter(math.log(2.0), _NEG_INF), math.nextafter(math.log(2.0), _POS_INF))
    for temperature in (4.2, 300.0, 1000.0):
        enclosure = Interval.exact(scipy_constants.Boltzmann) * Interval.exact(temperature) * ln2
        repo_cost = bit_erasure_cost(1.0, temperature)
        assert enclosure.contains(repo_cost), (
            f"INTERVAL-ENCLOSURE VIOLATED: repo Landauer cost={repo_cost!r} is OUTSIDE the certified "
            f"enclosure [{enclosure.lo!r}, {enclosure.hi!r}] of k_B*T*ln2 at T={temperature}. "
            f"k_B(repo)={K_BOLTZMANN!r}, k_B(scipy)={scipy_constants.Boltzmann!r}."
        )
        rel_width = enclosure.width / abs(repo_cost)
        assert rel_width < 1e-12, (
            f"INTERVAL-ENCLOSURE too loose: relative width {rel_width:.2e} >= 1e-12 for Landauer "
            f"at T={temperature}."
        )


def test_enclosure_excludes_a_wrong_value() -> None:
    """Negative control: a value perturbed beyond the enclosure is provably NOT contained.

    Proves the certificate is discriminating: shifting the repo result by far more
    than the enclosure width must fall outside, so a wrong float could not be
    certified as the true value.
    """
    mu, sigma_sq = 0.002, 2.5e-3
    enclosure = Interval.exact(mu) / Interval.exact(sigma_sq)
    repo_f = kelly_from_edge_variance(mu, sigma_sq, fractional_kelly=1.0, max_fraction=1e9)
    wrong = repo_f + 1e-9  # far larger than the ~ULP enclosure width
    assert not enclosure.contains(wrong), (
        f"INTERVAL-ENCLOSURE CONTROL BROKEN: a wrong value {wrong!r} was inside the enclosure "
        f"[{enclosure.lo!r}, {enclosure.hi!r}] (width={enclosure.width!r}); the certificate cannot "
        f"discriminate a wrong float from the true value."
    )
