# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Event-addressed (indexed) random number generator — control-flow-free.

A stateful ``np.random.Generator`` has one critical weakness for
deterministic replay: the value of the *n*-th ``.random()`` call depends
on how many draws preceded it. Two runs that produce the same logical
fill sequence in a different internal order will diverge, silently. This
is the single worst obstacle to bit-identical replay of execution-layer
stochasticity.

:class:`IndexedRNG` addresses each draw by a 4-tuple
``(seed, stream_id, event_id, event_index)`` and hashes it through
BLAKE2b into a 64-bit seed for a fresh NumPy PCG64 generator. The result
is:

* **Replayable.** The same tuple always returns the same value.
* **Control-flow independent.** Adding, removing or reordering unrelated
  draws does not perturb the value of any draw addressed by its tuple.
* **Stream-separated.** ``execution``, ``model``, ``bootstrap``,
  ``simulation``, and test streams are mathematically independent
  without a coordinating counter.
* **Cross-platform stable.** BLAKE2b (RFC 7693) and PCG64 are
  byte-identical across CPython builds, operating systems and
  architectures.

This is a primitive. Integration into :class:`BacktesterCAL.Execution`
(to replace ``self._rng.random() < queue_fill_p``) is a follow-up PR —
keeping the primitive isolated lets it fail-close on its own invariant
tests before touching the hot path.

References
----------
* BLAKE2b — Saarinen & Aumasson, RFC 7693 (2015).
* PCG64 — O'Neill, "PCG: A family of simple fast space-efficient
  statistically good algorithms for random number generation" (2014).
* Salmon et al., "Parallel random numbers: as easy as 1, 2, 3"
  (Random123), *SC 2011* — the canonical counter-based RNG architecture
  this module follows in spirit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

import numpy as np

_HASH_DIGEST_BYTES: Final[int] = 8
"""BLAKE2b output length feeding the PCG64 seed (64 bits)."""

_INT64_MASK: Final[int] = (1 << 63) - 1
"""Mask to an unsigned 63-bit integer so ``np.random.default_rng`` accepts it."""

CANONICAL_STREAMS: Final[frozenset[str]] = frozenset(
    {"execution", "model", "bootstrap", "simulation", "tests"}
)
"""Stream ids that a full GeoSync deterministic run is expected to use.

Not enforced at runtime — a test or diagnostic can open an ad-hoc
stream — but listed here so the canonical coverage is documentable.
"""


@dataclass(frozen=True)
class IndexedRNG:
    """Deterministic, event-addressed RNG.

    Attributes
    ----------
    seed
        Global integer seed for the entire deterministic run.
    stream_id
        Stream namespace, e.g. ``"execution"``. Two instances with
        different ``stream_id`` are mathematically independent.
    """

    seed: int
    stream_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError(f"seed must be int, got {type(self.seed).__name__}")
        if not isinstance(self.stream_id, str) or not self.stream_id:
            raise ValueError("stream_id must be a non-empty string")

    # --- addressable seed -------------------------------------------------

    def _tuple_seed(self, event_id: str, event_index: int) -> int:
        """Derive a PCG64-ready seed from ``(seed, stream, event, index)``.

        Uses BLAKE2b keyed by the 4-tuple. The pipe separator is safe
        because event ids are free-form strings chosen by the caller;
        if an event id contains ``|`` it will collide with a different
        encoding only if another ``(event_id, event_index)`` produces
        the same byte stream, which requires a full BLAKE2b collision.
        """
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(event_index, int) or isinstance(event_index, bool):
            raise TypeError(f"event_index must be int, got {type(event_index).__name__}")
        material = f"{self.seed}|{self.stream_id}|{event_id}|{event_index}".encode("utf-8")
        digest = hashlib.blake2b(material, digest_size=_HASH_DIGEST_BYTES).digest()
        return int.from_bytes(digest, "big", signed=False) & _INT64_MASK

    def _fresh_generator(self, event_id: str, event_index: int) -> np.random.Generator:
        """One-shot PCG64 generator keyed by the 4-tuple."""
        return np.random.default_rng(self._tuple_seed(event_id, event_index))

    # --- public draw API --------------------------------------------------

    def uniform(self, event_id: str, event_index: int) -> float:
        """Return a float in ``[0.0, 1.0)`` addressed by the 4-tuple."""
        return float(self._fresh_generator(event_id, event_index).random())

    def normal(
        self,
        event_id: str,
        event_index: int,
        *,
        mean: float = 0.0,
        std: float = 1.0,
    ) -> float:
        """Return a Gaussian draw addressed by the 4-tuple."""
        return float(self._fresh_generator(event_id, event_index).normal(mean, std))

    def integer(
        self,
        event_id: str,
        event_index: int,
        *,
        low: int,
        high: int,
    ) -> int:
        """Return an integer in ``[low, high)`` addressed by the 4-tuple."""
        if low >= high:
            raise ValueError(f"low must be strictly less than high; got {low}, {high}")
        return int(self._fresh_generator(event_id, event_index).integers(low, high))

    def bernoulli(self, event_id: str, event_index: int, *, p: float) -> bool:
        """Coin flip with probability ``p`` of ``True``.

        This is the direct replacement for
        ``self._rng.random() < self.queue_fill_p`` in
        :class:`geosync_hpc.execution.Execution` — ``event_index`` should
        be the bar index, ``event_id`` should be ``"queue_fill"`` or an
        equivalent semantic label.
        """
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"p must lie in [0, 1]; got {p}")
        return bool(self.uniform(event_id, event_index) < p)

    # --- stream spawning --------------------------------------------------

    def spawn(self, child_stream_id: str) -> IndexedRNG:
        """Derive a child stream whose draws are independent of the parent.

        The child's full stream identifier is ``f"{parent.stream_id}.{child}"``;
        the resulting BLAKE2b digest is statistically independent of any
        draw in the parent stream. Useful for subsystem isolation
        (e.g. ``execution.spawn("retry")``).
        """
        if not isinstance(child_stream_id, str) or not child_stream_id:
            raise ValueError("child_stream_id must be a non-empty string")
        return IndexedRNG(seed=self.seed, stream_id=f"{self.stream_id}.{child_stream_id}")
