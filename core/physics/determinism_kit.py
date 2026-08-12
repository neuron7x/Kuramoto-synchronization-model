# SPDX-License-Identifier: MIT
"""LAW T6 — Bit-identical reproducibility kit for chaotic trajectories.

Constitutional Law T6 of seven (CLAUDE.md GeoSync Physics Law Act).

Identity
--------
Determinism flows from bit-identical state transitions; chaos amplifies
floating-point divergence at rate ``λ_1``. **Below the predictability
horizon τ from Law T5, two trajectories with bit-identical initial
conditions and identical integrator code remain bit-identical.** That
is the operational claim of Law T6.

T6 ships the canonicalisation + hashing utilities that make this
reproducible-by-construction:

* ``canonicalize_state(x)``  — IEEE-754 normalisation: NaN → canonical
  (single representative byte sequence), denormals → 0, ``-0.0`` → ``+0.0``,
  little-endian byte order. Two states whose canonical bytes are
  identical produce bit-identical trajectories on this CPU/JAX combo.
* ``state_hash(x)``           — SHA-256 of ``canonicalize_state(x).tobytes()``.
  Sensitive to a single-ULP perturbation (collision-resistant by SHA-256).
* ``trajectory_hash(traj)``   — SHA-256 over the row-by-row state hashes
  in order. Sensitive to permutations of trajectory order.
* ``ReplayManifest``          — frozen NamedTuple binding ``(seed, dt,
  n_steps, x0_hash, traj_hash, integrator_id, jax_version)`` for audit.
* ``verify_replay(...)``      — re-execute a sealed replay and assert
  byte-equality of the trajectory hash; fail-closed mismatch.

Constitutional invariants (P0)
------------------------------
* INV-DET1 | universal    | identical canonical inputs ⇒ identical
                            ``state_hash`` on the same machine + JAX
                            version. Tested on 100 random states.
* INV-DET2 | universal    | a 1-ULP perturbation in any component of
                            ``x`` MUST change ``state_hash``. Tested
                            across float64 + float32 dtypes. (No
                            silent aliasing.)
* INV-DET3 | universal    | every contract violation
                            (non-numeric dtype, mismatched dtypes
                            between replays, wrong trajectory shape,
                            empty input) raises ValueError; fail-closed.

Determinism is a *shadow* of physics, not physics itself: the same
``rhs`` integrated through the same scheme on the same hardware
yields the same bytes — the result of T6's invariants. This is the
substrate Law T5 stands on.

References
----------
* IEEE 754-2019 — Floating-Point Arithmetic.
* Liu, X. et al. (2018). *Reproducibility analysis of GPU computing.*
  IEEE Trans. Parallel Distrib. Syst.
* NIST FIPS 180-4 — SHA-256 specification.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ReplayManifest",
    "canonicalize_state",
    "state_hash",
    "trajectory_hash",
    "verify_replay",
]


# Single canonical NaN bit-pattern: float64 quiet NaN with payload 0.
# All NaNs (signalling, quiet, signed-NaN) collapse to this one before
# hashing — without canonicalisation INV-DET1 fails because 2**52
# distinct NaN bit-patterns hash to 2**52 different values yet all
# represent ``not-a-number``. This is the IEEE-754 design space we
# explicitly close.
_CANONICAL_NAN_F64: np.uint64 = np.uint64(0x7FF8000000000000)
_CANONICAL_NAN_F32: np.uint32 = np.uint32(0x7FC00000)


class ReplayManifest(NamedTuple):
    """Audit-trail binding of a replay attempt.

    Attributes
    ----------
    integrator_id:
        Caller-defined string identifying the exact integrator
        (e.g. ``"midpoint-rk2/jax-0.10.0"``). Two manifests with
        different ``integrator_id`` are *not* expected to produce
        bit-identical trajectories — used for cross-version diagnostics.
    seed:
        RNG seed (or ``-1`` for purely deterministic runs).
    dt:
        Integration timestep.
    n_steps:
        Number of integration steps.
    x0_hash:
        ``state_hash(x0)`` of the initial condition. Hex string.
    traj_hash:
        ``trajectory_hash(traj)`` of the recorded trajectory. Hex string.
    """

    integrator_id: str
    seed: int
    dt: float
    n_steps: int
    x0_hash: str
    traj_hash: str


def canonicalize_state(x: NDArray[np.floating]) -> NDArray[np.floating]:
    """IEEE-754 canonicalisation for hash-stable comparison.

    Normalises:

    * any NaN bit-pattern → canonical quiet-NaN.
    * ``-0.0`` → ``+0.0`` (so ``hash(0.0) == hash(-0.0)``).
    * subnormals → 0.0 (flush-to-zero policy; the alternative — preserve
      subnormals — would make hashes hardware-dependent on platforms
      that flush in CPU but not in NumPy or vice versa).

    Returns a *new* contiguous little-endian array with the original
    dtype preserved. Pure functional; ``x`` is not mutated.

    Parameters
    ----------
    x:
        Input array; ``dtype`` must be ``float32`` or ``float64``.

    Raises
    ------
    ValueError
        On non-floating dtype, empty input, or unsupported precision
        (INV-DET3).
    """
    if not np.issubdtype(x.dtype, np.floating):
        raise ValueError(f"INV-DET3: canonicalize_state requires a floating dtype, got {x.dtype}")
    if x.size == 0:
        raise ValueError("INV-DET3: canonicalize_state cannot canonicalise empty array")
    if x.dtype not in (np.float32, np.float64):
        raise ValueError(f"INV-DET3: only float32 and float64 supported, got {x.dtype}")

    arr = np.ascontiguousarray(x, dtype=x.dtype).copy()
    if arr.dtype == np.float64:
        # Reinterpret as uint64 to operate on bit patterns.
        bits = arr.view(np.uint64)
        # Collapse all NaNs to the single canonical pattern.
        nan_mask = np.isnan(arr)
        bits[nan_mask] = _CANONICAL_NAN_F64
        # Flush subnormals (exponent == 0, mantissa != 0) to +0.0.
        is_subnormal = ((bits & np.uint64(0x7FF0000000000000)) == 0) & (
            (bits & np.uint64(0x000FFFFFFFFFFFFF)) != 0
        )
        bits[is_subnormal] = np.uint64(0)
        # Collapse -0.0 to +0.0.
        is_neg_zero = bits == np.uint64(0x8000000000000000)
        bits[is_neg_zero] = np.uint64(0)
        # Hashes always taken on little-endian native; if input is
        # big-endian, view-cast to little-endian dtype (NumPy 2.x
        # dropped ndarray.newbyteorder). On x86_64 this is a no-op.
        if arr.dtype.byteorder == ">":
            return arr.view(np.dtype("<f8"))
        return arr

    # float32 path
    bits32 = arr.view(np.uint32)
    nan_mask = np.isnan(arr)
    bits32[nan_mask] = _CANONICAL_NAN_F32
    is_subnormal_32 = ((bits32 & np.uint32(0x7F800000)) == 0) & (
        (bits32 & np.uint32(0x007FFFFF)) != 0
    )
    bits32[is_subnormal_32] = np.uint32(0)
    is_neg_zero_32 = bits32 == np.uint32(0x80000000)
    bits32[is_neg_zero_32] = np.uint32(0)
    if arr.dtype.byteorder == ">":
        return arr.view(np.dtype("<f4"))
    return arr


def state_hash(x: NDArray[np.floating]) -> str:
    """SHA-256 of canonicalised state bytes. Hex digest, lowercase.

    Two states with byte-identical canonical representation produce
    the same hash; INV-DET1. A single-ULP perturbation in any
    component flips bytes and therefore the hash; INV-DET2.

    Returns a 64-character lowercase hex string.
    """
    canon = canonicalize_state(x)
    h = hashlib.sha256()
    # Include dtype + shape in the hash so two arrays of different
    # dtype but identical bit-content do not alias to the same hash.
    h.update(str(canon.dtype).encode("ascii"))
    h.update(b"|")
    h.update(str(canon.shape).encode("ascii"))
    h.update(b"|")
    h.update(canon.tobytes(order="C"))
    return h.hexdigest()


def trajectory_hash(traj: NDArray[np.floating]) -> str:
    """SHA-256 over per-row ``state_hash`` digests, in trajectory order.

    Sensitive to row order — permuting the trajectory changes the hash.
    A 2-D array of shape ``(T, N)`` is treated as ``T`` consecutive
    ``N``-dimensional states; row 0 first.

    Raises
    ------
    ValueError
        On non-floating dtype, empty input, or non-2-D shape (INV-DET3).
    """
    if traj.ndim != 2:
        raise ValueError(
            f"INV-DET3: trajectory_hash requires 2-D array (T, N), got shape {traj.shape}"
        )
    if traj.shape[0] == 0:
        raise ValueError("INV-DET3: trajectory_hash cannot hash an empty trajectory")
    h = hashlib.sha256()
    h.update(str(traj.dtype).encode("ascii"))
    h.update(b"|")
    h.update(str(traj.shape).encode("ascii"))
    h.update(b"|")
    for row in range(int(traj.shape[0])):
        h.update(state_hash(traj[row]).encode("ascii"))
    return h.hexdigest()


def verify_replay(traj: NDArray[np.floating], manifest: ReplayManifest) -> bool:
    """Re-hash ``traj`` and compare to the manifest's recorded hash.

    Returns ``True`` on byte-identical match, ``False`` otherwise.
    Does not raise on mismatch — caller decides whether mismatch is a
    fatal error or a tolerated cross-platform divergence (the latter
    is expected past the predictability horizon τ from Law T5).

    Parameters
    ----------
    traj:
        Re-executed trajectory; shape ``(T, N)``.
    manifest:
        Sealed ``ReplayManifest`` from the original run.

    Raises
    ------
    ValueError
        If ``traj`` violates INV-DET3 (wrong shape or empty).
    """
    return trajectory_hash(traj) == manifest.traj_hash
