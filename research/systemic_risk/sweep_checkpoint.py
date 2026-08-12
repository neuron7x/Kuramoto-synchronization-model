# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002D — Checkpoint / resume infrastructure for long sweeps.

Rationale
=========
The D-002B-A high-budget sweep (PR #656, issue #652) kept every
completed work-unit result in coordinator RAM until end-of-run
JSON write. A 17 h run that loses RAM mid-flight loses every
cell. The D-002C Signal Amplification Sweep grid (issue #654)
is 69 120 evaluations on a substrate × metric × variance grid;
running it without per-cell checkpointing is operationally
unsafe.

This module provides:

  * ``CellResult``        — frozen dataclass per (cell_key) outcome
  * ``SweepCheckpoint``   — frozen snapshot of completed work
  * ``CheckpointManager`` — atomic per-cell save / load / resume

Strict scope
============
Driver / infrastructure ONLY. NO science change. NO test
relaxation. NO threshold tuning. NO claim layer. The capsule
emitted by any sweep using this module remains scoped per its
own protocol (D-002C, etc.); this module is callable from any
sweep but never emits a claim of its own.

The contract is small and frozen:

  * cell_key is hashable (we use a stable repr key for I/O)
  * save_cell is atomic on POSIX (write `.tmp` → ``os.replace``)
  * resume is a pure subtraction:
        ``remaining_cells(full_grid) = full_grid - completed_cells``
  * sweep identity is the ``config_sha`` over the canonicalised
    sweep_config dict; a mismatch is a hard fail (different
    sweep — refuse to merge ledgers)
  * code drift is a soft warning (``code_sha``): the sweep can
    resume across a refactor as long as the science contract
    didn't change, but we log the drift so the reviewer can
    audit
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema version — bumped only on incompatible on-disk format changes.
# Old files with a known older version may be migrated forward; an unknown
# version is a hard refuse (we won't silently mis-interpret a future format).
#
# Version history
# ---------------
# 1 — original D-002D format (per-cell verdict payload only).
# 2 — D-002C C2.4-A2: per-cell payload may carry a ``null_audit_payload``
#     sub-dict (paired-CRN precursor/null per-seed arrays) for the
#     post-sweep null-audit aggregator. The on-disk JSON layout is a
#     pure additive extension — v1 readers ignore the new sub-dict and
#     v2 readers tolerate v1 files (cells without ``null_audit_payload``
#     are surfaced as "no per-seed data" to the aggregator, which records
#     them as SKIPPED_NO_PER_SEED_DATA = fail-closed). The fence is
#     therefore "v2 reads v1, v1 ignores v2 extras"; the strict refusal
#     remains for any version strictly greater than this module knows.
# ---------------------------------------------------------------------------
SCHEMA_VERSION: int = 2


class OverwritePolicy(enum.Enum):
    """How :meth:`CheckpointManager.save_cell` handles a re-save of a
    cell_key that is already present in the ledger.

    Default is :attr:`IDEMPOTENT_ONLY` — fail-closed under
    non-determinism. A sweep that recomputes a cell and produces a
    DIFFERENT result on the second pass is a real bug we want to
    surface, not silently mask by overwriting the ledger.
    """

    IDEMPOTENT_ONLY = "idempotent_only"
    """Same payload → silent no-op. Different payload → raise
    :class:`CheckpointCellConflict`."""

    OVERWRITE_WITH_WARNING = "overwrite_with_warning"
    """Any re-save overwrites and logs a warning. Use only when the
    science layer explicitly wants last-write-wins (e.g. mid-sweep
    re-runs with tuned parameters)."""

    REJECT = "reject"
    """Any re-save raises :class:`CheckpointCellConflict`, including
    a bit-identical re-save. Use to surface every redundant
    compute as a bug."""


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellResult:
    """One sweep cell's result.

    ``cell_key`` is the canonicalised string form (used as JSON key
    + as the key in ``SweepCheckpoint.results``). ``payload`` is an
    arbitrary JSON-serialisable dict — the science layer decides
    its shape; this module makes no claims about its contents.
    """

    cell_key: str
    payload: dict[str, Any]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_key": self.cell_key,
            "payload": dict(self.payload),
            "duration_seconds": float(self.duration_seconds),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Evidence-only view for hashing / idempotency comparison.

        Excludes ``duration_seconds`` (wall-clock, non-reproducible): the same
        science re-run in a different time must hash identically and count as an
        idempotent no-op, not a bit-mismatch. ``duration_seconds`` stays in
        :meth:`to_dict` (the on-disk / human-facing form) for auditability.
        """
        return {
            "cell_key": self.cell_key,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CellResult:
        return cls(
            cell_key=str(d["cell_key"]),
            payload=dict(d.get("payload", {})),
            duration_seconds=float(d.get("duration_seconds", 0.0)),
        )


@dataclass(frozen=True)
class SweepCheckpoint:
    """Frozen snapshot of a sweep's checkpoint state.

    The on-disk JSON format is the canonical form: it round-trips
    through :meth:`to_dict` / :meth:`from_dict` and is the input
    to :func:`stable_ledger_sha256`.

    The ``schema_version`` field is the forward-compat fence: an
    on-disk file with an unknown version is refused by
    :meth:`from_dict` rather than silently mis-interpreted. Bump
    :data:`SCHEMA_VERSION` only on incompatible format changes.
    """

    sweep_id: str
    config_sha: str
    code_sha: str
    created_at: str
    last_updated: str
    completed_cells: tuple[str, ...]
    results: dict[str, CellResult] = field(default_factory=dict)
    code_drift_events: tuple[dict[str, str], ...] = ()
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "sweep_id": self.sweep_id,
            "config_sha": self.config_sha,
            "code_sha": self.code_sha,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "completed_cells": list(self.completed_cells),
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "code_drift_events": [dict(e) for e in self.code_drift_events],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SweepCheckpoint:
        # Schema-version fence: silently absent → assume v1
        # (back-compat with files written before the field
        # existed). Present but unknown → hard refuse.
        version = int(d.get("schema_version", 1))
        if version > SCHEMA_VERSION:
            raise CheckpointSchemaError(
                f"on-disk schema_version={version} is newer than this "
                f"module's SCHEMA_VERSION={SCHEMA_VERSION}; refusing to "
                f"load (a newer module may have written this file)"
            )
        return cls(
            schema_version=version,
            sweep_id=str(d["sweep_id"]),
            config_sha=str(d["config_sha"]),
            code_sha=str(d["code_sha"]),
            created_at=str(d["created_at"]),
            last_updated=str(d["last_updated"]),
            completed_cells=tuple(str(x) for x in d.get("completed_cells", ())),
            results={str(k): CellResult.from_dict(v) for k, v in d.get("results", {}).items()},
            code_drift_events=tuple(
                {str(kk): str(vv) for kk, vv in e.items()} for e in d.get("code_drift_events", [])
            ),
        )


# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """Stable JSON form: sort keys, separators tight, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_sha256(sweep_config: dict[str, Any]) -> str:
    """sha256 of the canonicalised sweep_config dict.

    Two callers with the same ``sweep_config`` always get the same
    sha. A different ``sweep_config`` always gets a different sha.
    NaN / non-finite values raise; sets and tuples are not
    JSON-canonical and must be normalised by the caller.
    """
    payload = canonical_json(sweep_config)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cell_key(parts: tuple[Any, ...]) -> str:
    """Canonical string form for a heterogeneous cell tuple.

    The encoding is the canonical-JSON array of the parts:

        cell_key((50, 0.5, "block_structured", "tau_onset"))
            → '[50,0.5,"block_structured","tau_onset"]'

    This form is collision-free in two ways the previous
    ``"|".join(...)`` design was NOT:

    * **type-preserving** — ``cell_key((5,))`` (int) is
      distinct from ``cell_key(("5",))`` (str) because the
      string components keep their JSON quotes.
    * **delimiter-safe** — a string component that itself
      contains a "|" or "[" character does not collide with
      a multi-part tuple of those characters, because the
      JSON encoder quotes and escapes the string.

    The form is also stable (no Python ``repr`` quirks),
    hashable as a str, and round-trips losslessly via
    ``json.loads(key)``.
    """
    return canonical_json(list(parts))


def stable_ledger_sha256(checkpoint: SweepCheckpoint) -> str:
    """Order-invariant sha256 of the checkpoint's completed results.

    Use this to verify two checkpoints carry the same evidence
    independent of the order in which cells were completed.
    """
    rows = sorted((k, canonical_json(v.to_canonical_dict())) for k, v in checkpoint.results.items())
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


class CheckpointConfigMismatch(RuntimeError):
    """Raised when an on-disk checkpoint's config_sha disagrees with
    the caller's sweep_config — refusing to merge ledgers from
    different sweeps."""


class CheckpointSchemaError(RuntimeError):
    """Raised when an on-disk checkpoint declares a ``schema_version``
    this module does not know how to interpret. Refusing to load
    rather than silently mis-interpreting a future format."""


class CheckpointCellConflict(RuntimeError):
    """Raised by :meth:`CheckpointManager.save_cell` when the
    configured :class:`OverwritePolicy` forbids the requested
    re-save. The default policy is :attr:`OverwritePolicy.IDEMPOTENT_ONLY`
    which raises on a non-identical re-save (a real bug in the
    science layer that would otherwise be masked by a silent
    overwrite)."""


class CheckpointTypeError(TypeError):
    """Raised by :func:`normalize_config` when the supplied
    ``sweep_config`` contains a value that has no canonical JSON
    representation (e.g. ``set``, ``datetime``, custom class)."""


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical-JSON-safe copy of ``config`` for hashing.

    Two callers that build the same logical sweep config from
    different Python idioms (tuple vs list, ``frozenset`` vs sorted
    list, ``numpy.float64`` vs ``float``) must end up with the same
    sweep identity. This helper enforces that contract.

    Rules:

    * ``tuple`` → ``list`` (recursive)
    * ``set`` / ``frozenset`` → sorted ``list`` (raises if elements
      are not totally orderable)
    * ``Path`` → ``str`` (its POSIX form)
    * ``bool`` / ``int`` / ``float`` / ``str`` / ``None`` → kept as-is
    * ``dict`` → ``dict`` with str keys, recursively normalised
    * any other type → :class:`CheckpointTypeError`

    Non-finite floats (NaN, ±Inf) are rejected — the same rule
    :func:`canonical_json` enforces — because ``NaN != NaN`` would
    silently break sweep identity.
    """
    normalised = _normalize(config)
    if not isinstance(normalised, dict):
        raise CheckpointTypeError(f"sweep_config must be a dict; got {type(config).__name__}")
    return normalised


def _normalize(obj: Any) -> Any:
    if isinstance(obj, bool):
        # bool is a subclass of int; check first to preserve True/False
        return obj
    if obj is None or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise CheckpointTypeError(f"non-finite float in sweep_config: {obj!r}")
        return obj
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        try:
            ordered = sorted(obj)
        except TypeError as exc:
            raise CheckpointTypeError(
                f"set in sweep_config contains non-orderable elements: {obj!r}"
            ) from exc
        return [_normalize(v) for v in ordered]
    raise CheckpointTypeError(f"unsupported type {type(obj).__name__!r} in sweep_config: {obj!r}")


class CheckpointManager:
    """Atomic durable per-cell checkpoint store.

    Usage::

        mgr = CheckpointManager(path, sweep_config={...})
        ckpt = mgr.load_or_create()
        for cell in mgr.remaining_cells(full_grid):
            result = compute(cell)  # science layer
            mgr.save_cell(cell, result=result)
        df = mgr.export_ledger()

    Concurrency contract — single-writer only
    -----------------------------------------
    This class is **NOT** thread-safe and **NOT** multi-process
    safe. Only one CheckpointManager instance per checkpoint file
    may be writing at a time. The atomic ``replace`` guarantees
    file integrity (no torn writes) but a concurrent writer would
    race on the read-modify-write cycle: two writers can both
    observe the same pre-state, each compute an updated state, and
    the second writer's ``replace`` overwrites the first writer's
    cell.

    For a multi-process sweep (e.g. ``multiprocessing.Pool``), the
    canonical pattern is: workers return their per-cell results to
    a *single* coordinator process, and the coordinator owns the
    CheckpointManager. Workers must not touch the checkpoint file
    directly. A future PR may add file-locking + shard-per-cell
    storage to allow safe concurrent writers; until then,
    single-writer is the contract.

    Multiple **readers** are safe (the ``replace`` is atomic) so
    long as no writer is active.
    """

    def __init__(
        self,
        path: Path,
        sweep_config: dict[str, Any],
        *,
        code_sha: str = "unknown",
    ) -> None:
        self._path = Path(path)
        self._sweep_config = dict(sweep_config)
        self._config_sha = config_sha256(self._sweep_config)
        self._sweep_id = self._config_sha[:16]
        self._code_sha = str(code_sha)
        self._checkpoint: SweepCheckpoint | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config_sha(self) -> str:
        return self._config_sha

    @property
    def sweep_id(self) -> str:
        return self._sweep_id

    def load_or_create(self) -> SweepCheckpoint:
        """Load on-disk checkpoint OR create a fresh one.

        Raises ``CheckpointConfigMismatch`` if an on-disk file
        exists but its ``config_sha`` doesn't match the caller's
        sweep_config — we refuse to merge across sweeps.
        """
        if self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"checkpoint at {self._path} is unreadable: {exc}") from exc
            on_disk = SweepCheckpoint.from_dict(payload)
            if on_disk.config_sha != self._config_sha:
                raise CheckpointConfigMismatch(
                    f"on-disk config_sha {on_disk.config_sha} != "
                    f"caller config_sha {self._config_sha} — refusing to "
                    f"merge ledgers from different sweeps"
                )
            # Code drift: warn but do not fail
            drift_events = list(on_disk.code_drift_events)
            drift_detected = on_disk.code_sha != self._code_sha
            if drift_detected:
                drift_event = {
                    "from_code_sha": on_disk.code_sha,
                    "to_code_sha": self._code_sha,
                    "at": _now_iso(),
                }
                drift_events.append(drift_event)
                logger.warning(
                    "checkpoint code_sha drift: %s -> %s (resume permitted; "
                    "verify science contract unchanged)",
                    on_disk.code_sha,
                    self._code_sha,
                )
            self._checkpoint = SweepCheckpoint(
                sweep_id=on_disk.sweep_id,
                config_sha=on_disk.config_sha,
                code_sha=self._code_sha,
                created_at=on_disk.created_at,
                last_updated=_now_iso() if drift_detected else on_disk.last_updated,
                completed_cells=on_disk.completed_cells,
                results=dict(on_disk.results),
                code_drift_events=tuple(drift_events),
                schema_version=on_disk.schema_version,
            )
            # Persist drift metadata immediately so the audit trail
            # survives even when the run exits before any save_cell
            # call (e.g. zero remaining cells). Without this write,
            # the file still carries the old code_sha and the same
            # drift WARNING would repeat on every subsequent load.
            if drift_detected:
                self._atomic_write(self._checkpoint)
            return self._checkpoint

        now = _now_iso()
        self._checkpoint = SweepCheckpoint(
            sweep_id=self._sweep_id,
            config_sha=self._config_sha,
            code_sha=self._code_sha,
            created_at=now,
            last_updated=now,
            completed_cells=(),
            results={},
        )
        self._atomic_write(self._checkpoint)
        return self._checkpoint

    def save_cell(
        self,
        cell_key_str: str,
        result: CellResult,
        *,
        policy: OverwritePolicy = OverwritePolicy.IDEMPOTENT_ONLY,
    ) -> None:
        """Save one cell result to disk atomically and durably.

        Re-save semantics are governed by ``policy``:

        * :attr:`OverwritePolicy.IDEMPOTENT_ONLY` (default,
          fail-closed): bit-identical re-save is a no-op; a
          non-identical re-save raises
          :class:`CheckpointCellConflict`. A sweep that recomputes
          a cell and produces a *different* payload on the second
          pass is a real bug we want to surface, not silently mask.
        * :attr:`OverwritePolicy.OVERWRITE_WITH_WARNING`: any
          re-save overwrites; a warning is logged. Use when the
          science layer explicitly wants last-write-wins.
        * :attr:`OverwritePolicy.REJECT`: any re-save raises,
          including a bit-identical one. Use to surface every
          redundant compute.
        """
        if self._checkpoint is None:
            self.load_or_create()
        assert self._checkpoint is not None
        completed = set(self._checkpoint.completed_cells)
        if cell_key_str in completed:
            existing = self._checkpoint.results.get(cell_key_str)
            # Idempotency is judged on the evidence (cell_key + payload), NOT on
            # wall-clock duration_seconds — a re-run that took a different time is
            # still the same result and must be a no-op, not a conflict.
            identical = (
                existing is not None and existing.to_canonical_dict() == result.to_canonical_dict()
            )
            if policy is OverwritePolicy.IDEMPOTENT_ONLY:
                if identical:
                    return  # idempotent no-op
                raise CheckpointCellConflict(
                    f"cell {cell_key_str!r} already has a different result; "
                    f"re-save refused under IDEMPOTENT_ONLY policy. Pass "
                    f"policy=OverwritePolicy.OVERWRITE_WITH_WARNING to "
                    f"override explicitly."
                )
            if policy is OverwritePolicy.REJECT:
                raise CheckpointCellConflict(
                    f"cell {cell_key_str!r} already present; re-save refused under REJECT policy"
                )
            # OVERWRITE_WITH_WARNING
            if not identical:
                logger.warning(
                    "checkpoint cell %s overwritten with new result",
                    cell_key_str,
                )
            elif identical:
                # No-op write to keep behaviour equivalent to
                # IDEMPOTENT_ONLY on identical payloads.
                return
        new_results = dict(self._checkpoint.results)
        new_results[cell_key_str] = result
        new_completed = tuple(sorted(set(self._checkpoint.completed_cells) | {cell_key_str}))
        self._checkpoint = SweepCheckpoint(
            sweep_id=self._checkpoint.sweep_id,
            config_sha=self._checkpoint.config_sha,
            code_sha=self._checkpoint.code_sha,
            created_at=self._checkpoint.created_at,
            last_updated=_now_iso(),
            completed_cells=new_completed,
            results=new_results,
            code_drift_events=self._checkpoint.code_drift_events,
        )
        self._atomic_write(self._checkpoint)

    def is_done(self, cell_key_str: str) -> bool:
        if self._checkpoint is None:
            self.load_or_create()
        assert self._checkpoint is not None
        return cell_key_str in set(self._checkpoint.completed_cells)

    def remaining_cells(self, full_grid: list[str]) -> list[str]:
        """Return the subset of full_grid that is NOT yet completed."""
        if self._checkpoint is None:
            self.load_or_create()
        assert self._checkpoint is not None
        done = set(self._checkpoint.completed_cells)
        return [k for k in full_grid if k not in done]

    def export_ledger(self) -> list[dict[str, Any]]:
        """Order-stable export: a sorted list of cell dicts.

        Returning a plain list-of-dicts (not pandas) keeps this
        module free of a hard pandas dependency at the
        infrastructure layer. The science layer can wrap with
        ``pd.DataFrame.from_records(mgr.export_ledger())`` if it
        wants a frame.
        """
        if self._checkpoint is None:
            self.load_or_create()
        assert self._checkpoint is not None
        rows = sorted((k, v.to_dict()) for k, v in self._checkpoint.results.items())
        return [{"cell_key": k, **v} for k, v in rows]

    def export_ledger_sha256(self) -> str:
        """Stable sha256 of the ledger (cf. :func:`stable_ledger_sha256`)."""
        if self._checkpoint is None:
            self.load_or_create()
        assert self._checkpoint is not None
        return stable_ledger_sha256(self._checkpoint)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _atomic_write(self, checkpoint: SweepCheckpoint) -> None:
        """Durable atomic write of the checkpoint to disk.

        Strategy: write to ``path.tmp`` → ``flush`` →
        ``os.fsync(fileno)`` → ``os.replace`` to the final path.
        Without the fsync, ``os.replace`` is atomic but not durable:
        a power-loss between the rename and the kernel flushing the
        page cache can leave the on-disk inode pointing at a new
        name with old (or stale) contents. The fsync guarantees the
        data hits stable storage before the rename is observed by
        any reader.

        Atomicity (POSIX): a reader either sees the old file or the
        new file, never a half-written file.

        Durability (POSIX with fsync): after this method returns,
        the new state survives a kernel panic or power loss.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = json.dumps(
            checkpoint.to_dict(),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        # Open with O_WRONLY|O_CREAT|O_TRUNC; write; flush; fsync.
        # Mode 0o600 (owner-only): a sweep checkpoint may carry parameter
        # grids and partial research results that should not be world- or
        # group-readable. Closes CodeQL py/overly-permissive-file (#831).
        fd = os.open(
            tmp_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(fd, "wb", closefd=True) as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            # Drop the partial tmp file on any error path so a
            # subsequent run doesn't see stale .tmp leftovers.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        os.replace(tmp_path, self._path)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
