#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared primitives for the executable proof-gate probes.

The proof gates (E/G/H/K/M/Q in ``release_gate.py``) each emit a JSON
artifact that records *machine evidence*, not prose. This module supplies
the common provenance + hashing helpers so every artifact is anchored to a
git commit, records dirty state, and is content-addressable. No gate may
become GREEN on words: the artifact must carry a hash and a verdict that a
re-run reproduces.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Canonical machine verdict vocabulary shared across probes.
SURVIVED = "SURVIVED"
REFUTED = "REFUTED"
BLOCKED = "BLOCKED"
PASS = "PASS"
FAIL = "FAIL"


def head_sha() -> str:
    """Return the current ``HEAD`` commit sha, or ``"UNKNOWN"`` outside git."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def git_dirty() -> bool:
    """True if the working tree has uncommitted tracked changes."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(proc.stdout.strip())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, no volatile whitespace."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def canonical_sha256(payload: Any) -> str:
    """Content hash of a payload over its canonical-JSON encoding."""
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def hardware_fingerprint() -> dict[str, str | int | None]:
    """Stable description of the host so benchmark budgets are comparable."""
    import os

    return {
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "system": platform.system(),
        "release": platform.release(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def hardware_id(fingerprint: dict[str, str | int | None] | None = None) -> str:
    """Short content hash of the hardware fingerprint for budget matching."""
    fp = fingerprint if fingerprint is not None else hardware_fingerprint()
    return canonical_sha256(fp)[:16]


def write_artifact(rel_path: str, payload: dict[str, Any]) -> Path:
    """Write a provenance-stamped artifact and return its path.

    Adds ``git_sha`` / ``git_dirty`` if the caller did not, and an
    ``artifact_sha256`` self-hash computed over the canonical body (the body
    without the self-hash field), so a verifier can confirm the file was not
    edited after generation.
    """
    body = dict(payload)
    body.setdefault("git_sha", head_sha())
    body.setdefault("git_dirty", git_dirty())
    body.pop("artifact_sha256", None)
    body["artifact_sha256"] = canonical_sha256(body)

    out = ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical_json(body) + "\n", encoding="utf-8")
    return out


def verify_artifact_selfhash(payload: dict[str, Any]) -> bool:
    """Confirm an artifact's recorded ``artifact_sha256`` matches its body."""
    recorded = payload.get("artifact_sha256")
    if not isinstance(recorded, str):
        return False
    body = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    return canonical_sha256(body) == recorded
