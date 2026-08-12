# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Frozen calibration trajectory replay — epistemic-integrity insulation.

The CALIB-GRID pre-registered ledgers (CALIB-GRID-001 / R1 / CALIB-GRID-002)
score a *frozen* experiment. Their reproduction historically re-ran the live
:class:`core.kuramoto.second_order.SecondOrderKuramotoEngine` to regenerate the
phase trajectory, which coupled a byte-frozen scientific artifact to mutable
physics code. A correctness fix to the integrator (explicit-Euler friction →
BBK velocity Verlet) therefore changed the *reproduction* of artifacts that the
append-only governance contract forbids recomputing.

This module decouples the two. The frozen experiment is reproduced by replaying
a committed trajectory **snapshot** (the integrator output captured at the
pre-registration integrator state), so identification runs on byte-identical
data regardless of how the live engine evolves. The live engine remains the
correct path for new physics and is exercised by the second-order physics tests
directly; it is simply not on the historical-reproduction path.

Design:

* :data:`_BASIS` defaults to ``"frozen"`` — every ``simulate_phases`` call that
  matches a snapshotted configuration replays the frozen trajectory. A
  configuration absent from the snapshot (a genuinely new / live experiment)
  falls through to the live engine; a frozen artifact whose key drifts will
  miss the snapshot and surface loudly as a reproduction mismatch, never a
  silent recompute.
* :func:`use_live_integrator` is an explicit opt-out for code that wants the
  live engine on the calibration path.
* :func:`capture_session` records live-engine output into a fresh snapshot; it
  is the one-shot tool used to mint the committed basis, never CI behaviour.

Invariants: the snapshot is append-only frozen evidence; the frozen RESULTS.json
ledgers are never touched; thresholds are never tuned.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "frozen_trajectories.npz"

#: Reproduction basis. "frozen" replays the committed snapshot; "live" runs the
#: mutable engine. Module-level so the single choke point (simulate_phases) is
#: insulated without threading a parameter through every ledger builder.
_BASIS = "frozen"

#: Active capture sink (populated only inside capture_session).
_CAPTURE: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] | None = None

_CACHE: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] | None = None


@dataclass(frozen=True)
class ReplayTrajectory:
    """Stand-in for the live engine result on the frozen-reproduction path."""

    phases: NDArray[np.float64]
    velocities: NDArray[np.float64]


def trajectory_key(
    *,
    system_name: str,
    inertia: NDArray[np.float64],
    damping: NDArray[np.float64],
    k_true: NDArray[np.float64],
    omega_true: NDArray[np.float64],
    dt: float,
    steps: int,
    seed: int,
    theta0_perturb: float,
) -> str:
    """Stable content hash of every determinant of the raw engine output.

    Excludes post-integration knobs (noise σ, keep_frac, estimator path): the
    noiseless and noisy regimes share one raw trajectory; noise and trimming are
    applied after replay.
    """
    h = hashlib.sha256()
    h.update(system_name.encode("utf-8"))
    for arr in (inertia, damping, k_true, omega_true):
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode("utf-8"))
        h.update(a.tobytes())
    h.update(f"{dt!r}|{steps!r}|{seed!r}|{theta0_perturb!r}".encode("utf-8"))
    return h.hexdigest()


def _load_cache() -> dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    if _SNAPSHOT_PATH.is_file():
        with np.load(_SNAPSHOT_PATH) as data:
            keys = {name.rsplit("__", 1)[0] for name in data.files}
            for key in keys:
                out[key] = (
                    np.asarray(data[f"{key}__phases"], dtype=np.float64),
                    np.asarray(data[f"{key}__velocities"], dtype=np.float64),
                )
    _CACHE = out
    return out


@contextmanager
def use_live_integrator() -> Iterator[None]:
    """Force the live engine on the calibration path within this block."""
    global _BASIS
    prev = _BASIS
    _BASIS = "live"
    try:
        yield
    finally:
        _BASIS = prev


@contextmanager
def capture_session() -> Iterator[dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]]]:
    """Record live-engine trajectories for every key seen in the block.

    One-shot tool to mint the committed snapshot from the pre-registration
    integrator state. Never used by CI.
    """
    global _CAPTURE, _BASIS
    sink: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    prev_cap, prev_basis = _CAPTURE, _BASIS
    _CAPTURE, _BASIS = sink, "live"
    try:
        yield sink
    finally:
        _CAPTURE, _BASIS = prev_cap, prev_basis


def write_snapshot(
    entries: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    path: Path = _SNAPSHOT_PATH,
) -> None:
    """Persist captured trajectories to the committed ``.npz`` basis."""
    flat: dict[str, NDArray[np.float64]] = {}
    for key, (phases, velocities) in entries.items():
        flat[f"{key}__phases"] = np.asarray(phases, dtype=np.float64)
        flat[f"{key}__velocities"] = np.asarray(velocities, dtype=np.float64)
    with path.open("wb") as fh:
        np.savez(fh, **flat)


def obtain_trajectory(
    key: str,
    run_engine: Callable[[], Any],
) -> ReplayTrajectory | Any:
    """Return the raw trajectory for *key*: frozen replay or live engine.

    * frozen basis + key in snapshot → replay (the engine is never called);
    * capture session → run live engine and record;
    * otherwise (live basis, or a key with no frozen snapshot) → live engine.
    """
    if _CAPTURE is not None:
        result = run_engine()
        _CAPTURE[key] = (
            np.asarray(result.phases, dtype=np.float64),
            np.asarray(result.velocities, dtype=np.float64),
        )
        return result
    if _BASIS == "frozen":
        cache = _load_cache()
        snap = cache.get(key)
        if snap is not None:
            phases, velocities = snap
            return ReplayTrajectory(phases=phases, velocities=velocities)
    return run_engine()
