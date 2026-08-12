# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Replication manifest for every falsification run.

Section 13 of the official validation protocol mandates that every
run preserves: commit hash, dataset version, config, random seed,
dependency lockfile, machine environment, timestamp, full logs,
generated figures, raw metrics, failed tests. This module captures
the *static* part of that contract — the run-time provenance —
in a single deterministic dataclass that callers persist alongside
their numerical artefacts.

The dynamic parts (logs, figures) are the orchestrator's responsibility;
this module exists so that no caller can invent its own provenance
schema and silently omit a field.

Pure-function API. Reads the system state once at construction.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "RunManifest",
    "build_run_manifest",
]


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Deterministic provenance record for a single falsification run.

    Attributes
    ----------
    commit_sha
        Output of ``git rev-parse HEAD`` at run start. ``"unknown"``
        when not in a git tree.
    git_dirty
        ``True`` when the working tree has uncommitted changes —
        callers should refuse to claim ``MEASURED`` from a dirty run.
    timestamp_utc
        ISO-8601 UTC timestamp at manifest construction.
    seed
        The single root RNG seed used for the run. Every downstream
        sub-process derives its seed deterministically from this one.
    config_hash
        SHA-256 of ``json.dumps(config, sort_keys=True)`` so any
        change to the config produces a different hash.
    python
        ``sys.version`` short form (e.g. ``"3.12.5 (...)"``).
    platform_info
        ``platform.platform()`` — kernel, distro, machine.
    package_versions
        Mapping of every loaded *runtime-relevant* package to its
        version string (numpy, scipy, pandas, networkx, sklearn,
        scipy, the GeoSync wheel itself).
    config
        Full caller-supplied config dict (echoed verbatim). Together
        with ``config_hash`` it forms the falsification's frozen
        pre-registration.
    extra
        Free-form metadata for caller-specific provenance fields
        (e.g. ``{"dataset": "e-MID_2009Q1-2015Q4", "data_sha256": "..."}``).
    """

    commit_sha: str
    git_dirty: bool
    timestamp_utc: str
    seed: int
    config_hash: str
    python: str
    platform_info: str
    package_versions: dict[str, str]
    config: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Deterministic JSON serialisation (sorted keys + trailing newline)."""
        payload = {
            "commit_sha": self.commit_sha,
            "git_dirty": self.git_dirty,
            "timestamp_utc": self.timestamp_utc,
            "seed": self.seed,
            "config_hash": self.config_hash,
            "python": self.python,
            "platform_info": self.platform_info,
            "package_versions": dict(sorted(self.package_versions.items())),
            "config": self.config,
            "extra": dict(sorted(self.extra.items())),
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _git_head_sha(cwd: Path) -> tuple[str, bool]:
    try:
        sha = subprocess.run(  # nosec B603 - explicit argv
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown", False
    try:
        status = subprocess.run(  # nosec B603 - explicit argv
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return sha, False
    return sha, bool(status.strip())


_RELEVANT_PACKAGES: tuple[str, ...] = (
    "numpy",
    "scipy",
    "pandas",
    "networkx",
    "scikit-learn",
    "geosync",
)


def _package_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in _RELEVANT_PACKAGES:
        try:
            from importlib.metadata import PackageNotFoundError, version

            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "not-installed"
        except Exception:  # pragma: no cover - defensive
            out[name] = "unknown"
    return out


def _config_hash(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_run_manifest(
    *,
    seed: int,
    config: dict[str, Any],
    extra: dict[str, Any] | None = None,
    cwd: Path | None = None,
) -> RunManifest:
    """Capture the system state into a frozen :class:`RunManifest`.

    Parameters
    ----------
    seed
        Root RNG seed for the run.
    config
        Full pre-registered config dict — every threshold, window
        length, bootstrap count, etc. The dict is hashed with
        ``sort_keys=True`` so any change produces a different
        ``config_hash``.
    extra
        Optional free-form metadata (dataset id, data sha256, ...).
    cwd
        Working directory used for ``git`` calls. Defaults to
        ``Path.cwd()``.
    """
    cwd_path = cwd if cwd is not None else Path.cwd()
    sha, dirty = _git_head_sha(cwd_path)
    return RunManifest(
        commit_sha=sha,
        git_dirty=dirty,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        seed=int(seed),
        config_hash=_config_hash(config),
        python=(
            sys.version.split(" (")[0] + " (" + sys.version.split(" (", 1)[1]
            if "(" in sys.version
            else sys.version
        ),
        platform_info=platform.platform() + " | " + os.uname().machine,
        package_versions=_package_versions(),
        config=dict(config),
        extra=dict(extra) if extra is not None else {},
    )
