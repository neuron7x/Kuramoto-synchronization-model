"""Deterministic utilities for ricci_microstructure_v1."""

from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

ZERO_GIT_SHA = "0" * 40


def set_global_seed(seed: int) -> np.random.Generator:
    if seed < 0:
        raise ValueError("seed must be non-negative")
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    return np.random.default_rng(seed)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    if path.is_symlink():
        raise RuntimeError(f"refusing symlinked path: {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.is_dir():
        raise RuntimeError(f"unsupported path type: {path}")
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise RuntimeError(f"refusing symlinked tree member: {child}")
        if child.is_file():
            digest.update(child.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(child.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or len(value) != 40:
        raise RuntimeError("git rev-parse HEAD failed; refusing hardcoded git_sha")
    if value == ZERO_GIT_SHA:
        raise RuntimeError("hardcoded zero git_sha is forbidden")
    return value


def timestamp_utc() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
