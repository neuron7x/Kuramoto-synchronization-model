"""T4 · Phase 0 SOURCE_HASHES.json matches rechecked hashes now; no
protected artefact mutated during the offline-robustness run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HASHES_FILE = (
    REPO / "results" / "cross_asset_kuramoto" / "offline_robustness" / "SOURCE_HASHES.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_hashes_file_present() -> None:
    assert HASHES_FILE.is_file(), f"missing {HASHES_FILE}"


def test_all_protected_artefacts_unchanged() -> None:
    data = json.loads(HASHES_FILE.read_text())
    mismatches: list[str] = []
    for rel, expected in data["hashes"].items():
        p = REPO / rel
        if not p.is_file():
            mismatches.append(f"{rel}: disappeared")
            continue
        actual = _sha(p)
        if actual != expected:
            mismatches.append(f"{rel}: sha mismatch\n  expected {expected}\n  actual   {actual}")
    assert not mismatches, "protected artefact(s) mutated:\n" + "\n".join(mismatches)
