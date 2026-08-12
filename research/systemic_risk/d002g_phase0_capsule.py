# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G — Phase 0 verification capsule writer.

Emits ``phase0_verification_capsule_v1``: a content-addressed JSON
artifact carrying the per-cell Phase 0a / 0b / 0c evidence, the
aggregate verdict, and the fallback recommendation ("M2" on FAIL).

Strict scope
============
Capsule serialisation ONLY. The verification logic lives in
:mod:`d002g_phase0_verification`; this module is a thin writer that
applies the same canonical-JSON discipline as the D-002C preflight
capsules so the sha256 round-trips across machines.

The capsule is intentionally SEPARATE from the sweep capsule so a
Phase 0 FAIL does not contaminate sweep ledger entries and so the
implementation PR can ship Phase 0 infrastructure without
launching a sweep (the canonical run is a downstream PR).
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final

from .d002c_preflight import canonical_preflight_json
from .d002g_phase0_verification import (
    Phase0CellEvidence,
    Phase0Verdict,
)

CAPSULE_VERSION: Final[str] = "phase0_verification_capsule_v1"


def _finite_or_str(x: float) -> Any:
    f = float(x)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "Infinity" if f > 0 else "-Infinity"
    return f


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _evidence_dict(ev: Phase0CellEvidence) -> dict[str, Any]:
    """Per-cell evidence → JSON-pure dict with NaN/Inf sanitisation."""

    def _scalar(payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, float):
                out[k] = _finite_or_str(v)
            else:
                out[k] = v
        return out

    return {
        "substrate_id": ev.substrate_id,
        "N": int(ev.N),
        "all_passed": bool(ev.all_passed),
        "phase_0a": _scalar(asdict(ev.phase_0a)),
        "phase_0b": _scalar(asdict(ev.phase_0b)),
        "phase_0c": _scalar(asdict(ev.phase_0c)),
    }


def verdict_to_capsule(verdict: Phase0Verdict) -> dict[str, Any]:
    """Serialise a :class:`Phase0Verdict` to a JSON-pure capsule dict.

    The returned dict carries the load-bearing fields under canonical
    keys; the ``sha256`` field is recomputed deterministically over
    everything except ``generated_at`` and ``sha256`` itself.
    """
    body: dict[str, Any] = {
        "capsule_version": CAPSULE_VERSION,
        "verdict": str(verdict.verdict),
        "fallback_recommendation": str(verdict.fallback_recommendation),
        "metric_id": str(verdict.metric_id),
        "base_seed": int(verdict.base_seed),
        "null_seed_offset": int(verdict.null_seed_offset),
        "n_seeds": int(verdict.n_seeds),
        "n_shuffles": int(verdict.n_shuffles),
        "t_threshold": float(verdict.t_threshold),
        "p_lo": float(verdict.p_lo),
        "p_hi": float(verdict.p_hi),
        "metadata": dict(verdict.metadata),
        "cell_evidence": [_evidence_dict(ev) for ev in verdict.cell_evidence],
    }
    sha = hashlib.sha256(canonical_preflight_json(body).encode("utf-8")).hexdigest()
    return {
        **body,
        "generated_at": _now_iso(),
        "sha256": sha,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """tmp + fsync + os.replace — same discipline as d002c_null_audit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(canonical_preflight_json(payload))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_phase0_capsule(verdict: Phase0Verdict, path: Path) -> dict[str, Any]:
    """Serialise + write the Phase 0 capsule to ``path``.

    Returns the in-memory capsule dict (same as :func:`verdict_to_capsule`).
    The on-disk JSON is canonical (sort_keys, tight separators) so the
    ``sha256`` round-trips bit-exactly.
    """
    capsule = verdict_to_capsule(verdict)
    _atomic_write(Path(path), capsule)
    return capsule


__all__ = [
    "CAPSULE_VERSION",
    "verdict_to_capsule",
    "write_phase0_capsule",
]
