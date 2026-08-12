# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Byte-exact root-hash lock on the D-002H canonical-run authorisation grants.

Gate E pins 16 governance/source files by byte-exact sha256; Gate G pins the
D-002C ledger and the D-002H prereg. But the two *authorisation grant* artifacts
themselves — the Gate F authorisation and the Gate G terminal final-lock that
GRANT the canonical run — were verified only field-by-field, not byte-for-byte.
That left the most authorisation-critical files held to a weaker standard than
the files they authorise a run over: a change to a non-asserted field (a gate-
chain sha, a timestamp, the scope text) would pass silently.

This extends the Gate E root-hash contour to the grants: each grant artifact's
on-disk sha256 must match its pinned value. It does NOT grant, weaken, or
re-verify authorisation — it freezes the grant bytes so any mutation requires a
deliberate human pin update (the same tamper-tripwire discipline as Gate E).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = REPO_ROOT / "artifacts" / "d002h" / "authorization"

# Byte-exact pins of the two canonical-run authorisation grants. Frozen at the
# committed grant bytes; a change here is a deliberate, reviewed re-lock.
GRANT_PINS: dict[str, str] = {
    "d002h_canonical_run_authorisation.json": "6e76c6a35e7082203a88a7dd7d4aa4e44ff7107352063177187284d265e9248a",  # pragma: allowlist secret  # Gate F grant byte-exact
    "d002h_canonical_run_final_lock.json": "88d1125d17c96fbec2c57eb41f6073e37421c3bed616344cd8c971b453ea4b71",  # pragma: allowlist secret  # Gate G terminal grant byte-exact
}


def _disk_sha256(path: Path) -> str:
    assert path.is_file(), f"authorisation grant missing on disk: {path}"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_both_grant_artifacts_exist_and_parse() -> None:
    for name in GRANT_PINS:
        path = AUTH_DIR / name
        assert path.is_file(), f"grant artifact missing: {name}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict) and payload, f"grant artifact empty/invalid: {name}"


def test_authorisation_grant_byte_exact() -> None:
    name = "d002h_canonical_run_authorisation.json"
    disk = _disk_sha256(AUTH_DIR / name)
    assert disk == GRANT_PINS[name], (
        f"Gate F grant byte drift: on-disk sha256 {disk!r} != pinned "
        f"{GRANT_PINS[name]!r}; the authorisation grant was mutated"
    )


def test_final_lock_grant_byte_exact() -> None:
    name = "d002h_canonical_run_final_lock.json"
    disk = _disk_sha256(AUTH_DIR / name)
    assert disk == GRANT_PINS[name], (
        f"Gate G terminal grant byte drift: on-disk sha256 {disk!r} != pinned "
        f"{GRANT_PINS[name]!r}; the terminal authorisation grant was mutated"
    )


def test_pin_count_matches_grant_files_on_disk() -> None:
    """Counter consistency: exactly the two grant files are pinned and present."""
    on_disk = {p.name for p in AUTH_DIR.glob("*.json")}
    assert set(GRANT_PINS) <= on_disk, f"pinned grants not all on disk: {set(GRANT_PINS) - on_disk}"
    assert len(GRANT_PINS) == 2
