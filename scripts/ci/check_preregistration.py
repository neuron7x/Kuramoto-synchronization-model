# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over the flagship preregistration (RES-002).

A preregistration is only worth the name if it is *tamper-evident*: the frozen
analysis plan cannot be quietly edited after the fact, and any legitimate change
must be an appended, dated deviation rather than a silent overwrite of the plan.

This gate enforces exactly that over ``protocols/flagship_preregistration.yaml``,
the preregistration companion to the flagship research question
``research/flagship/rq.yaml`` (FLAGSHIP-RQ-001, an infrastructure / synthetic-only
question — see docs/PREREGISTRATION_POLICY.md).

It verifies three independent invariants:

    1. COMPLETENESS  — every required preregistration section is present and
       non-empty inside ``protocol_body``.
    2. TAMPER-EVIDENCE — the stored ``digest`` equals the SHA-256 recomputed over
       the *canonical* serialization of ``protocol_body``. Mutating a single byte
       of the frozen plan without re-deriving the digest is caught here.
    3. APPEND-ONLY DEVIATIONS — ``deviations`` is a list whose entries carry
       strictly-increasing, contiguous ``seq`` numbers starting at 1, each with
       the required keys. Reordering, deleting, or overwriting an entry breaks
       the sequence and fails the gate.

The digest is deliberately taken over ``protocol_body`` ONLY. The deviations log
lives *outside* the hashed body precisely so that appending a deviation does not
require (and cannot silently mask) a change to the frozen plan.

Determinism: ``prereg_date`` is a fixed string (no wall-clock call), so the
canonical body and its digest are reproducible bit-for-bit.

Exit codes:
    0  — preregistration intact (complete + digest matches + deviations append-only)
    1  — a required section is missing/empty, the digest mismatches (tamper), or
         the deviations log violates append-only ordering
    2  — a required file is absent or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREREG = ROOT / "protocols" / "flagship_preregistration.yaml"

# The fixed preregistration date. NEVER derived from datetime.now(): the digest
# must be reproducible, so no wall-clock dependence is permitted.
PREREG_DATE = "2026-07-19"

# Required analysis-plan sections, all inside ``protocol_body``. Every one must
# be present and non-empty. These are the elements that MUST be frozen before any
# run per docs/PREREGISTRATION_POLICY.md.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "hypotheses",
    "primary_outcomes",
    "secondary_outcomes",
    "dataset_versions",
    "exclusions",
    "splits",
    "nulls",
    "baselines",
    "metrics",
    "multiple_testing_corrections",
    "stopping_rules",
    "promotion_rules",
)

# Meta fields required at the top level (outside the hashed body).
REQUIRED_META: tuple[str, ...] = (
    "prereg_id",
    "rq_ref",
    "prereg_date",
    "digest_algo",
    "digest",
)

# Keys every deviation entry must carry.
DEVIATION_KEYS: tuple[str, ...] = ("seq", "date", "reason", "decision")


class GateError(Exception):
    """Malformed / missing input — maps to exit code 2 (fail-closed)."""


def canonical_body_bytes(body: Any) -> bytes:
    """Return the canonical serialization of the protocol body.

    Canonical form is JSON with sorted keys, compact separators, and non-ASCII
    preserved. This is independent of YAML whitespace / key ordering, yet any
    change to a *value* (a single semantic byte of the plan) changes the output.
    """
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_digest(body: Any) -> str:
    """SHA-256 hex digest over the canonical protocol body."""
    return hashlib.sha256(canonical_body_bytes(body)).hexdigest()


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise GateError(f"malformed YAML in {path}: {exc}") from exc


def _check_deviations(deviations: Any) -> list[str]:
    """Validate the append-only deviations log; return a list of problems.

    Append-only is enforced structurally: entries must carry strictly-increasing,
    contiguous ``seq`` values starting at 1 (a deletion leaves a gap; a reorder
    breaks monotonicity), and each entry must carry the required keys. An empty
    log is valid (no deviations yet).
    """
    problems: list[str] = []
    if not isinstance(deviations, list):
        problems.append("deviations: must be a list (append-only log)")
        return problems
    expected_seq = 1
    for idx, entry in enumerate(deviations):
        if not isinstance(entry, dict):
            problems.append(f"deviations[{idx}]: entry must be a mapping")
            continue
        missing = [k for k in DEVIATION_KEYS if k not in entry]
        if missing:
            problems.append(
                f"deviations[{idx}]: missing key(s): {', '.join(missing)}"
            )
        seq = entry.get("seq")
        if seq != expected_seq:
            problems.append(
                f"deviations[{idx}]: seq must be {expected_seq} "
                f"(contiguous, strictly increasing from 1); got {seq!r}"
            )
        expected_seq += 1
    return problems


def evaluate(path: Path) -> dict[str, Any]:
    """Return a machine-readable verdict for the preregistration at *path*.

    Raises GateError (exit 2) on missing/malformed input.
    """
    data = _load_yaml(path)
    if not isinstance(data, dict):
        raise GateError(f"{path}: must parse to a mapping")

    body = data.get("protocol_body")
    if not isinstance(body, dict):
        raise GateError(f"{path}: 'protocol_body' must be a mapping")

    problems: list[str] = []

    # 1. Meta completeness.
    for field in REQUIRED_META:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"meta: required field '{field}' missing or empty")

    # Fixed, deterministic prereg date.
    if data.get("prereg_date") != PREREG_DATE:
        problems.append(
            f"meta: prereg_date must be the fixed '{PREREG_DATE}'; "
            f"got {data.get('prereg_date')!r}"
        )
    if data.get("digest_algo") not in (None, "sha256"):
        problems.append("meta: digest_algo must be 'sha256'")

    # 2. Section completeness.
    missing_sections: list[str] = []
    for section in REQUIRED_SECTIONS:
        value = body.get(section)
        if value is None or (
            isinstance(value, (str, list, dict)) and len(value) == 0
        ):
            missing_sections.append(section)
    for section in missing_sections:
        problems.append(f"protocol_body: section '{section}' missing or empty")

    # 3. Tamper-evidence: stored digest must equal the recomputed digest.
    stored_digest = data.get("digest")
    computed_digest = compute_digest(body)
    digest_ok = (
        isinstance(stored_digest, str)
        and stored_digest.lower() == computed_digest
    )
    if not digest_ok:
        problems.append(
            "digest: MISMATCH — stored digest does not match the SHA-256 of the "
            f"canonical protocol_body (stored={stored_digest!r}, "
            f"computed={computed_digest!r}). The frozen plan was altered without "
            "re-deriving the digest, or the digest was tampered."
        )

    # 4. Append-only deviations log.
    problems.extend(_check_deviations(data.get("deviations", [])))

    return {
        "path": str(path),
        "prereg_id": data.get("prereg_id"),
        "rq_ref": data.get("rq_ref"),
        "required_sections": list(REQUIRED_SECTIONS),
        "missing_sections": missing_sections,
        "stored_digest": stored_digest,
        "computed_digest": computed_digest,
        "digest_ok": digest_ok,
        "deviations_count": (
            len(data["deviations"])
            if isinstance(data.get("deviations"), list)
            else None
        ),
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PREREG,
        help="path to the flagship preregistration YAML",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable verdict"
    )
    args = parser.parse_args(argv)

    try:
        verdict = evaluate(args.path)
    except GateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"PREREGISTRATION GATE: MALFORMED — {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        if verdict["ok"]:
            print(
                f"PREREGISTRATION GATE: PASS — {verdict['prereg_id']} intact; "
                f"digest matches; {verdict['deviations_count']} deviation(s) "
                "logged (append-only)."
            )
        else:
            print("PREREGISTRATION GATE: FAIL", file=sys.stderr)
            for problem in verdict["problems"]:
                print(f"  - {problem}", file=sys.stderr)

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
