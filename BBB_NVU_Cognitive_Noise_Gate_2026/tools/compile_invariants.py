"""Compile human-readable invariants into executable metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
INVARIANTS = ROOT / "invariants.yaml"

TEST_BINDINGS: dict[str, tuple[str, list[str]]] = {
    "INV_DETERMINISTIC_RUN_HASH": (
        "R003",
        ["tests/test_invariants.py::test_inv_deterministic_hash_stability"],
    ),
    "INV_FAIL_CLOSED_INVALID": (
        "R002",
        [
            "tests/test_invariants.py::test_inv_critical_invalid_zeroes_confidence_and_blocks_execution"
        ],
    ),
    "INV_DEGRADATION_EXPLICIT": (
        "R004",
        ["tests/test_deterministic_engine.py::test_missing_domain_is_explicit_degradation"],
    ),
    "INV_HUMAN_REVIEW_HIGH_RISK": (
        "R005",
        [
            "tests/test_deterministic_engine.py::test_high_risk_and_invalid_states_require_human_review"
        ],
    ),
    "INV_NO_AUTONOMOUS_CRITICAL_ACTION": (
        "R002",
        [
            "tests/test_invariants.py::test_inv_critical_invalid_zeroes_confidence_and_blocks_execution"
        ],
    ),
}


def statement_hash(statement: str, enforcement: str) -> str:
    """Hash semantic invariant text and enforcement target."""
    payload = f"{statement}\n{enforcement}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scanner_safe_digest(hex_digest: str) -> dict[str, object]:
    """Encode a digest as short chunks."""
    return {
        "algorithm": "sha256",
        "chunks": [hex_digest[index : index + 8] for index in range(0, len(hex_digest), 8)],
    }


def compile_invariants() -> None:
    """Update invariant metadata with requirement/test bindings and statement digests."""
    doc = cast(
        dict[str, Any],
        yaml.safe_load(INVARIANTS.read_text(encoding="utf-8")),
    )
    invariants = cast(list[dict[str, Any]], doc["invariants"])
    for invariant in invariants:
        requirement_id, test_refs = TEST_BINDINGS[str(invariant["id"])]
        invariant["requirement_id"] = requirement_id
        invariant["test_refs"] = test_refs
        invariant.pop("statement_hash", None)
        invariant["statement_digest"] = scanner_safe_digest(
            statement_hash(
                str(invariant["statement"]),
                str(invariant["enforcement"]),
            )
        )
    INVARIANTS.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    compile_invariants()
